import importlib.util
from decimal import Decimal
from pathlib import Path
import ssl
import unittest
from unittest.mock import MagicMock, patch


SPEC = importlib.util.spec_from_file_location("omega_public", Path(__file__).parents[1] / "scripts/omega_public.py")
omega = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(omega)


def fixture(reference="109640", title="Msi - MAG A750BN PCIE5", price="$6,929.95",
            part="MAG A750GLS PCIE5", description=None, quantity="48"):
    # Minimal structural fixture taken from Omega's public response. It includes
    # an unrelated menu currency/product, so selectors cannot search globally.
    description = description or "POWER SUPPLY MSI MAG A750GLS PCIE5, 750W, ATX, 80 PLUS GOLD, MODULAR"
    return f'''<!doctype html><html><head>
    <meta property="og:url" content="https://tienda.omega.com.do/es/product/consul/{reference}">
    <meta Property="og:image" content="https://sis.omega.com.do/ProductImages/example.png">
    </head><body><nav><option selected>DOP</option><button data-product="987">Otro</button></nav>
    <select id="select-currency"><option>US (USD)</option><option selected>RD (DOP)</option></select>
    <ol class="breadcrumb"><li><a href="/es">Inicio</a></li><li><a href="/es/category/list/95">Partes Para Computadora</a></li>
    <li><a href="/es/category/list/194">Power Supply</a></li><li>Producto</li></ol>
    <div Class="summary entry-summary"><h3><strong>{title}</strong></h3>
    <p><span>N&#250;mero de parte :</span> {part}</p><div class="price"><div class="amount">{price}</div></div>
    <form><button data-product="{reference}">Agregar al Carrito</button></form></div>
    <div id="productDescription">{description}</div>
    <div class="list-group-item product-col"><table><tbody><tr><td>PRINCIPAL SD</td><td>0</td></tr>
    <tr><td>La Nave</td><td>{quantity}</td></tr></tbody></table></div></body></html>'''


class PublicParserTests(unittest.TestCase):
    def test_exact_reference_currency_decimal_inventory_and_model_conflict(self):
        product = omega.parse_product(fixture(), "109640")
        self.assertEqual(product["price"], Decimal("6929.95"))
        self.assertEqual(product["currency"], "DOP")
        self.assertEqual(product["reference"], "109640")
        self.assertEqual(product["partNumber"], "MAG A750GLS PCIE5")
        self.assertEqual(product["brand"], "MSI")
        self.assertEqual(product["sourceCategories"], ["Partes Para Computadora", "Power Supply"])
        self.assertEqual(product["inventory"], [{"branch": "PRINCIPAL SD", "quantity": 0}, {"branch": "La Nave", "quantity": 48}])
        self.assertTrue(product["stock"])
        self.assertIn("A750BN", product["rawTitle"])
        self.assertIn("A750GLS", product["name"])
        self.assertEqual(len(product["conflicts"]), 1)

    def test_zero_stock_is_not_missing_and_generic_title_is_not_conflict(self):
        source = fixture(title="Xtech - BOCINAS FIRESHOT 2.0", part="XTS-131", quantity="0",
                         description="BOCINAS XTECH FIRESHOT 2.0, AUDIO JACK 3.5 + USB PARA LUCES LED, NEGRO (XTS-131)")
        product = omega.parse_product(source, "109640")
        self.assertFalse(product["stock"])
        self.assertFalse(product["conflicts"])
        self.assertEqual(product["name"], "Xtech - BOCINAS FIRESHOT 2.0")

    def test_foreign_identity_or_canonical_fails_even_with_related_exact_button(self):
        source = fixture().replace('data-product="109640"', 'data-product="111698"')
        source += '<aside><button data-product="109640">Relacionado</button></aside>'
        with self.assertRaises(omega.OmegaParseError):
            omega.parse_product(source, "109640")
        with self.assertRaises(omega.OmegaParseError):
            omega.parse_product(fixture(reference="111698"), "109640")
        with self.assertRaises(omega.OmegaParseError):
            omega.parse_product(fixture(), "109640", "https://tienda.omega.com.do/es/product/consul/111698")

    def test_selected_currency_must_be_inside_currency_selector(self):
        source = fixture().replace('<option selected>RD (DOP)</option>', '<option selected>US (USD)</option>')
        with self.assertRaises(omega.OmegaParseError):
            omega.parse_product(source, "109640")

    def test_sale_uses_current_amount_not_crossed_out_price(self):
        source = fixture().replace('<div class="price">', '<div class="price"><div class="amount del">$8,000.00</div>')
        product = omega.parse_product(source, "109640")
        self.assertEqual(product["price"], Decimal("6929.95"))
        self.assertEqual(product["oldPrice"], Decimal("8000.00"))

    def test_missing_listing_is_distinct_from_broken_or_incomplete_response(self):
        with self.assertRaises(omega.OmegaProductMissing):
            omega.parse_product('<html><h1>Producto no encontrado</h1></html>', "109640")
        for source in ('<html><h1>En mantenimiento</h1></html>', fixture().replace('id="productDescription"', 'id="broken"'), fixture(quantity="Consultar")):
            with self.subTest(source=source[:50]), self.assertRaises(omega.OmegaParseError):
                omega.parse_product(source, "109640")

    def test_omega_branded_soft_404_requires_its_body_signature(self):
        branded = '<html><head><title>OMEGA TECH S.A. - 404</title></head><body><h2>404 <i class="fa fa-file"></i></h2><p>Parece que esta p&#225;gina no existe.</p></body></html>'
        with self.assertRaises(omega.OmegaProductMissing):
            omega.parse_product(branded, "106122")
        for broken in (branded.replace('Parece que esta p&#225;gina no existe.', 'Mantenimiento'), branded.replace('<h2>404 <i class="fa fa-file"></i></h2>', ''), '<html><title>OMEGA TECH S.A. - 404</title></html>'):
            with self.subTest(source=broken), self.assertRaises(omega.OmegaParseError):
                omega.parse_product(broken, "106122")

    def test_abbreviated_model_does_not_conflict_with_part_number_suffix(self):
        for title, part in [('Antec - CASE ANTEC C6 CURVE AIR BLACK', 'C6-CURVE-AIR-BLACK'), ('Antec - CASE ANTEC VCX10M RGB', 'VCX10M-RGB')]:
            self.assertFalse(omega._title_conflicts(title, part))
        self.assertTrue(omega._title_conflicts('Antec - ABANICO C120 ARGB', 'C120R.ARGB-3PK'))

    def test_features_use_explicit_omega_description_without_invented_enrichment(self):
        product = omega.parse_product(fixture(description="<ul><li>Panel: Rapid IPS</li><li>2X HDMI, 1X DISPLAYPORT 1.2A</li></ul>"), "109640")
        self.assertEqual(product["descriptionLines"], ["Panel: Rapid IPS", "2X HDMI, 1X DISPLAYPORT 1.2A"])
        self.assertEqual(product["specifications"][1], {"label": "Panel", "value": "Rapid IPS"})
        self.assertEqual(product["specifications"][2]["value"], "2X HDMI, 1X DISPLAYPORT 1.2A")
        self.assertNotIn("1 ms", repr(product["specifications"]))

    def test_image_and_numeric_price_validation(self):
        for source in (fixture(price="$6.929,95"), fixture().replace('https://sis.omega.com.do/ProductImages/example.png', 'http://sis.omega.com.do/ProductImages/example.png')):
            with self.subTest(source=source[:50]), self.assertRaises(omega.OmegaPublicError):
                omega.parse_product(source, "109640")

    def test_explicit_zero_or_consultation_price_is_unavailable_not_missing(self):
        consultation = fixture().replace('<div class="amount">$6,929.95</div>', '<p>Consultar precio</p>')
        for source in (fixture(price="$0.00"), consultation):
            product = omega.parse_product(source, "109640")
            self.assertIsNone(product["price"])
            self.assertTrue(product["priceUnavailable"])
            self.assertFalse(product["stock"])
            self.assertEqual(product["reference"], "109640")


class PublicTransportTests(unittest.TestCase):
    def test_redirect_to_verified_home_is_missing_but_home_at_product_url_is_not(self):
        home = b'<html><head><title>OMEGA TECH S.A. - Inicio</title></head><body><select id="select-currency"></select></body></html>'
        context = omega._default_context()
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = home
        response.url = "https://tienda.omega.com.do/es"
        opener = MagicMock()
        opener.open.return_value = response
        with patch.object(omega, "build_opener", return_value=opener):
            with self.assertRaisesRegex(omega.OmegaProductMissing, "74026.*inicio"):
                omega.read_public_url(omega.product_url("74026"), context)
            response.url = omega.product_url("74026")
            body = omega.read_public_url(omega.product_url("74026"), context)
            with self.assertRaises(omega.OmegaParseError):
                omega.parse_product(body.decode(), "74026")

    def test_redirect_to_another_product_or_unverified_home_is_rejected(self):
        home = b'<html><title>Proxy error</title></html>'
        for final_url in ("https://tienda.omega.com.do/es", omega.product_url("111698")):
            with self.subTest(url=final_url), self.assertRaises(omega.OmegaParseError):
                omega._check_product_response_url(omega.product_url("74026"), final_url, home)

    def test_https_host_and_context_checks_are_required(self):
        for url in ("http://tienda.omega.com.do/es/product/consul/1", "https://evil.example/image.png", "https://user:secret@tienda.omega.com.do/"):
            with self.assertRaises(omega.OmegaFetchError):
                omega.read_public_url(url)
        context = ssl._create_unverified_context()
        with self.assertRaises(omega.OmegaFetchError):
            omega.read_public_url(omega.product_url("1"), context)

    def test_partial_tls_chain_cannot_be_used(self):
        context = omega._default_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        if hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
            context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
            with self.assertRaises(omega.OmegaFetchError):
                omega.read_public_url(omega.product_url("1"), context)

    def test_batch_distinguishes_confirmed_missing_from_network_failure(self):
        context = omega._default_context()
        with patch.object(omega, "read_public_url", side_effect=[fixture().encode(), omega.OmegaProductMissing("404")]):
            sources, missing = omega.fetch_selected_references(["109640", "1"], context, workers=1)
        self.assertEqual(list(sources), ["109640"])
        self.assertEqual(missing, ["1"])
        with patch.object(omega, "read_public_url", side_effect=omega.OmegaFetchError("timeout")):
            with self.assertRaises(omega.OmegaFetchError):
                omega.fetch_selected_references(["109640"], context)

    def test_invalid_selection_and_excessive_parallelism_fail_before_network(self):
        for refs, workers in [(["1", "1"], 2), (["../../etc/passwd"], 2), (["1"], 3)]:
            with self.assertRaises(ValueError):
                omega.fetch_selected_references(refs, workers=workers)


if __name__ == "__main__":
    unittest.main()
