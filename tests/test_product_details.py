from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from product_details import clean_part_number, enrich_catalog


def product(description="MONITOR AOC 27\" IPS, 2560 X 1440, 180HZ, 0.3MS, 2X HDMI 2.0, 1X DISPLAYPORT 1.4.", **overrides):
    value = {
        "id": "1", "reference": "12345", "model": "Q27G4H***", "brand": "AOC",
        "name": "Monitor AOC", "category": "Monitores", "subcategory": "Gaming",
        "description": description, "spec": description, "price": 1234.23, "stock": True,
        "specifications": [{"label": "Número de parte", "value": "Q27G4H***"},
                           {"label": "Información del producto", "value": description}],
        "features": [], "specificationSources": ["https://tienda.omega.com.do/es/product/consul/12345"],
    }
    value.update(overrides)
    return value


def catalog(*products):
    return {"source": "Omega Tech — catálogo público", "count": len(products), "products": list(products)}


def rows(value):
    return {row["label"]: row["value"] for row in value["specifications"]}


class SupplierDetailsTests(unittest.TestCase):
    def test_monitor_extracts_only_explicit_specs_and_preserves_identity_and_prices(self):
        original = product()
        data = catalog(original)
        self.assertIs(enrich_catalog(data), data)
        result = data["products"][0]
        technical = rows(result)
        self.assertEqual(technical["Marca"], "AOC")
        self.assertEqual(technical["Número de parte"], "Q27G4H")
        self.assertEqual(technical["Tipo"], "Gaming")
        self.assertEqual(technical["Tamaño de pantalla"], '27"')
        self.assertEqual(technical["Resolución"], "2560 × 1440")
        self.assertEqual(technical["Panel"], "IPS")
        self.assertEqual(technical["Tasa de refresco"], "180 Hz")
        self.assertEqual(technical["Tiempo de respuesta"], "0.3 ms")
        self.assertEqual(technical["Conectividad"], "2 × HDMI 2.0; 1 × DisplayPort 1.4")
        for key in ("id", "reference", "model", "brand", "price", "stock", "spec"):
            self.assertEqual(result[key], original[key])
        self.assertNotIn("Información del producto", technical)

    def test_g4_does_not_inherit_curvature_from_an_incorrect_name_or_model(self):
        data = catalog(product('MONITOR SAMSUNG 27" IPS, 240HZ, FLAT, 1MS.', brand="Samsung",
                               model="LS27BG402ENXGO***", name="Samsung G4 CURVO"))
        enrich_catalog(data)
        self.assertEqual(rows(data["products"][0])["Diseño"], "Plano")
        self.assertNotIn("Curvo", data["products"][0]["description"])

    def test_response_ports_and_accessories_are_not_filled_from_a_model(self):
        data = catalog(product('MONITOR AOC 27" QHD, 180HZ.'))
        enrich_catalog(data)
        self.assertNotIn("Tiempo de respuesta", rows(data["products"][0]))
        self.assertNotIn("Conectividad", rows(data["products"][0]))
        self.assertEqual(data["products"][0]["features"], [])

    def test_negated_curvature_is_not_reported_as_curved(self):
        data = catalog(product('MONITOR 27" IPS, NO CURVO.'))
        enrich_catalog(data)
        self.assertNotIn("Diseño", rows(data["products"][0]))

    def test_resolution_with_thousands_separator(self):
        data = catalog(product('MONITOR 32" UHD (3,840 X 2,160), PANEL VA, 60 HZ.'))
        enrich_catalog(data)
        self.assertEqual(rows(data["products"][0])["Resolución"], "3840 × 2160")

    def test_laptop_ram_and_storage_are_not_swapped(self):
        data = catalog(product('LAPTOP 14", CORE I5-1135G7, 256GB SSD, 16GB DDR4 RAM, WINDOWS 11 PRO.',
                               category="Laptops", subcategory="Laptops", brand="Dell", model="ABC-123"))
        enrich_catalog(data)
        technical = rows(data["products"][0])
        self.assertEqual(technical["Memoria RAM"], "16 GB")
        self.assertEqual(technical["Almacenamiento"], "256 GB")
        self.assertEqual(technical["Procesador"], "CORE I5-1135G7")
        self.assertEqual(technical["Tipo de memoria"], "DDR4")

    def test_memory_before_capacity_and_nvme_before_storage(self):
        data = catalog(product('LAPTOP 16", MEMORIA DDR5 DE 16GB, NVME DE 512GB.',
                               category="Laptops", subcategory="Laptops"))
        enrich_catalog(data)
        self.assertEqual(rows(data["products"][0])["Memoria RAM"], "16 GB")
        self.assertEqual(rows(data["products"][0])["Almacenamiento"], "512 GB")

    def test_unspecified_capacity_is_not_guessed_to_be_ram(self):
        data = catalog(product('LAPTOP 16", 16GB, 512GB SSD.', category="Laptops", subcategory="Laptops"))
        enrich_catalog(data)
        self.assertNotIn("Memoria RAM", rows(data["products"][0]))
        self.assertEqual(rows(data["products"][0])["Almacenamiento"], "512 GB")

    def test_usb_version_generation_and_counts_are_preserved(self):
        data = catalog(product('CASE, USB-A 3.2 GEN 1 X2, 1X USB-C 3.2 GEN 2, 2X USB 2.0.',
                               category="Componentes", subcategory="Gabinetes / Case"))
        enrich_catalog(data)
        self.assertEqual(rows(data["products"][0])["Conectividad"],
                         "2 × USB-A 3.2 GEN 1; 1 × USB-C 3.2 GEN 2; 2 × USB 2.0")

    def test_included_and_not_included_accessories_remain_explicit(self):
        data = catalog(product('MONITOR 15.6", INCLUYE CABLE USB Y CABLE HDMI. NO INCLUYE FUENTE.'))
        enrich_catalog(data)
        self.assertEqual(data["products"][0]["features"],
                         ["Incluye cable USB y cable HDMI.", "No incluye fuente."])
        self.assertNotIn("CABLE DISPLAYPORT", data["products"][0]["description"].upper())

    def test_bare_details_and_unique_source_information_are_preserved(self):
        source = "SILLA GAMING CON ESPALDAR AJUSTABLE Y BASE CON RUEDAS ROBUSTAS"
        data = catalog(product(source, category="Mobiliario", subcategory="Sillas gaming"))
        enrich_catalog(data)
        self.assertEqual(len(rows(data["products"][0])), 3)
        self.assertEqual(data["products"][0]["description"].upper().rstrip("."), source)

    def test_unavailable_and_conflicted_records_stay_unchanged(self):
        missing = product("", sourceUnavailable=True, price=None, stock=False, model=None)
        conflict = product("", sourceContentConflict=True, stock=False, model=None)
        original = catalog(missing, conflict)
        data = deepcopy(original)
        enrich_catalog(data)
        self.assertEqual(data, original)

    def test_repeat_is_identical(self):
        data = catalog(product(), product('LAPTOP 14" | 256GB SSD | 16GB DDR4 RAM | WINDOWS 11 PRO',
                                          id="2", category="Laptops", subcategory="Laptops"))
        enrich_catalog(data)
        first = deepcopy(data)
        enrich_catalog(data)
        self.assertEqual(data, first)

    def test_part_number_cleaning_keeps_variant_and_region(self):
        self.assertEqual(clean_part_number("CC-9011233-WW**"), "CC-9011233-WW")
        self.assertEqual(clean_part_number("DG4U7UT#ABA CANAL"), "DG4U7UT#ABA")
        self.assertEqual(clean_part_number("SKU-WHITE/CANAL"), "SKU-WHITE/CANAL")
        self.assertEqual(clean_part_number("SKU*MID"), "SKU*MID")


class ReviewedManufacturerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "official.json"
        self.entry = {"reference": "12345", "model": "Q27G4H", "brand": "AOC",
                      "description": "Monitor AOC con resolución QHD y panel IPS.",
                      "specifications": [{"label": "Panel", "value": "Fast IPS"},
                                         {"label": "Ángulo de visión", "value": "178°"}],
                      "features": ["Soporte ajustable."],
                      "sources": ["https://aoc.com/es/gaming/products/monitors/q27g4h"]}

    def save(self, entry=None):
        self.path.write_text(json.dumps({"products": {"1": entry if entry is not None else self.entry}}), encoding="utf-8")

    def test_exact_identity_is_enriched_and_supplier_details_survive(self):
        self.save()
        data = catalog(product())
        enrich_catalog(data, self.path)
        result = data["products"][0]
        self.assertEqual(rows(result)["Panel"], "Fast IPS")
        self.assertEqual(rows(result)["Ángulo de visión"], "178°")
        self.assertIn("180Hz", result["description"])
        self.assertTrue(result["description"].startswith(self.entry["description"]))
        self.assertEqual(result["specificationSources"][-1], self.entry["sources"][0])
        self.assertEqual(result["features"], ["Soporte ajustable."])
        self.assertEqual(result["model"], "Q27G4H***")

    def test_identity_mismatch_stops_before_any_product_mutation(self):
        for field, wrong in (("reference", "99999"), ("model", "Q27G4X"), ("brand", "Samsung")):
            with self.subTest(field=field):
                entry = dict(self.entry, **{field: wrong})
                self.save(entry)
                data = catalog(product())
                before = deepcopy(data)
                with self.assertRaises(ValueError):
                    enrich_catalog(data, self.path)
                self.assertEqual(data, before)

    def test_variant_and_region_differences_do_not_match(self):
        for actual, wrong in (("SKU-BLACK", "SKU-WHITE"), ("ABC#ABA", "ABC#ABU")):
            self.save(dict(self.entry, model=wrong))
            with self.assertRaises(ValueError):
                enrich_catalog(catalog(product(model=actual)), self.path)

    def test_case_spaces_and_distributor_annotations_match(self):
        self.save(dict(self.entry, model=" q27 g4h ", brand="aoc"))
        enrich_catalog(catalog(product()), self.path)

    def test_source_requires_https_and_no_credentials(self):
        for url in ("http://aoc.com/model", "https://user:password@aoc.com/model", "https://aoc.com:80/model"):
            self.save(dict(self.entry, sources=[url]))
            with self.assertRaises(ValueError):
                enrich_catalog(catalog(product()), self.path)

    def test_unknown_fields_and_commercial_rows_are_rejected(self):
        entries = [dict(self.entry, cost=100),
                   dict(self.entry, specifications=[{"label": "Garantía", "value": "Tres años"}])]
        for entry in entries:
            self.save(entry)
            with self.assertRaises(ValueError):
                enrich_catalog(catalog(product()), self.path)

    def test_curated_repeat_is_identical_and_does_not_duplicate_sources_or_prose(self):
        self.save()
        data = catalog(product())
        enrich_catalog(data, self.path)
        before = deepcopy(data)
        enrich_catalog(data, self.path)
        self.assertEqual(data, before)
        self.assertEqual(data["products"][0]["description"].count(self.entry["description"]), 1)


if __name__ == "__main__":
    unittest.main()
