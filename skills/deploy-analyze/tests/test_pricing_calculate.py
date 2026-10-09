"""Costing and budget guarantees using synthetic prices, no external services."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import price
from pricing_contract import InputError, input_hash
from pricing_calculate import calculate, compare_costs
from pricing_map import map_inventory

EXAMPLES=ROOT/'references/examples/pricing'


def read(name):return json.loads((EXAMPLES/name).read_text())
def amount(value):return {'min':str(value),'max':str(value)}
def numeric(value):return None if value is None else tuple(None if bound is None else Decimal(bound) for bound in value.values())
def candidate(result):return result['candidates'][0]

def case(usages,increments=None,tiers=None):
    data=read('input.json');base=data['candidates'][0]['items'][0]
    data['candidates'][0]['items']=[]
    records=[]
    tiers=tiers or [{'from':'0','to':None,'unit_price':'1'}]
    for index,bounds in enumerate(usages):
        item=copy.deepcopy(base);item.update(item_id='item-'+str(index),resource_id='resource-'+str(index),resource_kind='logs',billing_dimension='ingestion',
            unit='gb',cost_type='variable',quantity=1,attributes={},monthly_usage=bounds,incremental_usage=increments[index] if increments else amount('0'))
        data['candidates'][0]['items'].append(item)
        p=copy.deepcopy(read('prices-complete.json')['candidates'][0]['items'][0]);p.update(item_id=item['item_id'])
        p['price'].update(sku='shared-sku',unit='gb',source_unit='GB',tiers=copy.deepcopy(tiers))
        records.append(p)
    prices=read('prices-complete.json');prices['candidates'][0]['items']=records;prices['input_sha256']=input_hash(data)
    return data,prices

TIERS=[{'from':'0','to':'10','unit_price':'1'},{'from':'10','to':None,'unit_price':'0.5'}]


class CalculationTests(unittest.TestCase):
    def test_complete_example_and_fx(self):
        data,prices=read('input.json'),read('prices-complete.json')
        result=calculate(data,prices);out=candidate(result)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(numeric(out['summary']['known_total_usd']),(Decimal('182.5'),Decimal('182.5')))
        self.assertEqual(out['summary']['total_krw'],amount('255500'))
        self.assertEqual(out['budget']['status'],'within')
        self.assertEqual(result['input_sha256'],input_hash(data));self.assertEqual(result['prices_sha256'],input_hash(prices))

    def test_hourly_quantity_and_storage_not_all_multiplied_by_730(self):
        data,prices=case([amount('20')]);item=data['candidates'][0]['items'][0];item.update(unit='gb_month',billing_dimension='storage')
        prices['candidates'][0]['items'][0]['price'].update(unit='gb_month',source_unit='GB-Mo')
        prices['input_sha256']=input_hash(data)
        result=calculate(data,prices)
        self.assertEqual(candidate(result)['summary']['known_total_usd'],amount('20'))

    def test_same_sku_usage_pooled_before_tier_charge(self):
        data,prices=case([amount('6'),amount('8')],tiers=TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_total_usd'],amount('12'))
        self.assertEqual([item['total_usd'] for item in out['items']],[amount('6'),amount('6')])

    def test_quantity_multiplies_usage_before_pooling(self):
        data,prices=case([amount('5'),amount('5')],tiers=TIERS)
        data['candidates'][0]['items'][0]['quantity']=2;prices['input_sha256']=input_hash(data)
        self.assertEqual(candidate(calculate(data,prices))['summary']['known_total_usd'],amount('12.5'))

    def test_same_sku_conflicting_tariffs_rejected(self):
        data,prices=case([amount('1'),amount('2')]);prices['candidates'][0]['items'][1]['price']['tiers'][0]['unit_price']='2'
        with self.assertRaises(InputError):calculate(data,prices)

    def test_same_sku_mixed_classification_rejected(self):
        data,prices=case([amount('730'),amount('730')]);data['candidates'][0]['items'][0]['cost_type']='fixed';prices['input_sha256']=input_hash(data)
        with self.assertRaises(InputError):calculate(data,prices)

    def test_incremental_tiers_use_total_minus_existing_not_first_tier(self):
        data,prices=case([amount('15')],[amount('3')],TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_total_usd'],amount('12.5'))
        self.assertEqual(out['summary']['known_incremental_usd'],amount('1.5'))
        self.assertEqual(out['items'][0]['incremental_usd'],amount('1.5'))

    def test_multi_item_incremental_marginals_sum_to_group_delta(self):
        data,prices=case([amount('6'),amount('8')],[amount('1'),amount('2')],TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_incremental_usd'],amount('1.5'))
        self.assertEqual(sum(Decimal(item['incremental_usd']['min']) for item in out['items']),Decimal('1.5'))

    def test_known_total_and_incremental_range(self):
        data,prices=case([amount('15')],[{'min':'1','max':'3'}],TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_incremental_usd'],{'min':'0.5','max':'1.5'})
        self.assertEqual(out['items'][0]['incremental_usd'],{'min':'0.5','max':'1.5'})

    def test_variable_total_with_exact_increment_has_bounded_delta(self):
        data,prices=case([{'min':'8','max':'12'}],[amount('2')],TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_incremental_usd'],{'min':'1','max':'2'})
        self.assertTrue(out['summary']['incremental_complete'])

    def test_both_ranges_need_correlation_for_tier_increment(self):
        data,prices=case([{'min':'8','max':'12'}],[{'min':'1','max':'3'}],TIERS)
        out=candidate(calculate(data,prices))
        self.assertFalse(out['summary']['incremental_complete'])
        self.assertIsNone(out['items'][0]['incremental_usd'])
        self.assertTrue(out['summary']['total_complete'])

    def test_range_marginal_extrema_not_summed_as_total_extrema(self):
        data,prices=case([{'min':'8','max':'12'},{'min':'10','max':'14'}],tiers=TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_total_usd'],{'min':'14','max':'18'})
        self.assertEqual(out['items'][0]['total_usd'],{'min':'8','max':'11'})
        self.assertEqual(out['items'][1]['total_usd'],{'min':'5','max':'8'})

    def test_missing_price_not_zero_and_budget_not_within(self):
        out=candidate(calculate(read('input.json'),read('prices-partial.json')))
        self.assertIsNone(out['items'][1]['total_usd']);self.assertIsNone(out['summary']['total_krw'])
        self.assertFalse(out['summary']['total_complete']);self.assertEqual(out['budget']['status'],'unknown')
        self.assertEqual(out['summary']['known_total_usd'],amount('146'))

    def test_known_partial_subtotal_can_prove_over_budget(self):
        data,prices=read('input.json'),read('prices-partial.json');data['monthly_budget']={'min':0,'max':100000,'currency':'KRW'};prices['input_sha256']=input_hash(data)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['budget']['status'],'over');self.assertFalse(out['summary']['total_complete'])

    def test_all_prices_unavailable_has_no_fake_zero_subtotal(self):
        data,prices=read('input.json'),read('prices-partial.json')
        error=copy.deepcopy(prices['issues'][0]);error['item_id']='nodes'
        prices['candidates'][0]['items'][0].update(status='unavailable',price=None,issue=error)
        prices['issues']=[error,prices['issues'][0]]
        out=candidate(calculate(data,prices));self.assertIsNone(out['summary']['known_total_usd'])
        self.assertIsNone(out['summary']['fixed_usd']);self.assertEqual(out['budget']['status'],'unknown')

    def test_unknown_and_unbounded_usage(self):
        for total in (None,{'min':'1','max':None}):
            data,prices=case([total])
            result=calculate(data,prices);out=candidate(result)
            self.assertEqual(result['status'],'partial');self.assertFalse(out['summary']['total_complete'])
            self.assertEqual(out['budget']['status'],'unknown')
            if total is None:self.assertIsNone(out['items'][0]['total_usd'])
            else:self.assertIsNone(out['items'][0]['total_usd']['max'])

    def test_zero_usage_and_real_zero_rate_are_valid_zeros(self):
        for quantity,rate in (('0','1'),('1','0')):
            data,prices=case([amount(quantity)]);prices['candidates'][0]['items'][0]['price']['tiers'][0]['unit_price']=rate
            self.assertEqual(candidate(calculate(data,prices))['summary']['known_total_usd'],amount('0'))

    def test_no_fx_does_not_fail_usd_calculation(self):
        data,prices=read('input.json'),read('prices-complete.json');data['fx']=None;prices['input_sha256']=input_hash(data)
        result=calculate(data,prices)
        self.assertEqual(result['status'],'complete');self.assertEqual(candidate(result)['budget']['status'],'unknown')
        self.assertIsNone(candidate(result)['summary']['total_krw'])

    def test_null_or_unbounded_budget_not_unlimited(self):
        for budget in (None,{'min':1000001,'max':None,'currency':'KRW'}):
            data,prices=read('input.json'),read('prices-complete.json');data['monthly_budget']=budget;prices['input_sha256']=input_hash(data)
            self.assertEqual(candidate(calculate(data,prices))['budget']['status'],'unknown')

    def test_budget_boundary_and_range_crossing(self):
        for bounds,expected in ((amount('10'),'within'),(amount('10.0001'),'over'),({'min':'8','max':'12'},'may_exceed')):
            data,prices=case([bounds]);data.update(monthly_budget={'min':0,'max':100000,'currency':'KRW'});data['fx']['usd_to_krw']='10000';prices['input_sha256']=input_hash(data)
            self.assertEqual(candidate(calculate(data,prices))['budget']['status'],expected)

    def test_incremental_budget_basis_is_explicit(self):
        data,prices=case([amount('100')],[amount('1')]);data['budget_basis']='incremental';data['fx']['usd_to_krw']='10000';data['monthly_budget']={'min':0,'max':100000,'currency':'KRW'};prices['input_sha256']=input_hash(data)
        out=candidate(calculate(data,prices));self.assertEqual(out['budget']['status'],'within');self.assertEqual(out['budget']['basis'],'incremental')

    def test_changed_input_and_mismatching_price_identity_rejected(self):
        mutations=[lambda p:p.update(input_sha256='wrong'),lambda p:p.update(input_id='wrong'),
                   lambda p:p['candidates'][0].update(region='wrong'),lambda p:p['candidates'][0]['items'].pop(),
                   lambda p:p['candidates'].append(copy.deepcopy(p['candidates'][0])),lambda p:p.update(unknown=True),
                   lambda p:p.update(issues=[{}])]
        for mutate in mutations:
            prices=read('prices-complete.json');mutate(prices)
            with self.subTest(mutate=mutate),self.assertRaises(InputError):calculate(read('input.json'),prices)

    def test_malformed_tiers_and_currency_rejected(self):
        for update in ({'currency':'KRW'},{'unit':'gib'},{'tiers':[{'from':'1','to':None,'unit_price':'1'}]},
                       {'tiers':[{'from':'0','to':'10','unit_price':'1'}]}, {'tiers':[{'from':'0','to':None,'unit_price':'NaN'}]}):
            data,prices=case([amount('1')]);prices['candidates'][0]['items'][0]['price'].update(update)
            with self.subTest(update=update),self.assertRaises(InputError):calculate(data,prices)

    def test_gcp_money_evidence_checked(self):
        data,prices=read('gcp-input.json'),read('gcp-prices-complete.json')
        result=calculate(data,prices);out=candidate(result)
        self.assertEqual(out['summary']['known_total_usd'],amount('92.75526'))
        details=prices['candidates'][0]['items'][0]['price']['provider_details'];details['tiers'][0]['nanos']+=1
        with self.assertRaises(InputError):calculate(data,prices)

    def test_gcp_aggregation_requires_explicit_baseline_and_monthly_period(self):
        data,prices=case([amount('15')],[amount('3')],TIERS)
        p=prices['candidates'][0]['items'][0]['price'];p['source_unit']='GBy'
        p['provider_details']={'usage_unit':'GBy','base_unit':'By','base_unit_conversion_factor':'1000000000','display_quantity':'1','currency_conversion_rate':'1',
            'aggregation':{'aggregationLevel':'ACCOUNT','aggregationInterval':'MONTHLY','aggregationCount':1},'effective_time':p['effective_at'],
            'tiers':[{'from':'0','units':'1','nanos':0},{'from':'10','units':'0','nanos':500000000}]}
        out=candidate(calculate(data,prices));self.assertFalse(out['summary']['total_complete']);self.assertIsNone(out['summary']['known_total_usd'])
        data['candidates'][0]['items'][0]['attributes']['tier_baseline_usage']='100';prices['input_sha256']=input_hash(data)
        out=candidate(calculate(data,prices));self.assertEqual(out['summary']['known_total_usd'],amount('7.5'))
        p['provider_details']['aggregation']['aggregationInterval']='DAILY'
        result=calculate(data,prices);self.assertEqual(result['status'],'partial')
        self.assertEqual(result['issues'][0]['code'],'unsupported_aggregation')

    def test_mapping_assessment_hash_and_feasibility_are_checked(self):
        manifest=read('demo-inventory.json');mapped,audit=map_inventory(manifest)
        # Identity mismatch must fail before any generated result.
        audit['input_sha256']='wrong'
        with self.assertRaises(InputError):calculate(mapped,read('prices-complete.json'),audit)
        data,prices=read('input.json'),read('prices-complete.json')
        cid=data['candidates'][0]['candidate_id']
        error={'candidate_id':cid,'item_id':None,'code':'unknown_capacity','message':'Capacity needs review','retryable':False}
        a={'schema_version':'1','input_id':data['input_id'],'input_sha256':input_hash(data),'inventory_sha256':'0'*64,'status':'partial','candidates':[
            {'candidate_id':cid,'selected_values':{},'used_values':[],'shared_resources':[],'excluded_resources':{},'sizing':{},'operating_costs':{},'issues':[error]}],'issues':[error]}
        out=candidate(calculate(data,prices,a));self.assertEqual(out['budget']['status'],'unknown')
        a['input_sha256']='wrong'
        with self.assertRaises(InputError):calculate(data,prices,a)

    def test_onprem_zero_cloud_cost_not_zero_operating_budget(self):
        data=read('input.json');data['candidates'][0].update(target='onprem',region=None,items=[])
        prices=read('prices-complete.json');prices['input_sha256']=input_hash(data);prices['candidates'][0].update(target='onprem',region=None,items=[])
        out=candidate(calculate(data,prices));self.assertEqual(out['summary']['known_total_usd'],amount('0'));self.assertEqual(out['budget']['status'],'unknown')

    def test_comparison_uses_two_quotes_and_signed_differences(self):
        before=calculate(read('input.json'),read('prices-complete.json'))
        changed=read('input.json');changed['candidates'][0]['items'][0]['quantity']=1
        prices=read('prices-complete.json');prices['input_sha256']=input_hash(changed)
        after=calculate(changed,prices)
        result=compare_costs(before,after);self.assertEqual(result['candidates'][0]['monthly_savings'],amount('73'))
        self.assertEqual(compare_costs(after,before)['candidates'][0]['monthly_savings'],amount('-73'))
        self.assertEqual(compare_costs(before,before)['candidates'][0]['monthly_savings'],amount('0'))

    def test_comparison_never_invents_savings_from_partial_subtotal(self):
        complete=calculate(read('input.json'),read('prices-complete.json'));partial=calculate(read('input.json'),read('prices-partial.json'))
        result=compare_costs(complete,partial);self.assertEqual(result['status'],'partial');self.assertIsNone(result['candidates'][0]['monthly_savings'])
        partial['candidates'][0]['summary']['total_complete']=True;partial['candidates'][0]['summary']['known_total_usd']=None
        with self.assertRaises(InputError):compare_costs(complete,partial)

    def test_partial_incremental_subtotal_preserved_and_can_prove_over(self):
        data,prices=case([amount('3'),amount('3')],[amount('1'),None])
        data['budget_basis']='incremental';data['monthly_budget']={'min':0,'max':100000,'currency':'KRW'};data['fx']['usd_to_krw']='200000';prices['input_sha256']=input_hash(data)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_incremental_usd'],{'min':'1','max':None})
        self.assertFalse(out['summary']['incremental_complete']);self.assertEqual(out['budget']['status'],'over')

    def test_partial_tier_increment_preserves_only_known_lower_bound(self):
        data,prices=case([amount('6'),amount('8')],[amount('1'),None],TIERS)
        out=candidate(calculate(data,prices))
        self.assertEqual(out['summary']['known_incremental_usd'],{'min':'0.5','max':None})
        self.assertFalse(out['summary']['incremental_complete'])

    def test_paid_gcp_record_cannot_drop_original_evidence_or_add_free_tier(self):
        for change in ('metadata','zero'):
            data,prices=read('gcp-input.json'),read('gcp-prices-complete.json')
            p=prices['candidates'][0]['items'][0]['price']
            if change=='metadata':p.pop('provider_details')
            else:p['tiers'][0]['unit_price']='0';p['provider_details']['tiers'][0]['nanos']=0
            with self.subTest(change=change),self.assertRaises(InputError):calculate(data,prices)

    def test_aggregation_baselines_compare_numerically_and_conflicts_rejected(self):
        data,prices=case([amount('6'),amount('8')],tiers=TIERS)
        items=data['candidates'][0]['items'];items[0]['attributes']['tier_baseline_usage']='100';items[1]['attributes']['tier_baseline_usage']='100.0'
        prices['input_sha256']=input_hash(data)
        self.assertEqual(candidate(calculate(data,prices))['summary']['known_total_usd'],amount('7'))
        items[1]['attributes']['tier_baseline_usage']='200';prices['input_sha256']=input_hash(data)
        with self.assertRaises(InputError):calculate(data,prices)

    def test_input_objects_not_mutated(self):
        data,prices=read('input.json'),read('prices-complete.json');before=(copy.deepcopy(data),copy.deepcopy(prices))
        calculate(data,prices);self.assertEqual((data,prices),before)

    def test_cli_offline_calculation_and_failure_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'costs.json';stdout=io.StringIO()
            with patch('pricing_aws.boto3.client') as aws,patch('pricing_gcp.google.auth.default') as gcp,redirect_stdout(stdout):
                code=price.main(['calculate','--input',str(EXAMPLES/'input.json'),'--prices',str(EXAMPLES/'prices-complete.json'),'--output',str(output)])
            aws.assert_not_called();gcp.assert_not_called();self.assertEqual(code,0)
            self.assertEqual(json.loads(output.read_text())['candidates'][0]['summary']['total_krw'],amount('255500'))
            original=output.read_bytes();bad=root/'bad-prices.json';bad.write_text('{}')
            with redirect_stdout(io.StringIO()):code=price.main(['calculate','--input',str(EXAMPLES/'input.json'),'--prices',str(bad),'--output',str(output)])
            self.assertEqual(code,2);self.assertEqual(output.read_bytes(),original)

    def test_cli_partial_and_source_overwrite_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'costs.json'
            with redirect_stdout(io.StringIO()):code=price.main(['calculate','--input',str(EXAMPLES/'input.json'),'--prices',str(EXAMPLES/'prices-partial.json'),'--output',str(output)])
            self.assertEqual(code,3)
            source=Path(directory)/'prices.json';source.write_text((EXAMPLES/'prices-complete.json').read_text());original=source.read_bytes()
            with redirect_stdout(io.StringIO()):code=price.main(['calculate','--input',str(EXAMPLES/'input.json'),'--prices',str(source),'--output',str(source)])
            self.assertEqual(code,2);self.assertEqual(source.read_bytes(),original)

    def test_cli_compare_writes_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'savings.json';stdout=io.StringIO()
            with redirect_stdout(stdout):code=price.main(['compare','--baseline',str(EXAMPLES/'costs-complete.json'),'--alternative',str(EXAMPLES/'costs-complete.json'),'--output',str(output)])
            self.assertEqual(code,0);self.assertEqual(json.loads(output.read_text())['candidates'][0]['monthly_savings'],amount('0'))


if __name__=='__main__':unittest.main()
