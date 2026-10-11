"""Official rows replace equivalent supplier labels without duplicate claims."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from product_details import _merge_rows, _align_button_count


class SpecificationMergingTests(unittest.TestCase):
    def test_equivalent_official_labels_replace_supplier_values(self):
        base = [{'label': 'Panel', 'value': 'IPS'}, {'label': 'Potencia indicada', 'value': '500 W'},
                {'label': 'Tasa de refresco', 'value': '144 Hz'}]
        official = [{'label': 'Tipo de panel', 'value': 'Rapid IPS'},
                    {'label': 'Potencia', 'value': '550 W'},
                    {'label': 'Frecuencia de actualización', 'value': '180 Hz'}]
        merged = _merge_rows(base, official)
        self.assertEqual(merged, official)
        self.assertEqual(base[0]['value'], 'IPS')

    def test_response_measurements_remain_distinct(self):
        base = [{'label': 'Tiempo de respuesta (GtG)', 'value': '1 ms'}]
        extra = [{'label': 'Tiempo de respuesta (MPRT)', 'value': '0.3 ms'}]
        self.assertEqual(_merge_rows(base, extra), base + extra)

    def test_verified_button_count_is_consistent_with_supplier_name_and_prose(self):
        official = [{'label': 'Cantidad de botones', 'value': '6'}]
        self.assertEqual(_align_button_count('Mouse KMW-330BK con 5 botones.', official),
                         'Mouse KMW-330BK con 6 botones.')
        self.assertEqual(_align_button_count('Mouse con 5 botones de 1200 DPI.', []),
                         'Mouse con 5 botones de 1200 DPI.')


if __name__ == '__main__':
    unittest.main()
