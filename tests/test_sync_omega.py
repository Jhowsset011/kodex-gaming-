"""Protect publication boundaries of the Omega synchronization command."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("sync_omega", SCRIPTS / "sync_omega.py")
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


def listing(pid="40", reference="900040"):
    return {
        "id": pid, "reference": reference, "name": "Monitor de prueba",
        "category": "Monitores", "subcategory": "De escritorio",
        "brand": "Marca de prueba", "price": 120.0, "stock": True,
        "image": "img/catalogo/sin-imagen.svg",
        "sourceImage": "", "specificationSources": [],
    }


def catalog(products=None, updated="2026-01-01T00:00:00+00:00"):
    products = [listing()] if products is None else products
    return {
        "source": "Omega Tech — catálogo público", "count": len(products),
        "products": products, "updated": updated,
    }


def write_fixture(root, products, selection=None):
    (root / "js").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    path = root / "js/productos.json"
    path.write_text(json.dumps(catalog(products), ensure_ascii=False) + "\n", encoding="utf-8")
    if selection is None:
        selection = [product["id"] for product in products]
    (root / "scripts/omega_ids.txt").write_text("\n".join(selection) + "\n", encoding="utf-8")
    return path


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_full_selection_keeps_kodex_ids_and_returns_omega_references_in_catalog_order(self):
        products = [listing(str(1000 + index), str(900000 + index)) for index in range(589)]
        # Selection files contain stable storefront IDs, not the supplier references;
        # their order must not accidentally rearrange existing product URLs.
        write_fixture(self.root, products, list(reversed([item["id"] for item in products])))
        current, references = sync.read_selection(self.root)
        self.assertEqual(current["products"], products)
        self.assertEqual(references, [item["reference"] for item in products])
        self.assertEqual(len(references), 589)

    def test_supplier_references_cannot_replace_stable_ids_in_selection_file(self):
        products = [listing("40", "900040"), listing("41", "900041")]
        write_fixture(self.root, products, [item["reference"] for item in products])
        with self.assertRaises(ValueError):
            sync.read_selection(self.root)

    def test_duplicates_and_incomplete_or_expanded_selections_fail_closed(self):
        first, second = listing("40", "900040"), listing("41", "900041")
        cases = [
            ([first, first], ["40"]),
            ([first, listing("41", "900040")], ["40", "41"]),
            ([first, second], ["40", "41", "41"]),
            ([first, second], ["40"]),
            ([first, second], ["40", "41", "42"]),
        ]
        for products, selection in cases:
            with self.subTest(products=products, selection=selection):
                path = write_fixture(self.root, products, selection)
                before = path.read_bytes()
                with self.assertRaises(ValueError):
                    sync.read_selection(self.root)
                self.assertEqual(path.read_bytes(), before)

    def test_removed_product_and_nonnumeric_reference_cannot_reenter(self):
        for product in (listing("21890", "900040"), listing("40", "62635"),
                        listing("40", "not-an-omega-reference")):
            with self.subTest(product=product):
                write_fixture(self.root, [product])
                with self.assertRaises(ValueError):
                    sync.read_selection(self.root)

    def test_empty_catalog_and_selection_are_rejected(self):
        write_fixture(self.root, [])
        with self.assertRaisesRegex(ValueError, "Selección inválida"):
            sync.read_selection(self.root)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "sources.json"
        self.references = ["900040", "900041", "900042"]

    def read(self, sources, missing, count=3):
        self.path.write_text(json.dumps({
            "sources": sources, "missingReferences": missing, "selectedCount": count,
        }), encoding="utf-8")
        return sync.read_snapshot(self.path, self.references)

    def test_exact_source_and_confirmed_missing_partition_is_accepted(self):
        sources = {"900040": {"reference": "900040"}, "900042": {"reference": "900042"}}
        result, missing = self.read(sources, ["900041"])
        self.assertEqual(result, sources)
        self.assertEqual(missing, ["900041"])

    def test_stale_extra_incomplete_overlapping_and_duplicate_missing_captures_fail(self):
        all_sources = {reference: {} for reference in self.references}
        cases = [
            ({"900040": {}}, []),
            ({**all_sources, "900099": {}}, []),
            (all_sources, ["900041"]),
            ({"900040": {}, "900042": {}}, ["900041", "900041"]),
            ({"900040": {}, "900042": {}}, ["900099"]),
            (all_sources, [], 2),
            ([], self.references),
            (all_sources, ""),
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.read(*case)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = write_fixture(self.root, [listing()])
        self.before = self.path.read_bytes()

    def assert_untouched(self):
        self.assertEqual(self.path.read_bytes(), self.before)
        self.assertEqual(sorted(path.name for path in self.path.parent.iterdir()), ["productos.json"])

    def test_timestamp_alone_does_not_rewrite_catalog_or_touch_mtime(self):
        before_mtime = self.path.stat().st_mtime_ns
        with patch.object(sync.tempfile, "NamedTemporaryFile") as create_temporary:
            changed = sync.write_catalog(self.path, catalog(updated="2026-01-02T00:00:00+00:00"))
        self.assertFalse(changed)
        create_temporary.assert_not_called()
        self.assert_untouched()
        self.assertEqual(self.path.stat().st_mtime_ns, before_mtime)

    def test_changed_price_replaces_complete_catalog_and_removes_temporary_file(self):
        new = catalog()
        new["products"][0]["price"] = 135.25
        self.assertTrue(sync.write_catalog(self.path, new))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), new)
        self.assertTrue(self.path.read_bytes().endswith(b"\n"))
        self.assertEqual(sorted(path.name for path in self.path.parent.iterdir()), ["productos.json"])

    def test_invalid_public_catalog_or_private_fields_never_start_a_write(self):
        invalid_cases = []
        for edit in (
            lambda data: data.update(count=2),
            lambda data: data.update(privatePricing={"exampleSecret": "must-stay-private"}),
            lambda data: data["products"][0].update(purchaseCost=100),
            lambda data: data["products"][0].update(price=float("nan")),
            lambda data: data["products"][0].update(price=None, stock=True),
        ):
            data = catalog()
            edit(data)
            invalid_cases.append(data)
        for data in invalid_cases:
            with self.subTest(data=data), patch.object(sync.tempfile, "NamedTemporaryFile") as create_temporary:
                with self.assertRaises(ValueError):
                    sync.write_catalog(self.path, data)
                create_temporary.assert_not_called()
                self.assert_untouched()

    def test_serialization_failure_removes_partial_file_and_preserves_published_bytes(self):
        new = catalog()
        new["products"][0]["price"] = 135.25

        def interrupted_dump(_data, handle, **_kwargs):
            handle.write('{"products": [')
            raise OSError("simulated disk failure")

        with patch.object(sync.json, "dump", side_effect=interrupted_dump):
            with self.assertRaises(OSError):
                sync.write_catalog(self.path, new)
        self.assert_untouched()

    def test_failed_atomic_replace_preserves_published_bytes_and_cleans_temporary(self):
        new = catalog()
        new["products"][0]["price"] = 135.25
        with patch.object(sync.Path, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaises(OSError):
                sync.write_catalog(self.path, new)
        self.assert_untouched()


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = write_fixture(self.root, [listing()])
        self.before = self.path.read_bytes()
        # Deliberately fictional rules: no actual merchant policy enters this repository.
        self.policy = sync.PricingPolicy.from_dict({
            "discountPercent": "20", "bands": [{"maxCost": "500", "markupPercent": "10"}],
            "aboveMax": "public",
        })

    def test_missing_private_rules_stop_before_any_selection_supplier_or_image_reads(self):
        with patch.object(sys, "argv", ["sync_omega.py"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", side_effect=ValueError("Private pricing configuration is required.")), \
                patch.object(sync, "read_selection") as selection, \
                patch.object(sync, "make_tls_context") as context, \
                patch.object(sync, "fetch_selected_references") as fetch, \
                patch.object(sync, "localize_images") as images, \
                patch.object(sync, "write_catalog") as write:
            with self.assertRaisesRegex(ValueError, "configuration is required"):
                sync.main()
            for operation in (selection, context, fetch, images, write):
                operation.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_empty_selection_aborts_before_tls_or_supplier_requests(self):
        self.path = write_fixture(self.root, [])
        self.before = self.path.read_bytes()
        with patch.object(sys, "argv", ["sync_omega.py"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                patch.object(sync, "make_tls_context") as context, \
                patch.object(sync, "fetch_selected_references") as fetch, \
                patch.object(sync, "write_catalog") as write:
            with self.assertRaisesRegex(ValueError, "Selección inválida"):
                sync.main()
            for operation in (context, fetch, write):
                operation.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_accept_missing_baseline_cannot_disable_network_run_protection(self):
        with patch.object(sys, "argv", ["sync_omega.py", "--accept-missing-baseline"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env") as policy, \
                patch.object(sync, "make_tls_context") as context, \
                patch.object(sync, "fetch_selected_references") as fetch, \
                patch.object(sync, "write_catalog") as write, redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as stopped:
                sync.main()
            self.assertEqual(stopped.exception.code, 2)
            for operation in (policy, context, fetch, write):
                operation.assert_not_called()
        self.assertIn("captura pública revisada", error.getvalue())
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_policy_file_inside_repository_is_rejected_before_reading_rules(self):
        internal_file = self.root / "private-rules.json"
        internal_file.write_text("must-not-be-read-or-published", encoding="utf-8")
        with patch.object(sys, "argv", ["sync_omega.py", "--policy-file", str(internal_file)]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env") as policy, \
                patch.object(sync, "read_selection") as selection, \
                patch.object(sync, "fetch_selected_references") as fetch, redirect_stderr(io.StringIO()) as error:
            with self.assertRaises(SystemExit) as stopped:
                sync.main()
            self.assertEqual(stopped.exception.code, 2)
            for operation in (policy, selection, fetch):
                operation.assert_not_called()
        self.assertIn("fuera del repositorio", error.getvalue())
        self.assertNotIn("must-not-be-read-or-published", error.getvalue())
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_external_symlink_to_repository_policy_is_also_rejected(self):
        internal_file = self.root / "private-rules.json"
        internal_file.write_text("private-example", encoding="utf-8")
        with tempfile.TemporaryDirectory() as external_directory:
            outside_link = Path(external_directory) / "linked-rules.json"
            outside_link.symlink_to(internal_file)
            with patch.object(sys, "argv", ["sync_omega.py", "--policy-file", str(outside_link)]), \
                    patch.object(sync, "ROOT", self.root), \
                    patch.object(sync.PricingPolicy, "from_env") as policy, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as stopped:
                    sync.main()
                self.assertEqual(stopped.exception.code, 2)
                policy.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_external_policy_file_is_passed_to_pricing_without_publishing_it(self):
        source_file = self.root / "sources.json"
        source_file.write_text(json.dumps({
            "sources": {"900040": {}}, "missingReferences": [], "selectedCount": 1,
        }), encoding="utf-8")
        with tempfile.TemporaryDirectory() as external_directory:
            policy_file = Path(external_directory) / "private-rules.json"
            policy_file.write_text("a-private-example-not-for-the-catalog", encoding="utf-8")
            with patch.object(sys, "argv", ["sync_omega.py", "--dry-run", "--source-file", str(source_file),
                                            "--policy-file", str(policy_file)]), \
                    patch.object(sync, "ROOT", self.root), \
                    patch.object(sync.PricingPolicy, "from_env", return_value=self.policy) as policy, \
                    patch.object(sync, "build_catalog", return_value=catalog()), \
                    patch.object(sync, "fetch_selected_references") as fetch, \
                    patch.object(sync, "write_catalog") as write, redirect_stdout(io.StringIO()) as output:
                sync.main()
                policy.assert_called_once_with(file_path=policy_file)
                fetch.assert_not_called()
                write.assert_not_called()
            self.assertNotIn("a-private-example-not-for-the-catalog", output.getvalue())
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_network_failure_aborts_before_building_or_localizing_and_preserves_catalog(self):
        with patch.object(sys, "argv", ["sync_omega.py"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                patch.object(sync, "make_tls_context", return_value=object()), \
                patch.object(sync, "fetch_selected_references", side_effect=RuntimeError("Supplier unavailable")), \
                patch.object(sync, "build_catalog") as build, \
                patch.object(sync, "localize_images") as images, \
                patch.object(sync, "write_catalog") as write:
            with self.assertRaisesRegex(RuntimeError, "Supplier unavailable"):
                sync.main()
            for operation in (build, images, write):
                operation.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_offline_dry_run_validates_snapshot_without_transport_images_or_writes(self):
        source_file = self.root / "sources.json"
        source_file.write_text(json.dumps({
            "sources": {"900040": {"reference": "900040"}},
            "missingReferences": [], "selectedCount": 1,
        }), encoding="utf-8")
        built = catalog()
        with patch.object(sys, "argv", ["sync_omega.py", "--dry-run", "--source-file", str(source_file)]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                patch.object(sync, "build_catalog", return_value=built) as build, \
                patch.object(sync, "make_tls_context") as context, \
                patch.object(sync, "fetch_selected_references") as fetch, \
                patch.object(sync, "localize_images") as images, \
                patch.object(sync, "write_catalog") as write, redirect_stdout(io.StringIO()) as output:
            sync.main()
            build.assert_called_once_with([listing()], {"900040": {"reference": "900040"}},
                                          self.policy, missing_confirmed=[])
            for operation in (context, fetch, images, write):
                operation.assert_not_called()
        self.assertIn("Sin escribir", output.getvalue())
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_unusually_many_confirmed_missing_records_abort_before_publish(self):
        products = [listing(str(1000 + index), str(900000 + index)) for index in range(100)]
        self.path = write_fixture(self.root, products)
        self.before = self.path.read_bytes()
        sources = {item["reference"]: {} for item in products[6:]}
        missing = [item["reference"] for item in products[:6]]
        with patch.object(sys, "argv", ["sync_omega.py"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                patch.object(sync, "make_tls_context", return_value=object()), \
                patch.object(sync, "fetch_selected_references", return_value=(sources, missing)), \
                patch.object(sync, "build_catalog") as build, \
                patch.object(sync, "localize_images") as images, \
                patch.object(sync, "write_catalog") as write:
            with self.assertRaisesRegex(ValueError, "demasiadas fichas"):
                sync.main()
            for operation in (build, images, write):
                operation.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)

    def test_known_missing_baseline_does_not_hide_newly_missing_threshold(self):
        products = [listing(str(1000 + index), str(900000 + index)) for index in range(100)]
        known_missing = [item["reference"] for item in products[:20]]
        self.path = write_fixture(self.root, products)
        current = json.loads(self.path.read_text(encoding="utf-8"))
        current["sourceMissingReferences"] = known_missing
        self.path.write_text(json.dumps(current), encoding="utf-8")
        self.before = self.path.read_bytes()
        # Twenty previously reviewed absences should not block the daily job;
        # its safety threshold still applies to newly missing references.
        for newly_missing_count in (5, 6):
            missing_count = len(known_missing) + newly_missing_count
            sources = {item["reference"]: {} for item in products[missing_count:]}
            missing = [item["reference"] for item in products[:missing_count]]
            with self.subTest(newly_missing_count=newly_missing_count), \
                    patch.object(sys, "argv", ["sync_omega.py", "--dry-run"]), \
                    patch.object(sync, "ROOT", self.root), \
                    patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                    patch.object(sync, "make_tls_context", return_value=object()), \
                    patch.object(sync, "fetch_selected_references", return_value=(sources, missing)), \
                    patch.object(sync, "build_catalog", return_value=catalog(products)) as build, \
                    patch.object(sync, "localize_images") as images, \
                    patch.object(sync, "write_catalog") as write, redirect_stdout(io.StringIO()):
                if newly_missing_count == 5:
                    sync.main()
                    build.assert_called_once_with(products, sources, self.policy, missing_confirmed=missing)
                else:
                    with self.assertRaisesRegex(ValueError, "demasiadas fichas"):
                        sync.main()
                    build.assert_not_called()
                images.assert_not_called()
                write.assert_not_called()
            self.assertEqual(self.path.read_bytes(), self.before)

    def test_large_initial_missing_baseline_requires_explicit_reviewed_snapshot_flag(self):
        products = [listing(str(1000 + index), str(900000 + index)) for index in range(100)]
        self.path = write_fixture(self.root, products)
        self.before = self.path.read_bytes()
        sources = {item["reference"]: {} for item in products[20:]}
        missing = [item["reference"] for item in products[:20]]
        source_file = self.root / "sources.json"
        source_file.write_text(json.dumps({
            "sources": sources, "missingReferences": missing, "selectedCount": len(products),
        }), encoding="utf-8")
        for explicit_review in (False, True):
            arguments = ["sync_omega.py", "--dry-run", "--source-file", str(source_file)]
            if explicit_review:
                arguments.append("--accept-missing-baseline")
            with self.subTest(explicit_review=explicit_review), \
                    patch.object(sys, "argv", arguments), \
                    patch.object(sync, "ROOT", self.root), \
                    patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                    patch.object(sync, "build_catalog", return_value=catalog(products)) as build, \
                    patch.object(sync, "make_tls_context") as context, \
                    patch.object(sync, "fetch_selected_references") as fetch, \
                    patch.object(sync, "write_catalog") as write, redirect_stdout(io.StringIO()):
                if explicit_review:
                    sync.main()
                    build.assert_called_once_with(products, sources, self.policy, missing_confirmed=missing)
                else:
                    with self.assertRaisesRegex(ValueError, "demasiadas fichas"):
                        sync.main()
                    build.assert_not_called()
                for operation in (context, fetch, write):
                    operation.assert_not_called()
            self.assertEqual(self.path.read_bytes(), self.before)

    def test_image_failure_preserves_catalog_even_after_successful_source_build(self):
        built = catalog()
        built["products"][0]["price"] = 135.25
        with patch.object(sys, "argv", ["sync_omega.py"]), \
                patch.object(sync, "ROOT", self.root), \
                patch.object(sync.PricingPolicy, "from_env", return_value=self.policy), \
                patch.object(sync, "make_tls_context", return_value=object()), \
                patch.object(sync, "fetch_selected_references", return_value=({"900040": {}}, [])), \
                patch.object(sync, "build_catalog", return_value=built), \
                patch.object(sync, "localize_images", side_effect=RuntimeError("Invalid supplier image")), \
                patch.object(sync, "write_catalog") as write:
            with self.assertRaisesRegex(RuntimeError, "Invalid supplier image"):
                sync.main()
            write.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.before)


if __name__ == "__main__":
    unittest.main()
