#!/usr/bin/env python3
"""Sync the owner's selected Nexcom IDs; Omega account prices are not consulted.

The repository is the source of existing enrichment, never the deployed website.
Network/validation failures leave the last valid catalog untouched.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import html
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
API = "https://nexcomtienda.com.do/wp-json/wc/store/v1/products"
PLACEHOLDER = "img/catalogo/sin-imagen.svg"
BRANDS = (
    "Western Digital", "Cooler Master", "Klip Xtreme", "Logitech", "TP-Link",
    "Redragon", "SteelSeries", "HyperX", "ViewSonic", "Ubiquiti", "Tripp Lite",
    "CyberPower", "Samsung", "Kingston", "Seagate", "Lenovo", "Dell", "AOC",
    "ASUS", "Gigabyte", "Corsair", "Razer", "Dahua", "Hikvision", "Cisco",
    "Intel", "AMD", "NVIDIA", "EVGA", "Zotac", "PNY", "Thermaltake", "Antec",
    "XPG", "ADATA", "Crucial", "SanDisk", "Lexar", "Verbatim", "Hiksemi",
    "Genius", "Forza", "Nexxt", "Manhattan", "StarTech", "Vention", "Ugreen",
    "Baseus", "Anker", "JBL", "Sony", "Edifier", "Bose", "BenQ", "LG",
    "Philips", "Apple", "Microsoft", "Epson", "Canon", "Brother", "D-Link",
    "Tenda", "APC", "Eaton", "HPE", "HP", "Grandstream", "Xtech", "Argom",
    "Agiler", "Myo", "MSI", "Primus", "Markvision", "Sonos", "Vitek", "Elo",
    "Rippa", "Maxtor", "Roku", "Huawei", "Haier", "ECS", "Titan", "Klipsch",
)
ALIASES = {"klipx": "Klip Xtreme", "thinkvision": "Lenovo", "thinkpad": "Lenovo", "ideapad": "Lenovo"}
COMPONENT_BRANDS = {"Intel", "AMD", "NVIDIA"}
CATEGORY_RULES = [
    (r"^monitor\b|^pantalla interactiva\b", "Monitores"),
    (r"^(?:laptop|notebook|portatil)\b|^lenovo thinkpad\b", "Laptops"),
    (r"^(?:computadora|mini pc|desktop)\b", "Computadoras"),
    (r"^(?:silla|escritorio)\b", "Mobiliario"),
    (r"^(?:disco|ssd|hdd|dvd|cd|pack \d+ dvd|caja (?:para disco|usb))\b|^memoria\s+(?:usb|micro|sd)\b", "Almacenamiento"),
    (r"^(?:smart tv|televisor|bocina|bocinas|audifono|audifonos|soundbar|sound bar|subwoofer|barra de sonido|streaming|soporte tv|consola (?:streamer|de control))\b", "Audio y Video"),
    (r"^(?:case|gabinete|power supply|fuente|placa madre|motherboard|mb|memoria|procesador|tarjeta (?:de video|msi|grafica)|abanico|ventilador|ventiladores|disipador|cooler|cpu liquid cooler|refrigeracion|enfriamiento|sistema enfriamiento|controladora)\b", "Componentes"),
    (r"^(?:mouse|teclado|combo|camara web|gamepad|control gamer|puntero|funda|candado|pedales|volante)\b", "Periféricos"),
]


def normalized(value):
    import unicodedata
    value = html.unescape(value or "").replace("″", '"').replace("”", '"').replace("′′", '"')
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).casefold()


def brand_of(name, fallback="Genérico"):
    candidates = []
    for token, brand in [(b, b) for b in BRANDS] + list(ALIASES.items()):
        match = re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", name, re.I)
        if match:
            candidates.append((match.start(), -len(token), brand))
    makers = [match for match in candidates if match[2] not in COMPONENT_BRANDS]
    if makers or candidates:
        return min(makers or candidates)[2]
    return ALIASES.get(fallback.casefold(), fallback) or "Genérico"


def subcategory_path(product):
    """Three child levels, inferred only from the name and supplied specifications.

    Model numbers alone never establish screen sizes, capacities or sockets.
    Missing characteristics remain explicit rather than being guessed.
    """
    name = normalized(product["name"])
    facts = product.get("specifications", [])

    def evidence(labels):
        values = [row.get("value", "") for row in facts
                  if re.search(labels, normalized(row.get("label", ""))) and not row.get("sourceValue")]
        return name + " " + normalized(" ".join(values))

    def find(pattern, text, suffix="", fallback="Por confirmar"):
        match = re.search(pattern, text)
        return match.group(1).upper().replace(",", ".") + suffix if match else fallback

    def size():
        return find(r"\b(\d{1,2}(?:[.,]\d)?)\s*(?:[\"″”]|pulg|inch)", evidence(r"pantalla|tamano|diagonal"), " pulgadas", "Tamaño por confirmar")

    def capacity():
        value = find(r"\b(\d+(?:[.,]\d+)?\s*(?:tb|gb|mb))(?!\w|\s*/)", evidence(r"capacidad|almacenamiento|memoria de video"), fallback="Capacidad por confirmar")
        return value.replace(" ", "") if value != "Capacidad por confirmar" else value

    def connection():
        text = evidence(r"conectividad|conexion|interfaz|tipo de conexion")
        if re.search(r"\bbluetooth\b|\bbt\b", text):
            return "Bluetooth"
        if re.search(r"inalambr|wireless|\b2[.,]4\s*g", text):
            return "Inalámbricos"
        if re.search(r"\busb\b|alambrico|wired|con cable", text):
            return "Con cable"
        return "Conexión por confirmar"

    def color():
        text = evidence(r"^color$")
        for pattern, label in [(r"blanco|white", "Blanco"), (r"negro|black", "Negro"), (r"rosado|rosa|pink", "Rosado"), (r"azul|blue", "Azul"), (r"gris|gray|grey|grafito|graphite", "Gris / grafito"), (r"rojo|red", "Rojo")]:
            if re.search(r"\b(?:" + pattern + r")\b", text):
                return label
        return "Color por confirmar"

    def processor():
        text = evidence(r"procesador|cpu")
        if "xeon" in text:
            return "Intel Xeon"
        if "ryzen" in text:
            return "AMD Ryzen"
        if re.search(r"intel|core|\bi[3579]\b|j4125", text):
            return "Intel"
        if re.search(r"\bamd\b", text):
            return "AMD"
        return "Procesador por confirmar"

    cat = product["category"]
    if cat == "Monitores":
        kind = "Interactivos" if "pantalla interactiva" in name else "Portátiles" if "portatil" in name else "Táctiles" if re.search(r"touch|tactil", evidence(r"pantalla|tipo")) else "Curvos" if re.search(r"curv", evidence(r"pantalla|curvatura|diseno")) else "De escritorio"
        text = evidence(r"panel|tecnologia de pantalla|tipo de pantalla")
        panel = next((label for token, label in [("oled", "OLED"), ("ips", "IPS"), ("va", "VA"), ("tn", "TN")] if re.search(r"\b" + token + r"\b", text)), "Panel por confirmar")
        return [kind, panel, size()]
    if cat == "Almacenamiento":
        if re.search(r"^caja\b", name):
            return ["Cajas para discos", find(r"\b([23][.,]5)\b", name, " pulgadas", "Formato por confirmar"), find(r"\b(usb\s*[234](?:[.,]\d)?)\b", name, fallback="Interfaz por confirmar")]
        if re.search(r"\bdvd|^cd|^pack", name):
            return ["Discos ópticos", "DVD" if "dvd" in name else "CD", capacity()]
        if re.search(r"^memoria\s+(?:micro|sd)", name):
            return ["Tarjetas de memoria", "MicroSD" if "microsd" in name or "micro sd" in name else "Micro M2" if "m2" in name else "SD", capacity()]
        if re.search(r"^memoria usb", name):
            return ["Memorias USB", find(r"\b(usb\s*[234](?:[.,]\d)?)\b", name, fallback="USB"), capacity()]
        ssd = bool(re.search(r"\bssd\b|estado solido", name))
        if ssd:
            text = evidence(r"interfaz|conexion|tipo de disco")
            interface = "NVMe" if "nvme" in text else "SATA" if "sata" in text else "USB" if "usb" in text else "Interfaz por confirmar"
        else:
            text = evidence(r"tipo de disco|ubicacion|formato")
            interface = "Externos" if "extern" in text else "Internos" if "intern" in text else "Ubicación por confirmar"
        return ["SSD" if ssd else "Discos duros", interface, capacity()]
    if cat == "Componentes":
        if re.search(r"^(?:abanico|ventilador|disipador|cooler|cpu liquid cooler|refrigeracion|enfriamiento|sistema enfriamiento|controladora)", name):
            kind = "Líquida" if re.search(r"liquid|liquid[ao]|\baio\b", name) else "Ventiladores" if re.search(r"^(?:abanico|ventilador)", name) else "Controladoras" if "controladora" in name else "Disipadores"
            return ["Refrigeración", kind, find(r"\b(\d{2,3})\s*mm\b", evidence(r"tamano|radiador|dimension"), " mm", "Tamaño por confirmar")]
        if re.search(r"^(?:case|gabinete)", name):
            text = evidence(r"formato|tipo de gabinete|tamano")
            kind = "Mini Tower" if re.search(r"mini[- ]tower", text) else "Mid Tower" if re.search(r"mid[- ]tower", text) else "Full Tower" if re.search(r"full[- ]tower", text) else "Micro-ATX" if re.search(r"micro[- ]?atx", text) else "Formato por confirmar"
            return ["Gabinetes", kind, color()]
        if re.search(r"^(?:power supply|fuente)", name):
            text = evidence(r"certificacion|eficiencia")
            certificate = next(("80 Plus " + v.title() for v in ("titanium", "platinum", "gold", "silver", "bronze") if re.search(r"\b"+v+r"\b", text)), "80 Plus Bronze" if "80 plus bronce" in text else "80 Plus" if "80 plus" in text else "Certificación por confirmar")
            return ["Fuentes de poder", certificate, find(r"\b(\d{3,4})\s*(?:w\b|watts?\b)", evidence(r"potencia"), " W", "Potencia por confirmar")]
        if re.search(r"^(?:mb|motherboard|placa madre)", name):
            socket = find(r"\b(lga\s*\d{3,4}|am[345]|fm[12])\b", evidence(r"socket|zócalo|plataforma"), fallback="Socket por confirmar")
            platform = "Intel" if "intel" in name or socket.startswith("LGA") else "AMD" if "amd" in name or re.match(r"[AF]M", socket) else "Plataforma por confirmar"
            return ["Placas madre", platform, socket]
        if name.startswith("memoria"):
            technology = find(r"\b(ddr\s*[2345])\b", evidence(r"tipo|tecnologia"), fallback="Tecnología por confirmar")
            return ["Memoria RAM", technology.replace(" ", "") if technology != "Tecnología por confirmar" else technology, capacity()]
        if name.startswith("procesador"):
            return ["Procesadores", processor(), find(r"\b(core\s+(?:i[3579]|ultra\s*[579])|ryzen\s*[3579]|xeon)\b", name, fallback="Familia por confirmar")]
        if name.startswith("tarjeta"):
            family = "NVIDIA GeForce" if re.search(r"geforce|\brtx\b|\bgtx\b", name) else "AMD Radeon" if "radeon" in name else "Familia por confirmar"
            return ["Tarjetas de video", family, capacity()]
        return ["Otros componentes", "Accesorios", "Características por confirmar"]
    if cat == "Periféricos":
        if re.search(r"^mouse pad", name):
            kind = "Con gel" if "gel" in name else "Extendidos" if re.search(r"extended|extendid|desk mat", name) else "Superficies para mouse"
            return ["Mouse pads", kind, color()]
        if name.startswith("mouse"):
            kind = "Verticales" if "vertical" in name else "Ergonómicos" if "ergonom" in name else "Ópticos" if re.search(r"optic", name) else "Mouse"
            return ["Mouse", connection(), kind]
        if name.startswith(("teclado", "combo")):
            combo = name.startswith("combo") or "mouse" in name
            kind = "Español" if "espanol" in name else "Inglés" if re.search(r"ingles|english", name) else "Idioma por confirmar"
            return ["Combos de teclado y mouse" if combo else "Teclados", connection(), kind]
        if name.startswith("camara web"):
            resolution = next((label for pattern, label in [(r"4k|2160p", "4K"), (r"2k|qhd|1440p", "2K / QHD"), (r"fhd|full hd|1080p", "Full HD"), (r"\bhd\b|720p", "HD")] if re.search(pattern, evidence(r"resolucion"))), "Resolución por confirmar")
            return ["Cámaras web", resolution, connection()]
        kind = "Pedales" if name.startswith("pedales") else "Volantes" if name.startswith("volante") else "Controles" if re.search(r"^gamepad|^control", name) else "Fundas para laptop" if name.startswith("funda") else "Candados" if name.startswith("candado") else "Presentadores"
        return ["Accesorios", kind, size() if name.startswith("funda") else connection()]
    if cat == "Audio y Video":
        if re.search(r"^audifono", name):
            return ["Audífonos", "In-ear" if "in-ear" in name else "Audífonos con micrófono" if "microfono" in name else "Audífonos", connection()]
        if re.search(r"^sound ?bar|^barra de sonido", name):
            return ["Barras de sonido", find(r"\b([2357][.,][012])\b", name, " canales", "Canales por confirmar"), connection()]
        if name.startswith("subwoofer"):
            return ["Subwoofers", connection(), color()]
        if name.startswith("bocina"):
            kind = "Portátiles" if re.search(r"portatil|recargable", name) else "Bluetooth" if "bluetooth" in name else "Para escritorio"
            return ["Bocinas", kind, find(r"\b([25][.,][01])\b", name, " canales", "Canales por confirmar")]
        if re.search(r"^smart tv|^televisor", name):
            text = evidence(r"resolucion")
            return ["Televisores", "4K" if re.search(r"4k|uhd", text) else "Full HD" if re.search(r"fhd|full hd|1080", text) else "Resolución por confirmar", size()]
        kind = "Streaming" if name.startswith("streaming") else "Soportes para TV" if name.startswith("soporte") else "Consolas para streaming"
        return ["Accesorios de audio y video", kind, connection()]
    if cat in ("Laptops", "Computadoras"):
        kind = "Convertibles 2 en 1" if re.search(r"2 en 1|2-in-1", name) else "Portátiles" if cat == "Laptops" else "Terminales" if re.search(r"terminal|wyse|thin client", name) else "Mini PC" if "mini pc" in name else "De escritorio"
        return [kind, processor(), size() if cat == "Laptops" else capacity()]
    if cat == "Mobiliario":
        return ["Sillas" if name.startswith("silla") else "Escritorios", "Gaming" if re.search(r"gamer|gaming", name) else "Para oficina", color()]
    return ["Otros productos", "Accesorios", "Características por confirmar"]


def classify(product):
    previous = product.get("sourceCategory", product.get("category", ""))
    product["sourceCategory"] = previous
    name = normalized(product["name"])
    product["category"] = next((category for pattern, category in CATEGORY_RULES if re.search(pattern, name)), product.get("category") or "Periféricos")
    product["brand"] = brand_of(product["name"], product.get("brand") or "Genérico")
    collections = set(product.get("collections", []))
    if previous == "Zona Gamer" or re.search(r"\b(?:gamer|gaming)\b", name):
        collections.add("Zona Gamer")
    product["collections"] = sorted(collections)
    product["subcategoryPath"] = subcategory_path(product)
    product.pop("subcategory", None)
    product.pop("subsubcategory", None)
    return product


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        if tag in ("div", "p", "li", "tr", "br", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")
        if tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("div", "p", "li", "tr", "h1", "h2", "h3", "h4"):
            self.parts.append("\n")

    def handle_data(self, value):
        if not self.skip:
            self.parts.append(value)


def lines(markup):
    parser = TextParser()
    parser.feed(markup or "")
    return [re.sub(r"\s+", " ", line).strip() for line in "".join(parser.parts).splitlines() if line.strip()]


def enrich(product, source):
    previous_details = {key: deepcopy(product.get(key)) for key in ("description", "specifications", "features", "model", "specificationSources")}
    reference = str(source.get("sku") or source["id"])
    if product.get("reference") and product["reference"] != reference:
        raise ValueError(f"La referencia cambió para el ID {product['id']}")
    product["reference"] = reference
    description = "\n\n".join(lines(source.get("short_description"))) or product.get("description") or product.get("spec", "")
    # Retailer warranty terms do not constitute Kodex's own warranty offer.
    product["description"] = re.sub(r"\s+y garantía oficial de \d+ años", "", description, flags=re.I)
    rows, features, seen = [], [], set()
    for line in lines(source.get("description")):
        line = re.sub(r"^[^\w]+", "", line).strip()
        if ":" in line:
            label, value = (part.strip() for part in line.split(":", 1))
            if label and value and len(label) < 80:
                if any(term in normalized(label) for term in ("garantia", "precio", "envio")):
                    continue
                if label.casefold() not in seen:
                    rows.append({"label": label, "value": value})
                    seen.add(label.casefold())
                continue
        if len(line) > 5 and "garantia" not in normalized(line):
            features.append(line)
    for attribute in source.get("attributes", []):
        label = html.unescape(attribute.get("name", ""))
        value = ", ".join(html.unescape(term.get("name", "")) for term in attribute.get("terms", []))
        if label and value and label.casefold() not in seen:
            rows.append({"label": label, "value": value})
            seen.add(label.casefold())
    if rows or features:
        product["specifications"], product["features"] = rows, features
    else:
        product.setdefault("specifications", [])
        product.setdefault("features", [])
    model = next((row["value"] for row in rows if normalized(row["label"]) in ("modelo", "numero de parte", "numero de modelo")), None)
    if model:
        product["model"] = model
    product["specificationSources"] = [{"name": "Nexcom", "url": source["permalink"], "reference": reference}]
    if product["id"] in ("19296", "22988"):
        for row in product["specifications"]:
            if normalized(row["label"]) in ("puertos", "conectividad", "entradas"):
                row["sourceValue"] = row["value"]
                row["value"] = "Confirmar conexiones de esta unidad por WhatsApp"
        product["specificationNote"] = "Confirma las conexiones de esta unidad reacondicionada antes de hacer el pedido."
    if any(product.get(key) != value for key, value in previous_details.items()):
        product["specificationsUpdated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return product


def fetch_json(url):
    result = subprocess.run(["curl", "--silent", "--show-error", "--fail", "--retry", "2", "--retry-delay", "1", "--max-time", "40", "--max-filesize", "10000000", url], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def fetch_sources(ids):
    ordered = sorted(ids, key=int)
    sources = {}
    for start in range(0, len(ordered), 80):
        batch = ordered[start:start + 80]
        items = fetch_json(API + "?" + urlencode({"per_page": 100, "include": ",".join(batch)}))
        if not isinstance(items, list):
            raise ValueError("Respuesta de API inválida")
        for item in items:
            pid = str(item.get("id"))
            if pid not in batch or pid in sources:
                raise ValueError("La API devolvió IDs ajenos o repetidos")
            sources[pid] = item
        print(f"Consultadas {min(start + 80, len(ordered))}/{len(ordered)} referencias", flush=True)
    if not sources:
        raise ValueError("Respuesta vacía: se conserva el catálogo anterior")
    return sources


def source_price(source, field="price"):
    prices = source.get("prices") or {}
    if prices.get("currency_code") != "DOP":
        raise ValueError("La moneda del catálogo debe ser DOP")
    units = prices.get("currency_minor_unit")
    if not isinstance(units, int) or units not in range(5):
        raise ValueError("Unidad monetaria inválida")
    return float(Decimal(str(prices.get(field) or 0)) / (10 ** units))


def validate(products):
    ids, references = set(), set()
    for p in products:
        if not isinstance(p.get("id"), str) or not p["id"].isdigit() or p["id"] in ids:
            raise ValueError("ID inválido o repetido")
        if not all(isinstance(p.get(key), str) and p[key].strip() for key in ("name", "category", "brand")):
            raise ValueError("Producto sin nombre, categoría o marca")
        if type(p.get("price")) not in (int, float) or not math.isfinite(p["price"]) or p["price"] <= 0 or not isinstance(p.get("stock"), bool):
            raise ValueError("Precio o disponibilidad inválidos")
        if p.get("old") is not None and not p["old"] > p["price"]:
            raise ValueError("Oferta inválida")
        reference = p.get("reference")
        path = p.get("subcategoryPath")
        if path is not None and (not isinstance(path, list) or len(path) != 3 or not all(isinstance(item, str) and item.strip() for item in path)):
            raise ValueError("Jerarquía de subcategorías inválida")
        if reference and reference in references:
            raise ValueError("Referencia de suplidor repetida")
        if reference:
            references.add(reference)
        ids.add(p["id"])


def merge_import(existing, incoming):
    validate(existing)
    validate(incoming)
    by_id = {p["id"]: deepcopy(p) for p in existing}
    for product in incoming:
        if product["id"] not in by_id:
            by_id[product["id"]] = deepcopy(product)
    return list(by_id.values())


def build_catalog(existing, sources, ids, import_products=None):
    seed = merge_import(existing, import_products) if import_products is not None else deepcopy(existing)
    previous = {p["id"]: p for p in seed}
    existing_ids = {p["id"] for p in existing}
    output, missing = [], []
    for pid in list(previous) + sorted(ids - previous.keys(), key=int):
        if pid not in ids:
            raise ValueError(f"Falta el ID existente {pid} en omega_ids.txt")
        source = sources.get(pid)
        old = previous.get(pid)
        if source is None:
            if import_products is not None and pid not in existing_ids:
                raise ValueError(f"Falta la ficha del producto importado {pid}")
            if old:
                p = classify(deepcopy(old))
                p["stock"] = False
                p["sourceUnavailable"] = True
                output.append(p)
            missing.append(pid)
            continue
        p = deepcopy(old or {})
        if import_products is None:
            price = source_price(source)
            if price <= 0:
                if not old:
                    raise ValueError(f"Producto nuevo sin precio: {pid}")
                p["stock"] = False
                p["sourceUnavailable"] = True
            else:
                p.update(id=pid, name=" ".join(lines(source.get("name"))), spec=" ".join(lines(source.get("short_description")))[:140], price=price)
                if not isinstance(source.get("is_in_stock"), bool):
                    raise ValueError(f"Disponibilidad inválida: {pid}")
                p["stock"] = source["is_in_stock"] and source.get("is_purchasable", True)
                p.pop("sourceUnavailable", None)
                regular = source_price(source, "regular_price")
                if source.get("on_sale") and regular > price:
                    p["old"] = regular
                else:
                    p.pop("old", None)
        if not p.get("sourceCategory"):
            names = {cat.get("name") for cat in source.get("categories", [])}
            if "Zona Gamer" in names:
                p["sourceCategory"] = "Zona Gamer"
        output.append(classify(enrich(p, source)))
    if len(missing) > max(3, len(ids) // 20):
        raise ValueError("Faltan demasiadas fichas en la API: se conserva el catálogo anterior")
    validate(output)
    return output, missing


def image_extension(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"avif", b"avis"):
        return "avif"
    raise ValueError("La descarga no es una imagen reconocida")


def localize_images(products, sources, root=ROOT):
    folder = root / "img/catalogo"
    folder.mkdir(parents=True, exist_ok=True)

    def update(p):
        source = sources.get(p["id"])
        if not source:
            return None
        images = source.get("images") or []
        url = (images[0].get("src") or images[0].get("thumbnail")) if images else None
        if not url:
            image = p.get("image", "")
            p["image"] = image if image.startswith("img/catalogo/") and (root / image).is_file() else PLACEHOLDER
            return None
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "nexcomtienda.com.do":
            raise ValueError("Origen de imagen inesperado")
        key = hashlib.sha256(url.encode()).hexdigest()[:20]
        cached = next((path for path in folder.glob(key + ".*") if path.suffix[1:] in ("png", "jpg", "webp", "gif", "avif")), None)
        old_image = p.get("image", "")
        p["sourceImage"] = url
        if cached:
            p["image"] = str(cached.relative_to(root))
            return None
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, delete=False) as handle:
                temp = Path(handle.name)
            subprocess.run(["curl", "--silent", "--show-error", "--fail", "--retry", "1", "--max-time", "30", "--max-filesize", "15000000", "--output", str(temp), url], capture_output=True, check=True)
            extension = image_extension(temp.read_bytes()[:40])
            target = folder / f"{key}.{extension}"
            temp.replace(target)
            p["image"] = str(target.relative_to(root))
        except (subprocess.CalledProcessError, ValueError) as error:
            p["image"] = old_image if old_image.startswith("img/catalogo/") and (root / old_image).is_file() else PLACEHOLDER
            return {"id": p["id"], "error": str(error)}
        finally:
            if temp and temp.exists():
                temp.unlink()
        return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        return [issue for issue in pool.map(update, products) if issue]


def write_catalog(path, products, missing):
    validate(products)
    metadata = {"source": "nexcomtienda.com.do (selección del propietario; no consulta precios privados de Omega)", "count": len(products), "products": products}
    previous = json.loads(path.read_text()) if path.exists() else {}
    if previous.get("products") == products and previous.get("source") == metadata["source"]:
        return False
    metadata["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if missing:
        metadata["sourceMissingIds"] = missing
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, encoding="utf-8", delete=False) as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    temp.replace(path)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-file", type=Path, help="Añadir IDs ausentes, conservando los precios de los productos existentes")
    parser.add_argument("--source-file", type=Path, help="Respuesta completa de API ya descargada, para reproducir una importación")
    parser.add_argument("--dry-run", action="store_true", help="Consultar y validar sin modificar catálogo ni imágenes")
    args = parser.parse_args()
    path = ROOT / "js/productos.json"
    existing = json.loads(path.read_text())["products"]
    ids = {line.strip() for line in (ROOT / "scripts/omega_ids.txt").read_text().splitlines() if line.strip()}
    if not ids or not all(pid.isdigit() for pid in ids):
        raise ValueError("Lista de selección vacía o inválida")
    incoming = json.loads(args.import_file.read_text())["products"] if args.import_file else None
    if args.source_file:
        raw = json.loads(args.source_file.read_text())
        sources = {str(p["id"]): p for p in raw}
        if len(sources) != len(raw) or not sources.keys() <= ids:
            raise ValueError("Snapshot con IDs repetidos o ajenos")
    else:
        sources = fetch_sources(ids)
    products, missing = build_catalog(existing, sources, ids, incoming)
    if args.dry_run:
        print(f"Validación sin escritura: {len(products)} referencias únicas; {len(missing)} ausentes; catálogo e imágenes conservados.")
        return
    issues = localize_images(products, sources)
    changed = write_catalog(path, products, missing)
    print(f"Catálogo: {len(products)} referencias únicas; {len(products) - len(existing)} nuevas; {len(missing)} ausentes en origen; imágenes pendientes: {len(issues)}; cambios: {changed}")
    if issues:
        print(json.dumps(issues, ensure_ascii=False))


if __name__ == "__main__":
    main()
