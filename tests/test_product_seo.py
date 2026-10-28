"""Ensure generated product pages are useful without JavaScript and stay current."""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from generate_product_pages import generate, product_path, render_page


def product(reference='109613'):
    return {'id': reference, 'reference': reference, 'name': 'Monitor AOC 27G50F2',
            'category': 'Monitores', 'subcategory': 'De escritorio', 'brand': 'AOC',
            'image': 'img/catalogo/sin-imagen.svg', 'price': 9900, 'stock': True,
            'description': 'Pantalla para jugar con claridad.',
            'specifications': [{'label': 'Resolución', 'value': '1920 × 1080'}],
            'features': ['Conexión HDMI']}


class ProductSEOTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'js').mkdir()
        self.template = (ROOT / 'producto.html').read_text()
        (self.root / 'producto.html').write_text(self.template)
        self.products = [product(), product('109614')]
        self.write_catalog()

    def write_catalog(self):
        (self.root / 'js/productos-v2.json').write_text(json.dumps({
            'products': self.products, 'updated': '2026-10-20T14:51:22+00:00'}))

    def test_complete_source_without_running_javascript(self):
        p = self.products[0]
        generate(self.root)
        page = (self.root / product_path(p).strip('/') / 'index.html').read_text()
        self.assertIn('<h1>Monitor AOC 27G50F2</h1>', page)
        self.assertIn('<title>Monitor AOC 27G50F2 | KODEX GAMING</title>', page)
        self.assertIn('a RD$9,900.00 en KODEX GAMING, Santo Domingo.', page)
        self.assertIn('1920 × 1080', page)
        self.assertIn('Pantalla para jugar con claridad.', page)
        self.assertIn('Monitores</a> <span aria-hidden="true">›</span>', page)
        self.assertIn('href="/#catalogo">Volver al catálogo', page)
        self.assertIn('https://wa.me/18098796463?text=Hola%2C%20me%20interesa%20Monitor%20AOC%2027G50F2%20%28REF%20109613%29', page)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
        self.assertEqual(schema['sku'], '109613')
        self.assertEqual(schema['offers']['price'], 9900)
        self.assertIsInstance(schema['offers']['price'], (int, float))
        self.assertEqual(schema['offers']['availability'], 'https://schema.org/InStock')
        self.assertIn('https://gaming.kodex.com.do/img/catalogo/sin-imagen.svg', page)
        self.assertIn('<base href="/">', page)
        self.assertLess(page.index('<base href="/">'), page.index('src="js/'))
        self.assertIn('href="/producto/monitor-aoc-27g50f2-109613/#caracteristicas"', page)

    def test_removal_and_rename_delete_obsolete_pages_and_sitemap_urls(self):
        generate(self.root)
        removed = self.root / product_path(self.products[1]).strip('/')
        old_name = self.root / product_path(self.products[0]).strip('/')
        self.products = [dict(self.products[0], name='Monitor AOC nuevo')]
        self.write_catalog()
        generate(self.root, '2026-10-21T10:00:00Z')
        self.assertFalse(removed.exists())
        self.assertFalse(old_name.exists())
        ns = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
        tree = ET.parse(self.root / 'producto-sitemap.xml')
        self.assertEqual([e.text for e in tree.findall('.//s:loc', ns)],
                         ['https://gaming.kodex.com.do' + product_path(self.products[0])])
        self.assertEqual(tree.findall('.//s:lastmod', ns), [])
        self.assertEqual((self.root / 'robots.txt').read_text(),
                         'User-agent: *\nAllow: /\nSitemap: https://gaming.kodex.com.do/sitemap.xml\n')

    def test_unavailable_product_is_not_advertised_in_stock(self):
        page = render_page(dict(product(), stock=False), self.template)
        self.assertIn('https://schema.org/OutOfStock', page)
        self.assertNotIn('data-add=', page)
        self.assertIn('Consultar por WhatsApp', page)

    def test_stock_quantity_is_visible_in_static_source_and_sold_out_fallback_is_honest(self):
        page=render_page(dict(product(),stockQuantity=62,stockText='62 disponibles'),self.template)
        self.assertIn('<p class="product-stock"><strong>Stock:</strong> <span>62 disponibles</span></p>',page)
        soldout=render_page(dict(product(),stock=False),self.template)
        self.assertIn('<span>Agotado</span>',soldout)
        unknown=render_page(product(),self.template)
        self.assertIn('<span>Disponible</span>',unknown)

    def test_coming_soon_has_visible_status_without_product_order_or_cart_buttons(self):
        page = render_page(dict(product(), stock=False, proximamente=True,
                                description='<p data-start="3">Panel <strong>IPS</strong></p>'), self.template)
        self.assertIn('Próximamente', page)
        self.assertNotIn('data-order-product=', page)
        self.assertNotIn('data-add=', page)
        self.assertNotIn('Consultar por WhatsApp', page)
        self.assertIn('<dl class="specifications-list">', page)
        self.assertNotIn('data-start', page)

    def test_nexcom_description_is_presented_in_original_kodex_grid_without_duplicate_emoji_list(self):
        p = dict(product(), description='<p>🖥️ <strong>Tamaño de pantalla:</strong> 27 pulgadas</p>',
                 specifications=[{'label':'Tamaño de pantalla','value':'27 pulgadas'}])
        page = render_page(p,self.template)
        details = page.split('<section class="specifications-section"',1)[1].split('</section>',1)[0]
        self.assertIn('specifications-list',details)
        self.assertIn('spec-icon',details)
        self.assertIn('27 pulgadas',details)
        self.assertNotIn('🖥',details)
        self.assertNotIn('product-description-full',details)

    def test_supplier_markup_cannot_inject_html_or_close_json_ld(self):
        name = '</script><img src=x onerror=alert(1)> & "Monitor"'
        page = render_page(dict(product(), name=name, description=name), self.template)
        self.assertNotIn('<img src=x', page)
        schema = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', page).group(1))
        self.assertEqual(schema['name'], name)

    def test_slug_matches_frontend_for_entire_catalog_and_long_names(self):
        products = json.loads((ROOT / 'js/productos-v2.json').read_text())['products']
        products += [dict(product(), name='ÁúDÍO — Ñ / & " RGB'), dict(product(), name='Monitor ' * 90)]
        source = (ROOT / 'js/kodex.js').read_text()
        function = source[source.index('const productURL ='):source.index('let filter =')]
        code = function + '\nlet data="";process.stdin.on("data",c=>data+=c);process.stdin.on("end",()=>process.stdout.write(JSON.stringify(JSON.parse(data).map(productURL))));'
        result = subprocess.run(['node', '-e', code], input=json.dumps(products), capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [product_path(p) for p in products])
        self.assertTrue(all(len(product_path(p).split('/')[2]) <= 255 for p in products))

    def test_duplicate_urls_do_not_prune_valid_existing_pages(self):
        generate(self.root)
        path = self.root / product_path(self.products[0]).strip('/') / 'index.html'
        before = path.read_bytes()
        self.products = [product(), product()]
        self.write_catalog()
        with self.assertRaises(ValueError): generate(self.root)
        self.assertEqual(path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
