"""Protect SKU identity, new-product semantics, public data and price barriers."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sync_nexcom_catalog as sync
from catalog_markup import clean_description, description_text
from costos_estimados import estimate_cost, load_factors, cost_document
from nexcom_feed import fetch_catalog, index_sources


def old(ref='100001', price=1000):
    return {'id': ref, 'reference': ref, 'name': 'Monitor MSI de prueba', 'category': 'Monitores',
            'subcategory': 'De escritorio', 'brand': 'MSI', 'price': price, 'stock': True,
            'image': 'img/catalogo/sin-imagen.svg', 'description': 'Ficha anterior'}


def source(ref='100001', price=100000, stock=True, brand='MSI', category='Componentes'):
    return {'id': int(ref), 'sku': ref, 'name': f'Monitor {brand} de prueba',
            'short_description': '<p>Intro</p>', 'description': '<p data-start="1">⚡ <strong>Panel:</strong> IPS</p>',
            'prices': {'price': str(price), 'currency_code': 'DOP', 'currency_minor_unit': 2},
            'is_in_stock': stock, 'stock_availability': {'class': 'in-stock' if stock else 'out-of-stock'},
            'categories': [{'name': category}], 'brands': [{'name': brand}],
            'images': [], 'attributes': [], 'permalink': f'https://nexcomtienda.com.do/producto/prueba-{ref}/'}


def catalog(products=None):
    return {'source': 'Anterior', 'updated': '2026-10-20T00:00:00Z', 'products': products or [old()]}


class NexcomCatalogTests(unittest.TestCase):
    def test_matching_sku_preserves_storefront_id_image_and_pulls_all_text(self):
        p = dict(old(), id='42', sourceImage='https://sis.omega.com.do/ProductImages/example.png')
        result, _, report = sync.plan_catalog(catalog([p]), [source()], {'100001'}, set())
        out = result['products'][0]
        self.assertEqual(out['id'], '42')
        self.assertEqual(out['image'], p['image'])
        self.assertEqual(out['sourceImage'], p['sourceImage'])
        self.assertEqual(out['spec'], 'Intro')
        self.assertEqual(out['description'], '<p>⚡ <strong>Panel:</strong> IPS</p>')
        self.assertEqual(out['price'], 1000)
        self.assertEqual(report['prices'][0]['source'], 'Nexcom')
        self.assertNotIn('estimatedCost', json.dumps(result))

    def test_first_run_seeds_full_catalog_without_importing_historical_products(self):
        result, baseline, _ = sync.plan_catalog(catalog(), [source(), source('100002')], set(), set())
        self.assertEqual(len(result['products']), 1)
        self.assertEqual(set(baseline['skus']), {'100001', '100002'})

    def test_legacy_hardware_caveats_do_not_replace_nexcom_specifications(self):
        previous=dict(old(),id='19296')
        incoming=source();incoming['description']='<p>Puertos: HDMI 2.0</p>'
        result,_,_=sync.plan_catalog(catalog([previous]),[incoming],{'100001'},set())
        product=result['products'][0]
        self.assertEqual(next(r['value'] for r in product['specifications'] if r['label']=='Puertos'),'HDMI 2.0')
        self.assertNotIn('specificationNote',product)

    def test_new_unavailable_product_is_imported_then_released_and_not_relabelled_later(self):
        rows = [source(), source('100002', stock=False)]
        result, baseline, report = sync.plan_catalog(catalog(), rows, {'100001'}, set())
        added = next(p for p in result['products'] if p['reference'] == '100002')
        self.assertTrue(added['proximamente'])
        self.assertFalse(added['stock'])
        self.assertEqual(report['newProducts'][0]['name'], rows[1]['name'])
        rows[1] = source('100002', stock=True)
        available, baseline, report = sync.plan_catalog(result, rows, set(baseline['skus']), set())
        self.assertNotIn('proximamente', available['products'][1])
        self.assertEqual(report['releasedComingSoon'], ['100002'])
        rows[1] = source('100002', stock=False)
        unavailable, _, _ = sync.plan_catalog(available, rows, set(baseline['skus']), set())
        self.assertNotIn('proximamente', unavailable['products'][1])

    def test_disappeared_and_reappeared_sku_is_not_a_new_product(self):
        result, baseline, _ = sync.plan_catalog(catalog(), [source(), source('100002', stock=False)], {'100001', '100002'}, set())
        self.assertEqual(len(result['products']), 1)
        self.assertIn('100002', baseline['skus'])

    def test_manual_import_overrides_seen_and_department_and_reports_unknown(self):
        new = source('100002', stock=False, brand='NewMaker', category='Seguridad y Redes')
        result, _, report = sync.plan_catalog(catalog(), [source(), new], {'100001', '100002'}, {'100002', '999999'})
        self.assertEqual(len(result['products']), 2)
        self.assertTrue(result['products'][1]['proximamente'])
        self.assertEqual(report['manualApplied'], ['100002'])
        self.assertEqual(report['manualMissing'], ['999999'])

    def test_security_department_requires_known_brand_but_honors_parent_category_paths(self):
        self.assertFalse(sync.interested(source('100002', brand='Unknown', category='Seguridad y Redes'), {'msi'}))
        self.assertTrue(sync.interested(source('100002', category='Seguridad y Redes'), {'msi'}))
        s = source('100002', brand='Unknown', category='Bocinas')
        s['categories'][0]['link'] = 'https://nexcomtienda.com.do/categoria-producto/audio-y-video/bocinas/'
        self.assertTrue(sync.interested(s, {'msi'}))

    def test_refurbished_and_explicitly_deleted_products_never_auto_import(self):
        refurb = source('100002');refurb['name'] += ' refurbished'
        result, _, _ = sync.plan_catalog(catalog(), [source(), refurb, source('62635')], {'100001'}, set())
        self.assertEqual(len(result['products']), 1)

    def test_price_guard_retains_over_500_and_blocks_mass_changes_even_if_retained(self):
        result, _, report = sync.plan_catalog(catalog(), [source(price=160000)], {'100001'}, set())
        self.assertEqual(result['products'][0]['price'], 1000)
        self.assertEqual(report['retainedPrices'], ['100001'])
        with self.assertRaises(sync.PriceGuardError): sync.enforce_guards(report)

    def test_initial_exception_keeps_individual_500_guard(self):
        result,_,report=sync.plan_catalog(catalog(),[source(price=160000)],{'100001'},set())
        sync.enforce_guards(report,initial_migration=True)
        self.assertEqual(result['products'][0]['price'],1000)
        self.assertEqual(report['retainedPrices'],['100001'])
        with self.assertRaises(sync.PriceGuardError):sync.enforce_guards(report)

    def test_initial_exception_is_rejected_once_source_is_nexcom(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'js').mkdir()
            current=dict(catalog(),source='Nexcom — API pública')
            path=root/'js/productos-v2.json';path.write_text(json.dumps(current));before=path.read_bytes()
            with patch.object(sync,'ROOT',root),patch.object(sys,'argv',['sync','--initial-price-migration']),patch.object(sync,'fetch_catalog') as fetch:
                with self.assertRaisesRegex(ValueError,'nunca sobre Nexcom'):sync.main()
                fetch.assert_not_called()
            self.assertEqual(path.read_bytes(),before)

    def test_exact_20_percent_allowed_and_over_20_rejected(self):
        products = [old(str(100001+i)) for i in range(5)]
        rows = [source(str(100001+i), price=110000 if i == 0 else 100000) for i in range(5)]
        _, _, report = sync.plan_catalog(catalog(products), rows, {p['reference'] for p in products}, set())
        sync.enforce_guards(report)
        rows[1]['prices']['price'] = '110000'
        _, _, report = sync.plan_catalog(catalog(products), rows, {p['reference'] for p in products}, set())
        with self.assertRaises(sync.PriceGuardError): sync.enforce_guards(report)

    def test_zero_null_negative_and_real_usd_prices_never_publish(self):
        for value in ('0', '-100', None, 'NaN'):
            with self.subTest(value=value):
                s=source();s['prices']['price']=value
                with self.assertRaises(ValueError):sync.sale_price(s)
        s=source();s['prices']['currency_code']='USD'
        with self.assertRaises(ValueError):sync.sale_price(s)
        s['prices'].update(currency_symbol='RD$', currency_prefix='RD$')
        self.assertEqual(sync.sale_price(s),1000)

    def test_unknown_stock_or_missing_currency_rejects_catalog(self):
        s=source();s['is_in_stock']='yes'
        with self.assertRaises(ValueError):sync.source_stock(s)
        s=source();s['stock_availability']={}
        with self.assertRaises(ValueError):sync.source_stock(s)

    def test_duplicate_sku_or_incomplete_pagination_stops_import(self):
        with self.assertRaises(ValueError): index_sources([source(), dict(source(),id=200000)])
        with patch('nexcom_feed.read_page', side_effect=[([source()],101,2),([source('100002')],102,2)]), patch('nexcom_feed.time.sleep'):
            with self.assertRaises(ValueError):fetch_catalog()

    def test_all_pages_are_collected_without_dropping_products(self):
        page1=[source(str(100001+i)) for i in range(100)]
        with patch('nexcom_feed.read_page', side_effect=[(page1,101,2),([source('100101')],101,2)]), patch('nexcom_feed.time.sleep'):
            self.assertEqual(len(fetch_catalog()),101)

    def test_api_failure_or_guard_keeps_both_catalogs_and_seen_untouched(self):
        for failure in ('api', 'guard'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'js').mkdir();(root/'scripts').mkdir()
                before=json.dumps(catalog())
                for name in ('productos.json','productos-v2.json'):(root/'js'/name).write_text(before)
                (root/'scripts/altas-manuales.json').write_text('[]')
                (root/'scripts/nexcom_seen_skus.json').write_text('{"version":1,"skus":["100001"]}')
                prior={p:p.read_bytes() for p in root.rglob('*.json')}
                with patch.object(sync,'ROOT',root),patch.object(sys,'argv',['sync_nexcom_catalog.py']), \
                     patch.object(sync,'fetch_catalog',side_effect=ValueError('API falló') if failure=='api' else None,return_value=[source(price=110000)]), \
                     patch.object(sync,'print_report'):
                    with self.assertRaises(ValueError):sync.main()
                self.assertTrue(all(path.read_bytes()==body for path,body in prior.items()))

    def test_single_factor_table_estimates_only_and_never_adds_private_fields_to_catalog(self):
        factors=load_factors()
        self.assertEqual(estimate_cost(1000,'100001',factors),Decimal('706.20'))
        for ref in ('105815','105816','111768'):
            self.assertEqual(estimate_cost(1000,ref,factors),Decimal('807.10'))
        current=catalog();before=deepcopy(current)
        document=cost_document(current,factors)
        self.assertEqual(document['kind'],'estimate')
        self.assertEqual(current,before)
        self.assertNotIn('estimatedCost',json.dumps(current))

    def test_estimates_use_fresh_nexcom_price_even_when_sale_price_is_held(self):
        current=catalog()
        document=cost_document(current,load_factors(),{'100001':1600})
        self.assertEqual(document['products'][0]['estimatedCost'],'1129.92')
        self.assertEqual(current['products'][0]['price'],1000)
        missing=cost_document(current,load_factors(),{})
        self.assertIsNone(missing['products'][0]['estimatedCost'])

    def test_cost_export_refuses_to_replace_any_existing_financial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'costos-vip.json'
            original='{"verifiedCost":1234.56}'
            output.write_text(original)
            result=subprocess.run([sys.executable,str(sync.ROOT/'scripts/costos_estimados.py'),'--output',str(output)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(output.read_text(),original)


class DescriptionSafetyTests(unittest.TestCase):
    def test_only_permitted_tags_without_attributes_or_script_contents(self):
        raw='<p data-start="4" onclick="evil()">⚡ <strong style="color:red">Panel</strong><br>IPS<img src=x onerror=evil()></p><script>evil()</script>'
        clean=clean_description(raw)
        self.assertEqual(clean,'<p>⚡ <strong>Panel</strong><br>IPS</p>')
        self.assertNotIn('evil',clean)

    def test_div_rows_become_readable_paragraphs_and_plain_text(self):
        clean=clean_description('<div>Marca: AOC</div><div>Panel: IPS</div>')
        self.assertEqual(clean,'<p>Marca: AOC</p><p>Panel: IPS</p>')
        self.assertEqual(description_text(clean),'Marca: AOC\nPanel: IPS')


if __name__=='__main__':unittest.main()
