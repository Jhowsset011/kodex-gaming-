"""Verify scoped inventory, exclusion, deduplication and restock behavior."""

from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from omega_catalog import build_catalog
from omega_pricing import PricingPolicy
from omega_selection import (extend_selection, filter_visible_catalog, is_refurbished,
                             read_full_selection, selected_inventory, selection_document, write_selection)
from sync_omega import read_selection
import sync_omega as sync


def identity(pid='40', reference='900040'):
    return {'id': pid, 'reference': reference, 'name': 'Monitor MSI de prueba', 'brand': 'MSI',
            'category': 'Monitores', 'subcategory': 'De escritorio'}


def source(reference='900040', principal=1, nave=1, elsewhere=0):
    return {'reference': reference, 'rawTitle': 'MSI - MONITOR MSI DE PRUEBA',
            'name': 'MSI - MONITOR MSI DE PRUEBA', 'brand': 'MSI', 'currency': 'DOP',
            'price': '120', 'stock': True, 'partNumber': 'TEST-1',
            'description': 'MONITOR MSI DE PRUEBA', 'descriptionLines': [], 'specifications': [],
            'sourceUrl': f'https://tienda.omega.com.do/es/product/consul/{reference}',
            'imageSource': '', 'sourceCategories': ['Monitor'],
            'inventory': [{'branch': 'PRINCIPAL SD', 'quantity': principal},
                          {'branch': 'La Nave', 'quantity': nave},
                          {'branch': 'SANTIAGO', 'quantity': elsewhere}]}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = PricingPolicy.from_dict({'discountPercent': '20',
            'bands': [{'maxCost': '500', 'markupPercent': '10'}], 'aboveMax': 'public',
            'rounding': {'step': 100, 'downThrough': 30}})

    def build(self, products, sources, missing=()):
        return build_catalog(products, sources, self.policy, missing_confirmed=missing)

    def test_inventory_sums_only_principal_and_nave_even_if_other_branches_have_stock(self):
        self.assertEqual(selected_inventory(source(principal=0, nave=1, elsewhere=999)), 1)
        self.assertEqual(selected_inventory(source(principal=1, nave=1, elsewhere=0)), 2)

    def test_incomplete_negative_boolean_or_repeated_branch_inventory_fails_closed(self):
        cases = []
        for rows in ([{'branch': 'La Nave', 'quantity': 2}],
                     [{'branch': 'PRINCIPAL SD', 'quantity': -1}, {'branch': 'La Nave', 'quantity': 2}],
                     [{'branch': 'PRINCIPAL SD', 'quantity': True}, {'branch': 'La Nave', 'quantity': 2}],
                     source()['inventory'] + [{'branch': 'principal sd', 'quantity': 2}]):
            item = source()
            item['inventory'] = rows
            cases.append(item)
        for item in cases:
            with self.subTest(item=item), self.assertRaises(ValueError):
                selected_inventory(item)

    def test_refurbished_matches_original_brand_title_description_and_part_number(self):
        for field in ('rawTitle', 'name', 'brand', 'description', 'partNumber'):
            for condition in ('Refurbish', 'REFURBISHED'):
                item = source()
                item[field] = 'Samsung ' + condition
                self.assertTrue(is_refurbished(item), (field, condition))
        self.assertFalse(is_refurbished(source()))

    def test_filter_removes_low_stock_refurbished_and_retired_without_mutating_inputs(self):
        products = [identity(str(i), str(900000+i)) for i in range(1, 6)]
        sources = {p['reference']: source(p['reference'], principal=0, nave=qty, elsewhere=99)
                   for p, qty in zip(products[:4], [0, 1, 2, 10])}
        sources[products[3]['reference']]['rawTitle'] += ' REFURBISHED'
        catalog = self.build(products, sources, [products[4]['reference']])
        before = deepcopy(catalog)
        visible, excluded = filter_visible_catalog(catalog, sources)
        self.assertEqual([p['id'] for p in visible['products']], ['3'])
        self.assertEqual(visible['count'], 1)
        self.assertNotIn('sourceMissingReferences', visible)
        self.assertEqual([p['reasons'] for p in excluded],
                         [['inventory_0_or_1'], ['inventory_0_or_1'], ['refurbished'], ['retired']])
        self.assertEqual(catalog, before)

    def test_empty_filter_and_missing_exact_supplier_identity_stop_publication(self):
        catalog = self.build([identity()], {'900040': source(principal=0, nave=1)})
        with self.assertRaises(ValueError):
            filter_visible_catalog(catalog, {'900040': source(principal=0, nave=1)})
        with self.assertRaises(ValueError):
            filter_visible_catalog(catalog, {'900040': source(reference='900041')})

    def test_extending_selection_skips_existing_and_foreign_brands_and_preserves_urls(self):
        old = identity()
        sources = {'900040': source(), '900041': source('900041'), '900042': source('900042')}
        sources['900042'].update(brand='Dell', name='Dell - MONITOR DELL', rawTitle='Dell - MONITOR DELL',
                                description='MONITOR DELL DE PRUEBA')
        selected, added = extend_selection([old], sources)
        self.assertEqual(added, ['900041'])
        self.assertEqual(selected[0], old)
        self.assertEqual(selected[1]['id'], '900000900041')
        repeated, added_again = extend_selection(selected, sources)
        self.assertEqual(added_again, [])
        self.assertEqual(repeated, selected)

    def test_new_reference_collision_and_changed_source_identity_fail(self):
        for old, item in [(identity('900000900041'), source('900041')),
                          (identity(), source('900042'))]:
            with self.subTest(item=item), self.assertRaises(ValueError):
                extend_selection([old], {'900041': item})

    def test_samsung_phones_and_tablets_get_their_own_category_instead_of_monitor_or_components(self):
        sources = {}
        for ref, description in [('900041', 'TABLETA SAMSUNG GALAXY TAB A11'),
                                 ('900042', 'TELEFONO SAMSUNG GALAXY A16 ANDROID')]:
            item = source(ref)
            item.update(brand='Samsung', name='Samsung - ' + description,
                        rawTitle='Samsung - ' + description, description=description)
            sources[ref] = item
        selected, added = extend_selection([identity()], sources)
        self.assertEqual(added, ['900041', '900042'])
        self.assertEqual([(p['category'], p['subcategory']) for p in selected[1:]],
                         [('Celulares y tablets', 'Tablets'), ('Celulares y tablets', 'Celulares')])

    def test_new_accessory_types_keep_one_correct_subcategory(self):
        cases = [
            ('MSI', 'GAME PAD MSI FORCE GC300 W', 'Periféricos', 'Controles de juego'),
            ('MSI', 'SOPORTE PARA DUAL MONITOR MSI MAG MT101DG', 'Periféricos', 'Soportes para monitores'),
            ('Antec', 'CABLE DE EXTENSIÓN ANTEC DE ALIMENTACIÓN', 'Componentes', 'Cables de alimentación'),
            ('Antec', 'SOPORTE VERTICAL PARA TARJETA GRÁFICA ANTEC', 'Componentes', 'Accesorios para GPU'),
            ('Samsung', 'COVER SAMSUNG, FUNDA PARA SAMSUNG I8190', 'Celulares y tablets', 'Accesorios para celulares'),
            ('Samsung', 'DOCKING STATION SAMSUNG CY-TF65BRC', 'Periféricos', 'Docking stations'),
        ]
        for maker, description, category, subcategory in cases:
            item = source('900041')
            item.update(brand=maker, name=maker + ' - ' + description,
                        rawTitle=maker + ' - ' + description, description=description)
            with self.subTest(description=description):
                products, _ = extend_selection([identity()], {'900041': item})
                self.assertEqual((products[1]['category'], products[1]['subcategory']), (category, subcategory))

    def test_manifest_keeps_hidden_identity_for_restock_and_prevents_refurbish_return(self):
        products = [identity('40', '900040'), identity('41', '900041')]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'data').mkdir()
            (root/'scripts').mkdir()
            (root/'js').mkdir()
            document = selection_document(products)
            write_selection(root/'data/omega-selection.json', document)
            initial = {'900040': source(principal=0, nave=1, elsewhere=100), '900041': source('900041')}
            visible, _ = filter_visible_catalog(self.build(products, initial), initial)
            (root/'js/productos-v2.json').write_text(json.dumps(visible))
            (root/'scripts/omega_ids.txt').write_text('40\n41\n')
            full, refs = read_selection(root)
            self.assertEqual(refs, ['900040', '900041'])
            self.assertEqual([p['id'] for p in full['products']], ['40', '41'])
            replenished = {'900040': source(principal=2, nave=0), '900041': source('900041')}
            result, _ = filter_visible_catalog(self.build(full['products'], replenished), replenished)
            self.assertEqual([p['id'] for p in result['products']], ['40', '41'])
            replenished['900040']['brand'] = 'MSI Refurbish'
            result, _ = filter_visible_catalog(self.build(full['products'], replenished), replenished)
            self.assertEqual([p['id'] for p in result['products']], ['41'])

    def test_manifest_preserves_known_missing_and_rejects_unselected_visible_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            doc = selection_document([identity()], ['900040'])
            write_selection(root/'data/omega-selection.json', doc)
            current = {'products': [], 'count': 0}
            full = read_full_selection(root, current)
            self.assertEqual(full['sourceMissingReferences'], ['900040'])
            with self.assertRaises(ValueError):
                read_full_selection(root, {'products': [identity('41', '900041')]})

    def test_manifest_does_not_copy_private_or_price_fields_and_noop_does_not_write(self):
        product = {**identity(), 'privatePricing': 'must-not-leak', 'price': 123, 'purchaseCost': 90}
        doc = selection_document([product])
        encoded = json.dumps(doc)
        self.assertNotIn('purchaseCost', encoded)
        self.assertNotIn('privatePricing', encoded)
        self.assertNotIn('price', encoded)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'selection.json'
            self.assertTrue(write_selection(path, doc))
            before = path.stat().st_mtime_ns
            self.assertFalse(write_selection(path, doc))
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_sync_publishes_filtered_outputs_and_reintroduces_restock_with_same_id(self):
        products = [identity('40', '900040'), identity('41', '900041')]
        initial = {'900040': source(), '900041': source('900041')}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'data').mkdir()
            (root/'scripts').mkdir()
            (root/'js').mkdir()
            write_selection(root/'data/omega-selection.json', selection_document(products))
            (root/'scripts/omega_ids.txt').write_text('40\n41\n')
            (root/'js/productos-v2.json').write_text(json.dumps(self.build(products, initial)))
            for quantity, expected in [(1, ['40']), (2, ['40', '41'])]:
                fresh = {'900040': source(), '900041': source('900041', principal=0, nave=quantity, elsewhere=100)}
                snapshot = root/'sources.json'
                snapshot.write_text(json.dumps({'sources': fresh, 'missingReferences': [], 'selectedCount': 2}))
                with patch.object(sync, 'ROOT', root), \
                        patch.object(sync.PricingPolicy, 'from_env', return_value=self.policy), \
                        patch.object(sys, 'argv', ['sync_omega.py', '--require-rounding', '--source-file', str(snapshot)]), \
                        patch.object(sync, 'make_tls_context') as tls, \
                        patch.object(sync, 'fetch_selected_references') as fetch, \
                        patch.object(sync, 'localize_images'), redirect_stdout(io.StringIO()):
                    sync.main()
                    tls.assert_not_called()
                    fetch.assert_not_called()
                canonical = json.loads((root/'js/productos-v2.json').read_text())
                legacy = json.loads((root/'js/productos.json').read_text())
                self.assertEqual([p['id'] for p in canonical['products']], expected)
                self.assertEqual(legacy['products'], canonical['products'])
                manifest = json.loads((root/'data/omega-selection.json').read_text())
                self.assertEqual([p['id'] for p in manifest['products']], ['40', '41'])

    def test_brand_import_filters_entire_store_and_remains_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'scripts').mkdir()
            (root/'js').mkdir()
            (root/'scripts/omega_ids.txt').write_text('40\n')
            (root/'js/productos-v2.json').write_text(json.dumps(self.build([identity()], {'900040': source()})))
            sources = {'900040': source(), '900041': source('900041', principal=0, nave=1),
                       '900042': source('900042'), '900043': source('900043')}
            for ref, maker in [('900042', 'AOC'), ('900043', 'Dell')]:
                sources[ref].update(brand=maker, name=f'{maker} - MONITOR {maker} DE PRUEBA',
                                    rawTitle=f'{maker} - MONITOR {maker} DE PRUEBA', description=f'MONITOR {maker} DE PRUEBA')
            snapshot = root/'audit.json'
            snapshot.write_text(json.dumps({'sources': sources, 'missingReferences': [], 'selectedCount': 4}))
            for repetition in range(2):
                with patch.object(sync, 'ROOT', root), \
                        patch.object(sync.PricingPolicy, 'from_env', return_value=self.policy), \
                        patch.object(sys, 'argv', ['sync_omega.py', '--import-brands', '--source-file', str(snapshot)]), \
                        patch.object(sync, 'localize_images'), redirect_stdout(io.StringIO()):
                    sync.main()
                visible = json.loads((root/'js/productos-v2.json').read_text())
                manifest = json.loads((root/'data/omega-selection.json').read_text())
                self.assertEqual([p['id'] for p in visible['products']], ['40', '900000900042'])
                self.assertEqual([p['reference'] for p in manifest['products']], ['900040', '900041', '900042'])
                self.assertEqual((root/'scripts/omega_ids.txt').read_text().split(),
                                 ['40', '900000900041', '900000900042'])

    def test_brand_audit_rejects_incomplete_selection_or_forged_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'audit.json'
            for sources, count in [({'900041': source('900041')}, 1),
                                   ({'900040': source('900041')}, 1),
                                   ({'900040': source()}, 2)]:
                path.write_text(json.dumps({'sources': sources, 'missingReferences': [], 'selectedCount': count}))
                with self.assertRaises(ValueError):
                    sync.read_brand_import_snapshot(path, {'products': [identity()]})


if __name__ == '__main__':
    unittest.main()
