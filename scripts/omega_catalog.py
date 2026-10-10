"""Build a public Kodex catalog from exact, selected Omega references.

This module performs no network or file operations. Pricing is supplied through
an external policy; public records deliberately contain only the final sale
price. Existing records supply stable identities and store classifications,
never supplier names, descriptions, pictures, specifications or prices.
"""

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import html
import math
import re
import unicodedata
from urllib.parse import urlparse


PLACEHOLDER = "img/catalogo/sin-imagen.svg"
EXCLUDED_IDS = {"21890"}
EXCLUDED_REFERENCES = {"62635"}
PUBLIC_PRODUCT_FIELDS = frozenset({
    "id", "reference", "name", "spec", "category", "subcategory", "brand",
    "price", "old", "image", "sourceImage", "stock", "description",
    "specifications", "features", "model", "specificationSources",
    "sourceCategory", "collections", "sourceUnavailable", "priceUnavailable",
    "specificationsUpdated", "imageUnavailable", "sourceContentConflict",
    "specificationNote",
})
PUBLIC_CATALOG_FIELDS = frozenset({
    "source", "count", "products", "updated", "sourceMissingReferences",
})
MAIN_CATEGORIES = {
    "Almacenamiento", "Audio y Video", "Componentes", "Computadoras",
    "Laptops", "Mobiliario", "Monitores", "Periféricos",
}
BRAND_ALIASES = {
    "msi": "MSI", "aoc": "AOC", "hp": "HP", "hpe": "HPE",
    "xtech": "Xtech", "klipx": "Klip Xtreme", "klip xtreme": "Klip Xtreme",
    "western digital": "Western Digital", "wd": "Western Digital",
    "thinkvision": "Lenovo", "genérico": "Genérico", "generico": "Genérico",
    "rippa": "Rippa", "myo": "Myo", "hiksemi": "Hiksemi", "hikvision": "Hikvision",
    "hp-enterprise (hpe)": "HPE", "memoria genérica": "Genérico",
}
KNOWN_MAKERS = (
    "Western Digital", "Cooler Master", "Klip Xtreme", "Logitech", "TP-Link",
    "Redragon", "SteelSeries", "HyperX", "ViewSonic", "Ubiquiti", "Tripp Lite",
    "CyberPower", "Samsung", "Kingston", "Seagate", "Lenovo", "Dell", "AOC",
    "ASUS", "Gigabyte", "Corsair", "Razer", "Dahua", "Hikvision", "Cisco",
    "EVGA", "Zotac", "PNY", "Thermaltake", "Antec", "XPG", "ADATA", "Crucial",
    "SanDisk", "Lexar", "Verbatim", "Hiksemi", "Genius", "Forza", "Nexxt",
    "Manhattan", "StarTech", "Vention", "Ugreen", "Baseus", "Anker", "JBL",
    "Sony", "Edifier", "Bose", "BenQ", "LG", "Philips", "Apple", "Microsoft",
    "Epson", "Canon", "Brother", "D-Link", "Tenda", "APC", "Eaton", "HPE",
    "HP", "Grandstream", "Xtech", "Argom", "Agiler", "Myo", "MSI", "Primus",
    "Markvision", "Sonos", "Vitek", "Elo", "Rippa", "Maxtor", "Roku", "Huawei",
    "Haier", "ECS", "Titan", "Klipsch", "Naruto",
)


def normalized(value):
    text = html.unescape(str(value or "")).replace("″", '"').replace("”", '"')
    return "".join(char for char in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(char)).casefold()


def _text(value, field, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise ValueError(f"Campo de Omega inválido: {field}")
    return value.strip()


def _reference(value):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9]\d{0,11}", value):
        raise ValueError("Referencia de Omega inválida")
    return value


def _source_url(url, reference):
    parts = urlparse(url)
    if (parts.scheme != "https" or parts.hostname != "tienda.omega.com.do"
            or parts.path.rstrip("/") != f"/es/product/consul/{reference}"
            or parts.query or parts.fragment or parts.username or parts.password
            or parts.port not in (None, 443)):
        raise ValueError("La fuente no confirma la referencia exacta de Omega")
    return url


def _image_url(value):
    if not value:
        return ""
    value = _text(value, "imageSource")
    parts = urlparse(value)
    if (parts.scheme != "https" or parts.hostname != "sis.omega.com.do"
            or not parts.path.startswith("/ProductImages/") or parts.username
            or parts.password or parts.port not in (None, 443)):
        raise ValueError("Imagen fuera del catálogo público de Omega")
    return value


def _positive_price(value, field):
    if isinstance(value, bool) or not isinstance(value, (Decimal, str, int, float)):
        raise ValueError(f"Precio inválido: {field}")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"Precio inválido: {field}") from None
    if not number.is_finite() or number <= 0:
        raise ValueError(f"Precio inválido: {field}")
    return number


def _public_price(value):
    number = _positive_price(value, "venta")
    result = float(number)
    if not math.isfinite(result):
        raise ValueError("Precio de venta no representable")
    return result


def _brand(source):
    """Use the supplier's maker, not a CPU brand found inside a laptop title."""
    brand = _text(source.get("brand", ""), "brand", optional=True)
    if not brand:
        title = _text(source.get("rawTitle", source.get("name", "")),
                      "rawTitle", optional=True)
        if " - " in title:
            brand = title.split(" - ", 1)[0].strip()
    brand = re.sub(r"\s+refurbish(?:ed)?\b", "", brand, flags=re.I).strip()
    canonical = {maker.casefold(): maker for maker in KNOWN_MAKERS}
    brand = BRAND_ALIASES.get(brand.casefold(), canonical.get(brand.casefold(), brand))
    description = source.get("description", "")
    # The description's explicitly named product maker resolves incorrect
    # supplier brand headings (e.g. HP Refurbish on a ViewSonic monitor).
    # CPU, RAM and GPU vendors inside a laptop's details are not its maker.
    if isinstance(description, str):
        beginning = description[:120]
        candidates = []
        for maker in KNOWN_MAKERS:
            match = re.search(r"(?<!\w)" + re.escape(maker) + r"(?!\w)", beginning, re.I)
            if match:
                candidates.append((match.start(), -len(maker), maker))
        if candidates:
            first = min(candidates)
            if first[0] <= 65:
                brand = first[2]
    return brand or "Genérico"


def _model_conflict(name, part_number):
    """Detect a different explicit model in the same model family."""
    actual = re.findall(r"\b[A-Z]*\d+[A-Z0-9-]*\b", name.upper())
    expected = re.findall(r"\b[A-Z]*\d+[A-Z0-9-]*\b", part_number.upper())
    for model in expected:
        if model in actual:
            continue
        stem = re.match(r"[A-Z]+\d+", model)
        if stem and any(candidate != model and not model.startswith(candidate + "-")
                        and candidate.startswith(stem.group(0))
                        for candidate in actual):
            return True
    return False


def _part_supported(part_number, text):
    """The full PN or its explicit main model must agree with Omega's text."""
    compact = lambda value: re.sub(r"[^a-z0-9]", "", normalized(value))
    if compact(part_number) in compact(text):
        return True
    # Packaging/color codes can follow a verified model (C120R.ARGB-3PK), and
    # need not occur in the technical description. Never accept C120 for C120R
    # or B760M for B760: these are distinct explicit model tokens.
    expected = re.findall(r"\b[A-Z]+\d+[A-Z0-9]*\b", part_number.upper())
    actual = set(re.findall(r"\b[A-Z]+\d+[A-Z0-9]*\b", text.upper()))
    return bool(expected and expected[0] in actual)


def _unresolved_conflict(source, part_number, description):
    title = _text(source.get("rawTitle") or source.get("name"), "título de Omega")
    conflict = bool(part_number and (source.get("conflicts") or _model_conflict(title, part_number)))
    return conflict and not _part_supported(part_number, description)


TYPE_PREFIXES = (
    (r"^pantalla interactiva\b", "Pantalla interactiva"),
    (r"^power supply\b|^fuente(?: de poder)?\b", "Fuente de poder"),
    (r"^mouse\s*pad\b", "Mouse pad"),
    (r"^camara web\b|^webcam\b", "Cámara web"),
    (r"^memoria usb\b", "Memoria USB"),
    (r"^memoria micro\s*sd\b", "Memoria microSD"),
    (r"^memoria sd\b", "Memoria SD"),
    (r"^barra de sonido\b|^sound ?bar\b", "Barra de sonido"),
    (r"^tarjeta de video\b|^tarjeta grafica\b", "Tarjeta gráfica"),
    (r"^placa madre\b|^motherboard\b|^mb\b", "Tarjeta madre"),
    (r"^monitor\b", "Monitor"),
    (r"^laptop\b|^notebook\b", "Laptop"),
    (r"^computadora\b|^desktop\b", "Computadora"),
    (r"^mini pc\b", "Mini PC"),
    (r"^terminal\b", "Terminal"),
    (r"^case\b|^gabinete\b", "Gabinete"),
    (r"^disco\b", "Disco"),
    (r"^ssd\b", "SSD"),
    (r"^hdd\b", "HDD"),
    (r"^dvd-r\b", "DVD-R"),
    (r"^dvd\b", "DVD"),
    (r"^cd-r\b", "CD-R"),
    (r"^cd\b", "CD"),
    (r"^combo\b", "Combo"),
    (r"^teclado\b", "Teclado"),
    (r"^mouse\b", "Mouse"),
    (r"^bocinas?\b|^speaker\b", "Bocinas"),
    (r"^audifonos?\b|^headset\b", "Audífonos"),
    (r"^microfonos?\b", "Micrófono"),
    (r"^subwoofer\b", "Subwoofer"),
    (r"^smart tv\b|^televisor\b", "Televisor"),
    (r"^memoria(?: ram)?\b", "Memoria"),
    (r"^procesador\b|^cpu\b", "Procesador"),
    (r"^abanico\b|^ventiladores?\b", "Ventilador"),
    (r"^disipador\b|^cooler\b", "Disipador"),
    (r"^refrigeracion\b|^cpu liquid cooler\b", "Refrigeración"),
    (r"^silla\b", "Silla"),
    (r"^escritorio\b", "Escritorio"),
)


def _type_prefix(value):
    text = normalized(value)
    for pattern, label in TYPE_PREFIXES:
        match = re.search(pattern, text)
        if match:
            return label, match.end()
    return "", 0


def _display_name(source, part_number, description):
    """Use only Omega's title, maker and verified part number for display."""
    raw = _text(source.get("rawTitle") or source.get("name"), "título de Omega")
    name = raw.split(" - ", 1)[1].strip() if " - " in raw else raw
    brand = _brand(source)
    raw_brand = source.get("brand", "")
    if isinstance(raw_brand, str) and raw_brand.strip() and brand != "Genérico":
        name = re.sub(r"(?<!\w)" + re.escape(raw_brand.strip()) + r"(?!\w)",
                      lambda _match: brand, name, flags=re.I)
    if part_number and (source.get("conflicts") or _model_conflict(name, part_number)):
        candidates = (description, source.get("name", ""))
        if not any(_part_supported(part_number, candidate)
                   for candidate in candidates if isinstance(candidate, str) and candidate):
            raise ValueError("Omega no resuelve la discrepancia del modelo")
        # A title with a wrong model is rebuilt from Omega's own confirmed part
        # number, avoiding either an incorrect title or a paragraph-long name.
        name = part_number
    direct_type, prefix_end = _type_prefix(name)
    product_type = direct_type or _type_prefix(description)[0]
    maker_in_title = bool(re.search(r"(?<!\w)" + re.escape(brand) + r"(?!\w)", name, re.I))
    if direct_type:
        remainder = name[prefix_end:].lstrip(" ,:.-")
        if not maker_in_title and brand != "Genérico":
            remainder = brand + (" " + remainder if remainder else "")
        name = direct_type + (" " + remainder if remainder else "")
    else:
        if not maker_in_title and brand != "Genérico":
            name = brand + " " + name
        if product_type:
            name = product_type + " " + name
    return re.sub(r"\s+", " ", name).strip()


def _classification_text(source, description):
    title = _text(source.get("name", ""), "name", optional=True)
    if " - " in title:
        title = title.split(" - ", 1)[1]
    # Product descriptions normally start with the product type; short supplier
    # titles frequently contain only a maker and model number.
    return normalized(description or title), normalized(title)


def _category(source, description, previous):
    text, title = _classification_text(source, description)
    patterns = (
        (r"^(?:monitor|pantalla interactiva|smart monitor)\b", "Monitores"),
        (r"^(?:laptop|notebook|portatil)\b|^lenovo thinkpad\b", "Laptops"),
        (r"^(?:computadora|mini pc|desktop|terminal)\b", "Computadoras"),
        (r"^(?:silla|escritorio)\b", "Mobiliario"),
        (r"^(?:disco|ssd|hdd|dvd|cd|pack \d+ dvd|caja (?:para disco|usb))\b|^memoria\s+(?:usb|micro|sd)\b", "Almacenamiento"),
        (r"^(?:smart tv|televisor|bocina|bocinas|speaker|audifono|audifonos|headset|microfono|microfonos|soundbar|sound bar|subwoofer|barra de sonido|streaming|soporte tv|consola (?:streamer|de control))\b", "Audio y Video"),
        (r"^(?:case|gabinete|power supply|fuente|placa madre|motherboard|mb|memoria|procesador|tarjeta (?:de video|msi|grafica)|abanico|ventilador|ventiladores|disipador|cooler|cpu liquid cooler|refrigeracion|enfriamiento|sistema enfriamiento|controladora)\b", "Componentes"),
        (r"^(?:mouse|teclado|combo|camara web|webcam|gamepad|joystick|control gamer|puntero|funda|candado|pedales|volante)\b", "Periféricos"),
    )
    for candidate in (text, title):
        for pattern, category in patterns:
            if re.search(pattern, candidate):
                return category
    # Retain the store's one-level taxonomy when Omega has only an obscure
    # model description. This is display classification, never supplier facts.
    old = previous.get("category")
    if old in MAIN_CATEGORIES:
        return old
    raise ValueError("No se pudo clasificar el producto de Omega")


def _subcategory(category, source, description, previous):
    text, title = _classification_text(source, description)
    text = text + " " + title
    if category == "Monitores":
        if "pantalla interactiva" in text:
            return "Pantallas interactivas"
        if re.search(r"\bportatil", text):
            return "Portátiles"
        if re.search(r"touch|tactil", text):
            return "Táctiles"
        # Supplier marketing titles can incorrectly call a flat monitor curved
        # (e.g. the Odyssey G4). Require an explicit technical description.
        return "Curvos" if "curv" in normalized(description) else "De escritorio"
    rules = {
        "Audio y Video": [
            (r"^audifono|^headset", "Audífonos"),
            (r"sound ?bar|barra de sonido|^subwoofer", "Equipos de sonido"),
            (r"^bocina|^speaker", "Bocinas"),
            (r"^soporte", "Soportes para TV"),
            (r"^streaming", "Streaming y TV Smart"),
            (r"^smart tv|^televisor", "Televisores"),
            (r"^microfono", "Micrófonos"),
            (r"^iluminacion|^luz|^luces", "Iluminación"),
        ],
        "Almacenamiento": [
            (r"^caja", "Gabinetes para discos"),
            (r"^memoria usb", "Memorias USB"),
            (r"^memoria\s+(?:micro|sd)", "Tarjetas de memoria"),
            (r"\bdvd|^cd|^pack", "Unidades ópticas"),
            (r"\bssd\b|estado solido", "Discos SSD"),
            (r"^disco|^hdd", "Discos HDD"),
        ],
        "Componentes": [
            (r"^controladora", "Controladores RGB"),
            (r"^(?:abanico|ventilador|disipador|cooler|cpu liquid cooler|refrigeracion|enfriamiento|sistema enfriamiento)", "Refrigeración"),
            (r"^(?:case|gabinete)", "Gabinetes / Case"),
            (r"^(?:power supply|fuente)", "Fuentes de poder"),
            (r"^(?:mb|motherboard|placa madre)", "Tarjetas madre"),
            (r"^memoria", "Memorias RAM"),
            (r"^procesador", "Procesadores"),
            (r"^tarjeta", "Tarjetas gráficas"),
        ],
        "Periféricos": [
            (r"^mouse\s*pad", "Mouse pads"),
            (r"^mouse", "Mouse"),
            (r"^combo|^teclado.*\bmouse\b", "Combos de teclado y mouse"),
            (r"^teclado", "Teclados"),
            (r"^camara web|^webcam", "Cámaras web"),
            (r"\bpresentador\b|\bpuntero\b", "Presentadores"),
            (r"^gamepad|^joystick|^control", "Controles de juego"),
            (r"^pedales|^volante", "Volantes y pedales"),
            (r"^funda|^candado", "Accesorios para laptop"),
            (r"^puntero", "Presentadores"),
        ],
    }
    if category == "Laptops":
        return "Convertibles 2 en 1" if re.search(r"2 en 1|2-in-1|2 in 1", text) else "Gaming" if re.search(r"gamer|gaming", text) else "Portátiles"
    if category == "Computadoras":
        return "Terminales" if re.search(r"terminal|wyse|thin client", text) else "Mini PC" if "mini pc" in text or "tiny" in text else "De escritorio"
    if category == "Mobiliario":
        return "Sillas" if text.startswith("silla") else "Escritorios"
    for pattern, subcategory in rules.get(category, []):
        if re.search(pattern, text):
            return subcategory
    old = previous.get("subcategory")
    if previous.get("category") == category and isinstance(old, str) and old.strip():
        return old
    defaults = {"Audio y Video": "Accesorios de audio", "Almacenamiento": "Discos HDD",
                "Componentes": "Otros componentes", "Periféricos": "Otros accesorios"}
    return defaults.get(category, "Otros productos")


def _rows(source, part_number):
    rows = source.get("specifications", [])
    if not isinstance(rows, list):
        raise ValueError("Especificaciones de Omega inválidas")
    output, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Fila de especificaciones de Omega inválida")
        label, value = _text(row.get("label"), "label"), _text(row.get("value"), "value")
        # Supplier warranty policies are not automatically Kodex's policies.
        if re.search(r"garantia|precio|envio", normalized(label)):
            continue
        key = normalized(label)
        if key not in seen:
            output.append({"label": label, "value": value})
            seen.add(key)
    if part_number and "numero de parte" not in seen:
        output.insert(0, {"label": "Número de parte", "value": part_number})
    return output


def _features(source, rows, description):
    """Keep explicit technical supplier lines that are not already in rows."""
    lines = source.get("descriptionLines")
    if lines is None:
        lines = [line.strip() for line in description.splitlines() if line.strip()]
    if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
        raise ValueError("Características de Omega inválidas")
    covered = set()
    for row in rows:
        covered.add(normalized(row["value"]).strip())
        covered.add(normalized(row["label"] + ": " + row["value"]).strip())
    output, seen = [], set()
    for line in lines:
        line = line.strip()
        key = normalized(line)
        if (len(line) <= 10 or key in covered or key in seen
                or re.search(r"\b(?:garantia|precio|precios|costo|costos|envio|envios|devoluciones|politica|financiamiento)\b", key)):
            continue
        output.append(line)
        seen.add(key)
    return output


def _product(previous, source, policy, timestamp):
    reference = _reference(previous["reference"])
    if not isinstance(source, dict) or source.get("reference") != reference:
        raise ValueError("La ficha de Omega cambió de referencia")
    if source.get("currency") != "DOP":
        raise ValueError("La ficha de Omega no usa DOP")
    url = _source_url(_text(source.get("sourceUrl"), "sourceUrl"), reference)
    description = _text(source.get("description", ""), "description", optional=True)
    part_number = _text(source.get("partNumber", ""), "partNumber", optional=True)
    if not isinstance(source.get("stock"), bool):
        raise ValueError("Disponibilidad de Omega inválida")
    category = _category(source, description, previous)
    content_conflict = _unresolved_conflict(source, part_number, description)
    subcategory = _subcategory(category, source, description, previous)
    maker = _brand(source)
    if content_conflict:
        product_type = _type_prefix(description)[0] or "Producto"
        public_name = f"{product_type} {maker} · referencia {reference}"
    else:
        public_name = _display_name(source, part_number, description)
        if category == "Monitores" and "curv" not in normalized(description):
            # Keep the display title consistent with the verified technical
            # description when Omega's marketing title adds an unsupported
            # curvature claim. This currently affects the Odyssey G4 title.
            public_name = re.sub(r"\bcurv[oa]s?\b\s*[,;]?", "", public_name, flags=re.I)
            public_name = re.sub(r",\s*,", ",", public_name)
            public_name = re.sub(r"\s+", " ", public_name).strip(" ,")
    product = {
        "id": previous["id"], "reference": reference,
        "name": public_name,
        "spec": description[:140], "category": category,
        "subcategory": subcategory,
        "brand": maker, "price": None, "stock": False,
        "image": PLACEHOLDER, "sourceImage": _image_url(source.get("imageSource", "")),
        "description": description, "specifications": _rows(source, part_number),
        "features": [], "specificationSources": [url], "collections": [],
    }
    if part_number:
        product["model"] = part_number
    product["features"] = _features(source, product["specifications"], description)
    categories = source.get("sourceCategories", [])
    if not isinstance(categories, list) or any(not isinstance(item, str) for item in categories):
        raise ValueError("Categorías de Omega inválidas")
    product["sourceCategory"] = categories[-1].strip() if categories else ""
    if re.search(r"\b(?:gaming|gamer)\b", normalized(description + " " + source.get("name", ""))):
        product["collections"] = ["Zona Gamer"]
    if source.get("price") is None:
        product["priceUnavailable"] = True
    else:
        public_price = _positive_price(source["price"], "fuente")
        product["price"] = _public_price(policy.sale_price(public_price))
        product["stock"] = source["stock"]
        # Both ends of an offer use the same private policy. Remove an old price
        # when crossing a pricing band eliminates the final public discount.
        if source.get("oldPrice") is not None:
            old_public = _positive_price(source["oldPrice"], "anterior de fuente")
            if old_public > public_price:
                old_sale = _public_price(policy.sale_price(old_public))
                if old_sale > product["price"]:
                    product["old"] = old_sale
    if content_conflict:
        product.update(stock=False, description="", spec="", specifications=[], features=[],
                       sourceContentConflict=True, specificationNote="Modelo pendiente de confirmación.")
        product.pop("model", None)
    detail_fields = ("description", "model", "specifications", "features",
                     "specificationSources")
    unchanged = all(previous.get(field) == product.get(field) for field in detail_fields)
    product["specificationsUpdated"] = (previous.get("specificationsUpdated")
                                        if unchanged and previous.get("specificationsUpdated")
                                        else timestamp)
    return product


def _missing_product(previous):
    category = previous.get("category")
    if category not in MAIN_CATEGORIES:
        raise ValueError("Categoría existente inválida para una ficha ausente")
    return {
        "id": previous["id"], "reference": previous["reference"],
        "name": _text(previous.get("name"), "nombre existente"),
        "spec": "", "category": category,
        "subcategory": _text(previous.get("subcategory"), "subcategoría existente"),
        "brand": _text(previous.get("brand"), "marca existente"),
        "price": None, "stock": False, "image": PLACEHOLDER, "sourceImage": "",
        "description": "", "specifications": [], "features": [],
        "specificationSources": [], "sourceCategory": "", "collections": [],
        "sourceUnavailable": True, "priceUnavailable": True,
    }


def validate_catalog(catalog):
    """Reject accidental private fields and malformed public records."""
    if not isinstance(catalog, dict) or set(catalog) - PUBLIC_CATALOG_FIELDS:
        raise ValueError("Metadatos públicos de catálogo inválidos")
    if catalog.get("source") != "Omega Tech — catálogo público":
        raise ValueError("La fuente pública del catálogo debe ser Omega")
    _text(catalog.get("updated"), "updated")
    products = catalog.get("products")
    if not isinstance(products, list) or not products or catalog.get("count") != len(products):
        raise ValueError("Conteo público de catálogo inválido")
    ids, references = set(), set()
    for product in products:
        if not isinstance(product, dict) or set(product) - PUBLIC_PRODUCT_FIELDS:
            raise ValueError("Campos públicos de producto inválidos")
        pid, reference = product.get("id"), product.get("reference")
        if not isinstance(pid, str) or not pid.isdigit() or pid in ids or pid in EXCLUDED_IDS:
            raise ValueError("ID inválido, duplicado o retirado")
        _reference(reference)
        if reference in references or reference in EXCLUDED_REFERENCES:
            raise ValueError("Referencia duplicada o retirada")
        ids.add(pid)
        references.add(reference)
        for field in ("name", "category", "subcategory", "brand"):
            _text(product.get(field), field)
        if product["category"] not in MAIN_CATEGORIES:
            raise ValueError("Categoría pública inválida")
        if not isinstance(product.get("stock"), bool):
            raise ValueError("Disponibilidad pública inválida")
        if product.get("price") is None:
            if product["stock"]:
                raise ValueError("Un producto sin precio no puede venderse")
            if not (product.get("sourceUnavailable") is True or product.get("priceUnavailable") is True):
                raise ValueError("Un producto sin precio debe indicar su ausencia")
        else:
            if type(product["price"]) not in (int, float):
                raise ValueError("Precio público debe ser numérico")
            _positive_price(product["price"], "venta pública")
        if "old" in product:
            if type(product["old"]) not in (int, float):
                raise ValueError("Precio anterior debe ser numérico")
            _positive_price(product["old"], "venta pública anterior")
            if product.get("price") is None or product["old"] <= product["price"]:
                raise ValueError("Oferta pública inválida")
        image = _text(product.get("image"), "image")
        if not image.startswith("img/catalogo/") or ".." in image.split("/"):
            raise ValueError("Imagen pública debe ser local")
        if "imageUnavailable" in product:
            if not isinstance(product["imageUnavailable"], bool):
                raise ValueError("Estado público de imagen inválido")
            if product["imageUnavailable"] and image != PLACEHOLDER:
                raise ValueError("Una imagen ausente debe usar el marcador local")
        for field in ("sourceUnavailable", "priceUnavailable", "sourceContentConflict"):
            if field in product and not isinstance(product[field], bool):
                raise ValueError("Estado público de producto inválido")
        if product.get("sourceContentConflict"):
            if (product["stock"] or product.get("description") or product.get("spec")
                    or product.get("model") or product.get("specifications") or product.get("features")):
                raise ValueError("Un modelo contradictorio debe quedar pendiente de confirmación")
        _image_url(product.get("sourceImage", ""))
        for url in product.get("specificationSources", []):
            _source_url(url, reference)
    missing = catalog.get("sourceMissingReferences", [])
    if (not isinstance(missing, list) or len(missing) != len(set(missing))
            or any(reference not in references for reference in missing)):
        raise ValueError("Referencias ausentes inválidas")
    return catalog


def build_catalog(existing, sources, policy, missing_confirmed=(), updated_at=None):
    """Return a public catalog, preserving selected identities and order.

    ``sources`` is keyed by the reference produced by omega_public.parse_product.
    Only explicit ``missing_confirmed`` references may lack a supplier record;
    network failures and incomplete responses must never be passed as missing.
    The function neither mutates the inputs nor writes files.
    """
    if not isinstance(existing, list) or not existing or not isinstance(sources, dict):
        raise ValueError("Selección de catálogo inválida")
    selected, ids, references = [], set(), set()
    for previous in existing:
        if not isinstance(previous, dict):
            raise ValueError("Selección de producto inválida")
        pid, reference = previous.get("id"), previous.get("reference")
        if not isinstance(pid, str) or not pid.isdigit():
            raise ValueError("ID existente inválido")
        _reference(reference)
        if pid in EXCLUDED_IDS or reference in EXCLUDED_REFERENCES:
            continue
        if pid in ids or reference in references:
            raise ValueError("Selección con identidades duplicadas")
        ids.add(pid)
        references.add(reference)
        selected.append(previous)
    missing = set(missing_confirmed)
    if (not missing <= references or set(sources) - references
            or missing & set(sources) or set(sources) | missing != references):
        raise ValueError("Las fuentes no coinciden con la selección exacta")
    timestamp = updated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    timestamp = _text(timestamp, "updated")
    products = [_missing_product(previous) if previous["reference"] in missing
                else _product(previous, sources[previous["reference"]], policy, timestamp)
                for previous in selected]
    catalog = {"source": "Omega Tech — catálogo público", "count": len(products),
               "products": products, "updated": _text(timestamp, "updated")}
    if missing:
        catalog["sourceMissingReferences"] = sorted(missing, key=int)
    return validate_catalog(catalog)
