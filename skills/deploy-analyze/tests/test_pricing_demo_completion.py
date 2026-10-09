"""Demonstration completion criteria with explicit forecast inputs and dated API prices."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from pricing_contract import input_hash
from pricing_calculate import calculate
from pricing_map import map_inventory
from pricing_report import render_reports, verified_costs
from pricing_reuse import reuse_prices

DEMO = ROOT.parents[1] / 'docs/validation/t16-demo'


def read(path): return json.loads(path.read_text())


class DemoCompletionTests(unittest.TestCase):
    def setUp(self):
        self.data = read(DEMO / 'baseline/pricing-input.json')
        self.prices = read(DEMO / 'baseline/prices.json')
        self.costs = read(DEMO / 'baseline/costs.json')
        self.assessment = read(DEMO / 'baseline/resource-assessment.json')

    def test_review_report_has_same_verified_costs_warning_and_savings(self):
        verified_costs(self.data, self.prices, self.costs, self.assessment)
        budget, summary = render_reports(self.data, self.prices, self.costs, 'demo-aws', self.assessment,
                                         read(DEMO/'alternative/costs.json'), read(DEMO/'savings.json'))
        self.assertEqual(budget, (DEMO/'baseline/budget.md').read_text())
        self.assertEqual(summary, (DEMO/'baseline/cost-summary.md').read_text())
        report = (DEMO/'report.md').read_text()
        self.assertIn(summary.strip(), report)
        self.assertIn('예산 초과', summary)
        self.assertIn('대안 견적 대비 월 차액', summary)
        self.assertIn('ADR-0014', report)
        self.assertIn('실제 청구·운영 통계가 아니다', report)
        self.assertTrue(self.costs['candidates'][0]['summary']['total_complete'])
        self.assertFalse(self.costs['candidates'][1]['summary']['total_complete'])

    def test_normal_over_unknown_and_simulated_api_failure(self):
        for case, budget, expected in [('normal',{'min':100001,'max':500000,'currency':'KRW'},'within'),
                                       ('over',{'min':0,'max':100000,'currency':'KRW'},'over'),
                                       ('unknown',None,'unknown')]:
            data = copy.deepcopy(self.data); data['monthly_budget'] = budget
            prices, _ = reuse_prices(data, self.data, self.prices)
            result = calculate(data, prices)
            with self.subTest(case=case): self.assertEqual(result['candidates'][0]['budget']['status'], expected)
        failed = copy.deepcopy(self.prices)
        record = failed['candidates'][0]['items'][1]
        error = {'candidate_id':'demo-aws','item_id':record['item_id'],'code':'timeout','message':'Simulated API timeout','retryable':True}
        record.update(status='unavailable',price=None,issue=error)
        failed.update(status='partial',issues=[error])
        result = calculate(self.data, failed)
        self.assertFalse(result['candidates'][0]['summary']['total_complete'])
        self.assertIsNone(result['candidates'][0]['items'][1]['total_usd'])

    def test_traffic_replica_change_recalculates_without_automatically_reducing_nodes(self):
        inventory = read(DEMO/'baseline-inventory.json')
        for candidate in inventory['candidates']:
            if candidate['traffic']:
                for workload in candidate['traffic']['workloads']: workload['replicas'] = 2
        data, assessment = map_inventory(inventory)
        prices, _ = reuse_prices(data, self.data, self.prices)
        result = calculate(data, prices, assessment)
        nodes = next(x for x in data['candidates'][0]['items'] if x['resource_kind']=='ec2')
        self.assertEqual(nodes['quantity'], 3)
        self.assertEqual(result['candidates'][0]['summary']['known_total_usd'], self.costs['candidates'][0]['summary']['known_total_usd'])
        self.assertEqual(assessment['candidates'][0]['sizing']['demand']['pod_slots'], '16')
