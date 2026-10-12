#!/usr/bin/env python3
"""Synchronize the owner's selected references using only public Omega data.

Private sale rules are required before reading the supplier. Any incomplete
response, invalid image or validation failure preserves the published catalog.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

from omega_catalog import build_catalog, validate_catalog
from omega_images import localize_images
from omega_pricing import PricingPolicy
from omega_public import fetch_selected_references, make_tls_context
from product_details import enrich_catalog
from product_conflicts import apply_reviewed_conflicts
from omega_selection import (extend_selection, filter_visible_catalog, read_full_selection,
                             selection_document, write_selection, write_selection_ids)

ROOT = Path(__file__).resolve().parents[1]


def read_selection(root):
    path = root / 'js/productos-v2.json'
    if not path.exists():
        path = root / 'js/productos.json'
    current = json.loads(path.read_text(encoding='utf-8'))
    current = read_full_selection(root, current)
    products = current['products']
    ids = [p['id'] for p in products]
    references = [p['reference'] for p in products]
    selected = (root / 'scripts/omega_ids.txt').read_text(encoding='utf-8').split()
    if (not ids or len(ids) != len(set(ids)) or len(references) != len(set(references))
            or len(selected) != len(set(selected)) or set(selected) != set(ids)
            or any(not isinstance(ref, str) or not ref.isdigit() for ref in references)
            or '21890' in ids or '62635' in references):
        raise ValueError('Selección inválida: se conserva el catálogo anterior')
    return current, references


def read_snapshot(path, references):
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    sources, missing = snapshot['sources'], snapshot['missingReferences']
    if (not isinstance(sources, dict) or not isinstance(missing, list)
            or len(missing) != len(set(missing)) or set(sources) & set(missing)
            or set(sources) | set(missing) != set(references)
            or snapshot.get('selectedCount') != len(references)):
        raise ValueError('La captura pública no cubre la selección exacta')
    return sources, missing


def read_brand_import_snapshot(path, current):
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    sources, missing = snapshot['sources'], snapshot['missingReferences']
    if (not isinstance(sources, dict) or not isinstance(missing, list)
            or any(not isinstance(ref, str) or not ref.isdigit() for ref in [*sources, *missing])
            or len(missing) != len(set(missing)) or set(sources) & set(missing)
            or type(snapshot.get('selectedCount')) is not int
            or snapshot['selectedCount'] != len(sources) + len(missing)
            or any(not isinstance(source, dict) or source.get('reference') != ref
                   for ref, source in sources.items())
            or not {p['reference'] for p in current['products']} <= set(sources) | set(missing)):
        raise ValueError('La auditoría de marcas no cubre toda la selección actual')
    products, added = extend_selection(current['products'], sources)
    selected = {p['reference'] for p in products}
    return ({**current, 'products': products, 'count': len(products)},
            {ref: source for ref, source in sources.items() if ref in selected},
            [ref for ref in missing if ref in selected], added)


def write_catalog(path, catalog):
    validate_catalog(catalog)
    previous = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    stable_keys = ('source', 'count', 'products', 'sourceMissingReferences')
    if all(previous.get(key) == catalog.get(key) for key in stable_keys):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(catalog, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return True
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def write_catalog_outputs(root, catalog):
    """Publish the full selection and a catalog readable by cached older clients.

    Older clients require every price to be positive. Keep those clients usable
    without inventing prices for unavailable products or losing selected IDs
    from the canonical catalog used by the current storefront and synchronizer.
    Both outputs must validate, and any write failure stops the caller before
    the workflow can commit or deploy the update.
    """
    validate_catalog(catalog)
    priced = [product for product in catalog['products']
              if isinstance(product['price'], (int, float)) and product['price'] > 0]
    legacy = {key: value for key, value in catalog.items()
              if key != 'sourceMissingReferences'}
    legacy.update(products=priced, count=len(priced))
    validate_catalog(legacy)
    canonical_changed = write_catalog(root / 'js/productos-v2.json', catalog)
    legacy_changed = write_catalog(root / 'js/productos.json', legacy)
    return canonical_changed or legacy_changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Validar sin cambiar catálogo ni imágenes')
    parser.add_argument('--require-rounding', action='store_true', help='Conservar el catálogo si las reglas privadas no incluyen redondeo')
    parser.add_argument('--policy-file', type=Path, help='Reglas privadas externas al repositorio')
    parser.add_argument('--source-file', type=Path, help='Captura pública revisada para una migración puntual')
    parser.add_argument('--import-brands', action='store_true', help='Añadir MSI, AOC, Antec y Samsung desde una auditoría pública completa')
    parser.add_argument('--image-cache', type=Path, help='Imágenes verificadas de esa captura, sin conexión')
    parser.add_argument('--accept-missing-baseline', action='store_true', help='Aceptar las ausencias confirmadas de una captura inicial revisada')
    args = parser.parse_args()
    if args.image_cache and not args.source_file:
        parser.error('--image-cache requiere --source-file')
    if args.accept_missing_baseline and not args.source_file:
        parser.error('--accept-missing-baseline requiere una captura pública revisada')
    if args.import_brands and not args.source_file:
        parser.error('--import-brands requiere una auditoría pública revisada mediante --source-file')
    if args.policy_file and args.policy_file.resolve().is_relative_to(ROOT.resolve()):
        parser.error('El archivo de reglas privadas debe estar fuera del repositorio')
    policy = PricingPolicy.from_env(file_path=args.policy_file)
    if (args.require_rounding or args.import_brands) and not policy.rounding_enabled:
        raise ValueError('Las reglas privadas deben incluir el redondeo antes de actualizar precios')
    current, references = read_selection(ROOT)
    context = None
    if args.source_file:
        if args.import_brands:
            current, sources, missing, added = read_brand_import_snapshot(args.source_file, current)
            references = [p['reference'] for p in current['products']]
            print(f"Marcas Omega: {len(added)} referencias nuevas, sin repetir las existentes.")
        else:
            sources, missing = read_snapshot(args.source_file, references)
    else:
        context = make_tls_context()
        sources, missing = fetch_selected_references(references, context=context, workers=2)
    newly_missing = set(missing) - set(current.get('sourceMissingReferences', []))
    if len(newly_missing) > max(3, len(references) // 20) and not args.accept_missing_baseline:
        raise ValueError('Omega no confirma demasiadas fichas: se conserva el catálogo anterior')
    catalog = build_catalog(current['products'], sources, policy, missing_confirmed=missing)
    apply_reviewed_conflicts(catalog, ROOT / 'data/product-conflicts.json')
    details_path = ROOT / 'data/product-details.json'
    enrich_catalog(catalog, details_path if details_path.exists() else None)
    previous_by_id = {product['id']: product for product in current['products']}
    detail_fields = ('description', 'model', 'specifications', 'features', 'specificationSources')
    for product in catalog['products']:
        previous = previous_by_id[product['id']]
        if ('specificationsUpdated' in product and previous.get('specificationsUpdated')
                and all(previous.get(field) == product.get(field) for field in detail_fields)):
            product['specificationsUpdated'] = previous['specificationsUpdated']
    selection_path = ROOT / 'data/omega-selection.json'
    selection = None
    if selection_path.exists() or args.import_brands:
        selection = selection_document(catalog['products'], missing)
        catalog, excluded = filter_visible_catalog(catalog, sources)
        print(f"Filtro Principal SD + La Nave: {catalog['count']} visibles; {len(excluded)} excluidos.")
    if args.dry_run:
        validate_catalog(catalog)
        print(f"Validado: {catalog['count']} productos, {len(missing)} referencias retiradas. Sin escribir.")
        return
    localize_images(catalog['products'], ROOT / 'img/catalogo', context=context, offline_dir=args.image_cache)
    changed = write_catalog_outputs(ROOT, catalog)
    if selection is not None:
        changed = write_selection(selection_path, selection) or changed
        changed = write_selection_ids(ROOT / 'scripts/omega_ids.txt', selection) or changed
    print(f"Omega: {catalog['count']} productos; catálogo {'actualizado' if changed else 'sin cambios'}.")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        # Never print the input pricing JSON or tracebacks containing it.
        raise SystemExit(f'Sincronización detenida; se conserva el catálogo anterior. {error}') from None
