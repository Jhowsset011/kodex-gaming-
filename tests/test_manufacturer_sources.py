"""Manufacturer citations must identify the product's own maker."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from manufacturer_sources import validate_manufacturer_url


class ManufacturerSourcesTests(unittest.TestCase):
    def test_verified_brand_domain_and_subdomains_are_supported(self):
        for brand, url in [
            ('MSI', 'https://www.msi.com/Monitor/MAG-272F-X24/Specification'),
            ('Logitech', 'https://www.logitechg.com/en-us/products/gaming-mice/g203.html'),
            ('HP', 'https://support.hp.com/us-en/product/example'),
            ('Corsair', 'https://www.corsair.com/us/en/p/pc-cases/example'),
        ]:
            with self.subTest(brand=brand, url=url):
                self.assertEqual(validate_manufacturer_url(url, brand), url)

    def test_unrelated_brand_shop_spoofed_domain_and_insecure_links_are_rejected(self):
        urls = [
            'https://www.corsair.com/us/en/p/monitor/example',
            'https://nexcomtienda.com.do/producto/example/',
            'https://msi.com.other.example/Monitor/example',
            'https://other-msi.com/Monitor/example',
            'http://www.msi.com/Monitor/example',
            'https://user:password@www.msi.com/Monitor/example',
            'https://www.msi.com:8080/Monitor/example',
            'https://www.msi.com:bad/Monitor/example',
            'https://www.msi.com/',
            'https://www.msi.com/Monitor/example\n',
            None,
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_manufacturer_url(url, 'MSI')

    def test_unknown_brand_is_not_assigned_another_makers_citation(self):
        with self.assertRaises(ValueError):
            validate_manufacturer_url('https://www.msi.com/Monitor/example', 'Genérico')


if __name__ == '__main__':
    unittest.main()
