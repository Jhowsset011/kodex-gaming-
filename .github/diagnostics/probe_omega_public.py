"""Read-only probe of the public Omega store. TLS verification stays enabled."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

BASE = 'https://tienda.omega.com.do/'
OUTPUT = Path('omega-public-probe')
MAX_BYTES = 2_000_000
TLS = ssl.create_default_context(cafile=os.environ.get('OMEGA_CA_BUNDLE'))
if hasattr(ssl, 'VERIFY_X509_PARTIAL_CHAIN'):
    TLS.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN


class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        destination = urlparse(new_url)
        if destination.scheme != 'https' or destination.hostname not in {
            'tienda.omega.com.do', 'omega.com.do', 'www.omega.com.do', 'sis.omega.com.do'
        }:
            raise URLError('Se rechazó una redirección fuera del sitio HTTPS de Omega')
        return super().redirect_request(request, response, code, message, headers, new_url)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.metadata, self.schemas, self.scripts = [], {}, [], []
        self.in_schema = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and values.get('href'):
            self.links.append(values['href'])
        if tag == 'script' and values.get('src'):
            self.scripts.append(values['src'])
        if tag == 'meta' and values.get('content'):
            key = values.get('property') or values.get('name') or values.get('itemprop')
            if key:
                self.metadata[key] = values['content']
        if tag == 'script' and values.get('type', '').lower() == 'application/ld+json':
            self.in_schema, self.buffer = True, []

    def handle_data(self, data):
        if self.in_schema:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.in_schema:
            try:
                self.schemas.append(json.loads(''.join(self.buffer)))
            except ValueError:
                pass
            self.in_schema = False


class Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def all(self, predicate):
        result = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, Node):
                result.extend(child.all(predicate))
        return result

    def text(self):
        if self.tag in ('script', 'style'):
            return ''
        return re.sub(r'\s+', ' ', ' '.join(child.text() if isinstance(child, Node) else child
                                           for child in self.children)).strip()

    def has_class(self, value):
        return value in self.attrs.get('class', '').split()


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        child = Node(tag, attrs)
        self.stack[-1].children.append(child)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(child)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def extract_product(report):
    match = re.search(r'/product/consul/(\d+)', report['url'])
    if report.get('status') != 200 or not match:
        return None
    reference = match.group(1)
    tree = Document((OUTPUT / report['file']).read_text(encoding='utf-8')).root
    product_buttons = tree.all(lambda node: node.attrs.get('data-product') == reference)
    summaries = tree.all(lambda node: node.has_class('entry-summary'))
    assert product_buttons and summaries, f'La respuesta no confirma el producto {reference}'
    summary = summaries[0]
    names = summary.all(lambda node: node.tag == 'h3')
    amounts = summary.all(lambda node: node.has_class('amount') and not node.has_class('del'))
    currencies = tree.all(lambda node: node.tag == 'option' and 'selected' in node.attrs
                          and 'DOP' in node.text())
    assert names and len(amounts) == 1 and currencies, f'Campos de producto incompletos: {reference}'
    price_text = amounts[0].text()
    amount = re.fullmatch(r'\$\s*([\d,]+\.\d{2})', price_text)
    assert amount, f'Formato de precio no reconocido: {reference}'
    details = tree.all(lambda node: node.attrs.get('id') == 'productDescription')
    parts = summary.all(lambda node: node.tag == 'p' and 'Número de parte' in node.text())
    inventory = []
    for box in tree.all(lambda node: node.has_class('product-col')):
        for row in box.all(lambda node: node.tag == 'tr'):
            cells = row.all(lambda node: node.tag == 'td')
            if len(cells) == 2 and cells[1].text().isdigit():
                inventory.append({'branch': cells[0].text(), 'quantity': int(cells[1].text())})
    return {'reference': reference, 'name': names[0].text(), 'currency': 'DOP',
            'price': amount.group(1).replace(',', ''),
            'part_number': parts[0].text().split(':', 1)[-1].strip() if parts else '',
            'description': details[0].text() if details else '',
            'image': report.get('metadata', {}).get('og:image', ''),
            'inventory': inventory, 'source_url': report['url']}


def check_image(product, index):
    url = product['image']
    parsed = urlparse(url)
    assert parsed.scheme == 'https' and parsed.hostname == 'sis.omega.com.do'
    assert parsed.path.startswith('/ProductImages/')
    opener = build_opener(HTTPSHandler(context=TLS), SecureRedirect())
    with opener.open(Request(url, headers={'User-Agent': 'KodexGaming-PublicCatalogProbe/1.0'}), timeout=20) as response:
        body = response.read(5_000_001)
        assert response.status == 200 and response.headers.get('Content-Type', '').startswith('image/')
    assert len(body) <= 5_000_000
    extension = Path(parsed.path).suffix.lower()
    if extension == '.png':
        assert body.startswith(b'\x89PNG\r\n\x1a\n')
    elif extension in ('.jpg', '.jpeg'):
        assert body.startswith(b'\xff\xd8\xff')
    else:
        raise ValueError('Formato de imagen no previsto')
    filename = f'sample-image-{index}{extension}'
    (OUTPUT / filename).write_bytes(body)
    return {'reference': product['reference'], 'url': url, 'bytes': len(body), 'file': filename}


def get(url, index):
    record = {'url': url}
    body = b''
    try:
        request = Request(url, headers={
            'User-Agent': 'KodexGaming-PublicCatalogProbe/1.0',
            'Accept': 'text/html,application/json;q=0.9,*/*;q=0.8',
        })
        opener = build_opener(HTTPSHandler(context=TLS), SecureRedirect())
        with opener.open(request, timeout=20) as response:
            record.update(status=response.status, final_url=response.url,
                          content_type=response.headers.get('Content-Type', ''))
            body = response.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError('Respuesta supera el límite de 2 MB')
    except HTTPError as error:
        record.update(status=error.code, error=str(error))
        body = error.read(3000)
    except (URLError, ValueError, TimeoutError, OSError) as error:
        record['error'] = str(error)
    text = body.decode('utf-8', errors='replace')
    if body:
        filename = f'{index:02d}-response.txt'
        (OUTPUT / filename).write_text(text, encoding='utf-8')
        record['file'] = filename
    record['bytes'] = len(body)
    if record.get('status') == 200:
        if 'json' in record.get('content_type', ''):
            try:
                value = json.loads(text)
                record['json_type'] = type(value).__name__
                record['json_keys'] = list(value)[:30] if isinstance(value, dict) else None
                if isinstance(value, list):
                    record['json_count'] = len(value)
                    record['sample'] = value[0] if value else None
            except ValueError:
                record['json_error'] = 'Respuesta JSON inválida'
        elif 'html' in record.get('content_type', ''):
            page = Page()
            page.feed(text)
            record.update(metadata=page.metadata, schemas=page.schemas, scripts=page.scripts,
                          links=page.links[:250])
            hints = ['wp-content', 'woocommerce', 'shopify', 'prestashop', 'magento', 'opencart']
            record['platform_hints'] = [hint for hint in hints if hint in text.lower()]
    print(json.dumps({k: v for k, v in record.items()
                      if k not in ('links', 'schemas', 'sample', 'scripts')}, ensure_ascii=False), flush=True)
    return record


def main():
    OUTPUT.mkdir(exist_ok=True)
    paths = ['', 'robots.txt', 'es/product/consul/111698', 'es/product/consul/110069',
             'es/product/consul/109640', 'es/product/consul/106019']
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(lambda pair: get(urljoin(BASE, pair[1]), pair[0]), enumerate(paths)))
    home = reports[0]
    candidates = []
    for href in home.get('links', []):
        url = urljoin(BASE, href)
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != urlparse(BASE).hostname:
            continue
        if re.search(r'cart|checkout|logout|wishlist|add-to|remove|account|login', url, re.I):
            continue
        if re.search(r'/(?:item|products?|productos?)/|(?:product|producto)details?|/detail/|\.html(?:\?|$)', parsed.path, re.I):
            if url not in candidates:
                candidates.append(url)
    samples = [product for report in reports if (product := extract_product(report))]
    assert len(samples) == 4, 'No se pudieron validar las cuatro muestras del catálogo de Kodex'
    images = [check_image(product, index) for index, product in enumerate(samples[:2])]
    (OUTPUT / 'samples.json').write_text(json.dumps({'products': samples, 'images': images}, ensure_ascii=False, indent=2), encoding='utf-8')
    for sample in samples:
        print('Producto público validado:', json.dumps(sample, ensure_ascii=False), flush=True)
    (OUTPUT / 'report.json').write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write('## Lectura pública de Omega con validación TLS\n\n')
            for report in reports:
                result = report.get('status', report.get('error', 'sin respuesta'))
                stream.write(f"- {report['url']}: {result}\n")
            stream.write('\nNo se modificó el catálogo de Kodex ni se inició sesión en Omega.\n')
    if home.get('status') != 200:
        raise SystemExit('No se pudo obtener la página pública de Omega; consultar report.json.')


if __name__ == '__main__':
    main()
