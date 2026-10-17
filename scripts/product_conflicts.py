"""Keep reviewed supplier/model contradictions pending until Omega corrects them."""

import json
import logging
from pathlib import Path
import re

from product_details import _identity

LOGGER = logging.getLogger(__name__)

def apply_reviewed_conflicts(catalog, path):
    path = Path(path)
    if not path.exists():
        return catalog
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or set(document) != {'products'} or not isinstance(document['products'], dict):
        raise ValueError('Registro de modelos pendientes inválido')
    by_id = {product['id']: product for product in catalog['products']}
    pending = []
    fields = {'reference', 'model', 'brand', 'supplierModel', 'manufacturerModel'}
    for pid, entry in document['products'].items():
        if not isinstance(entry, dict) or set(entry) != fields or pid not in by_id:
            raise ValueError('Producto pendiente desconocido')
        if any(not isinstance(value, str) or not value.strip() for value in entry.values()):
            raise ValueError('Identidad pendiente inválida')
        product = by_id[pid]
        if product.get('sourceUnavailable'):
            continue
        if any(product.get(field) != entry[field] for field in ('reference', 'brand')):
            raise ValueError('El modelo pendiente cambió de identidad')
        if product.get('sourceContentConflict'):
            continue
        if _identity(product.get('model', ''), part=True) != _identity(entry['model'], part=True):
            # The stable supplier reference still matches. Keep only this item
            # pending rather than blocking fresh prices for the entire store.
            LOGGER.warning('Referencia %s: número de parte pendiente cambió de %s a %s; producto no disponible hasta revisión.',
                           entry['reference'], entry['model'], product.get('model', '(vacío)'))
            pending.append(product)
            continue
        text = product['name'] + ' ' + product.get('description', '')
        if re.search(r'(?<!\w)' + re.escape(entry['supplierModel']) + r'(?!\w)', text, re.I):
            pending.append(product)
    for product in pending:
        product_type = 'Monitor' if product['category'] == 'Monitores' else product['subcategory']
        product.update(stock=False, name=f"{product_type} {product['brand']} · referencia {product['reference']}",
                       description='', spec='', specifications=[], features=[],
                       sourceContentConflict=True, specificationNote='Modelo pendiente de confirmación.')
        product.pop('model', None)
    return catalog
