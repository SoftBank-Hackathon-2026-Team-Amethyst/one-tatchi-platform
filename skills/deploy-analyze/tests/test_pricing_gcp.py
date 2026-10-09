"""GCP Catalog response fixtures, ADC preservation, and mixed lookup tests."""

import copy
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from google.auth.exceptions import DefaultCredentialsError, RefreshError
from requests import Response
from requests.exceptions import Timeout

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import price
from pricing_contract import input_hash, validate_input
from pricing_errors import LookupError
from pricing_gcp import GCPPrices

FIXTURES = Path(__file__).parent / "fixtures" / "pricing" / "gcp"
EXAMPLES = ROOT / "references" / "examples" / "pricing"
NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def data():
    return json.loads((EXAMPLES / "gcp-input.json").read_text())


def response(body, status=200):
    result = Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    return result


def prepare(*skus, service_pages=None):
    session = Mock()
    session.get.side_effect = [response(body) for body in (service_pages or [fixture("services.json")])] + [response({'skus': list(skus)})]
    return GCPPrices(session), session


class GCPLookupTests(unittest.TestCase):
    def setUp(self):
        self.data = data()
        self.candidate = self.data['candidates'][0]
        self.item = self.candidate['items'][0]

    def query(self, *skus, item=None):
        provider, session = prepare(*skus)
        result = provider.lookup(self.candidate, item or self.item, NOW)
        return result, session

    def issue(self, code, *skus):
        provider, _ = prepare(*skus)
        with self.assertRaises(LookupError) as caught:
            provider.lookup(self.candidate, self.item, NOW)
        self.assertEqual(caught.exception.code, code)

    def test_seoul_cpu_money_and_usd_query(self):
        result, session = self.query(fixture('cpu.json'))
        self.assertEqual(result['tiers'], [{'from':'0','to':None,'unit_price':'0.021177'}])
        self.assertEqual(result['unit'], 'vcpu_hour')
        self.assertEqual(result['provider_details']['tiers'], [{'from':'0','units':'0','nanos':21177000}])
        self.assertEqual(result['provider_details']['base_unit_conversion_factor'], '3600')
        self.assertEqual(session.get.call_args.args[0], 'https://cloudbilling.googleapis.com/v1/services/COMPUTE/skus')
        self.assertEqual(session.get.call_args.kwargs['params']['currencyCode'], 'USD')
        self.assertEqual(session.get.call_args.kwargs['timeout'], (5,15))

    def test_aggregation_baseline_is_not_a_gcp_catalog_selector(self):
        self.item['attributes']['tier_baseline_usage']='100'
        result,_=self.query(fixture('cpu.json'))
        self.assertEqual(result['sku'],'CPU-EXAMPLE')

    def test_memory_separate_from_cpu_and_catalog_cached(self):
        cpu, memory = fixture('cpu.json'), fixture('memory.json')
        provider, session = prepare(cpu, memory)
        first = provider.lookup(self.candidate, self.item, NOW)
        item = copy.deepcopy(self.item)
        item.update(billing_dimension='memory_hours',unit='gib_hour',attributes={'resource_family':'Compute','resource_group':'RAM','description':memory['description']})
        second = provider.lookup(self.candidate, item, NOW)
        self.assertEqual((first['sku'], second['sku']), ('CPU-EXAMPLE','RAM-EXAMPLE'))
        self.assertEqual(second['tiers'][0]['unit_price'], '0.002847')
        self.assertEqual(second['provider_details']['base_unit_conversion_factor'], str(1073741824*3600))
        self.assertEqual(session.get.call_count, 2)

    def test_regional_sku_not_used_in_another_region(self):
        self.candidate['region']='us-central1'
        self.issue('not_found', fixture('cpu.json'))

    def test_global_sku_requires_explicit_metadata(self):
        sku=fixture('global-cluster.json')
        self.item.update(resource_kind='gke',billing_dimension='cluster_hours',unit='hour',attributes={'resource_family':'ApplicationServices','resource_group':'Management','description':sku['description']})
        result,_=self.query(sku)
        self.assertEqual(result['sku'],'GKE-EXAMPLE')
        sku.pop('geoTaxonomy')
        self.issue('not_found',sku)
        sku['serviceRegions']=['global']
        self.assertEqual(self.query(sku)[0]['sku'],'GKE-EXAMPLE')

    def test_global_protobuf_empty_regions_may_be_omitted(self):
        sku=fixture('global-cluster.json')
        sku.pop('serviceRegions')
        sku['geoTaxonomy'].pop('regions')
        self.item.update(resource_kind='gke',billing_dimension='cluster_hours',unit='hour',attributes={'resource_family':'ApplicationServices','resource_group':'Management','description':sku['description']})
        result,_=self.query(sku)
        self.assertEqual(result['sku'],'GKE-EXAMPLE')

    def test_duplicate_response_json_keys_are_rejected(self):
        session=Mock()
        body=response({});body._content=b'{"services":[],"services":[]}'
        session.get.return_value=body
        with self.assertRaises(LookupError) as caught:
            GCPPrices(session).lookup(self.candidate,self.item,NOW)
        self.assertEqual(caught.exception.code,'invalid_provider_response')

    def test_conflicting_global_region_metadata_rejected(self):
        sku=fixture('cpu.json');sku['geoTaxonomy']={'type':'GLOBAL','regions':[]}
        self.issue('invalid_provider_response',sku)

    def test_service_and_sku_pages_follow_tokens(self):
        sku=fixture('cpu.json')
        session=Mock()
        session.get.side_effect=[response({'nextPageToken':'services-next'}),response(fixture('services.json')),
                                 response({'skus':[], 'nextPageToken':'skus-next'}),response({'skus':[sku]})]
        result=GCPPrices(session).lookup(self.candidate,self.item,NOW)
        self.assertEqual(result['sku'],'CPU-EXAMPLE')
        self.assertEqual(session.get.call_args_list[1].kwargs['params']['pageToken'],'services-next')
        self.assertEqual(session.get.call_args_list[3].kwargs['params']['pageToken'],'skus-next')
        self.assertEqual(session.get.call_count,4)

    def test_duplicate_matching_sku_on_later_page_is_ambiguous(self):
        sku=fixture('cpu.json');other=copy.deepcopy(sku);other.update(skuId='OTHER',name='services/COMPUTE/skus/OTHER')
        session=Mock()
        session.get.side_effect=[response(fixture('services.json')),response({'skus':[sku], 'nextPageToken':'next'}),response({'skus':[other]})]
        with self.assertRaises(LookupError) as caught:
            GCPPrices(session).lookup(self.candidate,self.item,NOW)
        self.assertEqual(caught.exception.code,'ambiguous_sku')

    def test_exact_sku_id_disambiguates(self):
        sku=fixture('cpu.json');other=copy.deepcopy(sku);other.update(skuId='OTHER',name='services/COMPUTE/skus/OTHER')
        self.item['attributes']['sku_id']='CPU-EXAMPLE'
        result,_=self.query(sku,other)
        self.assertEqual(result['sku'],'CPU-EXAMPLE')

    def test_latest_effective_version_and_future_excluded(self):
        sku=fixture('cpu.json');latest=copy.deepcopy(sku['pricingInfo'][0]);latest['effectiveTime']='2026-09-01T00:00:00.123456789Z'
        latest['pricingExpression']['tieredRates'][0]['unitPrice']['nanos']=123
        future=copy.deepcopy(latest);future['effectiveTime']='2027-01-01T00:00:00Z'
        sku['pricingInfo'] += [future,latest]
        result,_=self.query(sku)
        self.assertEqual(result['effective_at'],'2026-09-01T00:00:00.123456789Z')
        self.assertEqual(Decimal(result['tiers'][0]['unit_price']), Decimal('0.000000123'))

    def test_future_only_price_not_used(self):
        sku=fixture('cpu.json');sku['pricingInfo'][0]['effectiveTime']='2027-01-01T00:00:00Z'
        self.issue('not_found',sku)

    def test_duplicate_effective_price_is_ambiguous(self):
        sku=fixture('cpu.json');sku['pricingInfo'].append(copy.deepcopy(sku['pricingInfo'][0]))
        self.issue('ambiguous_sku',sku)

    def test_unit_conversion_changes_tier_bounds_and_rates(self):
        sku=fixture('memory.json');e=sku['pricingInfo'][0]['pricingExpression']
        e.update(usageUnit='GiBy.s',baseUnitConversionFactor=1073741824,displayQuantity=1000)
        e['tieredRates']=[{'startUsageAmount':0,'unitPrice':{'currencyCode':'USD','nanos':1000}},
                          {'startUsageAmount':7200,'unitPrice':{'currencyCode':'USD','nanos':500}}]
        self.item.update(billing_dimension='memory_hours',unit='gib_hour',attributes={'resource_family':'Compute','resource_group':'RAM','description':sku['description']})
        result,_=self.query(sku)
        self.assertEqual(Decimal(result['source_usage_per_unit']),Decimal('3600'))
        self.assertEqual(result['tiers'],[{'from':'0','to':'2','unit_price':'0.003600'}, {'from':'2','to':None,'unit_price':'0.0018000'}])
        self.assertEqual(result['provider_details']['display_quantity'],'1000')

    def test_storage_tiers_aggregation_and_month_convention_preserved(self):
        sku=fixture('tiered-storage.json')
        self.item.update(resource_kind='artifact_registry',billing_dimension='storage',unit='gib_month',attributes={'resource_family':'Storage','resource_group':'Storage','description':sku['description']})
        # Catalog's own month convention is preserved instead of reapplying 730h.
        sku['pricingInfo'][0]['pricingExpression']['baseUnitConversionFactor']=123456789
        result,_=self.query(sku)
        self.assertEqual(result['source_usage_per_unit'],'1')
        self.assertEqual(result['tiers'],[{'from':'0','to':'10','unit_price':'0.1'},{'from':'10','to':None,'unit_price':'0.05'}])
        self.assertEqual(result['provider_details']['aggregation'],{'aggregationLevel':'ACCOUNT','aggregationInterval':'MONTHLY','aggregationCount':1})
        self.assertEqual(result['provider_details']['base_unit_conversion_factor'],'123456789')

    def test_display_quantity_does_not_multiply_price(self):
        sku=fixture('cpu.json');sku['pricingInfo'][0]['pricingExpression']['displayQuantity']=1000000
        result,_=self.query(sku)
        self.assertEqual(result['tiers'][0]['unit_price'],'0.021177')

    def test_money_units_and_nanos_combined_without_float_rounding(self):
        sku=fixture('cpu.json');sku['pricingInfo'][0]['pricingExpression']['tieredRates'][0]['unitPrice'].update(units='2',nanos=1)
        result,_=self.query(sku)
        self.assertEqual(result['tiers'][0]['unit_price'],'2.000000001')

    def test_free_sku_is_not_used_for_paid_configuration(self):
        free=fixture('cpu.json');free.update(skuId='FREE',name='services/COMPUTE/skus/FREE')
        free['pricingInfo'][0]['pricingExpression']['tieredRates'][0]['unitPrice']['nanos']=0
        self.issue('not_found',free)
        result,_=self.query(free,fixture('cpu.json'))
        self.assertEqual(result['sku'],'CPU-EXAMPLE')

    def test_free_allowance_not_assumed_for_app(self):
        sku=fixture('cpu.json');sku['pricingInfo'][0]['pricingExpression']['tieredRates'].insert(0,{'startUsageAmount':0,'unitPrice':{'currencyCode':'USD'}})
        sku['pricingInfo'][0]['pricingExpression']['tieredRates'][1]['startUsageAmount']=10
        self.issue('unsupported_resource',sku)

    def test_committed_and_spot_prices_excluded(self):
        for usage in ('Preemptible','Commit1Yr'):
            sku=fixture('cpu.json');sku['category']['usageType']=usage
            self.issue('not_found',sku)
        self.item['attributes']['usage_type']='Preemptible'
        with self.assertRaises(LookupError) as caught:
            GCPPrices(Mock()).lookup(self.candidate,self.item,NOW)
        self.assertEqual(caught.exception.code,'unsupported_resource')

    def test_unknown_filters_fail_before_authentication(self):
        self.item['attributes']['machine_type']='e2-standard-2'
        with patch('pricing_gcp.google.auth.default') as credentials, self.assertRaises(LookupError) as caught:
            GCPPrices().lookup(self.candidate,self.item,NOW)
        credentials.assert_not_called()
        self.assertEqual(caught.exception.code,'unsupported_resource')

    def test_incompatible_units_and_missing_conversion_are_unavailable(self):
        sku=fixture('cpu.json');self.item['unit']='gib_hour'
        self.issue('unsupported_unit',sku)
        self.item['unit']='vcpu_hour';sku['pricingInfo'][0]['pricingExpression']['baseUnitConversionFactor']=0
        self.issue('unsupported_unit',sku)

    def test_non_usd_and_invalid_money_are_rejected(self):
        for change in ({'currencyCode':'KRW'},{'units':'-1'},{'nanos':1000000000},{'nanos':True},{'nanos':-1}):
            with self.subTest(change=change):
                sku=fixture('cpu.json');sku['pricingInfo'][0]['pricingExpression']['tieredRates'][0]['unitPrice'].update(change)
                self.issue('invalid_provider_response',sku)

    def test_duplicate_tier_boundaries_are_rejected(self):
        sku=fixture('cpu.json');sku['pricingInfo'][0]['pricingExpression']['tieredRates'].append(copy.deepcopy(sku['pricingInfo'][0]['pricingExpression']['tieredRates'][0]))
        self.issue('ambiguous_sku',sku)

    def test_malformed_page_and_repeated_token(self):
        for bodies in ([{'services':'wrong'}],[{'nextPageToken':'repeat'},{'nextPageToken':'repeat'}]):
            session=Mock();session.get.side_effect=[response(x) for x in bodies]
            with self.assertRaises(LookupError) as caught:
                GCPPrices(session).lookup(self.candidate,self.item,NOW)
            self.assertEqual(caught.exception.code,'invalid_provider_response')

    def test_disabled_api_permission_authentication_and_throttling(self):
        for status,reason,code,retry in ((403,'SERVICE_DISABLED','api_disabled',False),(403,'IAM_PERMISSION_DENIED','permission_denied',False),
                                       (401,'','authentication_failed',False),(429,'','rate_limited',True),(503,'','invalid_provider_response',True)):
            session=Mock();session.get.return_value=response({'error':{'message':'secret-token-value','details':[{'reason':reason}]}},status)
            with self.subTest(status=status,reason=reason),self.assertRaises(LookupError) as caught:
                GCPPrices(session).lookup(self.candidate,self.item,NOW)
            self.assertEqual((caught.exception.code,caught.exception.retryable),(code,retry))
            self.assertNotIn('secret-token-value',str(caught.exception))

    def test_adc_loading_and_refresh_failures_are_redacted(self):
        for error in (DefaultCredentialsError('secret-token-value'),RefreshError('secret-token-value')):
            with patch('pricing_gcp.google.auth.default',side_effect=error),self.assertRaises(LookupError) as caught:
                GCPPrices().lookup(self.candidate,self.item,NOW)
            self.assertEqual(caught.exception.code,'authentication_failed')
            self.assertNotIn('secret-token-value',str(caught.exception))

    def test_existing_adc_read_only_scope_and_no_settings_write(self):
        with tempfile.TemporaryDirectory() as directory:
            adc=Path(directory)/'adc.json';adc.write_text('{"fixture":"unchanged"}')
            before=adc.read_bytes()
            with patch('pricing_gcp.google.auth.default',return_value=(Mock(),'project')) as default, \
                    patch('pricing_gcp.AuthorizedSession',return_value=Mock()) as authorized:
                provider=GCPPrices();first=provider.session
                self.assertIs(provider.session,first)
                default.assert_called_once_with()
                self.assertEqual(authorized.call_args.kwargs,{'max_refresh_attempts':1,'refresh_timeout':15})
            self.assertEqual(adc.read_bytes(),before)

    def test_user_adc_scopes_preserved_and_unscoped_service_account_gets_readonly_scope(self):
        from google.oauth2.credentials import Credentials as UserCredentials
        from google.oauth2.service_account import Credentials as ServiceCredentials

        user = UserCredentials(token='fixture-token', scopes=['https://www.googleapis.com/auth/cloud-platform'])
        with patch('pricing_gcp.google.auth.default', return_value=(user, 'project')), \
                patch('pricing_gcp.AuthorizedSession') as authorized:
            GCPPrices().session
            self.assertIs(authorized.call_args.args[0], user)
            self.assertEqual(user.scopes, ['https://www.googleapis.com/auth/cloud-platform'])
        account = ServiceCredentials(signer=Mock(), service_account_email='fixture@example.com', token_uri='https://oauth2.googleapis.com/token')
        with patch('pricing_gcp.google.auth.default', return_value=(account, 'project')), \
                patch('pricing_gcp.AuthorizedSession') as authorized:
            GCPPrices().session
            scoped = authorized.call_args.args[0]
            self.assertIsNot(scoped, account)
            self.assertEqual(scoped.scopes, ['https://www.googleapis.com/auth/cloud-billing.readonly'])
            self.assertIsNone(account.scopes)

    def test_timeout_redacted(self):
        session=Mock();session.get.side_effect=Timeout('secret-url-and-token')
        with self.assertRaises(LookupError) as caught:
            GCPPrices(session).lookup(self.candidate,self.item,NOW)
        self.assertEqual((caught.exception.code,caught.exception.retryable),('timeout',True))
        self.assertNotIn('secret-url',str(caught.exception))

    def test_mixed_aws_gcp_preserves_aws_after_gcp_failure(self):
        mixed=json.loads((EXAMPLES/'input.json').read_text());mixed['candidates'].append(self.candidate)
        validate_input(mixed)
        aws,gcp=Mock(),Mock();aws.lookup.return_value={'sku':'aws-success'};gcp.lookup.side_effect=LookupError('api_disabled','GCP API disabled')
        result=price.lookup(mixed,provider=aws,gcp_provider=gcp)
        self.assertEqual(result['schema_version'],'2')
        self.assertEqual(result['input_sha256'],input_hash(mixed))
        self.assertEqual(result['status'],'partial')
        self.assertEqual(result['candidates'][0]['items'][0]['price']['sku'],'aws-success')
        self.assertIsNone(result['candidates'][1]['items'][0]['price'])

    def test_gcp_only_does_not_create_aws_client(self):
        provider,_=prepare(fixture('cpu.json'))
        with patch('pricing_aws.boto3.client') as aws:
            result=price.lookup(self.data,gcp_provider=provider)
        aws.assert_not_called()
        self.assertEqual(result['status'],'complete')
        self.assertEqual(result['candidates'][0]['items'][0]['price']['provider_details']['tiers'][0]['nanos'],21177000)

    def test_cli_writes_common_gcp_result(self):
        provider,_=prepare(fixture('cpu.json'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'input.json';destination=root/'prices.json'
            source.write_text(json.dumps(self.data));stdout=io.StringIO()
            with patch('pricing_gcp.GCPPrices',return_value=provider),redirect_stdout(stdout):
                code=price.main(['lookup','--input',str(source),'--output',str(destination)])
            result=json.loads(destination.read_text())
        self.assertEqual(code,0)
        self.assertEqual(result['schema_version'],'2')
        self.assertEqual(result['candidates'][0]['region'],'asia-northeast3')
        self.assertEqual(result['candidates'][0]['items'][0]['price']['sku'],'CPU-EXAMPLE')


if __name__=='__main__':
    unittest.main()
