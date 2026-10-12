#!/usr/bin/env python3
"""Audit public Omega brand searches without publishing or reading sale rules."""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlencode

from omega_catalog import _brand
from omega_images import download_source_images
from omega_public import (BASE_URL, _Document, _RateLimiter, _normalized,
                          fetch_selected_references, make_tls_context, read_public_url)

BRANDS = ('MSI', 'AOC', 'ANTEC', 'SAMSUNG')
BRAND_FILTERS = {'MSI': '7', 'AOC': '143', 'ANTEC': '822', 'SAMSUNG': '20'}
ROOT = Path(__file__).resolve().parents[1]


def parse_search_page(body, page, page_size=20):
    """Validate the actual product rows and contiguous pagination, not menus."""
    tree = _Document(body.decode('utf-8-sig')).root
    lists = tree.all(lambda node: node.attrs.get('id') == 'product-list')
    if len(lists) != 1:
        raise ValueError('Omega no proporcionó un resultado de búsqueda completo')
    listing = lists[0]
    report = re.search(r'mostrando\s+(\d+)\s+a\s+(\d+)\s+de\s+(\d+)\s*\((\d+)\s+paginas?\)',
                       _normalized(listing.text()))
    if not report:
        raise ValueError('Omega no confirma la paginación de la marca')
    first, last, total, pages = map(int, report.groups())
    cards = listing.all(lambda node: node.tag == 'li' and node.has_class('product'))
    if (page_size not in (20, 50, 100) or not 1 <= pages <= 50 or not 1 <= page <= pages
            or first != (page - 1) * page_size + 1
            or last < first or last - first + 1 != len(cards) or len(cards) > page_size
            or (page < pages and len(cards) != page_size)):
        raise ValueError('Omega devolvió una página incompleta o fuera de orden')
    references = []
    for card in cards:
        values = set()
        for link in card.all(lambda node: node.tag == 'a'):
            match = re.fullmatch(r'/es/product/consul/([1-9]\d{0,11})/?', link.attrs.get('href', ''))
            if match:
                values.add(match.group(1))
        if len(values) != 1:
            raise ValueError('Resultado de marca con referencia ambigua')
        references.append(values.pop())
    if len(set(references)) != len(references):
        raise ValueError('La búsqueda repite referencias en la misma página')
    # The supplier prints "de 1" on single-page results even when 19 cards
    # exist. Row indices and the final page establish the complete row count.
    if total < last and not (pages == 1 and total == 1):
        raise ValueError('El total de la búsqueda contradice sus resultados')
    return {'references': references, 'pages': pages, 'last': last, 'reportedTotal': total}


def discover_brand(brand, context, output, limiter):
    references = []
    pages = None
    page = 1
    reported_total = None
    while pages is None or page <= pages:
        url = BASE_URL + '/es/product/search?' + urlencode({
            'Terms': brand, 'page': page, 'type': 'grid', 'sort': 'NAS',
            'show': '100', 'brands': BRAND_FILTERS[brand]})
        body = read_public_url(url, context=context, limiter=limiter)
        (output / f'{brand}-{page}.html').write_bytes(body)
        parsed = parse_search_page(body, page, page_size=100)
        if pages is not None and (parsed['pages'] != pages or parsed['reportedTotal'] != reported_total):
            raise ValueError('La búsqueda cambió durante la auditoría; requiere una captura completa nueva')
        pages, reported_total = parsed['pages'], parsed['reportedTotal']
        references.extend(parsed['references'])
        print('Marca:', brand, 'página', page, 'de', pages, flush=True)
        page += 1
    if len(set(references)) != len(references) or len(references) != parsed['last']:
        raise ValueError('Las páginas de la marca no cubren una selección única completa')
    return references


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    context = make_tls_context(args.output / 'tls')
    limiter = _RateLimiter()
    discovered = {brand: discover_brand(brand, context, args.output, limiter) for brand in BRANDS}
    catalog = json.loads((ROOT / 'js/productos-v2.json').read_text(encoding='utf-8'))
    references = [product['reference'] for product in catalog['products']]
    references.extend(reference for results in discovered.values() for reference in results)
    references = list(dict.fromkeys(reference for reference in references if reference != '62635'))
    sources, missing = fetch_selected_references(references, context=context, cache_dir=args.output, workers=2)
    targets = {reference: source for reference, source in sources.items() if _brand(source).upper() in BRANDS}
    snapshot = {'sources': sources, 'missingReferences': missing, 'selectedCount': len(references)}
    (args.output / 'sources.json').write_text(json.dumps(
        snapshot, ensure_ascii=False, indent=2,
        default=lambda value: str(value) if isinstance(value, Decimal) else None) + '\n', encoding='utf-8')
    report = {'brandSearchReferences': discovered,
              'verifiedBrandReferences': {brand: [ref for ref, source in targets.items()
                                                  if _brand(source).upper() == brand] for brand in BRANDS}}
    (args.output / 'brands.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    images = args.output / 'images'
    images.mkdir(exist_ok=True)
    current_images = ROOT / 'img/catalogo'
    manifest = json.loads((current_images / 'manifest.json').read_text(encoding='utf-8'))
    existing = {source['imageSource']: manifest[source['imageSource']]
                for source in sources.values() if source.get('imageSource') in manifest}
    for filename in set(existing.values()) - {None}:
        if not re.fullmatch(r'[0-9a-f]{20}\.(?:png|jpg|webp|gif)', filename):
            raise ValueError('Nombre de fotografía inválido en el manifiesto')
        shutil.copy2(current_images / filename, images / filename)
    (images / 'manifest.json').write_text(json.dumps(existing), encoding='utf-8')
    download_source_images(sources, images, context=context)
    print('Auditoría completa:', len(sources), 'fichas públicas;', len(targets), 'de las cuatro marcas.', flush=True)


if __name__ == '__main__':
    main()
