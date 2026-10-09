"""Replay public API responses: service mapping, units and allowance boundaries."""

import copy
import json
import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import price
from pricing_aws import AWSPrices, PROFILES
from pricing_gcp import GCPPrices
from pricing_contract import input_hash
from pricing_calculate import calculate
from pricing_errors import LookupError
from pricing_map import map_inventory

FIXTURES = ROOT / 'tests/fixtures/pricing/mapping'
EXAMPLES = ROOT / 'references/examples/pricing'


def read(path):
    return json.loads(path.read_text())


class CatalogMappingTests(unittest.TestCase):
    def setUp(self):
        self.data, self.assessment = map_inventory(read(EXAMPLES / 'demo-catalog-inventory.json'))
        self.aws = read(FIXTURES / 'aws-products.json')
        self.gcp = read(FIXTURES / 'gcp-skus.json')

    def gcp_provider(self, sid):
        row = self.gcp[sid]
        service = row['metadata']['service']
        display = {'services/E505-1604-58F8':'Networking', 'services/5490-F7B7-8DF6':'Cloud Logging',
                   'services/58CD-E7C3-72CA':'Cloud Monitoring', 'services/EE82-7A5E-871C':'Secret Manager',
                   'services/149C-F9EC-3994':'Artifact Registry', 'services/CCD8-9BF1-090E':'Kubernetes Engine',
                   'services/9662-B51E-5089':'Cloud SQL', 'services/6F81-5844-456A':'Compute Engine'}[service]
        provider = GCPPrices(session=Mock())
        provider._services = [{'name':service, 'serviceId':service.split('/')[-1], 'displayName':display}]
        provider.request = Mock(side_effect=[copy.deepcopy(row['metadata']), copy.deepcopy(row['price'])])
        return provider

    def gcp_item(self, sid):
        candidate = self.data['candidates'][1]
        return candidate, next(x for x in candidate['items'] if x['attributes'].get('sku_id') == sid)

    def test_all_inventory_items_have_supported_catalog_selectors(self):
        self.assertFalse(any(x['code'] == 'unconfirmed_catalog' for x in self.assessment['issues']))
        self.assertEqual(len(self.data['candidates'][0]['items']), 21)
        self.assertEqual(len(self.data['candidates'][1]['items']), 23)

    def test_gcp_new_selectors_match_actual_service_region_and_units(self):
        candidate = self.data['candidates'][1]
        for item in candidate['items']:
            sid = item['attributes'].get('sku_id')
            if sid not in self.gcp:
                continue
            with self.subTest(item=item['item_id']):
                result = self.gcp_provider(sid).lookup(candidate, item)
                self.assertEqual(result['sku'], sid)
                self.assertEqual(result['unit'], item['unit'])
                self.assertIsNone(result['effective_at'])

    def test_aws_new_selectors_use_exact_usage_type_and_real_units(self):
        candidate = self.data['candidates'][0]
        for item in candidate['items']:
            usage_type = item['attributes'].get('usage_type')
            service = PROFILES[(item['resource_kind'], item['billing_dimension'])][0]
            product = next((x for x in self.aws.values() if x['serviceCode'] == service and x['product']['attributes']['usagetype'] == usage_type), None)
            if product is None:
                continue
            with self.subTest(item=item['item_id']):
                client = Mock()
                client.describe_services.return_value = {'Services':[{'ServiceCode':service, 'AttributeNames':list(product['product']['attributes'])}]}
                client.get_products.return_value = {'PriceList':[json.dumps(product)]}
                result = AWSPrices(client).lookup(candidate, item)
                self.assertEqual(result['sku'], product['product']['sku'])
                self.assertEqual(result['unit'], item['unit'])
                self.assertIn({'Type':'TERM_MATCH','Field':'usagetype','Value':usage_type}, client.get_products.call_args.kwargs['Filters'])

    def test_prometheus_price_per_million_is_per_sample_after_normalizing(self):
        candidate, item = self.gcp_item('A4E4-DF03-CDB6')
        quote = self.gcp_provider('A4E4-DF03-CDB6').lookup(candidate, item)
        self.assertEqual(Decimal(quote['tiers'][0]['unit_price']) * 1000000, Decimal('0.06'))
        self.assertEqual(quote['tiers'][1]['from'], '50000000000')

    def test_public_nat_gateway_count_cannot_be_used_as_assigned_vm_count(self):
        candidate, item = self.gcp_item('32E2-4EFC-EF9F')
        for change in ('basis', 'cap'):
            wrong = copy.deepcopy(item)
            if change == 'basis':
                wrong['attributes'].pop('nat_billing_basis')
            else:
                wrong['quantity'] = 33
            provider = self.gcp_provider('32E2-4EFC-EF9F')
            with self.subTest(change=change), self.assertRaises(LookupError):
                provider.lookup(candidate, wrong)
            provider.request.assert_not_called()

    def test_catalog_free_tiers_are_preserved_but_not_granted_automatically(self):
        candidate, item = self.gcp_item('143F-A1B0-E0BE')
        data = copy.deepcopy(self.data)
        data['candidates'] = [copy.deepcopy(candidate)]
        data['candidates'][0]['items'] = [copy.deepcopy(item)]
        item = data['candidates'][0]['items'][0]
        item.update(quantity=1, monthly_usage={'min':'100','max':'100'}, incremental_usage={'min':'0','max':'0'})
        for policy, baseline, expected in [(None,None,None), ('verified_catalog',None,None), (None,'40',None), ('verified_catalog','40','45')]:
            item['attributes'].pop('free_tier_policy', None)
            item['attributes'].pop('tier_baseline_usage', None)
            if policy: item['attributes']['free_tier_policy'] = policy
            if baseline: item['attributes']['tier_baseline_usage'] = baseline
            prices = price.lookup(data, gcp_provider=self.gcp_provider('143F-A1B0-E0BE'))
            quote = prices['candidates'][0]['items'][0]['price']
            self.assertEqual(quote['tiers'][0]['unit_price'], '0')
            costs = calculate(data, prices)
            actual = costs['candidates'][0]['items'][0]['total_usd']
            with self.subTest(policy=policy, baseline=baseline):
                if expected is None:
                    self.assertIsNone(actual)
                    self.assertIn('unverified_free_tier', [x['code'] for x in costs['issues']])
                else:
                    self.assertEqual(actual, {'min':expected,'max':expected})

    def test_source_unit_change_cannot_masquerade_as_another_canonical_unit(self):
        candidate, item = self.gcp_item('7756-ADEF-84F4')
        wrong = copy.deepcopy(item)
        wrong['unit'] = 'gb_month'
        with self.assertRaises(LookupError) as caught:
            self.gcp_provider('7756-ADEF-84F4').lookup(candidate, wrong)
        self.assertEqual(caught.exception.code, 'unsupported_unit')


if __name__ == '__main__':
    unittest.main()
