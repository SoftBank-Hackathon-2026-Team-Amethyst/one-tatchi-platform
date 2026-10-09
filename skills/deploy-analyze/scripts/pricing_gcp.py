"""Google Cloud public Catalog lookup using existing read-only ADC credentials."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, localcontext

import google.auth
from google.auth.credentials import with_scopes_if_required
from google.auth.exceptions import DefaultCredentialsError, RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession
from requests.exceptions import RequestException, Timeout, ConnectionError

from pricing_errors import LookupError
from pricing_contract import unique_object

BASE_URL = "https://cloudbilling.googleapis.com/v1/"
SCOPE = "https://www.googleapis.com/auth/cloud-billing.readonly"
PROFILES = {
    ("gke", "cluster_hours"): "Kubernetes Engine",
    ("gke_node", "cpu_hours"): "Compute Engine",
    ("gke_node", "memory_hours"): "Compute Engine",
    ("gcp_disk", "storage"): "Compute Engine",
    ("cloud_nat", "gateway_hours"): "Compute Engine",
    ("cloud_nat", "processed_data"): "Compute Engine",
    ("gcp_load_balancer", "load_balancer_hours"): "Compute Engine",
    ("gcp_load_balancer", "processed_data"): "Compute Engine",
    ("cloud_sql", "cpu_hours"): "Cloud SQL",
    ("cloud_sql", "memory_hours"): "Cloud SQL",
    ("cloud_sql", "instance_hours"): "Cloud SQL",
    ("cloud_sql", "storage"): "Cloud SQL",
    ("artifact_registry", "storage"): "Artifact Registry",
    ("gcp_logs", "ingestion"): "Cloud Logging",
    ("gcp_logs", "storage"): "Cloud Logging",
    ("gcp_internet_egress", "transfer"): "Compute Engine",
}
ATTRIBUTES = {"resource_family", "resource_group", "usage_type", "description", "sku_id", "service_id"}
# (provider base unit, canonical usage in base units, allowed source units).
GIB = Decimal(1073741824)
MONTH_SECONDS = Decimal(730 * 3600)
UNITS = {
    "hour": ("s", Decimal(3600), {"h", "s"}),
    "vcpu_hour": ("s", Decimal(3600), {"h", "s"}),
    "gib_hour": ("By.s", GIB * 3600, {"GiBy.h", "GiBy.s", "By.s"}),
    "gib_month": ("By.s", GIB * MONTH_SECONDS, {"GiBy.mo", "By.s"}),
    "gb_month": ("By.s", Decimal(1000000000) * MONTH_SECONDS, {"GBy.mo", "By.s"}),
    "gib": ("By", GIB, {"GiBy", "GBy", "By"}),
    "gb": ("By", Decimal(1000000000), {"GiBy", "GBy", "By"}),
    "request": ("count", Decimal(1), {"count"}),
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, str)):
        raise ValueError("invalid numeric type")
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("invalid nonnegative number")
    return result


def text(value):
    return format(value, "f")


def parse_time(value):
    if not isinstance(value, str):
        raise ValueError("invalid effective time")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("effective time has no timezone")
    return result.astimezone(timezone.utc)


def latest_price(sku, now):
    versions = sku["pricingInfo"]
    if not isinstance(versions, list):
        raise ValueError("invalid pricing timeline")
    valid = []
    for version in versions:
        effective = parse_time(version["effectiveTime"])
        if effective <= now:
            valid.append((effective, version))
    if not valid:
        raise LookupError("not_found", "No effective GCP public price was found")
    latest = max(effective for effective, _ in valid)
    valid = [version for effective, version in valid if effective == latest]
    if len(valid) != 1:
        raise LookupError("ambiguous_sku", "Multiple effective GCP price versions matched")
    return valid[0], latest


def money(value):
    if not isinstance(value, dict) or value.get("currencyCode") != "USD":
        raise ValueError("expected USD money")
    units, nanos = value.get("units", "0"), value.get("nanos", 0)
    if not isinstance(units, str) or re.fullmatch(r"(?:0|[1-9][0-9]*)", units) is None:
        raise ValueError("invalid money units")
    if int(units) > 9223372036854775807 or type(nanos) is not int or not 0 <= nanos <= 999999999:
        raise ValueError("invalid money nanos")
    return Decimal(units) + Decimal(nanos) / Decimal(1000000000), units, nanos


def regional(sku, region):
    regions = sku.get("serviceRegions", [])
    if not isinstance(regions, list) or any(not isinstance(x, str) or not x for x in regions):
        raise ValueError("invalid service regions")
    geo = sku.get("geoTaxonomy", {})
    if not isinstance(geo, dict):
        raise ValueError("invalid geo taxonomy")
    if geo.get("type") == "GLOBAL":
        if geo.get("regions", []) or any(x != "global" for x in regions):
            raise ValueError("conflicting global region metadata")
        return True
    if regions == ["global"] and not geo:
        return True
    return region in regions


class GCPPrices:
    def __init__(self, session=None):
        self._session = session
        self._services = None
        self._skus = {}

    @property
    def session(self):
        if self._session is None:
            credentials, _ = google.auth.default()
            credentials = with_scopes_if_required(credentials, scopes=[SCOPE])
            self._session = AuthorizedSession(credentials, max_refresh_attempts=1, refresh_timeout=15)
        return self._session

    def request(self, path, params):
        response = self.session.get(BASE_URL + path, params=params, timeout=(5, 15))
        try:
            body = json.loads(response.text, parse_float=Decimal, object_pairs_hook=unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
        except (ValueError, TypeError):
            body = None
        status = response.status_code
        if status != 200:
            details = body.get("error", {}).get("details", []) if isinstance(body, dict) and isinstance(body.get("error"), dict) else []
            disabled = isinstance(details, list) and any(isinstance(x, dict) and x.get("reason") == "SERVICE_DISABLED" for x in details)
            if status == 403:
                code = "api_disabled" if disabled else "permission_denied"
                raise LookupError(code, "GCP Billing API is disabled" if disabled else "GCP Billing Catalog access was denied")
            if status == 401:
                raise LookupError("authentication_failed", "GCP authentication failed")
            if status == 429:
                raise LookupError("rate_limited", "GCP Billing Catalog request was rate limited", True)
            if status == 404:
                raise LookupError("not_found", "GCP Billing Catalog resource was not found")
            raise LookupError("invalid_provider_response", "GCP Billing Catalog request failed", status >= 500)
        if not isinstance(body, dict):
            raise LookupError("invalid_provider_response", "GCP Billing Catalog returned invalid JSON")
        return body

    def pages(self, path, key, **params):
        token, seen = None, set()
        while True:
            body = self.request(path, dict(params, **({"pageToken": token} if token else {})))
            # Protobuf JSON may omit an empty repeated field.
            records = body.get(key, [])
            if not isinstance(records, list) or any(not isinstance(x, dict) for x in records):
                raise LookupError("invalid_provider_response", "GCP Catalog page has an invalid shape")
            yield from records
            token = body.get("nextPageToken", "")
            if token == "":
                break
            if not isinstance(token, str) or not token or token in seen:
                raise LookupError("invalid_provider_response", "GCP Catalog pagination token is invalid or repeated")
            seen.add(token)

    def services(self):
        if self._services is None:
            self._services = list(self.pages("services", "services", pageSize=5000))
        return self._services

    def skus(self, service):
        if service not in self._skus:
            self._skus[service] = list(self.pages(service + "/skus", "skus", currencyCode="USD", pageSize=5000))
        return self._skus[service]

    def lookup(self, candidate, item, now=None):
        try:
            with localcontext() as context:
                context.prec = 80
                return self._lookup(candidate, item, now or datetime.now(timezone.utc))
        except LookupError:
            raise
        except (DefaultCredentialsError, RefreshError):
            raise LookupError("authentication_failed", "GCP ADC credentials could not be loaded or refreshed") from None
        except (Timeout, ConnectionError, TransportError):
            raise LookupError("timeout", "GCP authentication or Catalog endpoint could not be reached in time", True) from None
        except RequestException:
            raise LookupError("invalid_provider_response", "GCP Catalog transport request failed") from None
        except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation, OverflowError):
            raise LookupError("invalid_provider_response", "GCP Catalog response is malformed or inconsistent") from None

    def _lookup(self, candidate, item, now):
        display_name = PROFILES.get((item["resource_kind"], item["billing_dimension"]))
        attrs = item["attributes"]
        if display_name is None or set(attrs) - ATTRIBUTES:
            raise LookupError("unsupported_resource", "GCP resource or lookup attributes are not supported")
        if not all(key in attrs for key in ("resource_family", "resource_group")) or not any(key in attrs for key in ("description", "sku_id")):
            raise LookupError("unsupported_resource", "GCP lookup requires resource_family, resource_group, and exact description or sku_id")
        if attrs.get("usage_type", "OnDemand") != "OnDemand":
            raise LookupError("unsupported_resource", "GCP base quotes require public OnDemand usage")
        services = []
        for service in self.services():
            name, sid = service["name"], service["serviceId"]
            if not isinstance(sid, str) or re.fullmatch(r"[A-Za-z0-9-]+", sid) is None or name != "services/" + sid:
                raise ValueError("invalid service identifier")
            if service["displayName"] == display_name and ("service_id" not in attrs or sid == attrs["service_id"]):
                services.append(name)
        if not services:
            raise LookupError("not_found", "GCP catalog service was not found")
        if len(services) != 1:
            raise LookupError("ambiguous_sku", "Multiple GCP catalog services matched")
        service = services[0]
        matches, free_issues = {}, []
        for sku in self.skus(service):
            sid = sku["skuId"]
            if not isinstance(sid, str) or not sid or sku["name"] != service + "/skus/" + sid:
                raise ValueError("invalid SKU identifier")
            category = sku["category"]
            if category.get("resourceFamily") != attrs["resource_family"] or category.get("resourceGroup") != attrs["resource_group"] or category.get("usageType") != "OnDemand":
                continue
            if "sku_id" in attrs and sid != attrs["sku_id"]:
                continue
            if "description" in attrs and sku["description"] != attrs["description"]:
                continue
            if not regional(sku, candidate["region"]):
                continue
            version, _ = latest_price(sku, now)
            prices = [money(rate["unitPrice"])[0] for rate in version["pricingExpression"]["tieredRates"]]
            if not prices:
                raise ValueError("empty pricing tiers")
            if all(value == 0 for value in prices):
                free_issues.append(LookupError("not_found", "Free GCP SKU excluded from the public paid configuration quote"))
                continue
            # Do not silently grant account/project free allowances to this app.
            if any(value == 0 for value in prices):
                free_issues.append(LookupError("unsupported_resource", "GCP free tier requires verified eligibility and sharing scope"))
                continue
            if sid in matches and matches[sid] != sku:
                raise LookupError("ambiguous_sku", "GCP returned conflicting records for one SKU")
            matches[sid] = sku
        if not matches:
            if free_issues:
                raise free_issues[0]
            raise LookupError("not_found", "No GCP paid SKU matched the requested configuration and region")
        if len(matches) != 1:
            raise LookupError("ambiguous_sku", "Multiple GCP paid SKUs matched; refine resource attributes")
        return normalize(next(iter(matches.values())), service, item, now)


def normalize(sku, service, item, now):
    version, effective = latest_price(sku, now)
    expression = version["pricingExpression"]
    source_unit, base_unit = expression["usageUnit"], expression["baseUnit"]
    conversion = number(expression["baseUnitConversionFactor"])
    desired = UNITS.get(item["unit"])
    if conversion <= 0 or desired is None or desired[0] != base_unit or source_unit not in desired[2]:
        raise LookupError("unsupported_unit", "GCP pricing unit cannot be converted to the requested canonical unit")
    # Same named month units preserve the provider's calendar convention.
    same_month = (source_unit, item["unit"]) in {("GiBy.mo", "gib_month"), ("GBy.mo", "gb_month")}
    factor = Decimal(1) if same_month else desired[1] / conversion
    if factor <= 0:
        raise ValueError("invalid unit factor")
    display = number(expression.get("displayQuantity", 1))
    if display <= 0:
        raise ValueError("invalid display quantity")
    currency_conversion = number(version.get("currencyConversionRate", 1))
    if currency_conversion != 1:
        raise ValueError("USD response unexpectedly contains currency conversion")
    aggregation = version.get("aggregationInfo")
    if aggregation is not None:
        if not isinstance(aggregation, dict):
            raise ValueError("invalid aggregation metadata")
        if aggregation.get("aggregationLevel", "AGGREGATION_LEVEL_UNSPECIFIED") not in {"AGGREGATION_LEVEL_UNSPECIFIED", "ACCOUNT", "PROJECT"}:
            raise ValueError("invalid aggregation level")
        if aggregation.get("aggregationInterval", "AGGREGATION_INTERVAL_UNSPECIFIED") not in {"AGGREGATION_INTERVAL_UNSPECIFIED", "DAILY", "MONTHLY"}:
            raise ValueError("invalid aggregation interval")
        count = aggregation.get("aggregationCount", 1)
        if type(count) is not int or count <= 0:
            raise ValueError("invalid aggregation count")
        aggregation = {key: aggregation[key] for key in ("aggregationLevel", "aggregationInterval", "aggregationCount") if key in aggregation}
    raw_tiers, tiers = [], []
    for rate in expression["tieredRates"]:
        start = number(rate.get("startUsageAmount", 0))
        amount, units, nanos = money(rate["unitPrice"])
        if amount == 0:
            raise LookupError("unsupported_resource", "GCP free allowances are not applied to a base quote")
        raw_tiers.append({"from": text(start), "units": units, "nanos": nanos})
        tiers.append({"from": text(start / factor), "to": None, "unit_price": text(amount * factor)})
    pairs = sorted(zip(raw_tiers, tiers), key=lambda pair: Decimal(pair[1]["from"]))
    if not pairs or Decimal(pairs[0][1]["from"]) != 0:
        raise ValueError("GCP price tiers must start at zero")
    for index, (_, tier) in enumerate(pairs[:-1]):
        next_start = pairs[index + 1][1]["from"]
        if Decimal(next_start) <= Decimal(tier["from"]):
            raise LookupError("ambiguous_sku", "GCP price tiers have duplicate boundaries")
        tier["to"] = next_start
    # Retain nanosecond timestamp precision when already Z-normalized.
    effective_text = version["effectiveTime"] if version["effectiveTime"].endswith("Z") else effective.isoformat().replace("+00:00", "Z")
    return {"sku": sku["skuId"], "provider_service": service, "currency": "USD",
            "source": "https://docs.cloud.google.com/billing/docs/reference/rest/v1/services.skus/list",
            "effective_at": effective_text, "unit": item["unit"], "source_unit": source_unit,
            "source_usage_per_unit": text(factor), "tiers": [pair[1] for pair in pairs],
            "provider_details": {"usage_unit": source_unit, "base_unit": base_unit,
                                 "base_unit_conversion_factor": text(conversion), "display_quantity": text(display),
                                 "currency_conversion_rate": text(currency_conversion), "aggregation": aggregation,
                                 "effective_time": version["effectiveTime"], "tiers": [pair[0] for pair in pairs]}}
