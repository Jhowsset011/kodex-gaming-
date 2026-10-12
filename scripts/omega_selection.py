"""Keep stable identities while filtering the visible store by supplier facts."""

import json
import os
from pathlib import Path
import re
import tempfile

from omega_catalog import (EXCLUDED_IDS, EXCLUDED_REFERENCES, MAIN_CATEGORIES,
                           _brand, _category, _subcategory, normalized)

IDENTITY_FIELDS = {'id', 'reference', 'name', 'brand', 'category', 'subcategory'}
BRANDS = {'MSI', 'AOC', 'ANTEC', 'SAMSUNG'}
BRANCHES = ('PRINCIPAL SD', 'La Nave')
MANIFEST_FIELDS = {'version', 'minimumInventory', 'inventoryBranches',
                   'excludeRefurbished', 'knownMissingReferences', 'products'}


def validate_selection(document):
    if (not isinstance(document, dict) or set(document) != MANIFEST_FIELDS
            or type(document['version']) is not int or document['version'] != 1
            or type(document['minimumInventory']) is not int or document['minimumInventory'] != 2
            or document['inventoryBranches'] != list(BRANCHES)
            or document['excludeRefurbished'] is not True):
        raise ValueError('Reglas públicas de selección inválidas')
    products = document['products']
    if not isinstance(products, list) or not products:
        raise ValueError('La selección completa no puede estar vacía')
    ids, references = set(), set()
    for product in products:
        if not isinstance(product, dict) or set(product) != IDENTITY_FIELDS:
            raise ValueError('Identidad de selección inválida')
        if any(not isinstance(value, str) or not value.strip() for value in product.values()):
            raise ValueError('La selección tiene un campo incompleto')
        pid, reference = product['id'], product['reference']
        if (not pid.isdigit() or pid in ids or pid in EXCLUDED_IDS
                or not re.fullmatch(r'[1-9]\d{0,11}', reference)
                or reference in references or reference in EXCLUDED_REFERENCES
                or product['category'] not in MAIN_CATEGORIES):
            raise ValueError('La selección repite o altera una identidad excluida')
        ids.add(pid)
        references.add(reference)
    missing = document['knownMissingReferences']
    if (not isinstance(missing, list) or any(not isinstance(ref, str) for ref in missing)
            or len(missing) != len(set(missing)) or not set(missing) <= references):
        raise ValueError('Referencias retiradas de selección inválidas')
    return document


def selection_document(products, missing=()):
    document = {'version': 1, 'minimumInventory': 2, 'inventoryBranches': list(BRANCHES),
                'excludeRefurbished': True, 'knownMissingReferences': sorted(missing, key=int),
                'products': [{key: product[key] for key in sorted(IDENTITY_FIELDS)} for product in products]}
    return validate_selection(document)


def read_full_selection(root, current):
    path = Path(root) / 'data/omega-selection.json'
    if not path.exists():
        return current
    document = validate_selection(json.loads(path.read_text(encoding='utf-8')))
    selected = {product['id']: product for product in document['products']}
    visible = {}
    for product in current['products']:
        pid = product['id']
        if (pid not in selected or pid in visible
                or product['reference'] != selected[pid]['reference']):
            raise ValueError('El catálogo visible no coincide con la selección completa')
        visible[pid] = product
    products = [visible.get(product['id'], dict(product)) for product in document['products']]
    return {**current, 'products': products, 'count': len(products),
            'sourceMissingReferences': document['knownMissingReferences']}


def extend_selection(existing, sources):
    """Append actual requested-brand references once, preserving previous URLs."""
    selected = list(existing)
    references = {product['reference'] for product in existing}
    ids = {product['id'] for product in existing}
    added = []
    for reference, source in sorted(sources.items(), key=lambda pair: int(pair[0])):
        if reference in references or reference in EXCLUDED_REFERENCES or _brand(source).upper() not in BRANDS:
            continue
        if source.get('reference') != reference:
            raise ValueError('La nueva ficha no confirma su referencia de Omega')
        pid = '900000' + reference
        if pid in ids or pid in EXCLUDED_IDS:
            raise ValueError('La nueva referencia colisiona con un enlace existente')
        category = _category(source, source['description'], {})
        product = {'id': pid, 'reference': reference, 'name': source['name'], 'brand': _brand(source),
                   'category': category,
                   'subcategory': _subcategory(category, source, source['description'], {})}
        selected.append(product)
        ids.add(pid)
        references.add(reference)
        added.append(reference)
    return selected, added


def selected_inventory(source):
    rows = source.get('inventory')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Omega no proporciona inventario verificable para el filtro')
    quantities = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'branch', 'quantity'}
                or not isinstance(row['branch'], str) or not row['branch'].strip()
                or type(row['quantity']) is not int or row['quantity'] < 0):
            raise ValueError('El inventario de Omega está incompleto o es inválido')
        branch = normalized(row['branch']).strip()
        if branch in quantities:
            raise ValueError('Omega repite una sucursal en el inventario')
        quantities[branch] = row['quantity']
    required = [normalized(branch) for branch in BRANCHES]
    if any(branch not in quantities for branch in required):
        raise ValueError('Omega no confirma Principal SD y La Nave; se conserva el catálogo')
    return sum(quantities[branch] for branch in required)


def is_refurbished(source):
    fields = ('rawTitle', 'name', 'brand', 'description', 'partNumber')
    text = ' '.join(str(source.get(field, '')) for field in fields)
    text += ' ' + ' '.join(str(line) for line in source.get('descriptionLines', []))
    text += ' ' + ' '.join(str(row.get('value', '')) for row in source.get('specifications', []) if isinstance(row, dict))
    return bool(re.search(r'(?<!\w)refurbish(?:ed)?(?!\w)', text, re.I))


def filter_visible_catalog(catalog, sources):
    """Filter only confirmed facts; missing branches never mean zero stock."""
    visible, excluded = [], []
    for product in catalog['products']:
        reference = product['reference']
        if product.get('sourceUnavailable'):
            reasons, quantity = ['retired'], None
        else:
            source = sources.get(reference)
            if not isinstance(source, dict) or source.get('reference') != reference:
                raise ValueError('El filtro no tiene una ficha exacta de Omega')
            quantity = selected_inventory(source)
            reasons = []
            if quantity < 2:
                reasons.append('inventory_0_or_1')
            if is_refurbished(source):
                reasons.append('refurbished')
        if reasons:
            excluded.append({'id': product['id'], 'reference': reference, 'name': product['name'],
                             'selectedInventory': quantity, 'reasons': reasons})
        else:
            visible.append(product)
    if not visible:
        raise ValueError('El filtro dejaría el catálogo vacío; requiere revisión')
    allowed = {product['reference'] for product in visible}
    result = {key: value for key, value in catalog.items() if key != 'sourceMissingReferences'}
    result.update(products=visible, count=len(visible))
    missing = [ref for ref in catalog.get('sourceMissingReferences', []) if ref in allowed]
    if missing:
        result['sourceMissingReferences'] = missing
    return result, excluded


def write_selection(path, document):
    validate_selection(document)
    path = Path(path)
    encoded = json.dumps(document, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return True
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def write_selection_ids(path, document):
    validate_selection(document)
    path = Path(path)
    encoded = ''.join(product['id'] + '\n' for product in document['products'])
    if path.exists() and path.read_text(encoding='utf-8') == encoded:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        return True
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
