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
TLS = ssl.create_default_context()


class SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        destination = urlparse(new_url)
        if destination.scheme != 'https' or destination.hostname not in {
            'tienda.omega.com.do', 'omega.com.do', 'www.omega.com.do'
        }:
            raise URLError('Se rechazó una redirección fuera del sitio HTTPS de Omega')
        return super().redirect_request(request, response, code, message, headers, new_url)


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links, self.metadata, self.schemas = [], {}, []
        self.in_schema = False
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'a' and values.get('href'):
            self.links.append(values['href'])
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
            record.update(metadata=page.metadata, schemas=page.schemas,
                          links=page.links[:250])
            hints = ['wp-content', 'woocommerce', 'shopify', 'prestashop', 'magento', 'opencart']
            record['platform_hints'] = [hint for hint in hints if hint in text.lower()]
    print(json.dumps({k: v for k, v in record.items()
                      if k not in ('links', 'schemas', 'sample')}, ensure_ascii=False), flush=True)
    return record


def main():
    OUTPUT.mkdir(exist_ok=True)
    paths = ['', 'robots.txt', 'sitemap.xml', 'wp-json/',
             'wp-json/wc/store/v1/products?per_page=1',
             'wp-json/wc/v3/products?per_page=1']
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
        if re.search(r'/(?:item|product|producto|productos)/|\.html(?:\?|$)', parsed.path, re.I):
            if url not in candidates:
                candidates.append(url)
    for index, url in enumerate(candidates[:2], len(reports)):
        reports.append(get(url, index))
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
