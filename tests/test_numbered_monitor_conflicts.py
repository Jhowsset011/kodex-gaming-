"""A manufacturer lookup must not resolve contradictory supplier identities."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from omega_catalog import _model_conflict, _unresolved_conflict


class NumberedMonitorConflictTests(unittest.TestCase):
    def test_distinct_digit_first_models_are_flagged(self):
        source = {'name': 'MONITOR MSI MAG 27C6X, 27 PULGADAS'}
        self.assertTrue(_model_conflict(source['name'], 'MAG 276CXF'))
        self.assertTrue(_unresolved_conflict(source, 'MAG 276CXF',
                                           'MONITOR MSI MAG 27C6X, 280 HZ'))

    def test_sizes_resolutions_and_refresh_rates_do_not_create_conflicts(self):
        self.assertFalse(_model_conflict('MSI MAG 276CXF, 27 PULGADAS, 280 HZ, 1920 X 1080',
                                         'MAG 276CXF'))
        self.assertFalse(_model_conflict('MSI GAMING 27 PULGADAS, 280 HZ, 1920 X 1080',
                                         'MAG 276CXF'))

    def test_exact_model_in_description_can_resolve_supplier_title_typo(self):
        self.assertFalse(_unresolved_conflict({'name': 'MSI MAG 27C6X'}, 'MAG 276CXF',
                                            'MONITOR MSI MAG 276CXF, 27 PULGADAS'))

    def test_capacity_suffix_in_part_number_is_not_a_conflicting_model(self):
        for part, name in [
            ('SKC600/512G', 'DISCO KINGSTON SSD 512GB'),
            ('SKC600/2048G', 'DISCO KINGSTON SSD 2048GB'),
            ('SNPDFK3YC/16G', 'MEMORIA DELL 16GB'),
            ('HS-SSD-WAVE(S)960G', 'DISCO HIKSEMI 960GB'),
        ]:
            with self.subTest(part=part):
                self.assertFalse(_model_conflict(name, part))


if __name__ == '__main__':
    unittest.main()
