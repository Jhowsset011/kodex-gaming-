import importlib.util
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import unittest


SPEC = importlib.util.spec_from_file_location(
    "omega_catalog", Path(__file__).parents[1] / "scripts/omega_catalog.py")
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


class FakePolicy:
    """Deliberately fictitious rule: tests the external-policy boundary."""
    def __init__(self):
        self.calls = []

    def sale_price(self, price):
        self.calls.append(price)
        return (price * Decimal("1.25")).quantize(Decimal("0.01"))


def existing(pid="1", reference="110001"):
    return {
        "id": pid, "reference": reference, "name": "Monitor MSI MAG 272F X24",
        "category": "Periféricos", "subcategory": "Otros accesorios", "brand": "NVIDIA",
        "price": 9999, "stock": True, "image": "img/catalogo/old-nexcom.jpg",
        "description": "Ficha antigua de otro suplidor", "model": "Viejo",
        "spec": "Dato viejo", "specifications": [{"label": "Dato viejo", "value": "Viejo"}],
        "features": ["Característica antigua"], "sourceImage": "https://nexcomtienda.com.do/old.jpg",
        "specificationSources": ["https://nexcomtienda.com.do/old-product/"],
        "sourceCategory": "Zona Gamer", "collections": ["Otra colección"],
        "subcategoryPath": ["No", "Debe", "Existir"], "customPrivateCost": 100,
        "old": 12500,
    }


def source(reference="110001"):
    return {
        "reference": reference, "rawTitle": "Msi - MAG 272F X24",
        "name": "Msi - MAG 272F X24", "brand": "Msi", "currency": "DOP",
        "price": Decimal("13.37"), "oldPrice": None, "stock": True,
        "partNumber": "MAG 272F X24", "description": "MONITOR MSI, MAG 272F X24, FHD, 240 HZ, RAPID IPS",
        "descriptionLines": ["MONITOR MSI, MAG 272F X24, FHD, 240 HZ, RAPID IPS"],
        "specifications": [{"label": "Número de parte", "value": "MAG 272F X24"},
                           {"label": "Panel", "value": "Rapid IPS"}],
        "sourceUrl": f"https://tienda.omega.com.do/es/product/consul/{reference}",
        "imageSource": "https://sis.omega.com.do/ProductImages/test.png",
        "sourceCategories": ["Perifericos", "Monitor"],
        "inventory": [{"branch": "La Nave", "quantity": 8}], "conflicts": [],
    }


class OmegaCatalogTests(unittest.TestCase):
    def build(self, old=None, new=None, policy=None, missing=(), timestamp="2026-01-01T00:00:00+00:00"):
        old = existing() if old is None else old
        new = source() if new is None else new
        return catalog.build_catalog([old], {old["reference"]: new},
                                     policy or FakePolicy(), missing,
                                     updated_at=timestamp)

    def test_exact_identity_final_price_and_no_mutation(self):
        old, new, policy = existing(), source(), FakePolicy()
        before_old, before_new = deepcopy(old), deepcopy(new)
        result = self.build(old, new, policy)
        p = result["products"][0]
        self.assertEqual((p["id"], p["reference"]), ("1", "110001"))
        self.assertEqual(p["name"], "Monitor MSI MAG 272F X24")
        self.assertEqual(p["price"], 16.71)
        self.assertEqual(policy.calls, [Decimal("13.37")])
        self.assertEqual((p["category"], p["subcategory"], p["brand"]),
                         ("Monitores", "De escritorio", "MSI"))
        self.assertEqual(old, before_old)
        self.assertEqual(new, before_new)

    def test_supplier_details_replace_every_legacy_field(self):
        result = self.build()
        p = result["products"][0]
        self.assertEqual(p["description"], source()["description"])
        self.assertEqual(p["specifications"], source()["specifications"])
        self.assertEqual(p["features"], source()["descriptionLines"])
        self.assertEqual(p["image"], catalog.PLACEHOLDER)
        self.assertEqual(p["sourceImage"], source()["imageSource"])
        self.assertEqual(p["sourceCategory"], "Monitor")
        self.assertEqual(p["model"], "MAG 272F X24")
        self.assertNotIn("old", p)
        self.assertNotIn("subcategoryPath", p)
        self.assertNotIn("nexcom", json.dumps(result).casefold())
        self.assertNotIn("Ficha antigua", json.dumps(result))
        self.assertNotIn("customPrivateCost", p)

    def test_current_supplier_name_does_not_copy_old_name_claims(self):
        old = existing()
        old["name"] = "Monitor MSI MAG 272F X24 360Hz 4K OLED características no verificadas"
        p = self.build(old=old)["products"][0]
        self.assertEqual(p["name"], "Monitor MSI MAG 272F X24")
        self.assertNotIn("360Hz", p["name"])
        self.assertNotIn("OLED", p["name"])

    def test_technical_features_skip_rows_policies_and_duplicates(self):
        new = source()
        new["descriptionLines"] = [
            "Panel: Rapid IPS", "Panel: Rapid IPS", "Dos conectores HDMI y uno DisplayPort",
            "Dos conectores HDMI y uno DisplayPort", "Garantía Omega de 3 años",
            "Precio de proveedor sujeto a cambios", "Política de devoluciones en tienda",
        ]
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["features"], ["Dos conectores HDMI y uno DisplayPort"])

    def test_whole_description_does_not_duplicate_information_row(self):
        new = source()
        new["specifications"] = [
            {"label": "Número de parte", "value": "MAG 272F X24"},
            {"label": "Información del producto", "value": new["description"]},
        ]
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["features"], [])

    def test_missing_information_never_falls_back_to_old_details(self):
        new = source()
        new.update(description="", descriptionLines=[], specifications=[],
                   partNumber="", imageSource="")
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["description"], "")
        self.assertEqual(p["spec"], "")
        self.assertEqual(p["specifications"], [])
        self.assertEqual(p["features"], [])
        self.assertEqual(p["sourceImage"], "")
        self.assertEqual(p["image"], catalog.PLACEHOLDER)
        self.assertNotIn("model", p)

    def test_reference_mismatch_currency_and_foreign_source_fail(self):
        for change in ({"reference": "110002"}, {"currency": "USD"},
                       {"sourceUrl": "https://tienda.omega.com.do/es/product/consul/110002"},
                       {"sourceUrl": "https://nexcomtienda.com.do/es/product/consul/110001"},
                       {"imageSource": "https://nexcomtienda.com.do/photo.png"}):
            with self.subTest(change=change):
                new = source()
                new.update(change)
                with self.assertRaises(ValueError):
                    self.build(new=new)

    def test_absent_source_requires_explicit_missing_confirmation(self):
        old = existing()
        with self.assertRaises(ValueError):
            catalog.build_catalog([old], {}, FakePolicy())
        result = catalog.build_catalog([old], {}, FakePolicy(), ["110001"],
                                       updated_at="2026-01-01T00:00:00+00:00")
        p = result["products"][0]
        self.assertEqual(result["sourceMissingReferences"], ["110001"])
        self.assertEqual((p["id"], p["reference"], p["name"]),
                         (old["id"], old["reference"], old["name"]))
        self.assertIsNone(p["price"])
        self.assertFalse(p["stock"])
        self.assertTrue(p["sourceUnavailable"])
        self.assertEqual(p["description"], "")
        self.assertEqual(p["specificationSources"], [])
        self.assertEqual(p["sourceImage"], "")
        self.assertEqual(p["image"], catalog.PLACEHOLDER)

    def test_missing_and_sources_must_be_an_exact_disjoint_selection(self):
        old = existing()
        for sources, missing in (({"110002": source("110002")}, []),
                                 ({"110001": source()}, ["110001"]),
                                 ({}, ["110002"])):
            with self.subTest(sources=sources, missing=missing):
                with self.assertRaises(ValueError):
                    catalog.build_catalog([old], sources, FakePolicy(), missing)

    def test_unpriced_product_is_unavailable_and_never_uses_old_price(self):
        new, policy = source(), FakePolicy()
        new.update(price=None, oldPrice=Decimal("22.00"), stock=True)
        p = self.build(new=new, policy=policy)["products"][0]
        self.assertIsNone(p["price"])
        self.assertFalse(p["stock"])
        self.assertTrue(p["priceUnavailable"])
        self.assertEqual(policy.calls, [])
        self.assertNotIn("old", p)

    def test_old_offer_is_recalculated_and_expired_offer_removed(self):
        new = source()
        new["oldPrice"] = Decimal("20")
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["old"], 25.00)
        new["oldPrice"] = Decimal("10")
        self.assertNotIn("old", self.build(new=new)["products"][0])

    def test_public_whitelist_blocks_private_policy_and_price_fields(self):
        new = source()
        new.update(purchaseCost=9, discountPercent=12, markupPercent=34)
        result = self.build(new=new)
        text = json.dumps(result, ensure_ascii=False)
        for private in ("purchaseCost", "discountPercent", "markupPercent", "oldPrice", "inventory", "rawTitle", "priceOmega"):
            self.assertNotIn(private, text)
        for target in (result, result["products"][0]):
            private = deepcopy(result)
            modified = private if target is result else private["products"][0]
            modified["purchaseCost"] = 9
            with self.assertRaises(ValueError):
                catalog.validate_catalog(private)

    def test_known_title_conflict_uses_correct_part_and_description(self):
        old, new = existing(reference="109640"), source("109640")
        old["name"] = "Power Supply MSI MAG A750GLS 750W ATX Gold Modular"
        new.update(rawTitle="Msi - MAG A750BN PCIE5", name="POWER SUPPLY MSI MAG A750GLS PCIE5, 750W, 80 PLUS GOLD, MODULAR",
                   partNumber="MAG A750GLS PCIE5", description="POWER SUPPLY MSI MAG A750GLS PCIE5, 750W, 80 PLUS GOLD, MODULAR",
                   specifications=[{"label": "Número de parte", "value": "MAG A750GLS PCIE5"}],
                   conflicts=["Título contradice número de parte"])
        p = self.build(old, new)["products"][0]
        self.assertEqual(p["name"], "Fuente de poder MSI MAG A750GLS PCIE5")
        self.assertEqual(p["model"], "MAG A750GLS PCIE5")
        self.assertEqual((p["category"], p["subcategory"]), ("Componentes", "Fuentes de poder"))
        old["name"] = "Power Supply MSI MAG A750BN PCIE5"
        p = self.build(old, new)["products"][0]
        self.assertEqual(p["name"], "Fuente de poder MSI MAG A750GLS PCIE5")
        self.assertNotIn("A750BN", json.dumps(p))

    def test_supplier_brand_wins_over_cpu_in_laptop_name(self):
        old, new = existing(), source()
        old.update(name="Laptop Lenovo Intel Core i5", category="Laptops", subcategory="Portátiles", brand="Intel")
        new.update(name="Lenovo - ThinkPad E14 Intel Core i5", rawTitle="Lenovo - ThinkPad E14 Intel Core i5",
                   brand="Lenovo", partNumber="", description="LAPTOP LENOVO THINKPAD E14, INTEL CORE I5, 16GB RAM")
        p = self.build(old, new)["products"][0]
        self.assertEqual((p["category"], p["brand"]), ("Laptops", "Lenovo"))

    def test_explicit_monitor_maker_resolves_wrong_supplier_heading(self):
        new = source()
        new.update(rawTitle="HP Refurbish - MONITOR VIEWSONIC VG2732M", name="HP Refurbish - MONITOR VIEWSONIC VG2732M",
                   brand="HP Refurbish", partNumber="VG2732M", description="MONITOR VIEWSONIC REFURBISHED VG2732M, 27 PULGADAS")
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["brand"], "ViewSonic")

    def test_model_confirmation_ignores_packaging_suffix_but_not_variant(self):
        new = source("107920")
        new.update(rawTitle="Antec - ABANICO ANTEC C120 ARGB PWM BLACK", name="Antec - ABANICO ANTEC C120 ARGB PWM BLACK",
                   brand="Antec", partNumber="C120R.ARGB-3PK", description="ABANICO ANTEC C120R ARGB PWM, COLOR NEGRO",
                   conflicts=["El título contradice el número de parte"],
                   specifications=[{"label": "Número de parte", "value": "C120R.ARGB-3PK"}],
                   descriptionLines=["ABANICO ANTEC C120R ARGB PWM, COLOR NEGRO"])
        old = existing(reference="107920")
        p = self.build(old, new)["products"][0]
        self.assertEqual(p["name"], "Ventilador Antec C120R.ARGB-3PK")
        self.assertTrue(p["stock"])
        self.assertNotIn("sourceContentConflict", p)
        new["description"] = "ABANICO ANTEC C120 ARGB PWM, COLOR NEGRO"
        p = self.build(old, new)["products"][0]
        self.assertFalse(p["stock"])
        self.assertTrue(p["sourceContentConflict"])
        self.assertNotIn("C120", p["name"])

    def test_unresolved_supplier_model_is_quarantined_without_blocking_catalog(self):
        old, new = existing(reference="107667"), source("107667")
        new.update(rawTitle="Msi - MB B760M GAMING PLUS WIFI, DDR5", name="Msi - MB B760M GAMING PLUS WIFI, DDR5",
                   partNumber="B760 GAMING PLUS WIFI.", description="MB MSI B760M GAMING PLUS WIFI, DDR5, ATX",
                   conflicts=["El título contradice el número de parte"],
                   specifications=[{"label": "Número de parte", "value": "B760 GAMING PLUS WIFI."}],
                   descriptionLines=["MB MSI B760M GAMING PLUS WIFI, DDR5, ATX"])
        p = self.build(old, new)["products"][0]
        self.assertEqual(p["name"], "Tarjeta madre MSI · referencia 107667")
        self.assertFalse(p["stock"])
        self.assertTrue(p["sourceContentConflict"])
        self.assertEqual(p["price"], 16.71)
        self.assertEqual(p["description"], "")
        self.assertEqual(p["features"], [])
        self.assertEqual(p["specifications"], [])
        self.assertNotIn("model", p)
        self.assertNotIn("B760", json.dumps(p))
        result = self.build(old, new)
        result["products"][0]["stock"] = True
        with self.assertRaises(ValueError):
            catalog.validate_catalog(result)

    def test_short_omega_model_is_not_conflicted_by_full_part_number(self):
        old, new = existing(), source()
        old.update(name="Case Gamer Antec C6 Curve Air Black Mid Tower", category="Componentes", subcategory="Gabinetes / Case")
        new.update(name="Antec - CASE ANTEC C6 CURVE AIR BLACK", rawTitle="Antec - C6 Curve Air Black", partNumber="C6-CURVE-AIR-B",
                   brand="Antec", description="CASE ANTEC C6 CURVE AIR BLACK, MID TOWER")
        p = self.build(old, new)["products"][0]
        self.assertEqual(p["name"], "Gabinete Antec C6 Curve Air Black")
        self.assertEqual(p["model"], new["partNumber"])

    def test_image_missing_flag_is_public_only_with_placeholder(self):
        result = self.build()
        p = result["products"][0]
        p["imageUnavailable"] = True
        catalog.validate_catalog(result)
        p["image"] = "img/catalogo/downloaded.png"
        with self.assertRaises(ValueError):
            catalog.validate_catalog(result)
        p["image"] = catalog.PLACEHOLDER
        p["imageUnavailable"] = "yes"
        with self.assertRaises(ValueError):
            catalog.validate_catalog(result)

    def test_one_level_classification_from_omega_description(self):
        examples = [
            ("MONITOR MSI MAG 272F X24, CURVO 1500R", "Monitores", "Curvos"),
            ("PANTALLA INTERACTIVA HIKVISION 65 PULGADAS", "Monitores", "Pantallas interactivas"),
            ("DISCO SSD KINGSTON 1TB", "Almacenamiento", "Discos SSD"),
            ("MEMORIA USB KINGSTON 64GB", "Almacenamiento", "Memorias USB"),
            ("COMBO TECLADO Y MOUSE LOGITECH", "Periféricos", "Combos de teclado y mouse"),
            ("MOUSE PAD ARGOM GAMING", "Periféricos", "Mouse pads"),
            ("TECLADO LOGITECH USB", "Periféricos", "Teclados"),
            ("BOCINAS XTECH FIRESHOT", "Audio y Video", "Bocinas"),
            ("BOCINA JBL CINEMA SB580, BARRA DE SONIDO 3.1", "Audio y Video", "Equipos de sonido"),
            ("CONTROL LOGITECH PRESENTADOR R400, PUNTERO LASER", "Periféricos", "Presentadores"),
            ("CASE ANTEC MID TOWER", "Componentes", "Gabinetes / Case"),
            ("TARJETA DE VIDEO MSI RTX 5060", "Componentes", "Tarjetas gráficas"),
        ]
        for description, category, subcategory in examples:
            with self.subTest(description=description):
                new = source()
                new.update(description=description, partNumber="", specifications=[])
                p = self.build(new=new)["products"][0]
                self.assertEqual((p["category"], p["subcategory"]), (category, subcategory))
                self.assertNotIn("subcategoryPath", p)
                self.assertNotIn("subsubcategory", p)

    def test_curved_monitor_requires_explicit_description_evidence(self):
        new = source()
        new.update(rawTitle="Msi - MONITOR CURVO MAG 272F X24", name="Msi - MONITOR CURVO MAG 272F X24")
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["subcategory"], "De escritorio")
        self.assertNotIn("CURVO", p["name"])
        new["description"] += ", CURVO 1500R"
        p = self.build(new=new)["products"][0]
        self.assertEqual(p["subcategory"], "Curvos")
        self.assertIn("CURVO", p["name"])

    def test_odyssey_g4_marketing_curvature_does_not_become_product_fact(self):
        new = source("94299")
        new.update(rawTitle='Samsung - MONITOR SAMSUNG 27" GAMING ODYSSEY G4, IPS, CURVO, 240 HZ',
                   name='Samsung - MONITOR SAMSUNG 27" GAMING ODYSSEY G4, IPS, CURVO, 240 HZ',
                   brand="Samsung", partNumber="LS27BG402ENXGO",
                   description='MONITOR SAMSUNG 27" GAMING ODYSSEY G4, IPS, 240 HZ')
        p = self.build(existing(reference="94299"), new)["products"][0]
        self.assertEqual(p["subcategory"], "De escritorio")
        self.assertNotIn("CURVO", p["name"])
        self.assertNotIn("specificationNote", p)
        self.assertIn("ODYSSEY G4", p["name"])

    def test_retired_product_cannot_return_and_other_id_stays_selected(self):
        old = existing()
        retired_id = existing("21890", "999001")
        retired_ref = existing("9992", "62635")
        result = catalog.build_catalog([old, retired_id, retired_ref], {"110001": source()}, FakePolicy())
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["products"][0]["id"], "1")
        with self.assertRaises(ValueError):
            catalog.build_catalog([old, old], {"110001": source()}, FakePolicy())

    def test_timestamp_stable_for_identical_omega_details(self):
        first = self.build()["products"][0]
        second = self.build(old=first, timestamp="2026-02-01T00:00:00+00:00")["products"][0]
        self.assertEqual(second["specificationsUpdated"], first["specificationsUpdated"])
        new = source()
        new["description"] += ", NUEVA INFORMACIÓN"
        third = self.build(old=first, new=new, timestamp="2026-02-01T00:00:00+00:00")["products"][0]
        self.assertEqual(third["specificationsUpdated"], "2026-02-01T00:00:00+00:00")

    def test_invalid_prices_and_unavailable_sale_validation(self):
        for value in (True, 0, -1, "NaN", float("inf")):
            with self.subTest(value=value):
                new = source()
                new["price"] = value
                with self.assertRaises(ValueError):
                    self.build(new=new)
        result = self.build()
        result["products"][0].update(price=None, stock=True)
        with self.assertRaises(ValueError):
            catalog.validate_catalog(result)
        result["products"][0]["stock"] = False
        with self.assertRaises(ValueError):
            catalog.validate_catalog(result)
        result["products"][0]["priceUnavailable"] = True
        catalog.validate_catalog(result)


if __name__ == "__main__":
    unittest.main()
