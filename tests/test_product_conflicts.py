"""Reviewed marketing-model conflicts never attach another model's details."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from product_conflicts import apply_reviewed_conflicts


class ReviewedConflictTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'conflicts.json'
        self.entry = {'reference': '900001', 'model': 'DISPLAY-X', 'brand': 'Samsung',
                      'supplierModel': 'OldModel', 'manufacturerModel': 'NewModel'}
        self.path.write_text(json.dumps({'products': {'1': self.entry}}))
        self.product = {'id': '1', 'reference': '900001', 'model': 'DISPLAY-X',
                        'brand': 'Samsung', 'name': 'Monitor OldModel', 'description': 'OldModel 27 pulgadas',
                        'category': 'Monitores', 'subcategory': 'De escritorio',
                        'price': 1900, 'stock': True, 'specifications': [{'label': 'Dato', 'value': 'Valor'}],
                        'features': ['Dato antiguo']}
        self.catalog = {'products': [self.product]}

    def test_conflicting_identity_disables_orders_and_details_without_losing_price_or_id(self):
        apply_reviewed_conflicts(self.catalog, self.path)
        self.assertEqual(self.product['id'], '1')
        self.assertEqual(self.product['price'], 1900)
        self.assertFalse(self.product['stock'])
        self.assertTrue(self.product['sourceContentConflict'])
        self.assertEqual(self.product['description'], '')
        self.assertEqual(self.product['specifications'], [])
        self.assertNotIn('model', self.product)
        apply_reviewed_conflicts(self.catalog, self.path)
        self.assertEqual(self.product['price'], 1900)

    def test_corrected_supplier_model_is_not_kept_unavailable(self):
        self.product.update(name='Monitor NewModel', description='NewModel 27 pulgadas')
        apply_reviewed_conflicts(self.catalog, self.path)
        self.assertTrue(self.product['stock'])
        self.assertNotIn('sourceContentConflict', self.product)

    def test_changed_reference_or_brand_still_requires_identity_review(self):
        for field in ['reference', 'brand']:
            with self.subTest(field=field):
                original = self.product[field]
                self.product[field] = 'Otro'
                with self.assertRaises(ValueError):
                    apply_reviewed_conflicts(self.catalog, self.path)
                self.assertTrue(self.product['stock'])
                self.product[field] = original

    def test_changed_part_quarantines_only_affected_product(self):
        self.product.update(model='DISPLAY-X-OTHER', name='Monitor NewModel', description='NewModel')
        other = dict(self.product, id='2', reference='900002', price=2600)
        self.catalog['products'].append(other)
        with self.assertLogs('product_conflicts', level='WARNING') as logs:
            self.assertIs(apply_reviewed_conflicts(self.catalog, self.path), self.catalog)
        self.assertIn('900001', logs.output[0])
        self.assertFalse(self.product['stock'])
        self.assertTrue(self.product['sourceContentConflict'])
        self.assertEqual(self.product['price'], 1900)
        self.assertNotIn('model', self.product)
        self.assertEqual(self.product['specifications'], [])
        self.assertTrue(other['stock'])
        self.assertEqual(other['price'], 2600)
        self.assertEqual(other['model'], 'DISPLAY-X-OTHER')

    def test_supplier_annotations_allow_corrected_model_to_return(self):
        self.product.update(model='display-x CANAL***', name='Monitor NewModel', description='NewModel')
        apply_reviewed_conflicts(self.catalog, self.path)
        self.assertTrue(self.product['stock'])
        self.assertNotIn('sourceContentConflict', self.product)


if __name__ == '__main__':
    unittest.main()
