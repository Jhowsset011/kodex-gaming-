"""Reject truncated brand discovery instead of silently omitting products."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from collect_omega_brands import parse_search_page, resolve_brand_filter


def page_html(first, last, total, pages, refs):
    cards = ''.join(f'<li class="product"><a href="/es/product/consul/{ref}">Producto</a></li>' for ref in refs)
    return (f'<div id="product-list"><p>Mostrando {first} a {last} de {total} ({pages} Páginas)</p>'
            f'<ul>{cards}</ul></div>').encode()


class SearchTests(unittest.TestCase):
    def test_brand_filter_uses_exact_labels_and_keeps_multiple_official_brand_variants(self):
        body = b'<label><input name="brand" value="15">Logitech</label><label><input name="brand" value="16">Logitech G</label><label><input name="brand" value="99">Another Logitech accessory</label>'
        self.assertEqual(resolve_brand_filter(body, 'LOGITECH'), ['15', '16'])
        with self.assertRaises(ValueError):
            resolve_brand_filter(body, 'CORSAIR')

    def test_full_first_and_final_pages_validate_contiguous_rows(self):
        first = parse_search_page(page_html(1, 20, 21, 2, range(100, 120)), 1)
        final = parse_search_page(page_html(21, 21, 21, 2, [120]), 2)
        self.assertEqual(len(first['references']), 20)
        self.assertEqual(final['references'], ['120'])

    def test_single_page_supplier_total_typo_keeps_all_real_cards(self):
        result = parse_search_page(page_html(1, 19, 1, 1, range(100, 119)), 1)
        self.assertEqual(len(result['references']), 19)
        self.assertEqual(result['last'], 19)

    def test_supported_large_page_keeps_complete_brand_without_sort_boundary_duplicates(self):
        result = parse_search_page(page_html(1, 63, 1, 1, range(100, 163)), 1, page_size=100)
        self.assertEqual(len(result['references']), 63)
        final = parse_search_page(page_html(101, 101, 101, 2, [300]), 2, page_size=100)
        self.assertEqual(final['references'], ['300'])

    def test_truncated_repeated_wrong_page_and_ambiguous_rows_fail(self):
        cases = [(page_html(1, 20, 21, 2, range(100, 119)), 1),
                 (page_html(1, 2, 2, 1, [100, 100]), 1),
                 (page_html(1, 20, 21, 2, range(100, 120)), 2),
                 (page_html(1, 1, 1, 1, [100]).replace(b'</li>', b'<a href="/es/product/consul/101">Otro</a></li>'), 1)]
        for body, page in cases:
            with self.subTest(page=page), self.assertRaises(ValueError):
                parse_search_page(body, page)


if __name__ == '__main__':
    unittest.main()
