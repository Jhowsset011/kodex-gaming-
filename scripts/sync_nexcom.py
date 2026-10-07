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
    (r"^(?:smart tv|televisor|bocina|bocinas|audifono|audifonos|microfono|microfonos|soundbar|sound bar|subwoofer|barra de sonido|streaming|soporte tv|consola (?:streamer|de control))\b", "Audio y Video"),
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


def subcategory_of(product):
    """One product-type subcategory beneath the main category, like Nexcom's menu."""
    name = normalized(product["name"])
    cat = product["category"]
    if cat == "Audio y Video":
        rules = [
            (r"^audifono", "Audífonos"),
            (r"^bocina", "Bocinas"),
            (r"^sound ?bar|^barra de sonido|^subwoofer", "Equipos de sonido"),
            (r"^soporte", "Soportes para TV"),
            (r"^streaming", "Streaming y TV Smart"),
            (r"^smart tv|^televisor", "Televisores"),
            (r"^microfono", "Micrófonos"),
            (r"^iluminacion|^luz|^luces", "Iluminación"),
        ]
        return next((label for pattern, label in rules if re.search(pattern, name)), "Accesorios de audio")
    if cat == "Almacenamiento":
        rules = [
            (r"^caja", "Gabinetes para discos"),
            (r"^memoria usb", "Memorias USB"),
            (r"^memoria\s+(?:micro|sd)", "Tarjetas de memoria"),
            (r"\bdvd|^cd|^pack", "Unidades ópticas"),
            (r"\bssd\b|estado solido", "Discos SSD"),
        ]
        return next((label for pattern, label in rules if re.search(pattern, name)), "Discos HDD")
    if cat == "Componentes":
        rules = [
            (r"^controladora", "Controladores RGB"),
            (r"^(?:abanico|ventilador|disipador|cooler|cpu liquid cooler|refrigeracion|enfriamiento|sistema enfriamiento)", "Refrigeración"),
            (r"^(?:case|gabinete)", "Gabinetes / Case"),
            (r"^(?:power supply|fuente)", "Fuentes de poder"),
            (r"^(?:mb|motherboard|placa madre)", "Tarjetas madre"),
            (r"^memoria", "Memorias RAM"),
            (r"^procesador", "Procesadores"),
            (r"^tarjeta", "Tarjetas gráficas"),
        ]
        return next((label for pattern, label in rules if re.search(pattern, name)), "Otros componentes")
    if cat == "Periféricos":
        if name.startswith("mouse pad"):
            return "Mouse pads"
        if name.startswith("mouse"):
            return "Mouse"
        if name.startswith(("teclado", "combo")):
            return "Combos de teclado y mouse" if name.startswith("combo") or "mouse" in name else "Teclados"
        if name.startswith("camara web"):
            return "Cámaras web"
        if name.startswith(("gamepad", "control")):
            return "Controles de juego"
        if name.startswith(("pedales", "volante")):
            return "Volantes y pedales"
        if name.startswith(("funda", "candado")):
            return "Accesorios para laptop"
        return "Presentadores" if name.startswith("puntero") else "Otros accesorios"
    if cat == "Monitores":
        facts = " ".join(row.get("value", "") for row in product.get("specifications", [])
                         if re.search(r"pantalla|tipo|curvatura|diseno", normalized(row.get("label", ""))))
        text = name + " " + normalized(facts)
        if name.startswith("pantalla interactiva"):
            return "Pantallas interactivas"
        if "portatil" in name:
            return "Portátiles"
        if re.search(r"touch|tactil", text):
            return "Táctiles"
        return "Curvos" if "curv" in text else "De escritorio"
    if cat == "Laptops":
        return "Convertibles 2 en 1" if re.search(r"2 en 1|2-in-1", name) else "Gaming" if re.search(r"gamer|gaming", name) else "Portátiles"
    if cat == "Computadoras":
        return "Terminales" if re.search(r"terminal|wyse|thin client", name) else "Mini PC" if "mini pc" in name else "De escritorio"
    if cat == "Mobiliario":
        return "Sillas" if name.startswith("silla") else "Escritorios"
    return "Otros productos"


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
    product["subcategory"] = subcategory_of(product)
    product.pop("subcategoryPath", None)
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
        subcategory = p.get("subcategory")
        if subcategory is not None and (not isinstance(subcategory, str) or not subcategory.strip()):
            raise ValueError("Subcategoría inválida")
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
