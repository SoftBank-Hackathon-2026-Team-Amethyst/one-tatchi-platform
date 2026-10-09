"""AWS response fixtures and observable CLI guarantees; no cloud access."""

import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, ReadTimeoutError
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import price
from pricing_aws import AWSPrices, LookupError
from pricing_contract import InputError, input_hash, load_input, validate_input

FIXTURES = Path(__file__).parent / "fixtures" / "pricing"
EXAMPLES = ROOT / "references" / "examples" / "pricing"
NOW = datetime(2026, 10, 9, tzinfo=timezone.utc)


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


def input_data():
    return json.loads((EXAMPLES / "input.json").read_text())


def dimension_item(kind, dimension, unit, usage_type):
    item = copy.deepcopy(input_data()["candidates"][0]["items"][0])
    item.update(resource_kind=kind, billing_dimension=dimension, unit=unit,
                attributes={"usage_type": usage_type})
    return item


class AWSLookupTests(unittest.TestCase):
    def setUp(self):
        self.client = boto3.client("pricing", region_name="us-east-1", aws_access_key_id="fixture-key",
                                   aws_secret_access_key="fixture-secret")
        self.stub = Stubber(self.client)
        self.stub.activate()
        self.addCleanup(self.stub.deactivate)
        self.provider = AWSPrices(self.client)
        self.candidate = input_data()["candidates"][0]
        self.node, self.db = self.candidate["items"]

    def metadata(self, product, pages=None):
        service = product["serviceCode"]
        names = list(product["product"]["attributes"])
        self.stub.add_response("describe_services", {"Services": [{"ServiceCode": service, "AttributeNames": names}]},
                               {"ServiceCode": service, "FormatVersion": "aws_v1", "MaxResults": 100})

    def products(self, product, pages=None):
        p = product["product"]
        filters = dict(p["attributes"], productFamily=p["productFamily"]) if product["serviceCode"] in {"AmazonEC2", "AmazonRDS"} else p["attributes"]
        params = {"ServiceCode": product["serviceCode"], "FormatVersion": "aws_v1", "MaxResults": 100,
                  "Filters": [{"Type": "TERM_MATCH", "Field": key, "Value": value} for key, value in sorted(filters.items())]}
        for index, page in enumerate(pages or [{"PriceList": [json.dumps(product)]}]):
            current = dict(params)
            if index:
                current["NextToken"] = (pages or [])[index - 1]["NextToken"]
            self.stub.add_response("get_products", page, current)

    def query(self, item, product):
        self.metadata(product)
        self.products(product)
        result = self.provider.lookup(self.candidate, item, NOW)
        self.stub.assert_no_pending_responses()
        return result

    def expect_issue(self, item, product, code):
        self.metadata(product)
        self.products(product)
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, item, NOW)
        self.assertEqual(caught.exception.code, code)
        self.stub.assert_no_pending_responses()

    def test_ec2_filters_seoul_while_api_endpoint_is_us_east(self):
        result = self.query(self.node, fixture("ec2.json"))
        self.assertEqual(self.client.meta.region_name, "us-east-1")
        self.assertEqual(result["sku"], "EC2-EXAMPLE")
        self.assertEqual(result["unit"], "hour")
        self.assertEqual(result["tiers"], [{"from": "0", "to": None, "unit_price": "0.052"}])

    def test_aggregation_baseline_is_not_an_aws_product_filter(self):
        self.node['attributes']['tier_baseline_usage']='100'
        result=self.query(self.node,fixture('ec2.json'))
        self.assertEqual(result['sku'],'EC2-EXAMPLE')

    def test_rds_selects_engine_size_and_deployment(self):
        result = self.query(self.db, fixture("rds.json"))
        self.assertEqual(result["provider_service"], "AmazonRDS")
        self.assertEqual(result["tiers"][0]["unit_price"], "0.025")
        self.assertEqual(result["effective_at"], "2026-01-01T00:00:00Z")

    def test_storage_unit_preserved(self):
        item = dimension_item("ecr", "storage", "gb_month", "APN2-TimedStorage-ByteHrs")
        result = self.query(item, fixture("ecr-storage.json"))
        self.assertEqual((result["unit"], result["source_unit"], result["source_usage_per_unit"]), ("gb_month", "GB-Mo", "1"))

    def test_tiers_preserved_in_numeric_order(self):
        item = dimension_item("logs", "ingestion", "gb", "APN2-DataProcessing-Bytes")
        product = fixture("logs-tiered.json")
        dimensions = next(iter(product["terms"]["OnDemand"].values()))["priceDimensions"]
        product["terms"]["OnDemand"]["LOGS-EXAMPLE.JRTCKXETXF"]["priceDimensions"] = dict(reversed(list(dimensions.items())))
        result = self.query(item, product)
        self.assertEqual(result["tiers"], [{"from": "0", "to": "10", "unit_price": "0.5"},
                                           {"from": "10", "to": None, "unit_price": "0.25"}])

    def test_get_products_follows_empty_page_with_next_token(self):
        product = fixture("ec2.json")
        self.metadata(product)
        self.products(product, [{"PriceList": [], "NextToken": "next"}, {"PriceList": [json.dumps(product)]}])
        self.assertEqual(self.provider.lookup(self.candidate, self.node, NOW)["sku"], "EC2-EXAMPLE")
        self.stub.assert_no_pending_responses()

    def test_distinct_sku_on_second_page_is_ambiguous(self):
        product = fixture("ec2.json")
        other = copy.deepcopy(product)
        other["product"]["sku"] = "OTHER"
        self.metadata(product)
        self.products(product, [{"PriceList": [json.dumps(product)], "NextToken": "next"}, {"PriceList": [json.dumps(other)]}])
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, self.node, NOW)
        self.assertEqual(caught.exception.code, "ambiguous_sku")

    def test_no_matches(self):
        product = fixture("ec2.json")
        self.metadata(product)
        self.products(product, [{"PriceList": []}])
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, self.node, NOW)
        self.assertEqual(caught.exception.code, "not_found")

    def test_response_outside_filters_is_rejected(self):
        product = fixture("ec2.json")
        wrong = copy.deepcopy(product)
        wrong["product"]["attributes"]["regionCode"] = "us-east-1"
        self.metadata(product)
        self.products(product, [{"PriceList": [json.dumps(wrong)]}])
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, self.node, NOW)
        self.assertEqual(caught.exception.code, "invalid_provider_response")

    def test_missing_required_attribute_without_network(self):
        del self.node["attributes"]["tenancy"]
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, self.node, NOW)
        self.assertEqual(caught.exception.code, "unsupported_resource")

    def test_unknown_resource_without_network(self):
        self.node["resource_kind"] = "unknown"
        with self.assertRaises(LookupError) as caught:
            self.provider.lookup(self.candidate, self.node, NOW)
        self.assertEqual(caught.exception.code, "unsupported_resource")

    def test_future_term_ignored_and_latest_current_selected(self):
        product = fixture("ec2.json")
        terms = product["terms"]["OnDemand"]
        term = copy.deepcopy(next(iter(terms.values())))
        term["effectiveDate"] = "2026-09-01T00:00:00Z"
        terms["current"] = term
        future = copy.deepcopy(term)
        future["effectiveDate"] = "2027-01-01T00:00:00Z"
        future["priceDimensions"]["ec2-hour"]["pricePerUnit"]["USD"] = "999"
        terms["future"] = future
        result = self.query(self.node, product)
        self.assertEqual(result["effective_at"], "2026-09-01T00:00:00Z")
        self.assertEqual(result["tiers"][0]["unit_price"], "0.052")

    def test_reserved_terms_are_not_used(self):
        product = fixture("ec2.json")
        product["terms"]["Reserved"] = product["terms"].pop("OnDemand")
        self.expect_issue(self.node, product, "not_found")

    def test_incompatible_unit_is_not_silently_converted(self):
        self.node["unit"] = "gib_hour"
        self.expect_issue(self.node, fixture("ec2.json"), "unsupported_unit")

    def test_invalid_price_values(self):
        for rate in ("NaN", "Infinity", "-0.1", "not-a-price"):
            with self.subTest(rate=rate):
                product = fixture("ec2.json")
                term = next(iter(product["terms"]["OnDemand"].values()))
                term["priceDimensions"]["ec2-hour"]["pricePerUnit"]["USD"] = rate
                provider = AWSPrices(Mock())
                provider.filters = Mock(return_value=("AmazonEC2", {}))
                provider.pages = Mock(return_value=iter([json.dumps(product)]))
                with self.assertRaises(LookupError) as caught:
                    provider.lookup(self.candidate, self.node, NOW)
                self.assertEqual(caught.exception.code, "invalid_provider_response")

    def test_overlapping_same_unit_dimensions_not_added_together(self):
        product = fixture("ec2.json")
        dimensions = next(iter(product["terms"]["OnDemand"].values()))["priceDimensions"]
        dimensions["extra"] = copy.deepcopy(dimensions["ec2-hour"])
        self.expect_issue(self.node, product, "ambiguous_sku")

    def test_conditional_applies_to_not_used_as_general_rate(self):
        product = fixture("ec2.json")
        next(iter(product["terms"]["OnDemand"].values()))["priceDimensions"]["ec2-hour"]["appliesTo"] = ["OTHER"]
        self.expect_issue(self.node, product, "unsupported_resource")

    def test_gaps_and_missing_final_tier(self):
        for start, end, code in (("1", "Inf", "ambiguous_sku"), ("0", "10", "invalid_provider_response")):
            with self.subTest(start=start, end=end):
                product = fixture("ec2.json")
                dim = next(iter(product["terms"]["OnDemand"].values()))["priceDimensions"]["ec2-hour"]
                dim.update(beginRange=start, endRange=end)
                provider = AWSPrices(Mock())
                provider.filters = Mock(return_value=("AmazonEC2", {}))
                provider.pages = Mock(return_value=iter([json.dumps(product)]))
                with self.assertRaises(LookupError) as caught:
                    provider.lookup(self.candidate, self.node, NOW)
                self.assertEqual(caught.exception.code, code)

    def test_aws_errors_redact_original_message(self):
        cases = [("AccessDeniedException", "permission_denied", False),
                 ("ExpiredTokenException", "authentication_failed", False),
                 ("ThrottlingException", "rate_limited", True)]
        for aws_code, code, retryable in cases:
            provider = AWSPrices(Mock())
            provider.filters = Mock(side_effect=ClientError({"Error": {"Code": aws_code, "Message": "secret-token-value"}}, "GetProducts"))
            with self.subTest(aws_code=aws_code), self.assertRaises(LookupError) as caught:
                provider.lookup(self.candidate, self.node, NOW)
            self.assertEqual((caught.exception.code, caught.exception.retryable), (code, retryable))
            self.assertNotIn("secret-token-value", str(caught.exception))

    def test_credentials_and_timeout_are_classified(self):
        for exception, code in ((NoCredentialsError(), "authentication_failed"),
                                (ReadTimeoutError(endpoint_url="https://example.com", error="secret"), "timeout")):
            provider = AWSPrices(Mock())
            provider.filters = Mock(side_effect=exception)
            with self.assertRaises(LookupError) as caught:
                provider.lookup(self.candidate, self.node, NOW)
            self.assertEqual(caught.exception.code, code)
            self.assertNotIn("secret", str(caught.exception))

    def test_real_lookup_pipeline_writes_complete_and_partial_json(self):
        ec2 = fixture("ec2.json")
        self.metadata(ec2)
        self.products(ec2)
        self.stub.add_client_error("describe_services", service_error_code="AccessDeniedException",
                                   service_message="do-not-print-secret",
                                   expected_params={"ServiceCode": "AmazonRDS", "FormatVersion": "aws_v1", "MaxResults": 100})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, destination = root / "input.json", root / "prices.json"
            source.write_text(json.dumps(input_data()))
            stdout = io.StringIO()
            with patch("pricing_aws.AWSPrices", return_value=self.provider), redirect_stdout(stdout):
                code = price.main(["lookup", "--input", str(source), "--output", str(destination)])
            result = json.loads(destination.read_text())
            response = json.loads(stdout.getvalue())
        self.assertEqual(code, 3)
        self.assertEqual(result["input_sha256"], input_hash(input_data()))
        self.assertEqual(result["candidates"][0]["items"][0]["price"]["tiers"][0]["unit_price"], "0.052")
        self.assertEqual(result["candidates"][0]["items"][1]["status"], "unavailable")
        self.assertEqual(response["issues"][0]["code"], "permission_denied")
        self.assertNotIn("do-not-print-secret", json.dumps(result) + stdout.getvalue())
        self.stub.assert_no_pending_responses()

    def test_full_ec2_rds_lookup_result(self):
        for product in (fixture("ec2.json"), fixture("rds.json")):
            self.metadata(product)
            self.products(product)
        result = price.lookup(input_data(), self.provider)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["issues"], [])
        self.assertEqual([item["price"]["sku"] for item in result["candidates"][0]["items"]],
                         ["EC2-EXAMPLE", "RDS-EXAMPLE"])
        self.stub.assert_no_pending_responses()

    def test_metadata_and_attribute_values_follow_pages(self):
        client = Mock()
        client.describe_services.side_effect = [dict(Services=[], NextToken="metadata-next"),
                                                 dict(Services=[dict(ServiceCode="AmazonEC2", AttributeNames=["regionCode"])])]
        client.get_attribute_values.side_effect = [dict(AttributeValues=[dict(Value="first")], NextToken="value-next"),
                                                   dict(AttributeValues=[dict(Value="second")])]
        provider = AWSPrices(client)
        self.assertIn("regionCode", provider.attributes("AmazonEC2"))
        self.assertEqual(provider.attribute_values("AmazonEC2", "usagetype"), {"first", "second"})
        self.assertEqual(client.describe_services.call_args.kwargs["NextToken"], "metadata-next")
        self.assertEqual(client.get_attribute_values.call_args.kwargs["NextToken"], "value-next")
        provider.attributes("AmazonEC2")
        provider.attribute_values("AmazonEC2", "usagetype")
        self.assertEqual(client.describe_services.call_count, 2)
        self.assertEqual(client.get_attribute_values.call_count, 2)

    def test_repeated_token_and_malformed_page(self):
        for pages in ([dict(PriceList=[], NextToken="same"), dict(PriceList=[], NextToken="same")], [dict(PriceList="wrong")]):
            client = Mock()
            client.get_products.side_effect = pages
            provider = AWSPrices(client)
            with self.assertRaises(LookupError) as caught:
                list(provider.pages("get_products", "PriceList"))
            self.assertEqual(caught.exception.code, "invalid_provider_response")


class ContractAndCLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.input = self.root / "input.json"
        self.output = self.root / "prices.json"
        self.data = input_data()
        self.input.write_text(json.dumps(self.data))

    def run_main(self, *args):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = price.main(list(args))
        return code, json.loads(stdout.getvalue())

    def test_example_validates_offline_without_writing(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts" / "price.py"), "validate", "--input", str(self.input)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"status": "complete", "output": None, "issues": []})
        self.assertFalse(self.output.exists())

    def test_invalid_input_and_unknown_fields_do_not_replace_output(self):
        self.output.write_text("old-results")
        self.data["candidates"][0]["target"] = "hybrid"
        self.input.write_text(json.dumps(self.data))
        code, response = self.run_main("lookup", "--input", str(self.input), "--output", str(self.output))
        self.assertEqual(code, 2)
        self.assertEqual(response["issues"][0]["code"], "invalid_input")
        self.assertEqual(self.output.read_text(), "old-results")

    def test_input_validation_rejects_wrong_types_duplicates_and_units(self):
        mutations = [lambda x: x.update(monthly_hours="NaN"), lambda x: x.update(extra=True),
                     lambda x: x.update(monthly_budget={"min": 0, "max": 1, "currency": "KRW"}),
                     lambda x: x["candidates"].append(copy.deepcopy(x["candidates"][0])),
                     lambda x: x["candidates"][0]["items"][0].update(quantity=True),
                     lambda x: x["candidates"][0]["items"][0].update(unit=[]),
                     lambda x: x["candidates"][0]["items"][0].update(monthly_usage={"min": "100", "max": "10"}),
                     lambda x: x["candidates"][0]["items"][0].update(incremental_usage={"min": "731", "max": "731"}),
                     lambda x: x["candidates"][0]["items"].append(copy.deepcopy(x["candidates"][0]["items"][0]))]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                data = input_data()
                mutation(data)
                with self.assertRaises(InputError):
                    validate_input(data)

    def test_duplicate_json_keys_and_nonfinite_numbers(self):
        for text in ('{"input_id":"first","input_id":"second"}', '{"value":NaN}', '\udcff'):
            with self.subTest(text=text):
                if text == '\udcff':
                    self.input.write_bytes(b'\xff')
                else:
                    self.input.write_text(text)
                with self.assertRaises(InputError):
                    load_input(self.input)

    def test_output_is_partial_and_preserves_success_after_failure(self):
        provider = Mock()
        provider.lookup.side_effect = [LookupError("permission_denied", "access denied"), {"sku": "later-success"}]
        result = price.lookup(self.data, provider)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["input_sha256"], input_hash(self.data))
        self.assertEqual(result["candidates"][0]["items"][0]["price"], None)
        self.assertEqual(result["candidates"][0]["items"][1]["price"]["sku"], "later-success")
        self.assertEqual(result["issues"][0]["item_id"], "nodes")

    def test_unsupported_target_never_queries_aws(self):
        self.data["candidates"][0]["target"] = "gcp"
        provider = Mock()
        result = price.lookup(self.data, provider)
        provider.lookup.assert_not_called()
        self.assertEqual(result["status"], "partial")
        self.assertTrue(all(x["price"] is None for x in result["candidates"][0]["items"]))

    def test_empty_onprem_needs_no_client(self):
        candidate = self.data["candidates"][0]
        candidate.update(target="onprem", region=None, items=[], assumptions=["Existing hardware; operating cost unpriced"])
        validate_input(self.data)
        provider = Mock()
        result = price.lookup(self.data, provider)
        provider.lookup.assert_not_called()
        self.assertEqual(result["status"], "complete")

    def test_lookup_cli_complete_and_partial_exit_codes(self):
        for status, expected in (("complete", 0), ("partial", 3)):
            with self.subTest(status=status), patch.object(price, "lookup", return_value={"status": status, "issues": []}):
                code, response = self.run_main("lookup", "--input", str(self.input), "--output", str(self.output))
                self.assertEqual(code, expected)
                self.assertEqual(response["status"], status)
                self.assertEqual(json.loads(self.output.read_text())["status"], status)

    def test_same_file_symlink_and_parent_symlink_are_rejected(self):
        original = self.input.read_bytes()
        link = self.root / "link.json"
        link.symlink_to(self.input)
        link_dir = self.root / "link-dir"
        link_dir.symlink_to(self.root, target_is_directory=True)
        for output in (self.input, link, link_dir / "prices.json"):
            with self.subTest(output=output):
                code, response = self.run_main("lookup", "--input", str(self.input), "--output", str(output))
                self.assertEqual(code, 2)
        self.assertEqual(self.input.read_bytes(), original)

    def test_failed_replace_preserves_previous_result_and_removes_temp(self):
        self.output.write_text("old-results")
        with patch.object(price, "lookup", return_value={"status": "complete", "issues": []}), \
                patch.object(price.os, "replace", side_effect=OSError("secret-file-error")):
            code, response = self.run_main("lookup", "--input", str(self.input), "--output", str(self.output))
        self.assertEqual(code, 1)
        self.assertEqual(response["issues"][0]["code"], "io_error")
        self.assertNotIn("secret-file-error", json.dumps(response))
        self.assertEqual(self.output.read_text(), "old-results")
        self.assertFalse(list(self.root.glob(".pricing-*.tmp")))

    def test_missing_input_and_output_parent_are_io_errors(self):
        for args in (("validate", "--input", str(self.root / "missing.json")),
                     ("lookup", "--input", str(self.input), "--output", str(self.root / "missing" / "prices.json"))):
            code, response = self.run_main(*args)
            self.assertEqual(code, 1)
            self.assertEqual(response["issues"][0]["code"], "io_error")

    def test_bad_cli_arguments_are_json_errors_without_echoing_values(self):
        for args in ((), ("lookup", "--input", str(self.input)), ("secret-option",), ("validate", "--secret-token", "secret-value")):
            code, response = self.run_main(*args)
            self.assertEqual(code, 2)
            self.assertNotIn("secret-value", json.dumps(response))


if __name__ == "__main__":
    unittest.main()
