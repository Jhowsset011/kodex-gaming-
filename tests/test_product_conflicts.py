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

    def test_changed_part_or_brand_requires_review_instead_of_attaching_old_conflict(self):
        for field in ['reference', 'brand', 'model']:
            with self.subTest(field=field):
                original = self.product[field]
                self.product[field] = 'Otro'
                with self.assertRaises(ValueError):
                    apply_reviewed_conflicts(self.catalog, self.path)
                self.assertTrue(self.product['stock'])
                self.product[field] = original


if __name__ == '__main__':
    unittest.main()
