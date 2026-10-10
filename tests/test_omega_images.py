from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "omega_images", Path(__file__).parents[1] / "scripts/omega_images.py")
images = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(images)


PNG = b"\x89PNG\r\n\x1a\nexample-image-payload"
JPEG = b"\xff\xd8\xff\xe0example-image-payload\xff\xd9"
WEBP = b"RIFF\x12\x00\x00\x00WEBPexample-image-payload"
GIF = b"GIF89aexample-image-payload"
URL = "https://sis.omega.com.do/ProductImages/example.png"
OTHER_URL = "https://sis.omega.com.do/ProductImages/other.png"


def name(data, extension=".png"):
    return hashlib.sha256(data).hexdigest()[:20] + extension


def product(url=URL):
    return {"id": "example", "sourceImage": url, "image": "img/catalogo/previous.jpg"}


def save_manifest(directory, mapping):
    (directory / "manifest.json").write_text(json.dumps(mapping), encoding="utf-8")


class ImageDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.context = object()

    def test_content_hashed_name_manifest_and_product_localization(self):
        products = [product()]
        with patch.object(images.omega_public, "read_public_url", return_value=PNG) as fetch:
            images.localize_images(products, self.directory, context=self.context)
        filename = name(PNG)
        self.assertEqual(products[0]["image"], "img/catalogo/" + filename)
        self.assertNotIn("imageUnavailable", products[0])
        self.assertEqual((self.directory / filename).read_bytes(), PNG)
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), {URL: filename})
        self.assertIs(fetch.call_args.kwargs["context"], self.context)
        self.assertEqual(fetch.call_args.kwargs["max_bytes"], 10_000_000)
        self.assertEqual(fetch.call_args.kwargs["limiter"].interval, 0.5)

    def test_magic_determines_extension_instead_of_url_suffix(self):
        for payload, extension in ((PNG, ".png"), (JPEG, ".jpg"), (WEBP, ".webp"), (GIF, ".gif")):
            with self.subTest(extension=extension):
                url = "https://sis.omega.com.do/ProductImages/" + extension[1:] + ".unknown"
                with patch.object(images.omega_public, "read_public_url", return_value=payload):
                    result = images.download_source_images(
                        {"example": {"imageSource": url}}, self.directory, context=self.context)
                self.assertEqual(result[url], name(payload, extension))

    def test_deduplicates_urls_and_identical_image_contents(self):
        products = [product(), product(), product(OTHER_URL)]
        with patch.object(images.omega_public, "read_public_url", return_value=PNG) as fetch:
            images.localize_images(products, self.directory, context=self.context)
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(list(self.directory.glob("*.png"))), 1)
        self.assertEqual(len({item["image"] for item in products}), 1)

    def test_confirmed_missing_image_and_absent_source_use_placeholder(self):
        products = [product(), product("")]
        with patch.object(images.omega_public, "read_public_url",
                          side_effect=images.omega_public.OmegaProductMissing("404")):
            images.localize_images(products, self.directory, context=self.context)
        for item in products:
            self.assertEqual(item["image"], images.PLACEHOLDER)
            self.assertTrue(item["imageUnavailable"])
        self.assertEqual(json.loads((self.directory / "manifest.json").read_text()), {URL: None})

    def test_missing_image_is_retried_on_next_online_sync(self):
        save_manifest(self.directory, {URL: None})
        with patch.object(images.omega_public, "read_public_url", return_value=PNG) as fetch:
            result = images.download_source_images([{"imageSource": URL}], self.directory, self.context)
        self.assertEqual(result, {URL: name(PNG)})
        fetch.assert_called_once()

    def test_transport_failure_leaves_all_products_and_manifest_unchanged(self):
        products = [product(), product(OTHER_URL)]
        before = deepcopy(products)
        original_manifest = (self.directory / "manifest.json")
        original_manifest.write_text("{}", encoding="utf-8")

        def read(url, **_kwargs):
            if url == OTHER_URL:
                raise images.omega_public.OmegaFetchError("timeout")
            return PNG

        with patch.object(images.omega_public, "read_public_url", side_effect=read):
            with self.assertRaises(images.omega_public.OmegaFetchError):
                images.localize_images(products, self.directory, context=self.context)
        self.assertEqual(products, before)
        self.assertEqual(original_manifest.read_text(), "{}")
        self.assertEqual(list(self.directory.glob("*.png")), [])

    def test_empty_html_unknown_magic_and_oversized_images_fail_closed(self):
        for payload in (b"", b"<html>error</html>", b"not an image", PNG + b"x" * 10_000_000):
            products = [product()]
            before = deepcopy(products)
            with patch.object(images.omega_public, "read_public_url", return_value=payload):
                with self.assertRaises(images.OmegaImageError):
                    images.localize_images(products, self.directory, context=self.context)
            self.assertEqual(products, before)
            self.assertEqual(list(self.directory.iterdir()), [])

    def test_foreign_hosts_credentials_http_and_traversal_fail_before_fetch(self):
        urls = (
            "http://sis.omega.com.do/ProductImages/example.png",
            "https://foreign.example/example.png",
            "https://sis.omega.com.do.foreign.example/example.png",
            "https://user:password@sis.omega.com.do/example.png",
            "https://sis.omega.com.do:8443/example.png",
            "https://sis.omega.com.do/ProductImages/../example.png",
            "https://sis.omega.com.do/ProductImages/%2e%2e/example.png",
            "https://sis.omega.com.do/ProductImages/%252e%252e/example.png",
            "https://sis.omega.com.do/ProductImages/%5c../example.png",
        )
        with patch.object(images.omega_public, "read_public_url") as fetch:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(images.OmegaImageError):
                    images.localize_images([product(url)], self.directory, context=self.context)
        fetch.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_only_two_workers_download_and_every_call_uses_shared_limiter(self):
        active = 0
        peak = 0
        limiters = []
        lock = threading.Lock()

        def read(_url, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                limiters.append(kwargs["limiter"])
            time.sleep(0.01)
            with lock:
                active -= 1
            return PNG

        sources = [{"imageSource": f"https://sis.omega.com.do/ProductImages/{number}.png"}
                   for number in range(6)]
        with patch.object(images.omega_public, "read_public_url", side_effect=read):
            images.download_source_images(sources, self.directory, self.context)
        self.assertEqual(peak, 2)
        self.assertEqual(len({id(limiter) for limiter in limiters}), 1)
        self.assertEqual(limiters[0].interval, 0.5)


class ImageCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.offline = self.root / "offline"
        self.offline.mkdir()

    def test_valid_content_cache_is_reused_without_fetch_or_rewrite(self):
        filename = name(PNG)
        path = self.output / filename
        path.write_bytes(PNG)
        before = path.stat().st_mtime_ns
        save_manifest(self.output, {URL: filename})
        with patch.object(images.omega_public, "read_public_url") as fetch:
            images.localize_images([product()], self.output)
        fetch.assert_not_called()
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_tampered_cache_is_rejected_and_not_overwritten(self):
        filename = name(PNG)
        path = self.output / filename
        path.write_bytes(JPEG)
        save_manifest(self.output, {URL: filename})
        with patch.object(images.omega_public, "read_public_url") as fetch:
            with self.assertRaises(images.OmegaImageError):
                images.localize_images([product()], self.output)
        fetch.assert_not_called()
        self.assertEqual(path.read_bytes(), JPEG)

    def test_existing_unmapped_target_is_never_overwritten(self):
        path = self.output / name(PNG)
        path.write_bytes(b"corrupted existing image")
        with patch.object(images.omega_public, "read_public_url", return_value=PNG):
            with self.assertRaises(images.OmegaImageError):
                images.localize_images([product()], self.output, context=object())
        self.assertEqual(path.read_bytes(), b"corrupted existing image")

    def test_offline_manifest_content_cache_and_confirmed_missing(self):
        filename = name(PNG)
        (self.offline / filename).write_bytes(PNG)
        save_manifest(self.offline, {URL: filename, OTHER_URL: None})
        products = [product(), product(OTHER_URL)]
        with patch.object(images.omega_public, "read_public_url") as fetch:
            images.localize_images(products, self.output, offline_dir=self.offline)
        fetch.assert_not_called()
        self.assertEqual((self.output / filename).read_bytes(), PNG)
        self.assertEqual(products[0]["image"], "img/catalogo/" + filename)
        self.assertEqual(products[1]["image"], images.PLACEHOLDER)

    def test_offline_url_hash_cache_is_converted_to_content_hash(self):
        for full_digest in (False, True):
            with self.subTest(full_digest=full_digest):
                directory = self.root / str(full_digest)
                directory.mkdir()
                digest = hashlib.sha256(URL.encode()).hexdigest()
                (directory / ((digest if full_digest else digest[:20]) + ".png")).write_bytes(PNG)
                with patch.object(images.omega_public, "read_public_url") as fetch:
                    images.localize_images([product()], self.output, offline_dir=directory)
                fetch.assert_not_called()
                self.assertEqual((self.output / name(PNG)).read_bytes(), PNG)

    def test_missing_offline_image_fails_without_network_or_product_mutation(self):
        products = [product()]
        before = deepcopy(products)
        with patch.object(images.omega_public, "read_public_url") as fetch:
            with self.assertRaises(images.OmegaImageError):
                images.localize_images(products, self.output, offline_dir=self.offline)
        fetch.assert_not_called()
        self.assertEqual(products, before)

    def test_manifest_traversal_invalid_data_and_foreign_urls_fail_closed(self):
        for mapping in ({URL: "../outside.png"}, {URL: "/tmp/outside.png"},
                        {URL: "arbitrary.png"}, {URL: 1}, [],
                        {"https://foreign.example/image.png": name(PNG)}):
            with self.subTest(mapping_type=type(mapping).__name__):
                save_manifest(self.offline, mapping)
                with patch.object(images.omega_public, "read_public_url") as fetch:
                    with self.assertRaises(images.OmegaImageError):
                        images.localize_images([product()], self.output, offline_dir=self.offline)
                fetch.assert_not_called()

    def test_symbolic_link_image_cannot_escape_cache(self):
        filename = name(PNG)
        outside = self.root / "outside.png"
        outside.write_bytes(PNG)
        (self.offline / filename).symlink_to(outside)
        save_manifest(self.offline, {URL: filename})
        with self.assertRaises(images.OmegaImageError):
            images.localize_images([product()], self.output, offline_dir=self.offline)
        self.assertEqual(outside.read_bytes(), PNG)

    def test_symbolic_link_manifest_is_rejected(self):
        outside = self.root / "outside.json"
        outside.write_text(json.dumps({URL: None}), encoding="utf-8")
        (self.offline / "manifest.json").symlink_to(outside)
        with self.assertRaises(images.OmegaImageError):
            images.localize_images([product()], self.output, offline_dir=self.offline)

    def test_offline_extension_and_content_hash_are_checked(self):
        digest = hashlib.sha256(URL.encode()).hexdigest()[:20]
        path = self.offline / (digest + ".png")
        path.write_bytes(JPEG)
        with self.assertRaises(images.OmegaImageError):
            images.localize_images([product()], self.output, offline_dir=self.offline)
        path.unlink()
        filename = name(PNG)
        (self.offline / filename).write_bytes(PNG + b"tampered")
        save_manifest(self.offline, {URL: filename})
        with self.assertRaises(images.OmegaImageError):
            images.localize_images([product()], self.output, offline_dir=self.offline)


if __name__ == "__main__":
    unittest.main()
