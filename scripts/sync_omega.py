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

ROOT = Path(__file__).resolve().parents[1]


def read_selection(root):
    current = json.loads((root / 'js/productos.json').read_text(encoding='utf-8'))
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Validar sin cambiar catálogo ni imágenes')
    parser.add_argument('--policy-file', type=Path, help='Reglas privadas externas al repositorio')
    parser.add_argument('--source-file', type=Path, help='Captura pública revisada para una migración puntual')
    parser.add_argument('--image-cache', type=Path, help='Imágenes verificadas de esa captura, sin conexión')
    parser.add_argument('--accept-missing-baseline', action='store_true', help='Aceptar las ausencias confirmadas de una captura inicial revisada')
    args = parser.parse_args()
    if args.image_cache and not args.source_file:
        parser.error('--image-cache requiere --source-file')
    if args.accept_missing_baseline and not args.source_file:
        parser.error('--accept-missing-baseline requiere una captura pública revisada')
    if args.policy_file and args.policy_file.resolve().is_relative_to(ROOT.resolve()):
        parser.error('El archivo de reglas privadas debe estar fuera del repositorio')
    policy = PricingPolicy.from_env(file_path=args.policy_file)
    current, references = read_selection(ROOT)
    context = None
    if args.source_file:
        sources, missing = read_snapshot(args.source_file, references)
    else:
        context = make_tls_context()
        sources, missing = fetch_selected_references(references, context=context, workers=2)
    newly_missing = set(missing) - set(current.get('sourceMissingReferences', []))
    if len(newly_missing) > max(3, len(references) // 20) and not args.accept_missing_baseline:
        raise ValueError('Omega no confirma demasiadas fichas: se conserva el catálogo anterior')
    catalog = build_catalog(current['products'], sources, policy, missing_confirmed=missing)
    if args.dry_run:
        validate_catalog(catalog)
        print(f"Validado: {catalog['count']} productos, {len(missing)} referencias retiradas. Sin escribir.")
        return
    localize_images(catalog['products'], ROOT / 'img/catalogo', context=context, offline_dir=args.image_cache)
    changed = write_catalog(ROOT / 'js/productos.json', catalog)
    print(f"Omega: {catalog['count']} productos; catálogo {'actualizado' if changed else 'sin cambios'}.")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as error:
        # Never print the input pricing JSON or tracebacks containing it.
        raise SystemExit(f'Sincronización detenida; se conserva el catálogo anterior. {error}') from None
