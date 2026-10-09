"""Reuse a dated API quote only when pricing selectors and units are unchanged."""

import copy

from pricing_calculate import validate_prices
from pricing_contract import input_hash, require, timestamp, validate_input

CALCULATION_ATTRIBUTES = {"tier_baseline_usage", "free_tier_policy"}


def selector(item):
    return {key: item[key] for key in ("resource_id", "resource_kind", "billing_dimension", "unit", "shared", "cost_type")} | {
        "attributes": {key: value for key, value in item["attributes"].items() if key not in CALCULATION_ATTRIBUTES}
    }


def reuse_prices(data, source_input, source_prices):
    validate_input(data)
    validate_input(source_input)
    records = validate_prices(source_input, source_prices)
    sources = {candidate["candidate_id"]: candidate for candidate in source_input["candidates"]}
    result = copy.deepcopy(source_prices)
    result.update(input_id=data["input_id"], input_sha256=input_hash(data), candidates=[], issues=[])
    for candidate in data["candidates"]:
        cid = candidate["candidate_id"]
        require(cid in sources, "reuse: new candidate requires a fresh lookup")
        source = sources[cid]
        require((candidate["target"], candidate["region"]) == (source["target"], source["region"]),
                "reuse: changed target or region requires a fresh lookup")
        items = {item["item_id"]: item for item in source["items"]}
        output = {key: candidate[key] for key in ("candidate_id", "target", "region")}
        output["items"] = []
        for item in candidate["items"]:
            iid = item["item_id"]
            require(iid in items and selector(item) == selector(items[iid]),
                    "reuse: changed resource, pricing selector or unit requires a fresh lookup")
            if candidate["target"] == "gcp" and item["resource_kind"] == "cloud_nat" and item["billing_dimension"] == "gateway_hours" and item["attributes"].get("catalog_api") == "v2beta":
                require(item["quantity"] <= 32, "reuse: capped NAT gateway requires a separate quote model")
            record = copy.deepcopy(records[cid][iid])
            output["items"].append(record)
            if record["issue"] is not None:
                result["issues"].append(record["issue"])
        result["candidates"].append(output)
    result["status"] = "partial" if result["issues"] else "complete"
    validate_prices(data, result)
    evidence = dict(schema_version="1", method="verified_usage_only_reuse", reused_at=timestamp(),
                    source_input_id=source_input["input_id"], source_input_sha256=input_hash(source_input),
                    source_prices_sha256=input_hash(source_prices), input_sha256=input_hash(data),
                    prices_sha256=input_hash(result), queried_at=source_prices["queried_at"],
                    note="No API request occurred. Pricing selectors and units matched; the original query time and price evidence are preserved.")
    return result, evidence
