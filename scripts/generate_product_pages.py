#!/usr/bin/env python3
"""Generate crawlable product pages from the published public catalog only."""
import argparse
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re
import shutil
import unicodedata
from urllib.parse import quote, urlencode, urljoin
import xml.etree.ElementTree as ET

from manufacturer_sources import validate_manufacturer_url
from catalog_markup import description_text

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://kodexgaming.com'
ARROW = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 19 19 5M5 5h14v14"/></svg>'
CART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 4h2l3 12h11l2-8H6M10 20h.01M18 20h.01"/></svg>'


def product_path(product):
    # Keep this algorithm in sync with productURL in js/kodex.js.
    name = unicodedata.normalize('NFD', product['name']).lower()
    name = ''.join(c for c in name if not unicodedata.combining(c))
    slug = re.sub(r'[^a-z0-9]+', '-', name).strip('-') or 'producto'
    if len(slug) > 200:
        slug = re.sub(r'-[^-]*$', '', slug[:200])
    reference = str(product['reference'])
    if not re.fullmatch(r'[1-9]\d{0,11}', reference):
        raise ValueError('Referencia inválida para la URL de producto')
    return f'/producto/{slug}-{reference}/'


def category_parts(product):
    return [str(product[key]) for key in ('category', 'subcategory', 'subsubcategory') if product.get(key)]


def money(price):
    return f'RD${Decimal(str(price)):,.2f}' if price is not None else 'Consultar precio'


def json_script(document):
    # A supplier string must never be able to close the JSON-LD script tag.
    return json.dumps(document, ensure_ascii=False, allow_nan=False).replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')


@lru_cache(maxsize=1)
def specification_icons():
    # Reuse the existing template's SVGs so static and legacy details look alike.
    source = (ROOT / 'js/producto.js').read_text(encoding='utf-8').split('function manufacturerLinks', 1)[0]
    default = re.search(r"let shape = '([^']+)';", source).group(1)
    rules = re.findall(r"if \(/([^/]+)/\.test\(key\)\) shape = '([^']+)';", source)
    return default, rules


def specification_icon(label):
    key = unicodedata.normalize('NFD', label).encode('ascii', 'ignore').decode().lower()
    default, rules = specification_icons()
    shape = next((svg for pattern, svg in rules if re.search(pattern, key)), default)
    return f'<svg class="spec-icon" viewBox="0 0 24 24" aria-hidden="true">{shape}</svg>'


def render_content(p):
    e = escape
    raw_description = str(p.get('description') or p.get('spec') or '').strip()
    description = description_text(raw_description)
    normalize = lambda text: ' '.join(text.split()).casefold()
    summary = description_text(p.get('spec', '')) or (description.splitlines()[0] if description else '')
    if len(summary) > 240: summary = summary[:240].rsplit(' ', 1)[0] + '…'
    paragraphs = ''.join(f'<p>{e(line)}</p>' for line in description.splitlines() if line.strip()) if normalize(description) not in (normalize(p['name']), normalize(summary)) else ''
    rows = [row for row in p.get('specifications', []) if not (normalize(row['label']) == 'información del producto' and normalize(row['value']) == normalize(description))]
    if rows:
        # Render specifications once, in Kodex's original grid with SVG icons.
        paragraphs = ''
    if p.get('brand') and not p.get('sourceContentConflict') and not any(row['label'].casefold() in ('marca', 'fabricante') for row in rows):
        rows.insert(0, {'label': 'Marca', 'value': p['brand']})
    specifications = ''.join(f'<div class="spec-row"><dt>{specification_icon(row["label"])}<span>{e(row["label"])}</span></dt><dd>{e(row["value"])}</dd></div>' for row in rows)
    features = ''.join(f'<li>{e(feature)}</li>' for feature in dict.fromkeys(p.get('features', [])) if normalize(feature) != normalize(description))
    sources = []
    for source in p.get('specificationSources', []):
        try:
            validate_manufacturer_url(source, p['brand'])
        except ValueError:
            continue
        sources.append(f'<a class="manufacturer-link" href="{e(source)}" target="_blank" rel="noopener noreferrer">Ficha del fabricante {ARROW}</a>')
    manufacturer_links = '<div class="manufacturer-links">' + ''.join(sources) + '</div>' if sources else ''
    note = f'<p class="specification-note">{e(p["specificationNote"])}</p>' if p.get('specificationNote') else ''
    categories = []
    for index, part in enumerate(category_parts(p)):
        params = {'categoria': p['category']}
        if index: params['subcategoria'] = p['subcategory']
        categories.append(f'<a href="/?{e(urlencode(params))}#catalogo">{e(part)}</a>')
    breadcrumb = ' <span aria-hidden="true">›</span> '.join(categories)
    text = f'Hola, me interesa {p["name"]} (REF {p["reference"]})'
    whatsapp = f'https://wa.me/18098796463?text={quote(text, safe="")}'
    available = p.get('stock') and not p.get('proximamente') and p.get('price') is not None and p['price'] > 0
    actions = f'<div class="product-actions detail-actions"><a class="order-product" data-order-product="{e(p["id"])}" href="{e(whatsapp)}" target="_blank" rel="noopener noreferrer">Hacer pedido {ARROW}</a><button class="add" data-add="{e(p["id"])}" aria-label="Añadir {e(p["name"])} al carrito" title="Añadir al carrito">{CART}<span>Añadir al carrito</span></button></div>' if available else f'<button class="order-product" disabled>No disponible</button><a class="text-link" href="{e(whatsapp)}" target="_blank" rel="noopener noreferrer">Consultar por WhatsApp</a>'
    if p.get('proximamente'): actions = ''
    old = f'<del>{money(p["old"])}</del>' if p.get('old') and p['price'] is not None and p['old'] > p['price'] else ''
    model = f' · Modelo: <span>{e(p["model"])}</span>' if p.get('model') else ''
    return f'''<div class="product-overview">
    <div class="product-photo"><img src="{e(p.get('image') or 'img/catalogo/sin-imagen.svg')}" alt="{e(p['name'])}" width="520" height="440" fetchpriority="high"></div>
    <div class="product-information">
      <a class="eyebrow" href="/?categoria={quote(p['category'])}#catalogo">{e(p['brand'])} · {e(p['category'])}</a>
      <nav class="product-category-path" aria-label="Categoría del producto">{breadcrumb}</nav>
      <h1>{e(p['name'])}</h1>
      <p class="product-reference">Referencia: <span>{e(p['reference'])}</span>{model}</p>
      <div class="product-description"><p>{e(summary)}</p></div>
      <a class="text-link specifications-link" href="{product_path(p)}#caracteristicas">Ver características principales <span aria-hidden="true">↓</span></a>
      <div class="page-pricing"><strong>{money(p['price'])}</strong>{old}</div>
      {actions}
      <p class="purchase-hint">{'Próximamente' if p.get('proximamente') else 'Pedidos y asesoría por WhatsApp.' if available else 'Consulta alternativas con nuestro equipo por WhatsApp.'}</p>
    </div>
  </div>
  <section class="specifications-section" id="caracteristicas" aria-labelledby="specifications-title">
    <div class="section-heading"><div><span class="eyebrow">CONOCE TU PRÓXIMO UPGRADE</span><h2 id="specifications-title">Descripción y características</h2></div></div>
    <div class="specifications-card">{'<div class="product-description product-description-full">' + paragraphs + '</div>' if paragraphs else ''}<dl class="specifications-list">{specifications}</dl>{'<div class="product-highlights"><h3>Lo más destacado</h3><ul class="product-features">' + features + '</ul></div>' if features else ''}{note}{manufacturer_links}</div>
  </section><a class="text-link" href="/#catalogo">Volver al catálogo</a>'''


def render_page(product, template):
    p, e = product, escape
    url = SITE + product_path(p)
    title = p['name'] + ' | KODEX GAMING'
    categories = ' › '.join(category_parts(p))
    description = f'{p["name"]} a {money(p["price"])} en KODEX GAMING, Santo Domingo. {categories}. Escríbenos por WhatsApp.'
    image = urljoin(SITE + '/', p.get('image') or 'img/catalogo/sin-imagen.svg')
    schema = {'@context': 'https://schema.org', '@type': 'Product', 'name': p['name'],
              'image': image, 'description': description_text(p.get('description') or p.get('spec') or p['name']),
              'sku': p['reference'], 'category': categories}
    if p['price'] is not None:
        schema['offers'] = {'@type': 'Offer', 'url': url, 'priceCurrency': 'DOP',
                            'price': p['price'],
                            'availability': 'https://schema.org/' + ('InStock' if p['stock'] else 'OutOfStock'),
                            'itemCondition': 'https://schema.org/NewCondition'}
    metadata = f'''<link rel="canonical" href="{e(url)}">
  <meta property="og:title" content="{e(title)}">
  <meta property="og:description" content="{e(description)}">
  <meta property="og:image" content="{e(image)}">
  <meta property="og:url" content="{e(url)}">
  <meta property="og:type" content="product">
  <script type="application/ld+json">{json_script(schema)}</script>'''
    page = re.sub(r'<title>.*?</title>', lambda _: f'<title>{e(title)}</title>', template, count=1)
    # Set the base before the parser encounters relative scripts/styles.
    page = page.replace('<head>', '<head>\n  <base href="/">', 1)
    page = re.sub(r'<meta name="description" content="[^"]*">', lambda _: f'<meta name="description" content="{e(description)}">', page, count=1)
    page = page.replace('</head>', metadata + '\n</head>', 1)
    page = page.replace('id="product-page"', f'id="product-page" data-product-id="{e(p["id"])}"', 1)
    page = page.replace('id="catalog-loading"', 'id="catalog-loading" hidden', 1)
    page = page.replace('<span id="product-breadcrumb">Producto</span>', f'<span id="product-breadcrumb">{e(p["name"])}</span>', 1)
    page = page.replace('<div id="product-view"></div>', f'<div id="product-view" data-prerendered="{e(p["id"])}">{render_content(p)}</div>', 1)
    return page


def generate(root=ROOT, lastmod=None):
    root = Path(root)
    path = root / 'js/productos-v2.json'
    if not path.exists(): path = root / 'js/productos.json'
    catalog = json.loads(path.read_text(encoding='utf-8'))
    products = catalog['products']
    if not products: raise ValueError('No se generan páginas con un catálogo vacío')
    lastmod = lastmod or catalog['updated']
    datetime.fromisoformat(lastmod.replace('Z', '+00:00'))
    template = (root / 'producto.html').read_text(encoding='utf-8')
    required = ('<div id="product-view"></div>', 'id="product-page"', '</head>')
    if not all(marker in template for marker in required):
        raise ValueError('Cambió la plantilla de producto; revisar el generador antes de publicar')
    # Render everything before changing files: malformed products never prune
    # pages from the previously valid catalog.
    rendered = {product_path(p): render_page(p, template) for p in products}
    if len(rendered) != len(products): raise ValueError('URL de producto duplicada')
    destination = root / 'producto'
    destination.mkdir(exist_ok=True)
    for url, page in rendered.items():
        folder = destination / url.split('/')[2]
        folder.mkdir(exist_ok=True)
        (folder / 'index.html').write_text(page, encoding='utf-8')
    expected = {url.split('/')[2] for url in rendered}
    for folder in destination.iterdir():
        if folder.name not in expected:
            if folder.is_dir(): shutil.rmtree(folder)
            else: folder.unlink()
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    sitemap = ET.Element(f'{{{namespace}}}urlset')
    for path in ['/', *rendered]:
        entry = ET.SubElement(sitemap, f'{{{namespace}}}url')
        ET.SubElement(entry, f'{{{namespace}}}loc').text = SITE + path
        ET.SubElement(entry, f'{{{namespace}}}lastmod').text = lastmod
    ET.indent(sitemap)
    ET.ElementTree(sitemap).write(root / 'sitemap.xml', encoding='utf-8', xml_declaration=True)
    (root / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n', encoding='utf-8')
    return len(rendered)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lastmod', help='Fecha ISO de esta sincronización; por defecto, la del catálogo')
    args = parser.parse_args()
    print(f'SEO: {generate(lastmod=args.lastmod)} páginas de producto; sitemap.xml y robots.txt regenerados.')
