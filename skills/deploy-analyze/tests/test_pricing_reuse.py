"""Dated price reuse must reject changes that require a new public API quote."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import price
from pricing_contract import InputError, input_hash
from pricing_reuse import reuse_prices


class PriceReuseTests(unittest.TestCase):
    def setUp(self):
        root = ROOT.parents[1] / 'docs/validation/t16-catalog-mapping'
        self.source = json.loads((root / 'pricing-input.json').read_text())
        self.prices = json.loads((root / 'prices.json').read_text())
        self.data = copy.deepcopy(self.source)
        self.data['input_id'] = 'demo-usage-scenario'

    def test_quantity_usage_changes_preserve_original_query_and_money(self):
        item = self.data['candidates'][0]['items'][0]
        item['quantity'] = 2
        item['incremental_usage'] = {'min':'1','max':'1'}
        with patch('pricing_aws.boto3.client') as aws, patch('pricing_gcp.google.auth.default') as gcp:
            result, proof = reuse_prices(self.data, self.source, self.prices)
        aws.assert_not_called(); gcp.assert_not_called()
        self.assertEqual(result['queried_at'], self.prices['queried_at'])
        self.assertEqual(result['candidates'], self.prices['candidates'])
        self.assertEqual(proof['source_prices_sha256'], input_hash(self.prices))
        self.assertEqual(result['input_sha256'], input_hash(self.data))

    def test_target_region_sku_unit_or_resource_changes_require_lookup(self):
        for change in ('target','region','sku','unit','resource'):
            data = copy.deepcopy(self.data)
            candidate = data['candidates'][0]
            item = candidate['items'][0]
            if change == 'target': candidate['target'] = 'gcp'
            elif change == 'region': candidate['region'] = 'us-east-1'
            elif change == 'sku': item['attributes']['usage_type'] = 'other-price'
            elif change == 'unit': item['unit'] = 'request'
            else: item['resource_kind'] = 'other-resource'
            with self.subTest(change=change), self.assertRaises(InputError):
                reuse_prices(data, self.source, self.prices)

    def test_source_input_hash_mismatch_is_rejected(self):
        self.prices['input_sha256'] = 'tampered'
        with self.assertRaises(InputError): reuse_prices(self.data, self.source, self.prices)

    def test_new_item_and_capped_nat_are_rejected(self):
        data = copy.deepcopy(self.data)
        data['candidates'][0]['items'][0]['item_id'] = 'new-item'
        with self.assertRaises(InputError): reuse_prices(data, self.source, self.prices)
        item = next(x for x in self.data['candidates'][1]['items'] if x['resource_kind'] == 'cloud_nat' and x['billing_dimension'] == 'gateway_hours')
        item['quantity'] = 33
        with self.assertRaises(InputError): reuse_prices(self.data, self.source, self.prices)

    def test_excluded_item_is_removed_without_inventing_a_zero_price(self):
        self.data['candidates'][0]['items'].pop()
        result, _ = reuse_prices(self.data, self.source, self.prices)
        self.assertEqual(len(result['candidates'][0]['items']), len(self.prices['candidates'][0]['items']) - 1)

    def test_cli_emits_separate_proof_and_rejects_overwriting_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, doc in [('input', self.data), ('source', self.source), ('prices', self.prices)]:
                (root / (name + '.json')).write_text(json.dumps(doc))
            args = ['reuse-prices','--input',str(root/'input.json'),'--source-input',str(root/'source.json'),
                    '--prices',str(root/'prices.json'),'--output',str(root/'reused.json'),'--evidence',str(root/'proof.json')]
            with redirect_stdout(io.StringIO()): self.assertEqual(price.main(args), 0)
            self.assertEqual(json.loads((root/'proof.json').read_text())['queried_at'], self.prices['queried_at'])
            before = (root/'source.json').read_bytes()
            args[-1] = str(root/'source.json')
            with redirect_stdout(io.StringIO()): self.assertEqual(price.main(args), 2)
            self.assertEqual((root/'source.json').read_bytes(), before)
