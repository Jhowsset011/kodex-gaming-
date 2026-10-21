"""Read Nexcom's public WooCommerce Store API with complete pagination."""
from concurrent.futures import ThreadPoolExecutor
import json
import math
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

API = 'https://nexcomtienda.com.do/wp-json/wc/store/v1/products'
USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'


def read_page(page):
    url = API + '?' + urlencode({'per_page': 100, 'page': page})
    for attempt in range(3):
        try:
            request = Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
            with urlopen(request, timeout=35) as response:
                if urlsplit(response.url).hostname != 'nexcomtienda.com.do':
                    raise ValueError('Redirección inesperada de Nexcom')
                raw = response.read(10_000_001)
                if len(raw) > 10_000_000: raise ValueError('Respuesta Nexcom demasiado grande')
                items = json.loads(raw)
                total = int(response.headers['X-WP-Total'])
                pages = int(response.headers['X-WP-TotalPages'])
            if not isinstance(items, list) or not 0 < total <= 100_000 or pages != math.ceil(total / 100):
                raise ValueError('Paginación Nexcom inválida')
            expected = 100 if page < pages else total - 100 * (pages - 1)
            if len(items) != expected: raise ValueError('Página Nexcom incompleta')
            return items, total, pages
        except HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise ValueError(f'API Nexcom no disponible (HTTP {error.code}); se conserva el catálogo') from None
        except (URLError, TimeoutError):
            if attempt == 2: raise ValueError('Timeout consultando Nexcom; se conserva el catálogo') from None
        time.sleep(attempt + 1)


def index_sources(items):
    by_sku, ids = {}, set()
    for source in items:
        if not isinstance(source, dict) or type(source.get('id')) is not int or source['id'] in ids:
            raise ValueError('Nexcom devolvió IDs inválidos o repetidos')
        ids.add(source['id'])
        sku = str(source.get('sku') or '').strip()
        if not sku: continue
        if sku in by_sku: raise ValueError(f'SKU Nexcom ambiguo o repetido: {sku}')
        by_sku[sku] = source
    return by_sku


def fetch_catalog():
    items, total, pages = read_page(1)
    def fetch(page):
        # Two workers, each spaced by a second: at most two page requests/sec.
        time.sleep(1)
        rows, current_total, current_pages = read_page(page)
        if (current_total, current_pages) != (total, pages):
            raise ValueError('El catálogo Nexcom cambió durante la paginación; volver a consultar')
        return rows
    with ThreadPoolExecutor(max_workers=2) as pool:
        for page in pool.map(fetch, range(2, pages + 1)):
            items.extend(page)
    if len(items) != total: raise ValueError('Catálogo Nexcom incompleto')
    index_sources(items)
    return items
