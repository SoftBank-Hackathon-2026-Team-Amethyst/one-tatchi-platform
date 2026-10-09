"""AWS public On-Demand price lookup; no resource creation or billing access."""

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError, ClientError, ConnectTimeoutError, CredentialRetrievalError,
    EndpointConnectionError, NoCredentialsError, PartialCredentialsError, ReadTimeoutError,
    SSOTokenLoadError, TokenRetrievalError, UnauthorizedSSOTokenError,
)


class LookupError(Exception):
    def __init__(self, code, message, retryable=False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


# API field names are discovered before use. Explicit usage_type selects a
# service's billing dimension, avoiding guesses about regional usage prefixes.
PROFILES = {
    ("ec2", "instance_hours"): ("AmazonEC2", ("instance_type", "operating_system", "tenancy"),
                                {"productFamily": "Compute Instance", "preInstalledSw": "NA", "capacitystatus": "Used"}),
    ("rds", "instance_hours"): ("AmazonRDS", ("instance_class", "engine", "deployment"), {"productFamily": "Database Instance"}),
    ("rds", "storage"): ("AmazonRDS", ("usage_type", "engine", "deployment"), {}),
    ("ebs", "storage"): ("AmazonEC2", ("usage_type",), {}),
    ("eks", "cluster_hours"): ("AmazonEKS", ("usage_type",), {}),
    ("nat", "gateway_hours"): ("AmazonEC2", ("usage_type",), {}),
    ("nat", "processed_data"): ("AmazonEC2", ("usage_type",), {}),
    ("alb", "load_balancer_hours"): ("AWSELB", ("usage_type",), {}),
    ("alb", "lcu_hours"): ("AWSELB", ("usage_type",), {}),
    ("ecr", "storage"): ("AmazonECR", ("usage_type",), {}),
    ("logs", "ingestion"): ("AmazonCloudWatch", ("usage_type",), {}),
    ("logs", "storage"): ("AmazonCloudWatch", ("usage_type",), {}),
    ("internet_egress", "transfer"): ("AWSDataTransfer", ("usage_type", "to_location"), {}),
}
ALIASES = {
    "instance_type": "instanceType", "instance_class": "instanceType",
    "operating_system": "operatingSystem", "tenancy": "tenancy", "engine": "databaseEngine",
    "deployment": "deploymentOption", "usage_type": "usagetype", "operation": "operation",
    "license_model": "licenseModel", "volume_api_name": "volumeApiName",
    "product_family": "productFamily", "to_location": "toLocation",
    "from_location": "fromLocation", "preinstalled_software": "preInstalledSw",
    "capacity_status": "capacitystatus",
}
# Preserve AWS's billed GB unit; never silently label it GiB.
UNITS = {"Hrs": "hour", "hrs": "hour", "Hours": "hour", "GB-Mo": "gb_month",
         "GB-month": "gb_month", "GB": "gb", "Requests": "request",
         "LCU-Hrs": "lcu_hour"}


def decimal_text(value):
    return format(value, "f")


def number(value):
    if not isinstance(value, str):
        raise ValueError("expected decimal string")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("invalid nonnegative number")
    return result


def aws_error(exc):
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError, CredentialRetrievalError,
                        SSOTokenLoadError, TokenRetrievalError, UnauthorizedSSOTokenError)):
        return LookupError("authentication_failed", "AWS credentials are unavailable or could not be retrieved")
    if isinstance(exc, (ReadTimeoutError, ConnectTimeoutError, EndpointConnectionError)):
        return LookupError("timeout", "AWS pricing endpoint could not be reached in time", True)
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        if code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
            return LookupError("permission_denied", "AWS pricing access was denied")
        if code in {"ExpiredToken", "ExpiredTokenException", "InvalidClientTokenId", "UnrecognizedClientException", "SignatureDoesNotMatch"}:
            return LookupError("authentication_failed", "AWS authentication failed")
        if code in {"Throttling", "ThrottlingException", "TooManyRequestsException", "RequestLimitExceeded"}:
            return LookupError("rate_limited", "AWS pricing request was rate limited", True)
        if code in {"InternalErrorException", "ServiceUnavailable", "ServiceUnavailableException"}:
            return LookupError("invalid_provider_response", "AWS pricing service is temporarily unavailable", True)
        if code == "NotFoundException":
            return LookupError("not_found", "AWS pricing service or product was not found")
    return LookupError("invalid_provider_response", "AWS pricing request or response could not be processed")


class AWSPrices:
    def __init__(self, client=None):
        self._client = client
        self._services = {}
        self._values = {}

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client("pricing", region_name="us-east-1",
                                        config=Config(connect_timeout=5, read_timeout=15,
                                                      retries={"mode": "standard", "total_max_attempts": 3}))
        return self._client

    def pages(self, method, list_key, **kwargs):
        token, seen = None, set()
        while True:
            response = getattr(self.client, method)(**kwargs, **({"NextToken": token} if token else {}))
            if not isinstance(response, dict) or not isinstance(response.get(list_key), list):
                raise LookupError("invalid_provider_response", "AWS pricing page has an invalid shape")
            yield from response[list_key]
            token = response.get("NextToken")
            if token is None:
                break
            if not isinstance(token, str) or not token or token in seen:
                raise LookupError("invalid_provider_response", "AWS pricing pagination token is invalid or repeated")
            seen.add(token)

    def attributes(self, service):
        if service not in self._services:
            records = list(self.pages("describe_services", "Services", ServiceCode=service, FormatVersion="aws_v1", MaxResults=100))
            if any(not isinstance(record, dict) for record in records):
                raise LookupError("invalid_provider_response", "AWS service metadata is invalid")
            records = [record for record in records if record.get("ServiceCode") == service]
            if len(records) != 1 or not isinstance(records[0].get("AttributeNames"), list):
                raise LookupError("invalid_provider_response", "AWS service attributes could not be determined")
            names = records[0]["AttributeNames"]
            if any(not isinstance(name, str) for name in names):
                raise LookupError("invalid_provider_response", "AWS service attribute names are invalid")
            self._services[service] = set(names) | {"productFamily", "sku"}
        return self._services[service]

    def attribute_values(self, service, attribute):
        key = (service, attribute)
        if key not in self._values:
            records = self.pages("get_attribute_values", "AttributeValues", ServiceCode=service, AttributeName=attribute, MaxResults=100)
            values = set()
            for record in records:
                if not isinstance(record, dict) or not isinstance(record.get("Value"), str):
                    raise LookupError("invalid_provider_response", "AWS service attribute value is invalid")
                values.add(record["Value"])
            self._values[key] = values
        return self._values[key]

    def filters(self, candidate, item):
        profile = PROFILES.get((item["resource_kind"], item["billing_dimension"]))
        if profile is None:
            raise LookupError("unsupported_resource", "AWS resource or billing dimension is not supported")
        service, required, defaults = profile
        attrs = item["attributes"]
        if any(key not in attrs for key in required):
            raise LookupError("unsupported_resource", "AWS lookup requires explicit resource attributes: " + ", ".join(required))
        unknown = set(attrs) - set(ALIASES) - {"rate_code"}
        if unknown:
            raise LookupError("unsupported_resource", "AWS lookup attributes are not supported")
        filters = dict(defaults)
        for key, value in attrs.items():
            if key == "rate_code":
                continue
            field = ALIASES[key]
            if field in filters and filters[field] != value:
                raise LookupError("unsupported_resource", "AWS attributes conflict with the resource profile")
            if field in filters and key in {"instance_type", "instance_class"}:
                raise LookupError("unsupported_resource", "AWS instance attributes conflict")
            filters[field] = value
        region_field = "fromRegionCode" if item["resource_kind"] == "internet_egress" else "regionCode"
        filters[region_field] = candidate["region"]
        names = self.attributes(service)
        if not set(filters) <= names:
            raise LookupError("unsupported_resource", "AWS service does not expose the requested lookup attributes")
        # Verify regional billing type spelling against provider metadata.
        if "usagetype" in filters and filters["usagetype"] not in self.attribute_values(service, "usagetype"):
            raise LookupError("not_found", "AWS billing usage type was not found")
        return service, filters

    def lookup(self, candidate, item, now=None):
        try:
            now = now or datetime.now(timezone.utc)
            service, filters = self.filters(candidate, item)
            request_filters = [{"Type": "TERM_MATCH", "Field": field, "Value": value} for field, value in sorted(filters.items())]
            products = {}
            for raw in self.pages("get_products", "PriceList", ServiceCode=service, Filters=request_filters,
                                  FormatVersion="aws_v1", MaxResults=100):
                if not isinstance(raw, str):
                    raise ValueError("invalid product record")
                data = json.loads(raw)
                product = data["product"]
                sku = product["sku"]
                if not isinstance(sku, str) or not sku:
                    raise ValueError("invalid sku")
                attributes = product["attributes"]
                actual = dict(attributes, productFamily=product.get("productFamily"), sku=sku)
                if any(actual.get(field) != value for field, value in filters.items()):
                    raise LookupError("invalid_provider_response", "AWS returned a product outside the requested filters")
                if data.get("serviceCode", attributes.get("servicecode")) != service:
                    raise LookupError("invalid_provider_response", "AWS returned another service's product")
                if sku in products and products[sku] != data:
                    raise LookupError("ambiguous_sku", "AWS returned conflicting prices for one SKU")
                products[sku] = data
            if not products:
                raise LookupError("not_found", "No AWS product matched the requested resource")
            if len(products) != 1:
                raise LookupError("ambiguous_sku", "Multiple AWS SKUs matched; refine resource attributes")
            return normalize(next(iter(products.values())), service, item, now)
        except LookupError:
            raise
        except (ClientError, BotoCoreError) as exc:
            raise aws_error(exc) from None
        except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation, OverflowError):
            raise LookupError("invalid_provider_response", "AWS pricing response is malformed or inconsistent") from None


def normalize(data, service, item, now):
    sku = data["product"]["sku"]
    terms = data["terms"].get("OnDemand", {})
    valid = []
    for term in terms.values():
        effective = datetime.fromisoformat(term["effectiveDate"].replace("Z", "+00:00"))
        if effective.tzinfo is None or effective.utcoffset().total_seconds() != 0 or term["sku"] != sku:
            raise ValueError("invalid term")
        if effective <= now:
            valid.append((effective, term))
    if not valid:
        raise LookupError("not_found", "No effective AWS On-Demand term was found")
    latest = max(date for date, _ in valid)
    valid = [term for date, term in valid if date == latest]
    if len(valid) != 1:
        raise LookupError("ambiguous_sku", "Multiple effective AWS On-Demand terms matched")
    dimensions = valid[0]["priceDimensions"].values()
    rate_code = item["attributes"].get("rate_code")
    selected, saw_unit = [], False
    for dimension in dimensions:
        source_unit = dimension["unit"]
        if UNITS.get(source_unit) != item["unit"]:
            continue
        saw_unit = True
        if rate_code and dimension["rateCode"] != rate_code:
            continue
        if dimension.get("appliesTo", []):
            raise LookupError("unsupported_resource", "AWS price dimension has conditional applicability")
        low = number(dimension["beginRange"])
        high = None if dimension["endRange"] == "Inf" else number(dimension["endRange"])
        rate = number(dimension["pricePerUnit"]["USD"])
        if high is not None and high <= low:
            raise ValueError("invalid tier bounds")
        selected.append((low, high, rate, source_unit))
    if not selected:
        code = "not_found" if saw_unit and rate_code else "unsupported_unit"
        raise LookupError(code, "No AWS price dimension matched the requested unit or rate code")
    selected.sort(key=lambda x: x[0])
    if len({x[3] for x in selected}) != 1:
        raise LookupError("ambiguous_sku", "AWS price dimensions use inconsistent source units")
    expected = Decimal(0)
    tiers = []
    for low, high, rate, _ in selected:
        if expected is None or low != expected:
            raise LookupError("ambiguous_sku", "AWS price dimensions overlap or have gaps")
        tiers.append({"from": decimal_text(low), "to": None if high is None else decimal_text(high), "unit_price": decimal_text(rate)})
        expected = high
    if expected is not None:
        raise LookupError("invalid_provider_response", "AWS price tiers do not cover the final usage range")
    return {"sku": sku, "provider_service": service, "currency": "USD",
            "source": "https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_pricing_GetProducts.html",
            "effective_at": latest.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "unit": item["unit"], "source_unit": selected[0][3], "source_usage_per_unit": "1", "tiers": tiers}
