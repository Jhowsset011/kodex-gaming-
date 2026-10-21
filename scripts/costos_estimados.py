"""Derived estimates only: never update verified VIP costs or public catalogs."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_factors(path=ROOT / 'scripts/factores-costo.json'):
    table = json.loads(Path(path).read_text(encoding='utf-8'))
    if set(table) != {'default', 'exceptions'} or not isinstance(table['exceptions'], dict):
        raise ValueError('Tabla de factores inválida')
    for factor in [table['default'], *table['exceptions'].values()]:
        value = Decimal(str(factor))
        if not value.is_finite() or not 0 < value <= 1: raise ValueError('Factor de costo inválido')
    return table


def estimate_cost(price, reference, table):
    factor = Decimal(str(table['exceptions'].get(reference, table['default'])))
    return (Decimal(str(price)) * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def cost_document(catalog, table, source_prices=None):
    products = []
    for product in catalog['products']:
        reference = product['reference']
        price = product['price'] if source_prices is None else source_prices.get(reference)
        products.append({'reference': reference, 'nexcomPublicPrice': price,
                         'estimatedCost': str(estimate_cost(price, reference, table)) if price is not None else None,
                         'status': 'estimated' if price is not None else 'source_unavailable'})
    return {'updated': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'catalogUpdated': catalog['updated'], 'kind': 'estimate', 'source': 'Nexcom',
            'products': products}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, default=ROOT / 'js/productos-v2.json')
    parser.add_argument('--output', type=Path, required=True, help='Archivo de estimados fuera del repositorio público')
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT.resolve()):
        parser.error('Los costos estimados no se guardan dentro del repositorio público')
    # An existing destination may contain official financial data. Never replace it.
    if args.output.exists(): parser.error('El destino ya existe; no se reemplazan archivos financieros')
    from nexcom_feed import fetch_catalog, index_sources
    from sync_nexcom_catalog import sale_price
    catalog = json.loads(args.catalog.read_text())
    sources = index_sources(fetch_catalog())
    prices = {p['reference']: sale_price(sources[p['reference']])
              for p in catalog['products'] if p['reference'] in sources}
    document = cost_document(catalog, load_factors(), prices)
    with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w', encoding='utf-8') as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
