"""Read the public Omega catalog without accounts or changes to the supplier site.

Prices are public DOP prices (Decimal), never negotiated account prices.  A
missing listing is different from an incomplete response or a network failure.
The caller must decide how to preserve or quarantine existing catalog entries.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
import re
import ssl
import subprocess
import tempfile
import threading
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


BASE_URL = "https://tienda.omega.com.do"
PUBLIC_HOSTS = {"tienda.omega.com.do", "sis.omega.com.do"}
CERTIFICATES = (
    "https://letsencrypt.org/certs/gen-y/int-ye2.pem",
    "https://letsencrypt.org/certs/gen-y/root-ye-by-x2.pem",
    "https://letsencrypt.org/certs/gen-y/root-x2-by-x1.pem",
)
USER_AGENT = "KodexGaming-CatalogSync/1.0 (+https://kodexgaming.com)"
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input",
             "link", "meta", "param", "source", "track", "wbr"}


class OmegaPublicError(RuntimeError):
    """Base class for public catalog errors."""


class OmegaFetchError(OmegaPublicError):
    """Transport, certificate, or response-size failure: do not mark unavailable."""


class OmegaParseError(OmegaPublicError):
    """Response does not securely identify a complete product in DOP."""


class OmegaProductMissing(OmegaPublicError):
    """Supplier explicitly reports a missing listing (404/410 or a soft 404)."""


def _reference(value):
    value = str(value)
    if not re.fullmatch(r"[1-9]\d{0,11}", value):
        raise ValueError("Referencia de Omega inválida")
    return value


def product_url(reference):
    return f"{BASE_URL}/es/product/consul/{_reference(reference)}"


def _public_url(url):
    parts = urlparse(url)
    if (parts.scheme != "https" or parts.hostname not in PUBLIC_HOSTS
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise OmegaFetchError("URL fuera de los hosts HTTPS públicos de Omega")
    return url


class _SecureRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        _public_url(new_url)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _default_context():
    context = ssl.create_default_context()
    # Intermediates supplied to OpenSSL must not become independent trust roots.
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
        context.verify_flags &= ~ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


def make_tls_context(cache_dir=None):
    """Complete Omega's omitted chain, verified against existing system roots.

    Omega currently sends only its YE2-issued leaf. Official intermediate and
    cross-signed CA certificates supply the path to ISRG Root X1 already trusted
    by the operating system. No leaf is trusted and TLS checks stay enabled.
    The explicit OpenSSL verification checks expiration, purpose and hostname
    before the chain is made available to the verified HTTPS client.
    """
    context = _default_context()
    cache = Path(cache_dir) if cache_dir else Path(tempfile.gettempdir()) / "kodex-omega-public"
    cache.mkdir(parents=True, exist_ok=True)
    chain = []
    for url in CERTIFICATES:
        path = cache / Path(urlparse(url).path).name
        try:
            if path.exists():
                certificate = path.read_bytes()
            else:
                request = Request(url, headers={"User-Agent": USER_AGENT})
                opener = build_opener(HTTPSHandler(context=context))
                with opener.open(request, timeout=25) as response:
                    if urlparse(response.url).scheme != "https" or urlparse(response.url).hostname != "letsencrypt.org":
                        raise OmegaFetchError("Redirección inesperada al obtener certificados oficiales")
                    certificate = response.read(32_769)
                if len(certificate) > 32_768:
                    raise OmegaFetchError("Certificado oficial supera el tamaño esperado")
                ssl.PEM_cert_to_DER_cert(certificate.decode("ascii"))
                path.write_bytes(certificate)
            ssl.PEM_cert_to_DER_cert(certificate.decode("ascii"))
            chain.append(certificate)
        except (OSError, URLError, ValueError, UnicodeError) as error:
            raise OmegaFetchError(f"No se pudo obtener la cadena TLS oficial: {error}") from error
    bundle = b"\n".join(chain)
    bundle_path = cache / "omega-intermediates.pem"
    bundle_path.write_bytes(bundle)
    ca = ssl.get_default_verify_paths()
    if not ca.cafile:
        raise OmegaFetchError("No se encuentra el almacén de raíces TLS del sistema")
    try:
        probe = subprocess.run(
            ["openssl", "s_client", "-connect", "tienda.omega.com.do:443",
             "-servername", "tienda.omega.com.do", "-showcerts",
             "-verify_return_error", "-verify_hostname", "tienda.omega.com.do"],
            input=b"", capture_output=True, timeout=30, check=False,
        )
        match = re.search(rb"-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----", probe.stdout)
        if not match:
            raise OmegaFetchError("Omega no proporcionó un certificado TLS verificable")
        leaf = cache / "omega-leaf.pem"
        leaf.write_bytes(match.group(0) + b"\n")
        verified = subprocess.run(
            ["openssl", "verify", "-CAfile", ca.cafile, "-untrusted", str(bundle_path),
             "-purpose", "sslserver", "-verify_hostname", "tienda.omega.com.do", str(leaf)],
            capture_output=True, timeout=15, check=False,
        )
        if verified.returncode:
            diagnostic = verified.stderr.decode("utf-8", errors="replace").strip()
            raise OmegaFetchError(f"La cadena TLS de Omega no es válida: {diagnostic}")
        context.load_verify_locations(cadata=bundle.decode("ascii"))
    except (OSError, subprocess.TimeoutExpired, ssl.SSLError) as error:
        raise OmegaFetchError(f"No se pudo verificar la cadena TLS de Omega: {error}") from error
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    return context


class _RateLimiter:
    def __init__(self, interval=0.5):
        self.interval = interval
        self.next_request = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            delay = self.next_request - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self.next_request = time.monotonic() + self.interval


def read_public_url(url, context=None, max_bytes=4_000_000, timeout=25, limiter=None):
    """GET public HTTPS Omega bytes with bounded size and transient retries."""
    _public_url(url)
    context = context or make_tls_context()
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise OmegaFetchError("Se requiere verificación completa del certificado y hostname")
    if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN") and context.verify_flags & ssl.VERIFY_X509_PARTIAL_CHAIN:
        raise OmegaFetchError("No se permite confiar en una cadena TLS parcial")
    opener = build_opener(HTTPSHandler(context=context), _SecureRedirect())
    for attempt in range(3):
        try:
            if limiter:
                limiter.wait()
            request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,image/*;q=0.9,*/*;q=0.5"})
            with opener.open(request, timeout=timeout) as response:
                _public_url(response.url)
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise OmegaFetchError(f"Respuesta pública supera {max_bytes} bytes")
                if not body:
                    raise OmegaFetchError("Respuesta pública vacía")
                _check_product_response_url(url, response.url, body)
                return body
        except HTTPError as error:
            if error.code in (404, 410):
                raise OmegaProductMissing(f"Omega devolvió HTTP {error.code}: {url}") from error
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise OmegaFetchError(f"Omega devolvió HTTP {error.code}: {url}") from error
        except (URLError, TimeoutError, OSError) as error:
            if attempt == 2:
                raise OmegaFetchError(f"No se pudo leer Omega: {url}: {error}") from error
        time.sleep(attempt + 1)
    raise OmegaFetchError(f"No se pudo leer Omega: {url}")


class _Node:
    def __init__(self, tag="", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def all(self, predicate):
        found = [self] if predicate(self) else []
        for child in self.children:
            if isinstance(child, _Node):
                found.extend(child.all(predicate))
        return found

    def has_class(self, value):
        return value in self.attrs.get("class", "").split()

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        return re.sub(r"\s+", " ", " ".join(
            child.text() if isinstance(child, _Node) else child for child in self.children)).strip()


class _Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def _normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(c))


def _money(value, reference):
    # USD and DOP share '$'; the selected currency is checked separately.
    match = re.fullmatch(r"(?:RD\s*)?\$\s*((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})", value, re.I)
    if not match:
        raise OmegaParseError(f"Precio público no reconocido para {reference}: {value!r}")
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation as error:
        raise OmegaParseError(f"Precio inválido para {reference}") from error
    if not amount.is_finite() or amount < 0:
        raise OmegaParseError(f"Precio negativo o no finito para {reference}")
    return amount


def _same_product_url(url, reference):
    parts = urlparse(url)
    return (parts.scheme == "https" and parts.hostname == "tienda.omega.com.do"
            and parts.path.rstrip("/") == f"/es/product/consul/{reference}"
            and not parts.query and not parts.fragment and not parts.username
            and not parts.password and parts.port in (None, 443))


def _check_product_response_url(requested_url, final_url, body):
    """A supplier redirect to its verified home marks a removed listing.

    Home HTML returned at the original product URL is ambiguous and still
    fails parsing. This distinction avoids treating proxy/cache failures as
    supplier removals.
    """
    requested = urlparse(requested_url)
    match = re.fullmatch(r"/es/product/consul/([1-9]\d{0,11})/?", requested.path)
    if requested.hostname != "tienda.omega.com.do" or not match:
        return
    reference = match.group(1)
    if _same_product_url(final_url, reference):
        return
    final = urlparse(final_url)
    home = (final.scheme == "https" and final.hostname == "tienda.omega.com.do"
            and final.path.rstrip("/").lower() in {"", "/es", "/es/home/index"}
            and not final.query and not final.fragment)
    if home:
        try:
            tree = _Document(body.decode("utf-8-sig")).root
        except UnicodeError as error:
            raise OmegaParseError(f"Redirección con HTML no UTF-8 para {reference}") from error
        titles = tree.all(lambda n: n.tag == "title")
        summaries = tree.all(lambda n: n.has_class("entry-summary"))
        currencies = tree.all(lambda n: n.tag == "select" and n.attrs.get("id") == "select-currency")
        if (len(titles) == 1 and re.fullmatch(r"OMEGA\s+TECH\s+S\.?A\.?\s*-\s*Inicio", titles[0].text(), re.I)
                and not summaries and len(currencies) == 1):
            raise OmegaProductMissing(f"Omega redirigió la referencia {reference} a su inicio: {requested_url} -> {final_url}")
    raise OmegaParseError(f"Redirección de producto inesperada para {reference}: {requested_url} -> {final_url}")


def _description_lines(node):
    """Keep explicit list/paragraph boundaries; never invent a feature."""
    blocks = node.all(lambda n: n.tag in {"li", "p", "tr"} and bool(n.text()))
    if blocks:
        lines = [block.text() for block in blocks]
    else:
        # Most Omega descriptions are one comma-separated line; preserve the
        # entire source as one feature when there are no explicit boundaries.
        lines = [node.text()] if node.text() else []
    return list(dict.fromkeys(lines))


def _specifications(lines, part_number):
    specifications = []
    if part_number:
        specifications.append({"label": "Número de parte", "value": part_number})
    for line in lines:
        pair = re.fullmatch(r"([^:]{2,60})\s*:\s*(.{1,1000})", line)
        if pair:
            specifications.append({"label": pair.group(1).strip(), "value": pair.group(2).strip()})
        elif line:
            specifications.append({"label": "Información del producto", "value": line})
    return specifications


def _title_conflicts(title, part_number):
    """Flag explicit lookalike model disagreements, not generic short titles."""
    actual = re.findall(r"\b[A-Z]*\d+[A-Z0-9-]*\b", title.upper())
    expected = re.findall(r"\b[A-Z]*\d+[A-Z0-9-]*\b", part_number.upper())
    conflicts = []
    for model in expected:
        if model in actual:
            continue
        stem = re.match(r"[A-Z]+\d+", model)
        if stem and any(candidate != model and candidate.startswith(stem.group(0)) for candidate in actual):
            conflicts.append(f"El título contradice el número de parte: {model}")
    return conflicts


def parse_product(html, reference, source_url=None):
    """Validate and extract one exact Omega reference from its public HTML."""
    reference = _reference(reference)
    source_url = source_url or product_url(reference)
    if not _same_product_url(source_url, reference):
        raise OmegaParseError(f"URL de producto no coincide con {reference}")
    if not isinstance(html, str) or not html.strip():
        raise OmegaParseError(f"HTML vacío para {reference}")
    tree = _Document(html).root
    summaries = tree.all(lambda n: n.has_class("entry-summary"))
    if not summaries:
        text = _normalized(tree.text())
        if re.search(r"(?:producto|articulo)\s+(?:(?:no\s+(?:fue\s+)?encontrado)|(?:no\s+existe)|(?:no\s+disponible))|404\s*(?:not found|pagina no encontrada)", text):
            raise OmegaProductMissing(f"Omega indica que no existe la referencia {reference}")
        raise OmegaParseError(f"Respuesta sin ficha de producto para {reference}")
    if len(summaries) != 1:
        raise OmegaParseError(f"Respuesta con fichas de producto ambiguas para {reference}")
    summary = summaries[0]
    identity = summary.all(lambda n: n.attrs.get("data-product") == reference)
    foreign = summary.all(lambda n: n.attrs.get("data-product") not in (None, reference))
    if not identity or foreign:
        raise OmegaParseError(f"La ficha no confirma la referencia exacta {reference}")
    canonical = tree.all(lambda n: (n.tag == "meta" and n.attrs.get("property", "").lower() == "og:url")
                         or (n.tag == "link" and n.attrs.get("rel", "").lower() == "canonical"))
    urls = [n.attrs.get("content") or n.attrs.get("href") for n in canonical]
    if not urls or any(not url or not _same_product_url(url, reference) for url in urls):
        raise OmegaParseError(f"La URL canónica no confirma la referencia {reference}")
    selectors = tree.all(lambda n: n.tag == "select" and n.attrs.get("id") == "select-currency")
    selected = [option for select in selectors for option in select.all(
        lambda n: n.tag == "option" and "selected" in n.attrs)]
    if len(selected) != 1 or not re.search(r"\bDOP\b", selected[0].text()):
        raise OmegaParseError(f"Omega no confirma el precio en DOP para {reference}")
    titles = summary.all(lambda n: n.tag in {"h1", "h2", "h3"} and bool(n.text()))
    if len(titles) != 1:
        raise OmegaParseError(f"Título incompleto o ambiguo para {reference}")
    title = titles[0].text()
    amounts = summary.all(lambda n: n.has_class("amount") and not n.has_class("del"))
    consultation = bool(re.search(r"\bconsult(?:ar|e)\s+(?:el\s+)?precio\b|\bprecio\s+(?:a\s+)?consultar\b", _normalized(summary.text())))
    if not amounts and consultation:
        price = None
    elif len(amounts) == 1:
        price = _money(amounts[0].text(), reference) or None
    else:
        raise OmegaParseError(f"Precio incompleto o ambiguo para {reference}")
    old_amounts = summary.all(lambda n: n.has_class("amount") and n.has_class("del"))
    if len(old_amounts) > 1:
        raise OmegaParseError(f"Precio anterior ambiguo para {reference}")
    old_price = _money(old_amounts[0].text(), reference) if old_amounts else None
    if old_price is not None and (price is None or old_price <= price):
        old_price = None
    parts = summary.all(lambda n: n.tag == "p" and "numero de parte" in _normalized(n.text()))
    part_number = parts[0].text().split(":", 1)[-1].strip() if len(parts) == 1 else ""
    descriptions = tree.all(lambda n: n.attrs.get("id") == "productDescription")
    if len(descriptions) != 1 or not descriptions[0].text():
        raise OmegaParseError(f"Descripción incompleta para {reference}")
    description = descriptions[0].text()
    lines = _description_lines(descriptions[0])
    inventories = tree.all(lambda n: n.has_class("product-col"))
    inventory = []
    for box in inventories:
        for row in box.all(lambda n: n.tag == "tr"):
            cells = row.all(lambda n: n.tag == "td")
            if not cells:
                continue
            if len(cells) != 2 or not cells[0].text() or not re.fullmatch(r"\d+", cells[1].text()):
                raise OmegaParseError(f"Inventario no reconocido para {reference}")
            inventory.append({"branch": cells[0].text(), "quantity": int(cells[1].text())})
    if not inventory or len({row["branch"] for row in inventory}) != len(inventory):
        raise OmegaParseError(f"No hay inventario verificable para {reference}")
    images = tree.all(lambda n: n.tag == "meta" and n.attrs.get("property", "").lower() == "og:image")
    image = images[0].attrs.get("content", "") if images else ""
    if image:
        _public_url(image)
        image_parts = urlparse(image)
        if image_parts.hostname != "sis.omega.com.do" or not image_parts.path.startswith("/ProductImages/"):
            raise OmegaParseError(f"Imagen de producto fuera del catálogo de Omega: {reference}")
    breadcrumbs = tree.all(lambda n: n.has_class("breadcrumb"))
    categories = []
    for breadcrumb in breadcrumbs:
        for link in breadcrumb.all(lambda n: n.tag == "a"):
            if re.fullmatch(r"/es/category/list/\d+/?", link.attrs.get("href", "")):
                categories.append(link.text())
    brand = title.split(" - ", 1)[0].strip() if " - " in title else ""
    brand = {"msi": "MSI", "aoc": "AOC", "hp": "HP", "hpe": "HPE", "xtech": "Xtech"}.get(brand.casefold(), brand)
    conflicts = _title_conflicts(title, part_number)
    # For the known A750BN/A750GLS disagreement both description and part number
    # confirm the same model. Expose the original title for review, use the exact
    # Omega description rather than silently publishing the contradicted title.
    name = description if conflicts and part_number and part_number.upper() in description.upper() else title
    return {"reference": reference, "rawTitle": title, "name": name, "brand": brand,
            "partNumber": part_number, "description": description, "descriptionLines": lines,
            "specifications": _specifications(lines, part_number), "currency": "DOP",
            "price": price, "oldPrice": old_price, "sourceUrl": source_url,
            "imageSource": image, "sourceCategories": categories, "inventory": inventory,
            "stock": price is not None and any(row["quantity"] > 0 for row in inventory),
            "priceUnavailable": price is None, "conflicts": conflicts}


def fetch_selected_references(references, context=None, cache_dir=None, workers=2):
    """Fetch all selected references; only confirmed missing pages are omitted.

    Snapshots, when requested, are written for audit outside the public catalog.
    They are never automatically reused as current supplier information.
    """
    selected = [_reference(reference) for reference in references]
    if len(selected) != len(set(selected)):
        raise ValueError("Referencias de Omega repetidas")
    if workers not in (1, 2):
        raise ValueError("Se permiten como máximo dos conexiones simultáneas a Omega")
    context = context or make_tls_context(cache_dir)
    limiter = _RateLimiter()
    snapshots = Path(cache_dir) / "omega-pages" if cache_dir else None
    if snapshots:
        snapshots.mkdir(parents=True, exist_ok=True)

    def fetch(reference):
        url = product_url(reference)
        try:
            body = read_public_url(url, context, limiter=limiter)
            try:
                text = body.decode("utf-8-sig")
            except UnicodeError as error:
                raise OmegaParseError(f"HTML no UTF-8 para {reference}") from error
            if snapshots:
                (snapshots / f"{reference}.html").write_text(text, encoding="utf-8")
            return reference, parse_product(text, reference), False
        except OmegaProductMissing as error:
            print(f"Referencia ausente confirmada: {error}", flush=True)
            return reference, None, True

    sources, missing = {}, []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for reference, source, is_missing in pool.map(fetch, selected):
            if is_missing:
                missing.append(reference)
            else:
                sources[reference] = source
    return sources, missing
