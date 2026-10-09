"""One-source report projection, stale artifact rejection and settings preservation."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import price
from pricing_calculate import calculate, compare_costs
from pricing_contract import InputError, input_hash
from pricing_report import render_reports, update_report, START, END

EXAMPLES=ROOT/'references/examples/pricing'


def read(name):return json.loads((EXAMPLES/name).read_text())
def complete():
    data,prices=read('input.json'),read('prices-complete.json')
    return data,prices,calculate(data,prices)


class ReportTests(unittest.TestCase):
    def test_table_and_summary_use_same_costs_and_hashes(self):
        data,prices,costs=complete()
        table,summary=render_reports(data,prices,costs,'aws-example')
        for text in (table,summary):
            self.assertIn('USD 182.5',text);self.assertIn('255,500원',text)
            self.assertIn('예산 범위 안',text);self.assertIn(prices['queried_at'],text)
        self.assertIn(input_hash(costs),table);self.assertIn(input_hash(costs)[:12],summary)
        self.assertIn('가격 적용 시점',table);self.assertIn('synthetic-nodes',table)
        self.assertIn('절감액 미산정',table);self.assertIn('절감액 미산정',summary)

    def test_over_budget_warning_and_savings_unavailable_in_both_outputs(self):
        data,prices,_=complete();data['monthly_budget']={'min':0,'max':100000,'currency':'KRW'};prices['input_sha256']=input_hash(data)
        costs=calculate(data,prices);table,summary=render_reports(data,prices,costs,'aws-example')
        for text in (table,summary):self.assertIn('예산 초과',text);self.assertIn('별도 대안 견적이 없습니다',text)

    def test_partial_cost_not_presented_as_full_total_or_zero(self):
        data,prices=read('input.json'),read('prices-partial.json');costs=calculate(data,prices)
        table,summary=render_reports(data,prices,costs,'aws-example')
        for text in (table,summary):self.assertIn('확인된 소계 USD 146',text);self.assertIn('추가 비용 미정',text);self.assertIn('판정 미정',text)
        self.assertIn('조회 권한 없음',table);self.assertIn('조회 권한 없음',summary)
        self.assertNotIn('전체 원화: 0원',summary)

    def test_null_fx_and_budget_preserved(self):
        data,prices,_=complete();data['fx']=None;data['monthly_budget']=None;prices['input_sha256']=input_hash(data)
        table,summary=render_reports(data,prices,calculate(data,prices),'aws-example')
        self.assertIn('월 예산 미정',table);self.assertIn('환율 미정',table);self.assertIn('환율: 미정',summary)
        self.assertIn('전체 원화: 미산정',summary)

    def test_unknown_candidate_and_stale_or_tampered_cost_rejected(self):
        data,prices,costs=complete()
        with self.assertRaises(InputError):render_reports(data,prices,costs,'missing')
        for change in ('cost','budget','input','time'):
            changed=copy.deepcopy(costs)
            if change=='cost':changed['candidates'][0]['summary']['known_total_usd']['min']='1'
            elif change=='budget':changed['candidates'][0]['budget']['status']='over'
            elif change=='input':changed['input_sha256']='wrong'
            else:changed['generated_at']='invalid'
            with self.subTest(change=change),self.assertRaises(InputError):render_reports(data,prices,changed,'aws-example')

    def test_changed_resource_size_requires_new_quote(self):
        data,prices,costs=complete();data['candidates'][0]['items'][0]['quantity']=3
        with self.assertRaises(InputError):render_reports(data,prices,costs,'aws-example')
        # Synthetic response for the changed input; not an actual API query.
        prices['input_sha256']=input_hash(data);new=calculate(data,prices)
        table,summary=render_reports(data,prices,new,'aws-example')
        self.assertIn('USD 255.5',table);self.assertIn('USD 255.5',summary)
        self.assertNotIn('USD 182.5',summary)

    def test_supplied_alternative_savings_must_match_both_quotes(self):
        data,prices,costs=complete();alt_data=copy.deepcopy(data);alt_data['candidates'][0]['items'][0]['quantity']=1
        alt_prices=copy.deepcopy(prices);alt_prices['input_sha256']=input_hash(alt_data);alternative=calculate(alt_data,alt_prices)
        savings=compare_costs(costs,alternative)
        table,summary=render_reports(data,prices,costs,'aws-example',alternative=alternative,savings=savings)
        self.assertIn('월 차액: USD 73',table);self.assertIn('월 차액: USD 73',summary)
        savings['baseline_sha256']='wrong'
        with self.assertRaises(InputError):render_reports(data,prices,costs,'aws-example',alternative=alternative,savings=savings)

    def test_savings_options_must_be_paired(self):
        data,prices,costs=complete()
        with self.assertRaises(InputError):render_reports(data,prices,costs,'aws-example',alternative=costs)

    def test_report_update_preserves_all_other_sections(self):
        original='# 분석 보고서\n\n## 추천\n선택 이유\n\n'+START+'\n오래된 비용\n'+END+'\n\n## 보안\ncompliance: regulated\n## 인프라\n기존 내용\n'
        data,prices,costs=complete();_,summary=render_reports(data,prices,costs,'aws-example')
        updated=update_report(original,summary)
        self.assertEqual(updated.split(START)[0],original.split(START)[0])
        self.assertEqual(updated.split(END)[1],original.split(END)[1])
        self.assertNotIn('오래된 비용',updated);self.assertIn('USD 182.5',updated)

    def test_missing_duplicate_or_reversed_markers_rejected(self):
        for content in ('# old report',START+END+START+END,END+START):
            with self.subTest(content=content),self.assertRaises(InputError):update_report(content,START+'new'+END)

    def test_dynamic_text_cannot_break_table_or_render_html(self):
        data,prices,_=complete();cid='<script>\n|bad'
        data['candidates'][0]['candidate_id']=cid;prices['candidates'][0]['candidate_id']=cid;prices['input_sha256']=input_hash(data)
        costs=calculate(data,prices);table,summary=render_reports(data,prices,costs,cid)
        self.assertNotIn('<script>',table);self.assertNotIn('<script>',summary)
        self.assertIn('&lt;script&gt; \\|bad',table)

    def test_cli_updates_budget_summary_report_and_preserves_config(self):
        data,prices,costs=complete()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);deploy=root/'.deploy';analysis=deploy/'analysis';analysis.mkdir(parents=True)
            config=deploy/'config.yaml';config.write_text('# existing comment\ncompliance: regulated\ntemplate_version: v1.14.0\nfuture_key: preserve\n')
            before=config.read_bytes();report=deploy/'report.md';report.write_text('# 보고서\n## 추천\n이유\n'+START+'\nold\n'+END+'\n## 보안\n규제 내용 유지\n')
            for name,value in [('input.json',data),('prices.json',prices),('costs.json',costs)]: (analysis/name).write_text(json.dumps(value))
            args=['report','--input',str(analysis/'input.json'),'--prices',str(analysis/'prices.json'),'--costs',str(analysis/'costs.json'),'--candidate','aws-example',
                  '--budget-output',str(analysis/'budget.md'),'--summary-output',str(analysis/'cost-summary.md'),'--report',str(report)]
            with patch('pricing_aws.boto3.client') as aws,patch('pricing_gcp.google.auth.default') as gcp,redirect_stdout(io.StringIO()):code=price.main(args)
            aws.assert_not_called();gcp.assert_not_called();self.assertEqual(code,0)
            self.assertEqual(config.read_bytes(),before);self.assertIn('규제 내용 유지',report.read_text())
            self.assertIn((analysis/'cost-summary.md').read_text().strip(),report.read_text())
            self.assertIn('255,500원',(analysis/'budget.md').read_text())
            # Invalid marker pairs must not replace any previously generated file.
            old_budget=(analysis/'budget.md').read_bytes();report.write_text('legacy without markers')
            with redirect_stdout(io.StringIO()):code=price.main(args)
            self.assertEqual(code,2);self.assertEqual((analysis/'budget.md').read_bytes(),old_budget)
            self.assertEqual(report.read_text(),'legacy without markers')

    def test_cli_cannot_write_config_or_replace_report_as_summary(self):
        data,prices,costs=complete()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in [('input.json',data),('prices.json',prices),('costs.json',costs)]: (root/name).write_text(json.dumps(value))
            config=root/'config.yaml';config.write_text('compliance: regulated\n')
            for destination in (config,root/'report.md'):
                args=['report','--input',str(root/'input.json'),'--prices',str(root/'prices.json'),'--costs',str(root/'costs.json'),'--candidate','aws-example',
                      '--budget-output',str(destination),'--summary-output',str(root/'summary.md')]
                with redirect_stdout(io.StringIO()):code=price.main(args)
                self.assertEqual(code,2);self.assertEqual(config.read_text(),'compliance: regulated\n')
                self.assertFalse((root/'summary.md').exists())

    def test_cli_partial_result_still_generates_honest_report(self):
        data,prices=read('input.json'),read('prices-partial.json');costs=calculate(data,prices)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,value in [('input.json',data),('prices.json',prices),('costs.json',costs)]: (root/name).write_text(json.dumps(value))
            args=['report','--input',str(root/'input.json'),'--prices',str(root/'prices.json'),'--costs',str(root/'costs.json'),'--candidate','aws-example',
                  '--budget-output',str(root/'budget.md'),'--summary-output',str(root/'summary.md')]
            with redirect_stdout(io.StringIO()):code=price.main(args)
            self.assertEqual(code,3);self.assertIn('확인된 소계',(root/'budget.md').read_text())


if __name__=='__main__':unittest.main()
