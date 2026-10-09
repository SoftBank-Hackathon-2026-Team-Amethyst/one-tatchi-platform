"""Explicit inventory mapping, provenance, shared resources and sizing checks."""

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
from pricing_contract import InputError, input_hash, validate_input
from pricing_map import capacity_assessment, map_inventory

EXAMPLE=ROOT/'references/examples/pricing/demo-inventory.json'


def inventory():return json.loads(EXAMPLE.read_text())

def items(candidate):return {item['item_id']:item for item in candidate['items']}

def capacity():
    return {'node_count':3,'per_node':{'cpu_millicores':2000,'memory_mib':'4096','pod_slots':17},
            'reserved':{'cpu_millicores':1000,'memory_mib':'4096','pod_slots':20},
            'source':{'path':'synthetic-capacity','ref':None,'note':'Synthetic cluster bounds, not live allocatable capacity.'}}


class MappingTests(unittest.TestCase):
    def test_demo_snapshot_nodes_nat_and_database(self):
        source=inventory();mapped,audit=map_inventory(source);validate_input(mapped)
        aws=items(mapped['candidates'][0])
        self.assertEqual(aws['aws-nodes-instance_hours']['quantity'],3)
        self.assertEqual(aws['aws-nodes-instance_hours']['attributes']['instance_type'],'t3.medium')
        self.assertEqual(aws['aws-nat-gateway_hours']['quantity'],1)
        self.assertEqual(aws['aws-db-instance_hours']['quantity'],1)
        self.assertEqual(aws['aws-db-instance_hours']['attributes']['instance_class'],'db.t4g.micro')
        self.assertEqual(aws['aws-db-storage']['monthly_usage'],{'min':'20','max':'20'})
        self.assertEqual(audit['input_sha256'],input_hash(mapped))
        self.assertEqual(audit['inventory_sha256'],input_hash(source))
        self.assertEqual(audit['status'],'partial')
        self.assertEqual(audit['candidates'][0]['selected_values']['nodes']['tier'],'root')

    def test_root_then_module_default_then_assumption(self):
        original=inventory()
        for remove,expected,tier in (((),3,'root'),(('root',),2,'module_default'),(('root','module_default'),4,'assumption')):
            source=copy.deepcopy(original);value=source['candidates'][0]['values']['nodes']
            value['assumption']={'value':{'desired':4},'source':{'path':'explicit-node-scenario','ref':None,'note':'Four nodes in a hypothetical scenario.'}}
            for name in remove:value.pop(name)
            mapped,audit=map_inventory(source)
            self.assertEqual(items(mapped['candidates'][0])['aws-nodes-instance_hours']['quantity'],expected)
            self.assertEqual(audit['candidates'][0]['selected_values']['nodes']['tier'],tier)

    def test_explicit_null_never_falls_back_to_default(self):
        source=inventory();source['candidates'][0]['values']['nodes']['root']['value']=None
        with self.assertRaises(InputError):map_inventory(source)

    def test_module_default_requires_matching_tag(self):
        source=inventory();source['candidates'][1]['values']['nodes']['module_default']['source']['ref']='v1.16.0'
        with self.assertRaises(InputError):map_inventory(source)

    def test_shared_resources_count_once_not_per_namespace(self):
        mapped,audit=map_inventory(inventory())
        aws=items(mapped['candidates'][0])
        self.assertTrue(aws['aws-db-instance_hours']['shared'])
        self.assertEqual(aws['aws-db-instance_hours']['monthly_usage'],{'min':'730','max':'730'})
        shared={r['resource_id']:r for r in audit['candidates'][0]['shared_resources']}
        self.assertEqual(shared['aws-db']['environments'],['test','prod'])
        self.assertTrue(shared['aws-db']['counted_once'])

    def test_duplicate_physical_resource_rejected(self):
        source=inventory();source['candidates'][0]['resources'].append(copy.deepcopy(source['candidates'][0]['resources'][5]))
        with self.assertRaises(InputError):map_inventory(source)

    def test_multiple_environments_require_sharing(self):
        source=inventory();source['candidates'][0]['resources'][0]['shared']=False
        with self.assertRaises(InputError):map_inventory(source)

    def test_replicas_only_change_never_changes_node_quantity(self):
        source=inventory();source['candidates'][0]['capacity']=capacity()
        before,audit_before=map_inventory(source)
        for workload in source['candidates'][0]['traffic']['workloads']:workload['replicas']=100
        after,audit_after=map_inventory(source)
        self.assertEqual(items(before['candidates'][0])['aws-nodes-instance_hours'],items(after['candidates'][0])['aws-nodes-instance_hours'])
        self.assertEqual(audit_before['candidates'][0]['sizing']['node_expansion'],'not_indicated')
        self.assertEqual(audit_after['candidates'][0]['sizing']['node_expansion'],'review_required')
        self.assertEqual(audit_after['candidates'][0]['sizing']['check'],'exceeds_supplied_bounds')

    def test_cpu_memory_pod_slots_include_environments_and_blue_green(self):
        source=inventory();traffic=source['candidates'][0]['traffic']
        result=capacity_assessment(traffic,capacity())
        self.assertEqual(result['demand'],{'cpu_millicores':'600','memory_mib':'640','pod_slots':'8'})
        self.assertEqual(result['available'],{'cpu_millicores':'5000','memory_mib':'8192','pod_slots':'31'})

    def test_unknown_capacity_does_not_claim_no_expansion(self):
        mapped,audit=map_inventory(inventory())
        self.assertEqual(audit['candidates'][0]['sizing']['node_expansion'],'review_required')
        self.assertIsNone(audit['candidates'][0]['sizing']['available'])
        self.assertEqual(items(mapped['candidates'][0])['aws-nodes-instance_hours']['quantity'],3)

    def test_invalid_capacity_checked_even_without_traffic(self):
        source=inventory();source['candidates'][0].update(traffic=None,capacity=capacity())
        source['candidates'][0]['capacity']['node_count']=True
        with self.assertRaises(InputError):map_inventory(source)

    def test_capacity_node_count_must_match_quote(self):
        source=inventory();source['candidates'][0]['capacity']=capacity();source['candidates'][0]['capacity']['node_count']=4
        with self.assertRaises(InputError):map_inventory(source)

    def test_reserved_capacity_cannot_exceed_supplied_cluster(self):
        source=inventory();source['candidates'][0]['capacity']=capacity();source['candidates'][0]['capacity']['reserved']['pod_slots']=100
        with self.assertRaises(InputError):map_inventory(source)

    def test_gcp_total_nodes_not_multiplied_by_zones(self):
        mapped,audit=map_inventory(inventory());gcp=items(mapped['candidates'][1])
        self.assertEqual(gcp['gcp-nodes-cpu_hours']['quantity'],3)
        self.assertEqual(gcp['gcp-nodes-memory_hours']['quantity'],3)
        self.assertEqual(gcp['gcp-node-disks-storage']['quantity'],3)
        self.assertEqual(audit['candidates'][1]['selected_values']['node_disk_gb']['value'],30)
        self.assertEqual(audit['candidates'][1]['selected_values']['db_class']['value'],'db-g1-small')
        self.assertIsNone(gcp['gcp-node-disks-storage']['monthly_usage'])

    def test_gcp_namespaced_ingress_costs_not_shared(self):
        mapped,_=map_inventory(inventory());gcp=items(mapped['candidates'][1])
        self.assertFalse(gcp['gcp-ingress-test-load_balancer_hours']['shared'])
        self.assertFalse(gcp['gcp-ingress-prod-load_balancer_hours']['shared'])
        self.assertNotEqual(gcp['gcp-ingress-test-load_balancer_hours']['resource_id'],gcp['gcp-ingress-prod-load_balancer_hours']['resource_id'])

    def test_unconfirmed_catalog_and_unknown_usage_stay_visible(self):
        mapped,audit=map_inventory(inventory());aws=items(mapped['candidates'][0])
        self.assertIn('aws-egress-transfer',aws)
        self.assertIsNone(aws['aws-egress-transfer']['monthly_usage'])
        self.assertEqual(aws['aws-egress-transfer']['attributes'],{})
        codes={error['code'] for error in audit['candidates'][0]['issues']}
        self.assertTrue({'unconfirmed_catalog','unknown_usage','unknown_incremental_usage'}<=codes)

    def test_required_resource_kind_and_dimensions_cannot_be_silently_dropped(self):
        for mutation in ('kind','dimension'):
            source=inventory()
            if mutation=='kind':source['candidates'][0]['resources']=[r for r in source['candidates'][0]['resources'] if r['resource_kind']!='rds']
            else:source['candidates'][0]['resources'][5]['items'].pop()
            with self.subTest(mutation=mutation),self.assertRaises(InputError):map_inventory(source)

    def test_explicit_absent_resource_explanation_preserved(self):
        source=inventory();aws=source['candidates'][0]
        aws['resources']=[r for r in aws['resources'] if r['resource_kind']!='rds']
        aws['excluded_resources']['rds']={'path':'no-db-scenario','ref':'v1.14.0','note':'Explicit hypothetical app without a database.'}
        _,audit=map_inventory(source)
        self.assertIn('rds',audit['candidates'][0]['excluded_resources'])

    def test_onprem_operating_costs_not_zero(self):
        mapped,audit=map_inventory(inventory());onprem=mapped['candidates'][2]
        self.assertEqual(onprem['items'],[])
        self.assertTrue(any('not total' in note for note in onprem['assumptions']))
        costs=audit['candidates'][2]['operating_costs']
        self.assertTrue(all(cost['monthly_krw'] is None for cost in costs.values()))
        source=inventory();source['candidates'][2]['operating_costs']['power']['monthly_krw']={'min':'10000','max':'15000'}
        _,audit=map_inventory(source)
        self.assertEqual(audit['candidates'][2]['operating_costs']['power']['monthly_krw']['max'],'15000')

    def test_missing_traffic_marks_default_scenario_and_recalculation(self):
        source=inventory();source['candidates'][0]['traffic']=None
        mapped,audit=map_inventory(source)
        self.assertEqual(mapped['candidates'][0]['configuration_status'],'assumed')
        self.assertTrue(any('recalculate' in note for note in mapped['candidates'][0]['assumptions']))
        self.assertEqual(audit['candidates'][0]['sizing']['check'],'unknown')

    def test_unknown_binding_member_and_unknown_fields(self):
        for mutation in ('binding','member','field'):
            source=inventory();aws=source['candidates'][0]
            if mutation=='binding':aws['resources'][1]['items'][0]['quantity']={'value_from':'missing'}
            elif mutation=='member':aws['resources'][1]['items'][0]['quantity']['member']='missing'
            else:aws['unknown']=True
            with self.subTest(mutation=mutation),self.assertRaises(InputError):map_inventory(source)

    def test_input_not_mutated(self):
        source=inventory();before=copy.deepcopy(source);map_inventory(source)
        self.assertEqual(source,before)

    def test_cli_maps_offline_and_returns_partial_with_audit_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'input.json';audit=root/'assessment.json';stdout=io.StringIO()
            with patch('pricing_aws.boto3.client') as aws,patch('pricing_gcp.google.auth.default') as gcp,redirect_stdout(stdout):
                code=price.main(['map','--inventory',str(EXAMPLE),'--output',str(out),'--assessment',str(audit)])
            aws.assert_not_called();gcp.assert_not_called()
            self.assertEqual(code,3)
            self.assertEqual(json.loads(audit.read_text())['input_sha256'],input_hash(json.loads(out.read_text())))
            self.assertEqual(json.loads(stdout.getvalue())['status'],'partial')

    def test_cli_same_outputs_and_invalid_recipe_preserve_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);out=root/'input.json';audit=root/'assessment.json';recipe=root/'inventory.json'
            out.write_text('old-input');audit.write_text('old-assessment');recipe.write_text('{}')
            for source,assessment in ((EXAMPLE,out),(recipe,audit)):
                stdout=io.StringIO()
                with redirect_stdout(stdout):code=price.main(['map','--inventory',str(source),'--output',str(out),'--assessment',str(assessment)])
                self.assertEqual(code,2)
                self.assertEqual(out.read_text(),'old-input');self.assertEqual(audit.read_text(),'old-assessment')


if __name__=='__main__':unittest.main()
