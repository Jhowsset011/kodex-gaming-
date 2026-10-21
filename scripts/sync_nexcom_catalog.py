#!/usr/bin/env python3
"""Single-source Nexcom sync; publish only after complete validation and guards."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from catalog_markup import clean_description, description_text
from costos_estimados import cost_document, load_factors
from nexcom_feed import fetch_catalog, index_sources, USER_AGENT
from omega_catalog import PUBLIC_PRODUCT_FIELDS
from sync_nexcom import classify, enrich, image_extension, normalized, validate

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'62635'}  # Explicitly removed by the owner; never auto-import again.


class PriceGuardError(ValueError):
    pass


def read_manual(path):
    values = json.loads(Path(path).read_text(encoding='utf-8'))
    if (not isinstance(values, list) or any(not isinstance(v, str) or not re.fullmatch(r'[1-9]\d{0,11}', v) for v in values)
            or len(values) != len(set(values)) or EXCLUDED.intersection(values)):
        raise ValueError('Lista de altas manuales inválida o contiene un producto excluido')
    return set(values)


def read_seen(path):
    if not Path(path).exists(): return set()
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    values = document.get('skus')
    if (set(document) != {'version', 'skus'} or document['version'] != 1
            or not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values)
            or len(values) != len(set(values))):
        raise ValueError('Registro de SKUs vistos inválido')
    return set(values)


def sale_price(source):
    prices = source.get('prices') or {}
    # Nexcom's current Woo configuration reports USD but renders RD$ in BOTH
    # symbol and prefix. Accept only that exact observed presentation mismatch;
    # never treat a real US$ amount as DOP or apply a currency conversion.
    dop_display = prices.get('currency_symbol') == 'RD$' and prices.get('currency_prefix') == 'RD$'
    currency_ok = prices.get('currency_code') == 'DOP' or (prices.get('currency_code') == 'USD' and dop_display)
    if not currency_ok or type(prices.get('currency_minor_unit')) is not int or prices['currency_minor_unit'] != 2:
        raise ValueError(f'Moneda o unidad inválida para SKU {source.get("sku")}')
    try:
        amount = Decimal(str(prices.get('price'))) / 100
    except InvalidOperation:
        raise ValueError(f'Precio inválido para SKU {source.get("sku")}') from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f'Precio cero, nulo o negativo para SKU {source.get("sku")}')
    return float(amount)


def source_stock(source):
    if type(source.get('is_in_stock')) is not bool:
        raise ValueError(f'Stock inválido para SKU {source.get("sku")}')
    availability = source.get('stock_availability')
    if not isinstance(availability, dict) or not isinstance(availability.get('class'), str):
        raise ValueError(f'Disponibilidad incompleta para SKU {source.get("sku")}')
    if availability['class'] in ('out-of-stock', 'available-on-backorder') or source.get('is_on_backorder') is True: return False
    return source['is_in_stock']


def interested(source, brands):
    brand_names = {normalized(b.get('name', '')) for b in source.get('brands', [])}
    candidate = classify({'name': description_text(source.get('name')), 'category': 'Periféricos'})
    brand_names.add(normalized(candidate['brand']))
    known_brand = bool(brands.intersection(brand_names))
    categories = {normalized(c.get('name', '')).replace('&', 'y') for c in source.get('categories', [])}
    for category in source.get('categories', []):
        link = urlsplit(category.get('link', ''))
        if link.hostname == 'nexcomtienda.com.do':
            categories.update(segment.replace('-', ' ') for segment in link.path.split('/') if segment)
    if any('seguridad' in c or 'redes' in c for c in categories) and not known_brand:
        return False
    departments = {'zona gamer', 'computadoras', 'componentes', 'audio y video', 'accesorios'}
    return known_brand or bool(categories.intersection(departments))


def excluded(source):
    text = description_text(' '.join(str(source.get(k) or '') for k in ('name', 'short_description', 'description')))
    return str(source['sku']) in EXCLUDED or bool(re.search(r'\brefurbish(?:ed)?\b', text, re.I))


def validate_public(products):
    validate(products)
    allowed = set(PUBLIC_PRODUCT_FIELDS) | {'proximamente'}
    for p in products:
        if set(p) - allowed: raise ValueError('Campo no público en catálogo Nexcom')
        if not isinstance(p.get('reference'), str) or not re.fullmatch(r'[1-9]\d{0,11}', p['reference']):
            raise ValueError('Referencia pública inválida')
        if not isinstance(p.get('subcategory'), str) or not p['subcategory'].strip():
            raise ValueError('Subcategoría pública vacía')
        if p.get('proximamente') is not None and (p['proximamente'] is not True or p['stock']):
            raise ValueError('Próximamente requiere stock falso')
        if not isinstance(p.get('image'), str) or not re.fullmatch(r'img/catalogo/[a-zA-Z0-9_-]+\.(?:avif|webp|png|jpe?g|gif|svg)', p['image']):
            raise ValueError('Ruta de imagen pública inválida')


def import_product(old, source, manual=False):
    reference = str(source['sku'])
    product = deepcopy(old or {})
    # Do not carry manufacturer/Supplier-A facts into a Supplier-B description.
    for field in ('sourceUnavailable', 'sourceContentConflict', 'priceUnavailable', 'specificationNote',
                  'model', 'old', 'specificationsUpdated'):
        product.pop(field, None)
    product.update(id=old['id'] if old else '800000' + reference,
                   reference=reference, name=description_text(source.get('name', '')),
                   spec=description_text(source.get('short_description', '')),
                   price=sale_price(source), stock=source_stock(source),
                   specifications=[], features=[], specificationSources=[])
    product.setdefault('image', 'img/catalogo/sin-imagen.svg')
    product = classify(product)
    product = enrich(product, source)
    product['description'] = clean_description(source.get('description', ''))
    product['specificationSources'] = [source['permalink']]
    if not product['stock'] and (not old or manual or old.get('proximamente')):
        product['proximamente'] = True
    else:
        product.pop('proximamente', None)
    # Keep detail timestamps stable when the public content did not change.
    detail_fields = ('description', 'spec', 'specifications', 'features', 'model', 'specificationSources')
    if old and all(old.get(k) == product.get(k) for k in detail_fields) and old.get('specificationsUpdated'):
        product['specificationsUpdated'] = old['specificationsUpdated']
    return product


def plan_catalog(current, items, seen, manual):
    sources = index_sources(items)
    previous = {p['reference']: p for p in current['products']}
    if len(previous) != len(current['products']): raise ValueError('Referencias existentes repetidas')
    brands = {normalized(p['brand']) for p in current['products']} - {'generico', 'otros', 'sin marca'}
    # Empty/missing baseline seeds all current Nexcom SKUs without adding old stock.
    new = set(sources) - seen - set(previous) if seen else set()
    additions = {ref for ref in new if re.fullmatch(r'[1-9]\d{0,11}', ref)
                 and interested(sources[ref], brands) and not excluded(sources[ref])}
    additions |= {ref for ref in manual if ref in sources and ref not in EXCLUDED}
    selected = list(previous) + sorted(additions - set(previous), key=int)
    output, audit, retained, new_products, missing, released = [], [], [], [], [], []
    changed = 0
    for reference in selected:
        old, source = previous.get(reference), sources.get(reference)
        if source is None:
            p = deepcopy(old)
            p.update(stock=False, sourceUnavailable=True)
            output.append(p)
            missing.append(reference)
            audit.append({'reference': reference, 'previousPrice': old['price'], 'newPrice': None,
                          'publishedPrice': old['price'], 'source': 'Nexcom', 'status': 'SKU no encontrado'})
            continue
        p = import_product(old, source, manual=reference in manual)
        proposed = p['price']
        if old and Decimal(str(proposed)) != Decimal(str(old['price'])):
            changed += 1
            if abs(Decimal(str(proposed)) - Decimal(str(old['price']))) > 500:
                p['price'] = old['price']
                retained.append(reference)
        if old and old.get('proximamente') and p['stock']: released.append(reference)
        if not old: new_products.append({'sku': reference, 'name': p['name'], 'proximamente': bool(p.get('proximamente')), 'manual': reference in manual})
        audit.append({'reference': reference, 'previousPrice': old['price'] if old else None,
                      'newPrice': proposed, 'publishedPrice': p['price'], 'source': 'Nexcom',
                      'status': 'retenido > RD$500' if reference in retained else 'actualizado'})
        output.append(p)
    validate_public(output)
    report = {'source': 'Nexcom', 'sourceCount': len(items), 'baselineSeeded': not bool(seen),
              'updated': len(previous) - len(missing), 'existingCount': len(previous),
              'proposedPriceChanges': changed, 'priceGuardBlocked': changed > len(previous) * Decimal('0.20'),
              'retainedPrices': retained, 'newProducts': new_products, 'missingExisting': missing,
              'manualApplied': sorted(manual & set(sources)), 'manualMissing': sorted(manual - set(sources)),
              'releasedComingSoon': released, 'prices': audit}
    catalog = {'source': 'Nexcom — API pública (sku = referencia)', 'count': len(output),
               'products': output, 'updated': datetime.now(timezone.utc).isoformat(timespec='seconds')}
    baseline = {'version': 1, 'skus': sorted(seen | set(sources))}
    return catalog, baseline, report


def enforce_guards(report):
    if report['priceGuardBlocked']:
        raise PriceGuardError(f"Candado 20%: {report['proposedPriceChanges']}/{report['existingCount']} precios propuestos cambian. No se publica el catálogo ni el registro de vistos.")
    if len(report['missingExisting']) > max(3, report['existingCount'] // 20):
        raise ValueError('Nexcom no contiene demasiadas referencias existentes; se conserva el catálogo')


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    try: temporary.replace(path)
    finally: temporary.unlink(missing_ok=True)


def localize_fallback_images(products, sources, root):
    issues = []
    folder = root / 'img/catalogo'
    folder.mkdir(parents=True, exist_ok=True)
    for product in products:
        images = sources[product['reference']].get('images') or []
        url = images[0].get('src', '') if images else ''
        try:
            parts = urlsplit(url)
            if (parts.scheme != 'https' or parts.hostname not in ('nexcomtienda.com.do', 'www.nexcomtienda.com.do')
                    or parts.username or parts.password or parts.port not in (None, 443)):
                raise ValueError('Sin imagen HTTPS de respaldo válida')
            with urlopen(Request(url, headers={'User-Agent': USER_AGENT}), timeout=30) as response:
                if urlsplit(response.url).hostname not in ('nexcomtienda.com.do', 'www.nexcomtienda.com.do'):
                    raise ValueError('Redirección de imagen inesperada')
                data = response.read(15_000_001)
            if not data or len(data) > 15_000_000: raise ValueError('Imagen vacía o demasiado grande')
            extension = image_extension(data[:40])
            name = hashlib.sha256(data).hexdigest()[:20] + '.' + extension
            (folder / name).write_bytes(data)
            product.update(image='img/catalogo/' + name, sourceImage=url)
        except (ValueError, OSError) as error:
            product['image'] = 'img/catalogo/sin-imagen.svg'
            issues.append({'reference': product['reference'], 'error': str(error)})
    return issues


def print_report(report):
    for row in report['prices']: print(json.dumps(row, ensure_ascii=False), flush=True)
    summary = {k: v for k, v in report.items() if k != 'prices'}
    print('Resumen Nexcom: ' + json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--source-file', type=Path, help='Captura completa verificada para revisión puntual; nunca caché automática')
    parser.add_argument('--report-file', type=Path)
    parser.add_argument('--cost-output', type=Path, help='Archivo interno de estimados fuera del repositorio; no sustituye costos VIP')
    args = parser.parse_args()
    if args.cost_output and (args.cost_output.resolve().is_relative_to(ROOT.resolve()) or args.cost_output.exists()):
        parser.error('El archivo de costos debe ser nuevo y externo al repositorio público')
    current = json.loads((ROOT / 'js/productos-v2.json').read_text(encoding='utf-8'))
    items = json.loads(args.source_file.read_text()) if args.source_file else fetch_catalog()
    seen = read_seen(ROOT / 'scripts/nexcom_seen_skus.json')
    manual = read_manual(ROOT / 'scripts/altas-manuales.json')
    catalog, baseline, report = plan_catalog(current, items, seen, manual)
    print_report(report)
    if args.report_file: write_json(args.report_file, report)
    enforce_guards(report)
    if args.dry_run:
        print('Validado sin modificar catálogo, imágenes, costos ni registro de SKUs.')
        return
    sources = index_sources(items)
    fallback = [p for p in catalog['products'] if p['reference'] in sources
                and (p.get('image') == 'img/catalogo/sin-imagen.svg' or not (ROOT / p['image']).is_file())]
    issues = localize_fallback_images(fallback, sources, root=ROOT)
    for issue in issues: print('Imagen de respaldo pendiente: ' + json.dumps(issue), flush=True)
    validate_public(catalog['products'])
    if args.cost_output:
        # Exclusive creation: this cannot overwrite a verified financial record.
        with os.fdopen(os.open(args.cost_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
            json.dump(cost_document(catalog, load_factors()), handle, ensure_ascii=False, indent=2)
    for name in ('productos-v2.json', 'productos.json'):
        write_json(ROOT / 'js' / name, catalog)
    write_json(ROOT / 'scripts/nexcom_seen_skus.json', baseline)
    print(f"Nexcom: {catalog['count']} productos; publicación validada.")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        raise SystemExit(f'Sincronización Nexcom detenida; se conserva el catálogo anterior. {error}') from None
