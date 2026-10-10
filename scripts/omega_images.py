"""Bounded, verified downloads of public Omega images into a content cache.

The manifest contains only public URLs and local image names. Transport and
invalid-cache failures abort localization before any product object is changed.
"""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import unquote, urlparse

try:
    import omega_public
except ModuleNotFoundError:
    from scripts import omega_public


MAX_IMAGE_BYTES = 10_000_000
MAX_MANIFEST_BYTES = 2_000_000
PLACEHOLDER = "img/catalogo/sin-imagen.svg"
PUBLIC_HOSTS = {"tienda.omega.com.do", "sis.omega.com.do"}
IMAGE_EXTENSIONS = (".png", ".jpg", ".webp", ".gif")
CONTENT_NAME = re.compile(r"[0-9a-f]{20}\.(?:png|jpg|webp|gif)\Z")


class OmegaImageError(omega_public.OmegaFetchError):
    """Invalid images or cache data must not silently publish broken photos."""


def _image_url(url):
    if not isinstance(url, str):
        raise OmegaImageError("La imagen de Omega requiere una URL HTTPS pública")
    try:
        parts = urlparse(url)
        decoded_path = unquote(unquote(parts.path))
        if (parts.scheme != "https" or parts.hostname not in PUBLIC_HOSTS
                or parts.username or parts.password or parts.port not in (None, 443)
                or parts.fragment or "\\" in decoded_path
                or ".." in decoded_path.split("/")):
            raise OmegaImageError("URL de imagen fuera de los hosts HTTPS públicos de Omega")
    except ValueError:
        raise OmegaImageError("URL de imagen de Omega inválida") from None
    return url


def _extension(data):
    if not isinstance(data, bytes) or not data or len(data) > MAX_IMAGE_BYTES:
        raise OmegaImageError("Imagen pública vacía o superior al límite permitido")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    raise OmegaImageError("La respuesta no es una imagen PNG, JPEG, WebP o GIF")


def _content_name(data):
    return hashlib.sha256(data).hexdigest()[:20] + _extension(data)


def _read_image(path):
    if path.is_symlink() or not path.is_file():
        raise OmegaImageError("Archivo de imagen local inválido")
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_IMAGE_BYTES + 1)
    except OSError:
        raise OmegaImageError("No se pudo leer la imagen local") from None
    _extension(data)
    return data


def _read_content_image(directory, filename):
    if not isinstance(filename, str) or not CONTENT_NAME.fullmatch(filename):
        raise OmegaImageError("Nombre de imagen inválido en el manifiesto")
    data = _read_image(directory / filename)
    if _content_name(data) != filename:
        raise OmegaImageError("El contenido de la imagen local no coincide con su hash")
    return data


def _load_manifest(directory):
    path = directory / "manifest.json"
    if not path.exists() and not path.is_symlink():
        return {}
    if path.is_symlink() or not path.is_file():
        raise OmegaImageError("Manifiesto de imágenes local inválido")
    try:
        with path.open("rb") as handle:
            encoded = handle.read(MAX_MANIFEST_BYTES + 1)
        if len(encoded) > MAX_MANIFEST_BYTES:
            raise OmegaImageError("Manifiesto de imágenes supera el límite permitido")
        mapping = json.loads(encoded)
    except (OSError, ValueError, UnicodeError):
        raise OmegaImageError("No se pudo leer el manifiesto de imágenes") from None
    if not isinstance(mapping, dict):
        raise OmegaImageError("El manifiesto de imágenes debe ser un objeto")
    for url, filename in mapping.items():
        _image_url(url)
        if filename is not None and (not isinstance(filename, str)
                                     or not CONTENT_NAME.fullmatch(filename)):
            raise OmegaImageError("Nombre de imagen inválido en el manifiesto")
    return mapping


def _save_manifest(directory, mapping):
    path = directory / "manifest.json"
    encoded = (json.dumps(mapping, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    if len(encoded) > MAX_MANIFEST_BYTES:
        raise OmegaImageError("Manifiesto de imágenes supera el límite permitido")
    if path.is_symlink():
        raise OmegaImageError("Manifiesto de imágenes local inválido")
    if path.is_file() and path.read_bytes() == encoded:
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".omega-manifest-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(encoded)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _store_image(directory, data):
    filename = _content_name(data)
    path = directory / filename
    if path.exists() or path.is_symlink():
        if _read_content_image(directory, filename) != data:
            raise OmegaImageError("Colisión del hash de una imagen local")
        return filename
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, prefix=".omega-image-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        try:
            # Linking creates the final file atomically and never replaces a cache entry.
            os.link(temporary, path)
        except FileExistsError:
            if _read_content_image(directory, filename) != data:
                raise OmegaImageError("Colisión del hash de una imagen local")
        return filename
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _offline_image(url, directory, manifest):
    if url in manifest:
        filename = manifest[url]
        return None if filename is None else _read_content_image(directory, filename)
    # Compatibility with collectors that named source files by the URL digest.
    digest = hashlib.sha256(url.encode()).hexdigest()
    for prefix in (digest[:20], digest):
        for extension in IMAGE_EXTENSIONS + (".jpeg",):
            path = directory / (prefix + extension)
            if path.exists() or path.is_symlink():
                data = _read_image(path)
                if _extension(data) != (".jpg" if extension == ".jpeg" else extension):
                    raise OmegaImageError("El formato de imagen no coincide con su extensión")
                return data
    raise OmegaImageError("Falta una imagen en el lote sin conexión")


def _source_urls(sources):
    items = sources.values() if isinstance(sources, dict) else sources
    urls = set()
    for source in items:
        if not isinstance(source, dict):
            raise OmegaImageError("Ficha de imagen de Omega inválida")
        url = source.get("sourceImage", source.get("imageSource", ""))
        if url:
            urls.add(_image_url(url))
    return sorted(urls)


def _localize_urls(urls, output_dir, context=None, offline_dir=None):
    # Validate the complete batch before starting downloads or creating files.
    urls = sorted({_image_url(url) for url in urls})
    output = Path(output_dir)
    cached = _load_manifest(output)
    offline = Path(offline_dir) if offline_dir is not None else None
    offline_manifest = _load_manifest(offline) if offline is not None else {}
    result, pending, data_by_url = {}, [], {}
    for url in urls:
        if cached.get(url) is not None:
            filename = cached[url]
            _read_content_image(output, filename)
            result[url] = filename
        elif offline is not None:
            data_by_url[url] = _offline_image(url, offline, offline_manifest)
        else:
            pending.append(url)
    if pending:
        context = context or omega_public.make_tls_context()
        limiter = omega_public._RateLimiter(interval=0.5)

        def download(url):
            try:
                data = omega_public.read_public_url(
                    url, context=context, max_bytes=MAX_IMAGE_BYTES, limiter=limiter)
            except omega_public.OmegaProductMissing:
                return url, None
            _extension(data)
            return url, data

        # Supplier traffic is bounded to two workers and two request starts per second.
        with ThreadPoolExecutor(max_workers=2) as executor:
            for url, data in executor.map(download, pending):
                data_by_url[url] = data
    output.mkdir(parents=True, exist_ok=True)
    for url, data in data_by_url.items():
        result[url] = None if data is None else _store_image(output, data)
    _save_manifest(output, {**cached, **result})
    return result


def download_source_images(sources, output_dir, context=None):
    """Collect source images and manifest; confirmed HTTP 404/410 maps to None."""
    return _localize_urls(_source_urls(sources), output_dir, context=context)


def localize_images(products, image_dir, context=None, offline_dir=None):
    """Set local product images only after the entire batch has succeeded.

    sourceImage contains the public supplier URL. imageUnavailable is true only
    for absent source photos or explicit HTTP 404/410, never network failures.
    """
    urls = _source_urls(products)
    mapping = _localize_urls(urls, image_dir, context=context, offline_dir=offline_dir)
    for product in products:
        url = product.get("sourceImage", product.get("imageSource", ""))
        filename = mapping.get(url) if url else None
        product["image"] = f"img/catalogo/{filename}" if filename else PLACEHOLDER
        if filename:
            product.pop("imageUnavailable", None)
        else:
            product["imageUnavailable"] = True
