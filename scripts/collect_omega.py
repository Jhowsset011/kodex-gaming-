#!/usr/bin/env python3
"""Download the selected public Omega entries for a migration audit.

This command does not read pricing rules, publish the store, or alter its catalog.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path

from omega_public import fetch_selected_references, parse_product, OmegaProductMissing

ROOT = Path(__file__).resolve().parents[1]


def public_decimal(value):
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError('Dato público no serializable')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume-dir', type=Path, help='HTML de la misma auditoría puntual; no usar para sincronizaciones diarias')
    args = parser.parse_args()
    current = json.loads((ROOT / 'js/productos.json').read_text(encoding='utf-8'))['products']
    references = [product['reference'] for product in current]
    assert len(references) == len(set(references)) and all(ref.isdigit() for ref in references)
    assert '62635' not in references, 'La referencia retirada no debe consultarse'
    args.output.mkdir(parents=True, exist_ok=True)
    sources, missing = {}, []
    if args.resume_dir:
        for reference in references:
            cached = args.resume_dir / f'{reference}.html'
            if cached.is_file():
                try:
                    sources[reference] = parse_product(cached.read_text(encoding='utf-8'), reference)
                except OmegaProductMissing:
                    missing.append(reference)
        print(f'Auditoría puntual retomada: {len(sources)} fichas previamente verificadas.', flush=True)
    pending = [ref for ref in references if ref not in sources and ref not in missing]
    fresh, retired = fetch_selected_references(pending, cache_dir=args.output, workers=2)
    sources.update(fresh)
    missing.extend(retired)
    public = {'sources': sources, 'missingReferences': missing, 'selectedCount': len(references)}
    (args.output / 'sources.json').write_text(json.dumps(public, ensure_ascii=False, indent=2,
                                                       default=public_decimal), encoding='utf-8')
    print(f'Omega consultado: {len(sources)} fichas públicas; {len(missing)} referencias ausentes confirmadas.')
    for reference, source in sources.items():
        if source.get('conflicts'):
            print('Revisión de título:', reference, ', '.join(source['conflicts']))


if __name__ == '__main__':
    main()
