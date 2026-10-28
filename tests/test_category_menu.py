"""Every real category menu item navigates to its generated page."""
from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from generate_product_pages import category_groups, category_path, render_category


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        if tag == 'a':
            self.links.append(dict(attributes).get('href'))


class CategoryMenuTests(unittest.TestCase):
    def setUp(self):
        self.products = json.loads((ROOT / 'js/productos-v2.json').read_text())['products']
        self.groups = category_groups(self.products)

    def test_sidebar_has_exactly_one_normal_link_for_every_generated_category(self):
        source = (ROOT / 'js/kodex.js').read_text()
        url = source[source.index('const categoryURL ='):source.index('function linkCategoryPages')]
        helpers = source[source.index('function productInCategory'):source.index('function renderFilterUI')]
        code = r'''
const products = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let filter = 'Todos', subcategory = '';
const hasPrice = p => Number.isFinite(p.price) && p.price > 0;
const document = {activeElement:null};
const box = {innerHTML:'', contains:()=>false, querySelectorAll:()=>[]};
const $ = () => box;
'''
        code += url + helpers + '\nrenderCategoryUI();process.stdout.write(box.innerHTML);'
        result = subprocess.run(['node', '-e', code], input=json.dumps(self.products), capture_output=True, text=True, check=True)
        paths = Links(result.stdout).links
        self.assertCountEqual(paths, [category_path(parts) for parts in self.groups])
        self.assertEqual(len(paths), len(set(paths)))
        self.assertIn('/categoria/perifericos-mouse/', paths)
        self.assertIn('/categoria/monitores-de-escritorio/', paths)
        self.assertIn('/categoria/componentes-gabinetes-case/', paths)
        self.assertNotIn('data-category="', result.stdout)

    def test_top_navigation_shortcuts_and_footer_use_normal_category_links(self):
        for name in ['index.html', 'producto.html']:
            html = (ROOT / name).read_text()
            for slug in ['componentes', 'perifericos', 'monitores']:
                self.assertIn('/categoria/' + slug + '/', Links(html).links)
            self.assertNotIn('data-category="Monitores"', html)
            self.assertNotIn('data-category="Periféricos"', html)
            self.assertNotIn('data-category="Componentes"', html)

    def test_legacy_product_links_navigate_to_categories_without_touching_external_links(self):
        source = (ROOT / 'js/kodex.js').read_text()
        code = source[source.index('const categoryURL ='):source.index('let filter =')]
        legacy = '/?categoria=Perif%C3%A9ricos&subcategoria=Mouse#catalogo'
        external = 'https://example.com/?categoria=Monitores'
        inputs = [legacy, '/index.html?categoria=Monitores#catalogo', external, '/?categoria=ofertas#catalogo', 'http://[']
        setup = "const products = JSON.parse(require('fs').readFileSync(0, 'utf8'));\n"
        setup += 'const links = ' + json.dumps([{'href': href} for href in inputs]) + ';\n'
        setup += "const document={querySelectorAll:()=>links};const location={href:'https://gaming.kodex.com.do/',origin:'https://gaming.kodex.com.do'};\n"
        result = subprocess.run(['node', '-e', setup + code + '\nlinkCategoryPages();process.stdout.write(JSON.stringify(links.map(a=>a.href)));'], input=json.dumps(self.products), capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), ['/categoria/perifericos-mouse/', '/categoria/monitores/', external, inputs[3], inputs[4]])

    def test_every_category_breadcrumb_level_is_a_real_link(self):
        template = (ROOT / 'producto.html').read_text()
        for parts, items in self.groups.items():
            html = render_category(parts, items, self.groups, template)
            breadcrumb = html.split('aria-label="Ubicación">', 1)[1].split('</nav>', 1)[0]
            self.assertEqual(Links(breadcrumb).links,
                             ['/'] + [category_path(parts[:depth]) for depth in range(1, len(parts) + 1)])
            self.assertIn('aria-current="page"', breadcrumb)


if __name__ == '__main__':
    unittest.main()
