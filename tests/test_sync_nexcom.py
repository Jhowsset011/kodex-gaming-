import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("sync_nexcom", Path(__file__).parents[1] / "scripts/sync_nexcom.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def product(pid="1", name="Monitor MSI 27 pulgadas"):
    return {"id": pid, "name": name, "category": "Zona Gamer", "brand": "MSI", "price": 800.0, "stock": True, "image": sync.PLACEHOLDER}


def source(pid=1, sku="110001"):
    return {"id": pid, "sku": sku, "name": "Monitor MSI 27 pulgadas", "short_description": "<p>Panel IPS</p>", "description": "<div>📏 <strong>Pantalla:</strong> 27 pulgadas</div>", "permalink": f"https://nexcomtienda.com.do/item/{sku}/", "prices": {"price": "95000", "regular_price": "100000", "currency_code": "DOP", "currency_minor_unit": 2}, "is_in_stock": True, "is_purchasable": True, "on_sale": False, "images": []}


class ClassificationTests(unittest.TestCase):
    def test_three_child_levels_use_product_evidence(self):
        examples = [
            ("Monitor Curvo Samsung 57″ 240Hz VA", ["Curvos", "VA", "57 pulgadas"]),
            ("Pantalla Interactiva Hikvision 65 pulgadas 4K", ["Interactivos", "Panel por confirmar", "65 pulgadas"]),
            ("Disco SSD Kingston NVMe 1TB", ["SSD", "NVMe", "1TB"]),
            ("Memoria Markvision DDR3 4GB", ["Memoria RAM", "DDR3", "4GB"]),
            ("Abanico Corsair 120mm RGB", ["Refrigeración", "Ventiladores", "120 mm"]),
            ("Power Supply MSI 650W 80 Plus Bronce", ["Fuentes de poder", "80 Plus Bronze", "650 W"]),
            ("Case Antec Full-Tower Negro", ["Gabinetes", "Full Tower", "Negro"]),
            ("Mouse Logitech Bluetooth Óptico", ["Mouse", "Bluetooth", "Ópticos"]),
        ]
        for name, path in examples:
            with self.subTest(name=name):
                self.assertEqual(sync.classify(product(name=name))["subcategoryPath"], path)

    def test_model_numbers_are_not_screen_sizes_or_capacities(self):
        p = sync.classify(product(name="Monitor MSI MAG 272F"))
        self.assertEqual(p["subcategoryPath"], ["De escritorio", "Panel por confirmar", "Tamaño por confirmar"])
        p["specifications"] = [{"label":"Tamaño de pantalla", "value":"27″"}, {"label":"Tipo de panel", "value":"Rapid IPS"}]
        self.assertEqual(sync.classify(p)["subcategoryPath"], ["De escritorio", "IPS", "27 pulgadas"])
        ssd = sync.classify(product(name="Disco SSD Kingston SXS2000 USB-C"))
        self.assertEqual(ssd["subcategoryPath"], ["SSD", "USB", "Capacidad por confirmar"])

    def test_new_product_categories_and_brands(self):
        for name, cat, brand in [("Pantalla Interactiva Hikvision 86″", "Monitores", "Hikvision"), ("Motherboard ECS AMD FM1", "Componentes", "ECS"), ("Power Supply Huawei 500W", "Componentes", "Huawei"), ("Monitor Haier 65″", "Monitores", "Haier"), ("Disco Titan Wireless 32GB", "Almacenamiento", "Titan")]:
            with self.subTest(name=name):
                p = sync.classify(product(name=name))
                self.assertEqual((p["category"],p["brand"]), (cat,brand))
        self.assertEqual(sync.classify(product(name="Pedales De Carreras Modulares"))["category"], "Periféricos")

    def test_hierarchy_reclassified_after_source_changes(self):
        p = product(name="Monitor Samsung 27″ IPS")
        p.update(subcategory="Vieja", subsubcategory="Samsung", subcategoryPath=["Vieja"])
        sync.classify(p)
        self.assertNotIn("subcategory",p)
        self.assertNotIn("subsubcategory",p)
        p["name"] = "Monitor Curvo Samsung 32″ VA"
        self.assertEqual(sync.classify(p)["subcategoryPath"], ["Curvos", "VA", "32 pulgadas"])

    def test_monitors_move_from_gamer_and_peripherals(self):
        for old in ("Zona Gamer", "Periféricos"):
            p = product(name="Monitor portátil AOC 15.6 pulgadas")
            p["category"] = old
            sync.classify(p)
            self.assertEqual(p["category"], "Monitores")
            self.assertEqual(p["brand"], "AOC")
            if old == "Zona Gamer":
                self.assertIn("Zona Gamer", p["collections"])

    def test_product_types_before_marketing_category(self):
        examples = {"Smart TV Samsung 50 pulgadas": "Audio y Video", "Disco SSD Kingston NVMe 512GB": "Almacenamiento", "Case Gamer Antec C6": "Componentes", "Mouse Gamer Logitech G305": "Periféricos", "Laptop Lenovo Thinkpad E14": "Laptops", "Silla Gamer Primus Thronos": "Mobiliario", "Computadora Dell Wyse": "Computadoras", "Memoria RAM Dell para laptop": "Componentes"}
        for name, category in examples.items():
            with self.subTest(name=name):
                self.assertEqual(sync.classify(product(name=name))["category"], category)

    def test_manufacturer_before_license_family_and_cpu(self):
        examples = {"Mouse Xtech Marvel Spider-Man": "Xtech", "Combo Xtech Disney Stitch": "Xtech", "Monitor Lenovo ThinkVision S22": "Lenovo", "Laptop Refurbished Thinkpad L13 Intel i5": "Lenovo", "Laptop 14 Intel i5 Vitek 16GB": "Vitek", "Memoria Markvision DDR3 Avant/Samsung": "Markvision", "Ventilador HPE Proliant": "HPE", "Monitor HP Pro Display": "HP", "Mouse Rippa M811": "Rippa", "Disco Maxtor SCSI": "Maxtor", "Streaming Roku 4K": "Roku"}
        for name, brand in examples.items():
            with self.subTest(name=name):
                self.assertEqual(sync.brand_of(name), brand)


class MergeTests(unittest.TestCase):
    def test_import_preserves_disappeared_existing_listing_but_rejects_missing_new(self):
        old = product()
        result, missing = sync.build_catalog([old], {}, {"1"}, [old])
        self.assertEqual(missing,["1"])
        self.assertFalse(result[0]["stock"])
        self.assertTrue(result[0]["sourceUnavailable"])
        self.assertEqual(len(result[0]["subcategoryPath"]),3)
        with self.assertRaises(ValueError):
            sync.build_catalog([old], {}, {"1","2"}, [old,product("2")])

    def test_invalid_hierarchy_rejected(self):
        for path in (["Uno"], ["Uno", "Dos", ""], "Uno / Dos / Tres"):
            p = product()
            p["subcategoryPath"] = path
            with self.assertRaises(ValueError):
                sync.validate([p])
    def test_import_adds_only_missing_ids_preserving_existing_prices(self):
        old = product()
        incoming = product()
        incoming["price"] = 9999
        new = product("2", "Laptop Dell 14 pulgadas")
        result = sync.merge_import([old], [incoming, new])
        self.assertEqual([p["id"] for p in result], ["1", "2"])
        self.assertEqual(result[0]["price"], 800)
        self.assertEqual(old["category"], "Zona Gamer")

    def test_repeated_ids_and_supplier_references_rejected(self):
        with self.assertRaises(ValueError):
            sync.merge_import([], [product(), product()])
        first, second = product(), product("2")
        first["reference"] = second["reference"] = "110001"
        with self.assertRaises(ValueError):
            sync.validate([first, second])

    def test_same_names_distinct_references_remain_distinct(self):
        first, second = product(), product("2")
        first["reference"], second["reference"] = "110001", "110002"
        sync.validate([first, second])

    def test_sync_updates_prices_removes_expired_sale_and_preserves_local_fields(self):
        old = product()
        old.update(old=1200, customField="retained", image="img/catalogo/photo.jpg")
        result, missing = sync.build_catalog([old], {"1": source()}, {"1"})
        self.assertFalse(missing)
        self.assertEqual(result[0]["price"], 950)
        self.assertNotIn("old", result[0])
        self.assertEqual(result[0]["customField"], "retained")
        self.assertEqual(result[0]["image"], "img/catalogo/photo.jpg")
        self.assertEqual(result[0]["specifications"], [{"label": "Pantalla", "value": "27 pulgadas"}])

    def test_out_of_stock_and_missing_listing_not_dropped_or_left_buyable(self):
        unavailable = source()
        unavailable["is_in_stock"] = False
        result, missing = sync.build_catalog([product(), product("2")], {"1": unavailable}, {"1", "2"})
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0]["stock"])
        self.assertFalse(result[1]["stock"])
        self.assertTrue(result[1]["sourceUnavailable"])
        self.assertEqual(missing, ["2"])

    def test_large_partial_response_and_removed_selection_fail(self):
        old = [product(str(i)) for i in range(1, 11)]
        with self.assertRaises(ValueError):
            sync.build_catalog(old, {"1": source()}, {p["id"] for p in old})
        with self.assertRaises(ValueError):
            sync.build_catalog([product(), product("2")], {"1": source()}, {"1"})

    def test_minor_currency_units_and_wrong_currency(self):
        data = source()
        self.assertEqual(sync.source_price(data), 950)
        data["prices"]["currency_minor_unit"] = 0
        self.assertEqual(sync.source_price(data), 95000)
        data["prices"]["currency_code"] = "USD"
        with self.assertRaises(ValueError):
            sync.source_price(data)

    def test_reference_change_fails_before_replace(self):
        old = product()
        old["reference"] = "another-reference"
        with self.assertRaises(ValueError):
            sync.build_catalog([old], {"1": source()}, {"1"})

    def test_unchanged_data_does_not_generate_daily_commit(self):
        products, missing = sync.build_catalog([product()], {"1": source()}, {"1"})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "productos.json"
            self.assertTrue(sync.write_catalog(path, products, missing))
            first = path.read_bytes()
            second, missing = sync.build_catalog(products, {"1": source()}, {"1"})
            self.assertFalse(sync.write_catalog(path, second, missing))
            self.assertEqual(first, path.read_bytes())

    def test_network_failure_keeps_last_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "js").mkdir()
            (root / "scripts").mkdir()
            path = root / "js/productos.json"
            path.write_text(json.dumps({"products": [product()]}))
            (root / "scripts/omega_ids.txt").write_text("1\n")
            before = path.read_bytes()
            with patch.object(sync, "ROOT", root), patch.object(sync, "fetch_json", side_effect=RuntimeError("network unavailable")), patch("sys.argv", ["sync_nexcom.py"]):
                with self.assertRaises(RuntimeError):
                    sync.main()
            self.assertEqual(path.read_bytes(), before)

    def test_bad_price_does_not_replace_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "productos.json"
            path.write_text('{"existing": true}')
            p = product()
            p["price"] = float("nan")
            with self.assertRaises(ValueError):
                sync.write_catalog(path, [p], [])
            self.assertEqual(path.read_text(), '{"existing": true}')

    def test_fetch_only_selected_ids_rejects_unexpected_api_item(self):
        with patch.object(sync, "fetch_json", return_value=[source(pid=99)]):
            with self.assertRaises(ValueError):
                sync.fetch_sources({"1"})


if __name__ == "__main__":
    unittest.main()
