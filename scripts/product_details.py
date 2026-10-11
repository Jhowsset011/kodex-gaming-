"""Build product details from explicit supplier text and reviewed maker fichas.

This module never retrieves pages, changes identities, prices or availability,
or infers specifications from a model number.  Reviewed manufacturer records
are bound to the exact selected product before any catalog mutation occurs.
"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit


def clean_part_number(value: str) -> str:
    """Remove only distributor annotations, keeping variant/region suffixes."""
    value = str(value).strip()
    for _ in range(2):
        value = re.sub(r"\*+$", "", value).strip()
        value = re.sub(r"\s+CANAL$", "", value, flags=re.I).strip()
    return value


def _identity(value: str, *, part=False) -> str:
    value = clean_part_number(value) if part else value.strip()
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", "", value) if part else re.sub(r"\s+", " ", value)


def _key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).casefold().split())


def _string(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Detalle de producto inválido: {field}")
    return value.strip()


def _https_url(value) -> str:
    value = _string(value, "source")
    try:
        parts = urlsplit(value)
        valid = (parts.scheme == "https" and parts.hostname and not parts.username
                 and not parts.password and parts.port in (None, 443))
    except ValueError:
        valid = False
    if not valid or any(c.isspace() for c in value):
        raise ValueError("La ficha oficial requiere una fuente HTTPS válida")
    return value


def _reviewed_entries(path: Path | None, products: list[dict]) -> dict:
    if path is None:
        return {}
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("No se pudo leer el archivo de fichas oficiales") from exc
    if not isinstance(document, dict) or set(document) != {"products"} or not isinstance(document["products"], dict):
        raise ValueError("Archivo de fichas oficiales inválido")
    by_id = {product["id"]: product for product in products}
    output = {}
    fields = {"reference", "model", "brand", "description", "specifications", "features", "sources"}
    for pid, entry in document["products"].items():
        if not isinstance(entry, dict) or set(entry) - fields or pid not in by_id:
            raise ValueError("Ficha oficial desconocida o inválida")
        product = by_id[pid]
        if product.get("sourceUnavailable") or product.get("sourceContentConflict"):
            raise ValueError("No se puede enriquecer una identidad pendiente de confirmación")
        for field in ("reference", "model", "brand"):
            actual = _string(product.get(field), field)
            expected = _string(entry.get(field), field)
            if _identity(actual, part=field == "model") != _identity(expected, part=field == "model"):
                raise ValueError(f"La ficha oficial no coincide con {field} del producto {pid}")
        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError("La ficha oficial requiere fuentes")
        reviewed = {"sources": list(dict.fromkeys(_https_url(url) for url in sources))}
        if "description" in entry:
            reviewed["description"] = _string(entry["description"], "description")
        rows = entry.get("specifications", [])
        if not isinstance(rows, list):
            raise ValueError("Especificaciones oficiales inválidas")
        reviewed["specifications"] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != {"label", "value"}:
                raise ValueError("Fila oficial inválida")
            label, value = _string(row["label"], "label"), _string(row["value"], "value")
            if re.search(r"precio|costo|descuento|garantia|envio", _key(label)):
                raise ValueError("Las fichas técnicas no deben importar precios ni políticas comerciales")
            reviewed["specifications"].append({"label": label, "value": value})
        features = entry.get("features", [])
        if not isinstance(features, list):
            raise ValueError("Características oficiales inválidas")
        reviewed["features"] = [_string(feature, "feature") for feature in features]
        output[pid] = reviewed
    return output


_TECH_WORDS = (
    "USB", "HDMI", "VGA", "DVI", "RJ", "LAN", "KVM", "HDR", "HDR10", "HDR10+",
    "FHD", "QHD", "UHD", "WQHD", "WUXGA", "IPS", "VA", "TN", "OLED", "LED", "LCD",
    "SSD", "HDD", "RAM", "DDR3", "DDR4", "DDR5", "GDDR6", "GDDR7", "SATA", "RGB",
    "ARGB", "PWM", "ATX", "ITX", "MATX", "MITX", "CPU", "GPU", "RTX", "GTX", "TWS", "PCAP", "PD",
    "GB", "TB", "MB", "NVME", "PCIE", "M.2", "HP", "MSI", "AOC", "AMD", "DVD", "DPI",
)


def _readable(text: str, product: dict) -> str:
    """Sentence case supplier prose while preserving codes and technical units."""
    text = re.sub(r"[ \t]+", " ", text.strip())
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > .65:
        codes = {}
        # Restore the exact original spelling of model/capacity/version tokens.
        for match in re.finditer(r"\b[A-Z][A-Z0-9]*(?:[-/#][A-Z0-9]+)+\b|\b[A-Z]{1,6}\d+[A-Z0-9+]*\b|\b\d{3,}[A-Z]+\b", text):
            codes[match.group().casefold()] = match.group()
        text = text.lower()
        for token in _TECH_WORDS:
            text = re.sub(r"(?<!\w)" + re.escape(token) + r"(?!\w)", token, text, flags=re.I)
        for folded, original in sorted(codes.items(), key=lambda item: -len(item[0])):
            text = re.sub(re.escape(folded), lambda _: original, text, flags=re.I)
        for field in ("brand", "model"):
            token = clean_part_number(product.get(field, ""))
            if token:
                text = re.sub(re.escape(token), lambda _: token, text, flags=re.I)
        for before, after in (("nvme", "NVMe"), ("pcie", "PCIe"), ("ghz", "GHz"), ("mhz", "MHz"),
                              ("hz", "Hz"), ("mah", "mAh"), ("mb/s", "MB/s"), ("gbps", "Gbps"),
                              ("bluetooth", "Bluetooth"), ("displayport", "DisplayPort"), ("windows", "Windows")):
            text = re.sub(r"(?<![a-z])" + re.escape(before) + r"(?![a-z])", after, text, flags=re.I)
        text = re.sub(r"(?<=\d)(\s*)(gb|tb|mb|w)\b", lambda m: m[1] + m[2].upper(), text, flags=re.I)
        text = re.sub(r"(^|[.!?]\s+|\n+)([a-záéíóúñ])", lambda m: m[1] + m[2].upper(), text)
    text = re.sub(r"\s*\|\s*", ".\n", text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _number(value: str) -> str:
    return value.replace(",", ".")


def _technical_rows(product: dict, text: str) -> list[dict]:
    rows = []
    seen = set()

    def add(label, value):
        value = str(value).strip()
        if value and _key(label) not in seen:
            rows.append({"label": label, "value": value})
            seen.add(_key(label))

    add("Marca", product["brand"])
    if product.get("model"):
        add("Número de parte", clean_part_number(product["model"]))
    add("Tipo", product.get("subcategory") or product["category"])
    upper = text.upper()
    screen = product["category"] in {"Monitores", "Laptops"} or bool(re.search(r"\bTELEVISOR\b", upper))
    if screen:
        size = re.search(r'\b(\d{1,2}(?:[.,]\d)?)\s*(?:["”]|PULGADAS?\b|INCH(?:ES)?\b)', upper)
        if size and 5 <= float(_number(size[1])) <= 99:
            add("Tamaño de pantalla", _number(size[1]) + '"')
        resolution = re.search(r"\b([1-9][\d,]{2,4})\s*[X×*]\s*([1-9][\d,]{2,4})\b", upper)
        if resolution and min(int(resolution[1].replace(",", "")), int(resolution[2].replace(",", ""))) >= 400:
            add("Resolución", f'{resolution[1].replace(",", "")} × {resolution[2].replace(",", "")}')
        else:
            quality = re.search(r"\b(?:WQHD|WUXGA|QHD|FHD|UHD|4K|2K|1080P|720P)\b", upper)
            if quality:
                add("Resolución indicada", quality[0])
        panel = re.search(r"\b(?:QD[- ]OLED|OLED|RAPID IPS|RAPID VA|IPS|VA|TN)\b", upper)
        if panel:
            add("Panel", panel[0].replace("RAPID", "Rapid"))
        curved = re.search(r"\bCURV[OA](?:S)?\b(?:\s+(?:RADIO\s*)?\d{3,4}R)?", upper)
        if curved and not re.search(r"\b(?:NO|SIN|NOT)\s+$", upper[max(0, curved.start() - 10):curved.start()]):
            add("Diseño", curved[0].capitalize())
        elif re.search(r"\b(?:FLAT|PLANO|PLANA)\b", upper):
            add("Diseño", "Plano")
        refresh = re.search(r"\b(\d{2,3})\s*HZ\b", upper)
        if refresh:
            add("Tasa de refresco", refresh[1] + " Hz")
        response = re.search(r"\b(\d+(?:[.,]\d+)?)\s*MS\b", upper)
        if response:
            add("Tiempo de respuesta", _number(response[1]) + " ms")
        brightness = re.search(r"\b(\d+)\s*CD\s*/\s*M[²2]\b", upper)
        if brightness:
            add("Brillo", brightness[1] + " cd/m²")

    ports = []
    port_pattern = re.compile(
        r"(?:(\d{1,2})\s*[X×]\s*|(\d{1,2}|UN|UNA|DOS|TRES)\s+(?:PUERTOS?\s+)?)?"
        r"\b(HDMI(?:\s*\d(?:\.\d+)?[AB]?)?|DISPLAYPORT(?:\s*\d(?:\.\d+)?[AB]?)?|"
        r"USB(?:[- ](?:A|C))?(?:\s*(?:TYPE[- ]?[AC]))?(?:\s*\d(?:\.\d+)?(?:\s*GEN\s*\d)?)?|"
        r"TYPE[- ]C(?:\s*\d(?:\.\d+)?)?|DVI(?:[- ][DI])?|VGA|RJ[- ]?45|ETHERNET)\b"
        r"(?:\s*[X×]\s*(\d{1,2}))?", re.I)
    counts = {"UN": "1", "UNA": "1", "DOS": "2", "TRES": "3"}
    for match in port_pattern.finditer(upper):
        prefix = match[1] or match[2] or match[4]
        prefix = counts.get(prefix, prefix)
        port = re.sub(r"\s+", " ", match[3])
        port = port.replace("DISPLAYPORT", "DisplayPort")
        rendered = (prefix + " × " if prefix else "") + port
        if rendered not in ports:
            ports.append(rendered)
    if ports:
        add("Conectividad", "; ".join(ports))
    if re.search(r"\b(?:AUDIO\s+JACK|AUX|JACK)\s*(?:DE\s*)?3[.,]5\s*(?:MM)?\b|\b3[.,]5\s*MM\s*JACK\b", upper):
        add("Conexión de audio", "Jack de 3.5 mm")
    bluetooth = re.search(r"\bBLUETOOTH(?:\s*(\d(?:\.\d)?))?\b", upper)
    if bluetooth:
        add("Bluetooth", bluetooth[1] or "Indicado por el proveedor")
    wireless = re.search(r"\bWI[- ]?FI(?:\s*(\dE?|802\.11[A-Z]+))?\b", upper)
    if wireless:
        add("Wi-Fi", wireless[1] or "Indicado por el proveedor")

    computing = product["category"] in {"Laptops", "Computadoras"}
    if computing:
        processor = re.search(r"\b(?:INTEL\s+)?CORE\s+(?:ULTRA\s+[3579](?:\s+\d+[A-Z0-9]*)?|I[3579](?:[- ]\d+[A-Z0-9]*)?)|"
                              r"\bAMD\s+RYZEN\s+[3579](?:\s+\d+[A-Z0-9]*)?|\b(?:INTEL\s+)?(?:CELERON|PENTIUM)(?:\s+[A-Z]?\d+[A-Z0-9]*)?", upper)
        if processor:
            add("Procesador", processor[0])
        ram_patterns = (
            r"\b(?:RAM|MEMORIA(?:\s+RAM)?(?:\s+DDR[345])?)\s*(?:DE\s*)?(\d+(?:[.,]\d+)?)\s*(GB|MB)\b",
            r"\b(\d+(?:[.,]\d+)?)\s*(GB|MB)\s*(?:DDR[345]|RAM|SODIMM)\b",
        )
        for pattern in ram_patterns:
            ram = re.search(pattern, upper)
            if ram:
                add("Memoria RAM", _number(ram[1]) + " " + ram[2])
                break
        storage_patterns = (
            r"\b(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)\s*(?:SSD|HDD|NVME|FLASH)\b",
            r"\b(?:SSD|HDD|NVME|DISCO(?:\s+DURO)?)\s*(?:DE\s*)?(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)\b",
        )
        for pattern in storage_patterns:
            storage = re.search(pattern, upper)
            if storage:
                add("Almacenamiento", _number(storage[1]) + " " + storage[2])
                break
        operating = re.search(r"\bWINDOWS\s+(?:10|11)\s*(?:PRO|HOME)?(?:\s*64\s*BITS)?", upper)
        if operating:
            add("Sistema operativo", operating[0].strip().replace("WINDOWS", "Windows"))

    if product["category"] == "Almacenamiento":
        capacity = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(TB|GB)\b", upper)
        if capacity:
            add("Capacidad", _number(capacity[1]) + " " + capacity[2])
        interface = re.findall(r"\b(?:SATA(?:\s*(?:REV\.?\s*)?\d(?:\.\d+)?)?|NVME|PCIE(?:\s*\d(?:\.\d+)?(?:\s*X\d)?)?)\b", upper)
        if interface:
            add("Interfaz de almacenamiento", "; ".join(dict.fromkeys(interface)))
        for label, pattern in (("Velocidad de lectura", r"(?:LECTURA\s*:?\s*(\d+)\s*MB\s*/\s*(?:S|SEG)|\b(\d+)\s*MB\s*/\s*S\s*LECTURA)"),
                               ("Velocidad de escritura", r"(?:ESCRITURA\s*:?\s*(\d+)\s*MB\s*/\s*(?:S|SEG)|\b(\d+)\s*MB\s*/\s*S\s*ESCRITURA)")):
            speed = re.search(pattern, upper)
            if speed:
                add(label, next(value for value in speed.groups() if value) + " MB/s")
    memory_type = re.search(r"\b(?:GDDR[567]|DDR[345])\b", upper)
    if memory_type:
        add("Tipo de memoria", memory_type[0])
    socket = re.search(r"\bSOCKET\s*(?:[:/-]\s*)?(AM[345]|LGA\s*\d+|\d{3,4})\b", upper)
    if socket:
        add("Socket", socket[1])
    case_format = re.search(r"\b(?:MID[- ]TOWER|MINI[- ]TOWER|FULL[- ]TOWER|MICRO[- ]ATX|MINI[- ]ITX|MATX|MITX|ATX)\b", upper)
    if case_format:
        add("Formato indicado", case_format[0])
    if re.search(r"\b(?:FUENTE|POWER SUPPLY|POWER ADAPTER|BOCINAS?|SPEAKER)\b", upper):
        watts = re.search(r"\b(\d+(?:[.,]\d+)?)\s*W(?:ATTS)?\b", upper)
        if watts:
            add("Potencia indicada", _number(watts[1]) + " W")
    dpi = re.search(r"\b(\d+)\s*DPI\b", upper)
    if dpi:
        add("Resolución del sensor", dpi[1] + " DPI")
    buttons = re.search(r"\b(\d+)\s*BOTONES\b", upper)
    if buttons:
        add("Botones", buttons[1])
    battery = re.search(r"\b(\d+)\s*MAH\b", upper)
    if battery:
        add("Capacidad de batería", battery[1] + " mAh")
    return rows


def _row_key(label: str) -> str:
    key = _key(label)
    return {
        'tipo de panel': 'panel',
        'frecuencia de actualizacion': 'tasa de refresco',
        'frecuencia de refresco': 'tasa de refresco',
        'potencia indicada': 'potencia',
        'formato indicado': 'formato',
        'cantidad de botones': 'botones',
        'numero de botones': 'botones',
        'resolucion de sensor': 'resolucion del sensor',
        'resolucion dpi': 'resolucion del sensor',
        'dimensiones del producto': 'dimensiones',
        'peso del producto': 'peso',
        'anchura': 'ancho',
        'conectividad de video': 'conectividad',
    }.get(key, key)


def _merge_rows(base: list[dict], extra: list[dict]) -> list[dict]:
    output = deepcopy(base)
    positions = {_row_key(row["label"]): i for i, row in enumerate(output)}
    for row in extra:
        key = _row_key(row["label"])
        if key in positions:
            output[positions[key]] = dict(row)
        else:
            positions[key] = len(output)
            output.append(dict(row))
    return output


def _align_button_count(text: str, official_rows: list[dict]) -> str:
    for row in official_rows:
        if _row_key(row['label']) != 'botones':
            continue
        match = re.fullmatch(r'(\d+)(?:\s+botones)?', row['value'], re.I)
        if match:
            text = re.sub(r'\b\d+\s+(botones|buttons)\b',
                          lambda found: match[1] + ' ' + found[1], text, flags=re.I)
    return text


def enrich_catalog(catalog: dict, curated_path: Path | None = None) -> dict:
    """Mutate and return a catalog after validating all reviewed identities.

    Manufacturer host allowlists remain the publisher's responsibility.  This
    layer validates HTTPS URLs and exact identity matches before adding sources.
    """
    if not isinstance(catalog, dict) or not isinstance(catalog.get("products"), list):
        raise ValueError("Catálogo inválido para enriquecer")
    reviewed = _reviewed_entries(curated_path, catalog["products"])
    output = deepcopy(catalog["products"])
    for product in output:
        if product.get("sourceUnavailable") or product.get("sourceContentConflict"):
            continue
        text = product.get("description") or product.get("spec") or ""
        if not isinstance(text, str):
            raise ValueError("Texto del proveedor inválido")
        official = reviewed.get(product["id"], {}).get("description")
        if official and text.startswith(official + "\n\n"):
            # The previous enrichment already prepended this exact reviewed
            # manufacturer description; retain the supplier paragraph once.
            text = text[len(official) + 2:]
        if product['id'] in reviewed:
            official_rows = reviewed[product['id']]['specifications']
            text = _align_button_count(text, official_rows)
            product['name'] = _align_button_count(product['name'], official_rows)
        rows = _technical_rows(product, text)
        # Preserve separately supplied technical rows, but do not repeat the
        # supplier's full paragraph as a specification named "Información".
        existing_rows = []
        generated = {_key(row["label"]) for row in rows}
        for row in product.get("specifications", []):
            label = row.get("label", "")
            if (_key(label) in generated or _key(label) == "informacion del producto"
                    or len(label) > 60 or re.match(r"(?i)^(?:monitor|televisor|laptop|soporte para tv)\b", label)):
                continue
            existing_rows.append(row)
        product["description"] = _readable(text, product)
        product["specifications"] = _merge_rows(rows, existing_rows)
        features = list(product.get("features", []))
        # An accessory is only listed when the source explicitly says includes
        # or does not include it.  Manufacturer defaults are never inferred.
        for match in re.finditer(r"\b(?:NO\s+)?INCLUYE\b[^.\n]+", text, flags=re.I):
            value = _readable(match[0].rstrip(" ,;"), product)
            if not any(_key(value) == _key(_readable(item, product)) for item in features):
                features.append(value)
        product["features"] = [_readable(item, product) for item in features]
        if product["id"] in reviewed:
            entry = reviewed[product["id"]]
            product["specifications"] = _merge_rows(product["specifications"], entry["specifications"])
            if entry.get("description"):
                product["description"] = entry["description"] + ("\n\n" + product["description"] if product["description"] else "")
            product["features"] = list(dict.fromkeys(product["features"] + entry["features"]))
            product["specificationSources"] = list(dict.fromkeys(product.get("specificationSources", []) + entry["sources"]))
    catalog["products"] = output
    return catalog
