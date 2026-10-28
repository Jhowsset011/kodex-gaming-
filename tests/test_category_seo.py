"""Categories remain directly shareable and follow the unchanged catalog."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from generate_product_pages import SITE, category_path, generate, product_path
from test_product_seo import product


class CategorySEOTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'js').mkdir()
        (self.root / 'producto.html').write_text((ROOT / 'producto.html').read_text())
        self.mouse = dict(product('111'), category='Periféricos', subcategory='Mouse', name='Mouse & teclado', price=1234.50)
        self.items = [self.mouse, product('222')]

    def write(self):
        self.catalog = self.root / 'js/productos-v2.json'
        self.catalog.write_text(json.dumps({'products': self.items, 'updated': '2026-10-20T14:51:22+00:00'}))
        return self.catalog.read_bytes()

    def locs(self, name):
        return [node.text for node in ET.parse(self.root / name).findall('.//{*}loc')]

    def test_static_category_contains_only_its_products_without_mutating_catalog(self):
        original = self.write()
        generate(self.root)
        path = category_path(('Periféricos', 'Mouse'))
        page = (self.root / path.strip('/') / 'index.html').read_text()
        self.assertIn('<h1>Mouse</h1>', page)
        self.assertIn('Mouse &amp; teclado', page)
        self.assertIn('RD$1,234.50', page)
        self.assertIn('src="img/catalogo/sin-imagen.svg"', page)
        self.assertIn('href="' + product_path(self.mouse) + '"', page)
        self.assertNotIn('Monitor AOC', page)
        self.assertNotIn('js/producto.js', page)
        self.assertIn('<form action="/" class="search"', page)
        self.assertIn('name="buscar"', page)
        self.assertIn(f'rel="canonical" href="{SITE}{path}"', page)
        self.assertIn('<base href="/">', page)
        self.assertEqual(original, self.catalog.read_bytes())

    def test_split_sitemaps_have_only_new_urls_and_no_dates(self):
        self.write()
        generate(self.root)
        index = ET.parse(self.root / 'sitemap.xml').getroot()
        self.assertTrue(index.tag.endswith('sitemapindex'))
        self.assertEqual(self.locs('sitemap.xml'), [SITE + '/' + name for name in
                         ['producto-sitemap.xml', 'categoria-sitemap.xml', 'pagina-sitemap.xml']])
        self.assertEqual(self.locs('producto-sitemap.xml'), [SITE + product_path(p) for p in self.items])
        self.assertEqual(self.locs('pagina-sitemap.xml'), [SITE + '/'])
        self.assertIn(SITE + '/categoria/perifericos-mouse/', self.locs('categoria-sitemap.xml'))
        for name in ['sitemap.xml', 'producto-sitemap.xml', 'categoria-sitemap.xml', 'pagina-sitemap.xml']:
            root = ET.parse(self.root / name).getroot()
            self.assertTrue(all(child.tag.endswith('loc') for entry in root for child in entry))
            self.assertTrue(all(url.startswith(SITE + '/') for url in self.locs(name)))

    def test_next_sync_adds_products_and_prunes_obsolete_categories(self):
        self.write()
        generate(self.root)
        self.items.append(dict(self.mouse, id='333', reference='333', name='Mouse nuevo'))
        self.write()
        generate(self.root)
        page = self.root / 'categoria/perifericos-mouse/index.html'
        self.assertIn('Mouse nuevo', page.read_text())
        self.items = [product('222')]
        self.write()
        generate(self.root)
        self.assertFalse(page.exists())
        self.assertFalse((self.root / 'categoria/perifericos').exists())
        self.assertNotIn(SITE + '/categoria/perifericos-mouse/', self.locs('categoria-sitemap.xml'))

    def test_repeated_subcategory_names_have_distinct_stable_routes(self):
        self.items = [dict(product('111'), category='Laptops', subcategory='Portátiles'),
                      dict(product('222'), category='Monitores', subcategory='Portátiles')]
        self.write()
        generate(self.root)
        for parent in ['laptops', 'monitores']:
            self.assertTrue((self.root / f'categoria/{parent}-portatiles/index.html').is_file())

    def test_category_markup_is_escaped_and_collisions_fail_before_writing(self):
        self.items = [dict(self.mouse, category='Periféricos <img src=x>', subcategory='Mouse " RGB')]
        self.write()
        generate(self.root)
        key = ('Periféricos <img src=x>', 'Mouse " RGB')
        target = self.root / category_path(key).strip('/') / 'index.html'
        page = target.read_text()
        self.assertNotIn('<img src=x>', page)
        self.assertIn('&lt;img src=x&gt;', page)
        before = target.read_bytes()
        self.items.append(dict(self.mouse, category='Perifericos img src x', id='444', reference='444'))
        self.write()
        with self.assertRaisesRegex(ValueError, 'URL de categoría duplicada'):
            generate(self.root)
        self.assertEqual(before, target.read_bytes())


if __name__ == '__main__':
    unittest.main()
