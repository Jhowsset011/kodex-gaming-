#!/usr/bin/env python3
"""Download the selected public Omega entries for a migration audit.

This command does not read pricing rules, publish the store, or alter its catalog.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from omega_public import fetch_selected_references

ROOT = Path(__file__).resolve().parents[1]


def public_decimal(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('Dato público no serializable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    current = json.loads((ROOT / 'js/productos.json').read_text(encoding='utf-8'))['products']
    references = [product['reference'] for product in current]
    assert len(references) == len(set(references)) and all(ref.isdigit() for ref in references)
    assert '62635' not in references, 'La referencia retirada no debe consultarse'
    args.output.mkdir(parents=True, exist_ok=True)
    sources, missing = fetch_selected_references(references, cache_dir=args.output, workers=2)
    public = {'sources': sources, 'missingReferences': missing, 'selectedCount': len(references)}
    (args.output / 'sources.json').write_text(json.dumps(public, ensure_ascii=False, indent=2,
                                                       default=public_decimal), encoding='utf-8')
    print(f'Omega consultado: {len(sources)} fichas públicas; {len(missing)} referencias ausentes confirmadas.')
    for reference, source in sources.items():
        if source.get('conflicts'):
            print('Revisión de título:', reference, ', '.join(source['conflicts']))


if __name__ == '__main__':
    main()
