"""Decimal-only monthly costing with strict input/price identity checks."""

import copy
import json
from collections import defaultdict
from decimal import Decimal, localcontext
from datetime import datetime, timezone
from pathlib import Path

from pricing_contract import (
    InputError, decimal_value, fields, input_hash, issue, require, string,
    unique_object, usage, utc_time, validate_input, timestamp,
)

PRICE_KEYS = "sku provider_service currency source effective_at unit source_unit source_usage_per_unit tiers"
ISSUE_CODES = {"authentication_failed", "permission_denied", "api_disabled", "timeout", "rate_limited", "not_found",
               "ambiguous_sku", "unsupported_resource", "unsupported_unit", "invalid_provider_response",
               "unknown_usage", "unknown_incremental_usage", "unbounded_usage"}


def load_document(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError("JSON: nonfinite number")))
    except (json.JSONDecodeError, UnicodeError):
        raise InputError("pricing document: invalid UTF-8 JSON") from None


def encoded(value):
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def rendered(value):
    return None if value is None else {"min": encoded(value[0]), "max": None if value[1] is None else encoded(value[1])}


def scaled(value, quantity):
    bounds = usage(value, "usage")
    return None if bounds is None else (bounds[0] * quantity, None if bounds[1] is None else bounds[1] * quantity)


def summed(values, empty_zero=False):
    known = [value for value in values if value is not None]
    if not known:
        return (Decimal(0), Decimal(0)) if empty_zero else None
    return sum(value[0] for value in known), (None if any(value[1] is None for value in known) else sum(value[1] for value in known))


def validate_price_record(value, item, version, target):
    require(isinstance(value, dict), "price: expected object")
    require(set(value) in (set(PRICE_KEYS.split()), set(PRICE_KEYS.split()) | {"provider_details"}), "price: missing or unknown fields")
    require(version in ("2", "3") or "provider_details" not in value, "provider_details requires result version 2")
    for key in ("sku", "provider_service", "source", "source_unit"):
        string(value[key], "price." + key)
    require(value["currency"] == "USD", "price: expected USD")
    require(value["unit"] == item["unit"], "price: unit does not match input")
    if value["effective_at"] is None:
        require(version == "3" and (value.get("provider_details") or {}).get("api") == "v2beta", "effective date can be unknown only for the explicit latest-price API")
    else:
        utc_time(value["effective_at"], "price.effective_at")
    factor = decimal_value(value["source_usage_per_unit"], "price.source_usage_per_unit", positive=True)
    tiers = value["tiers"]
    require(isinstance(tiers, list) and tiers, "price: tiers required")
    expected = Decimal(0)
    for tier in tiers:
        fields(tier, "from to unit_price", "price tier")
        low = decimal_value(tier["from"], "tier.from")
        high = None if tier["to"] is None else decimal_value(tier["to"], "tier.to")
        decimal_value(tier["unit_price"], "tier.unit_price")
        require(expected is not None and low == expected and (high is None or high > low), "price: overlapping or discontinuous tiers")
        expected = high
    require(expected is None, "price: final tier must be unbounded")
    details = value.get("provider_details")
    if target == "gcp" and version in ("2", "3"):
        require(details is not None and ((version == "3" and details.get("api") == "v2beta") or all(Decimal(tier["unit_price"]) > 0 for tier in tiers)),
                "GCP paid quote requires provider details and excludes unverified free tiers")
    if details is not None:
        if details.get("api") == "v2beta":
            validate_direct_details(details, value, version)
            return
        fields(details, "usage_unit base_unit base_unit_conversion_factor display_quantity currency_conversion_rate aggregation effective_time tiers", "provider_details")
        require(details["usage_unit"] == value["source_unit"], "provider_details: source unit mismatch")
        string(details["base_unit"], "provider_details.base_unit")
        for key in ("base_unit_conversion_factor", "display_quantity"):
            decimal_value(details[key], "provider_details." + key, positive=True)
        require(decimal_value(details["currency_conversion_rate"], "provider_details.currency_conversion_rate") == 1,
                "provider_details: USD conversion rate must equal 1")
        try:
            raw_time = datetime.fromisoformat(details["effective_time"].replace("Z", "+00:00"))
            require(raw_time.tzinfo is not None and raw_time.astimezone(timezone.utc) == utc_time(value["effective_at"], "price.effective_at"),
                    "provider_details: effective timestamp mismatch")
        except (ValueError, TypeError, AttributeError):
            raise InputError("provider_details: invalid effective timestamp") from None
        require(isinstance(details["tiers"], list) and len(details["tiers"]) == len(tiers), "provider_details: tier count mismatch")
        for raw, tier in zip(details["tiers"], tiers):
            fields(raw, "from units nanos", "provider money tier")
            low = decimal_value(raw["from"], "provider tier.from")
            require(isinstance(raw["units"], str) and raw["units"].isdigit() and type(raw["nanos"]) is int and 0 <= raw["nanos"] < 1000000000,
                    "provider_details: invalid money")
            amount = Decimal(raw["units"]) + Decimal(raw["nanos"]) / Decimal(1000000000)
            require(low / factor == Decimal(tier["from"]) and amount * factor == Decimal(tier["unit_price"]),
                    "provider_details: normalized tier differs from source money")
        agg = details["aggregation"]
        if agg is not None:
            require(isinstance(agg, dict) and set(agg) <= {"aggregationLevel", "aggregationInterval", "aggregationCount"}, "provider_details: invalid aggregation")
            require(agg.get("aggregationLevel", "AGGREGATION_LEVEL_UNSPECIFIED") in ("ACCOUNT", "PROJECT", "AGGREGATION_LEVEL_UNSPECIFIED"), "invalid aggregation level")
            require(agg.get("aggregationInterval", "AGGREGATION_INTERVAL_UNSPECIFIED") in ("DAILY", "MONTHLY", "AGGREGATION_INTERVAL_UNSPECIFIED"), "invalid aggregation interval")
            require(type(agg.get("aggregationCount", 1)) is int and agg.get("aggregationCount", 1) > 0, "invalid aggregation count")


def validate_direct_details(details, price, version):
    fields(details, "api usage_unit unit_quantity aggregation effective_time tiers", "direct provider details")
    require(version == "3" and price["effective_at"] is None and details["effective_time"] is None,
            "latest direct API must not invent a price effective timestamp")
    require(details["usage_unit"] == price["source_unit"] and price["source_usage_per_unit"] == "1", "direct unit mapping mismatch")
    from pricing_contract import GCP_DIRECT_UNITS
    require(GCP_DIRECT_UNITS.get(price["unit"]) == price["source_unit"], "direct canonical unit differs from source unit")
    quantity = decimal_value(details["unit_quantity"], "direct unit_quantity", positive=True)
    require(isinstance(details["tiers"], list) and len(details["tiers"]) == len(price["tiers"]), "direct tier count mismatch")
    for raw, tier in zip(details["tiers"], price["tiers"]):
        fields(raw, "from units nanos", "direct money tier")
        require(decimal_value(raw["from"], "direct tier.from") == Decimal(tier["from"]), "direct tier boundary mismatch")
        require(isinstance(raw["units"], str) and raw["units"].isdigit() and type(raw["nanos"]) is int and 0 <= raw["nanos"] < 1000000000,
                "invalid direct Money")
        amount = Decimal(raw["units"]) + Decimal(raw["nanos"]) / Decimal(1000000000)
        require(amount / quantity == Decimal(tier["unit_price"]), "direct normalized price differs from source Money")
    agg = details["aggregation"]
    fields(agg, "aggregationLevel aggregationInterval aggregationCount", "direct aggregation")
    require(agg["aggregationLevel"] in ("ACCOUNT", "PROJECT", "AGGREGATION_LEVEL_UNSPECIFIED") and agg["aggregationInterval"] in ("MONTHLY", "DAILY", "AGGREGATION_INTERVAL_UNSPECIFIED") and agg["aggregationCount"] == 1,
            "invalid direct aggregation")


def validate_prices(data, prices):
    fields(prices, "schema_version input_id input_sha256 queried_at status candidates issues", "prices")
    require(prices["schema_version"] in ("1", "2", "3"), "prices: unsupported schema version")
    require(prices["input_id"] == data["input_id"] and prices["input_sha256"] == input_hash(data), "prices: input identity or hash mismatch")
    utc_time(prices["queried_at"], "queried_at")
    require(prices["status"] in ("complete", "partial"), "prices: invalid status")
    require(isinstance(prices["candidates"], list), "prices.candidates: expected array")
    by_id, errors = {}, []
    inputs = {candidate["candidate_id"]: candidate for candidate in data["candidates"]}
    for candidate in prices["candidates"]:
        fields(candidate, "candidate_id target region items", "price candidate")
        cid = candidate["candidate_id"]
        string(cid, "price candidate_id")
        require(cid in inputs and cid not in by_id, "prices: missing/duplicate/unexpected candidate")
        expected = inputs[cid]
        require(candidate["target"] == expected["target"] and candidate["region"] == expected["region"], "prices: candidate target or region mismatch")
        require(isinstance(candidate["items"], list), "prices.items: expected array")
        items = {item["item_id"]: item for item in expected["items"]}
        records = {}
        for record in candidate["items"]:
            fields(record, "item_id status price issue", "price item")
            iid = record["item_id"]
            string(iid, "price item_id")
            require(iid in items and iid not in records, "prices: missing/duplicate/unexpected item")
            if record["status"] == "available":
                require(record["issue"] is None, "available price cannot have failure issue")
                validate_price_record(record["price"], items[iid], prices["schema_version"], candidate["target"])
            else:
                require(record["status"] == "unavailable" and record["price"] is None, "invalid failed price item")
                error = record["issue"]
                fields(error, "candidate_id item_id code message retryable", "price issue")
                require(error["candidate_id"] == cid and error["item_id"] == iid and isinstance(error["code"], str) and error["code"] in ISSUE_CODES and type(error["retryable"]) is bool,
                        "prices: invalid issue identity or code")
                string(error["message"], "price issue.message")
                errors.append(error)
            records[iid] = record
        require(set(records) == set(items), "prices: item set differs from input")
        by_id[cid] = records
    require(set(by_id) == set(inputs), "prices: candidate set differs from input")
    require(prices["issues"] == errors and prices["status"] == ("partial" if errors else "complete"), "prices: status/issues disagree with item failures")
    return by_id


def tariff(value, tiers):
    result = Decimal(0)
    for tier in tiers:
        low, high = Decimal(tier["from"]), None if tier["to"] is None else Decimal(tier["to"])
        amount = max(Decimal(0), (value if high is None else min(value, high)) - low)
        result += amount * Decimal(tier["unit_price"])
    return result


def marginal(usage_range, prefix_range, tiers, baseline=Decimal(0)):
    if usage_range is None:
        return None
    def extrema(amount, minimum):
        low = baseline + prefix_range[0]
        high = baseline + prefix_range[1] if prefix_range[1] is not None else max(low, Decimal(tiers[-1]["from"]) + amount + 1)
        points = {low, high}
        for tier in tiers:
            boundary = Decimal(tier["from"])
            points.update(point for point in (boundary, boundary - amount) if low <= point <= high)
        values = [tariff(point + amount, tiers) - tariff(point, tiers) for point in points]
        return min(values) if minimum else max(values)
    return extrema(usage_range[0], True), None if usage_range[1] is None else extrema(usage_range[1], False)


def group_cost(entries):
    price = entries[0][1]
    require(all(entry[1] == price for entry in entries), "same SKU has inconsistent price records")
    require(len({entry[0]["cost_type"] for entry in entries}) == 1, "same SKU must use one cost classification")
    tiers = price["tiers"]
    baseline_values = {decimal_value(item["attributes"]["tier_baseline_usage"], "tier_baseline_usage") for item, _ in entries if "tier_baseline_usage" in item["attributes"]}
    require(len(baseline_values) <= 1, "same SKU has conflicting aggregation baselines")
    baseline = next(iter(baseline_values)) if baseline_values else Decimal(0)
    aggregation = (price.get("provider_details") or {}).get("aggregation") or {}
    if (price.get("provider_details") or {}).get("api") == "v2beta" and any(Decimal(tier["unit_price"]) == 0 for tier in tiers):
        if not all(item["attributes"].get("free_tier_policy") == "verified_catalog" for item, _ in entries) or not baseline_values:
            return None, None, False, False, "unverified_free_tier", "Catalog free tiers need explicit verified eligibility and account/project baseline"
    if len(tiers) > 1:
        if aggregation.get("aggregationInterval") == "DAILY" or aggregation.get("aggregationCount", 1) != 1:
            return None, None, False, False, "unsupported_aggregation", "Monthly usage cannot resolve daily or multi-period tiers"
        if aggregation.get("aggregationLevel") in ("ACCOUNT", "PROJECT") and not baseline_values:
            return None, None, False, False, "unknown_aggregation_baseline", "Account/project tier baseline must be supplied explicitly"
    totals = [scaled(item["monthly_usage"], item["quantity"]) for item, _ in entries]
    increments = [scaled(item["incremental_usage"], item["quantity"]) for item, _ in entries]
    full_total = all(value is not None and value[1] is not None for value in totals)
    full_increment = all(value is not None and value[1] is not None for value in increments)
    total = summed(totals)
    if total is not None:
        high = total[1] if full_total else None
        total_cost = (tariff(baseline + total[0], tiers) - tariff(baseline, tiers),
                      None if high is None else tariff(baseline + high, tiers) - tariff(baseline, tiers))
    else:
        total_cost = None
    increment = summed(increments)
    increment_cost = None
    if increment is not None and len(tiers) == 1:
        rate = Decimal(tiers[0]["unit_price"])
        increment_cost = (increment[0] * rate, increment[1] * rate if full_increment else None)
    if full_increment:
        if len(tiers) == 1:
            increment_cost = tuple(bound * Decimal(tiers[0]["unit_price"]) for bound in increment)
        elif full_total and total[0] == total[1]:
            end = tariff(baseline + total[0], tiers)
            increment_cost = (end - tariff(baseline + total[0] - increment[0], tiers), end - tariff(baseline + total[0] - increment[1], tiers))
        elif full_total and increment[0] == increment[1]:
            increment_cost = marginal(increment, (total[0] - increment[0], total[1] - increment[0]), tiers, baseline)
    if not full_increment and increment is not None and full_total and total[0] == total[1] and len(tiers) > 1:
        end = tariff(baseline + total[0], tiers)
        increment_cost = (end - tariff(baseline + total[0] - increment[0], tiers), None)
    return total_cost, increment_cost, full_total, full_increment and increment_cost is not None, None, None


def assess_input(data, assessment):
    if assessment is None:
        return {}
    fields(assessment, "schema_version input_id inventory_sha256 input_sha256 status candidates issues", "assessment")
    require(assessment["schema_version"] == "1" and assessment["input_id"] == data["input_id"] and assessment["input_sha256"] == input_hash(data),
            "assessment: identity or input hash mismatch")
    require(isinstance(assessment["candidates"], list), "assessment: candidates required")
    candidates = {}
    for candidate in assessment["candidates"]:
        fields(candidate, "candidate_id selected_values used_values shared_resources excluded_resources sizing operating_costs issues", "assessment candidate")
        cid = candidate["candidate_id"]
        string(cid, "assessment.candidate_id")
        require(cid not in candidates and isinstance(candidate["issues"], list), "assessment: duplicate candidate or invalid issues")
        for error in candidate["issues"]:
            fields(error, "candidate_id item_id code message retryable", "assessment issue")
            require(error["candidate_id"] == cid and type(error["retryable"]) is bool, "assessment: invalid issue")
            for key in ("code", "message"):
                string(error[key], "assessment issue." + key)
        candidates[cid] = candidate
    require(set(candidates) == {candidate["candidate_id"] for candidate in data["candidates"]}, "assessment: candidate set differs from input")
    errors = [error for candidate in assessment["candidates"] for error in candidate["issues"]]
    require(assessment["issues"] == errors and assessment["status"] == ("partial" if errors else "complete"), "assessment: inconsistent status or issues")
    return candidates


def judge_budget(data, total, increment, total_complete, increment_complete, blocked, target):
    basis = data["budget_basis"]
    output = dict(basis=basis, range_krw=data["monthly_budget"], status="unknown", reason="Cost or budget conditions are unresolved")
    budget, fx = data["monthly_budget"], data["fx"]
    if budget is None or budget["max"] is None:
        output["reason"] = "Budget upper bound is unknown; it is not unlimited"
        return output
    if fx is None:
        output["reason"] = "USD estimate is available where calculated; explicit exchange rate is required for KRW comparison"
        return output
    selected, complete = (total, total_complete) if basis == "total" else (increment, increment_complete)
    if selected is None:
        return output
    rate, ceiling = Decimal(fx["usd_to_krw"]), Decimal(budget["max"])
    low, high = selected[0] * rate, None if selected[1] is None else selected[1] * rate
    if low > ceiling:
        output.update(status="over", reason="Known cost lower bound already exceeds the budget upper bound")
    elif target == "onprem":
        output["reason"] = "Onprem cloud cost excludes separately recorded power, hardware and labor; total operating budget is not confirmed"
    elif not complete or blocked or high is None:
        output["reason"] = "Missing cost, usage, or mapping conditions prevent confirming budget compliance"
    elif high > ceiling:
        output.update(status="may_exceed", reason="Complete estimated range crosses the budget upper bound")
    else:
        output.update(status="within", reason="Complete cost upper bound is within the budget upper bound")
    return output


def calculate(data, prices, assessment=None):
    with localcontext() as context:
        context.prec = 80
        return _calculate(data, prices, assessment)


def _calculate(data, prices, assessment):
    validate_input(data)
    records = validate_prices(data, prices)
    audited = assess_input(data, assessment)
    result = dict(schema_version="3", input_id=data["input_id"], input_sha256=input_hash(data), prices_sha256=input_hash(prices),
                  generated_at=timestamp(), queried_at=prices["queried_at"], status="complete", candidates=[], issues=[])
    for candidate in data["candidates"]:
        cid = candidate["candidate_id"]
        output = {key: copy.deepcopy(candidate[key]) for key in ("candidate_id", "target", "region", "configuration_status", "assumptions")}
        output["items"] = []
        groups, item_outputs = defaultdict(list), {}
        errors = []
        total_complete = increment_complete = True
        for item in candidate["items"]:
            iid, record = item["item_id"], records[cid][item["item_id"]]
            cost = dict(item_id=iid, cost_type=item["cost_type"], status="complete", total_usd=None, incremental_usd=None, issues=[])
            output["items"].append(cost); item_outputs[iid] = cost
            if record["status"] == "unavailable":
                cost["status"] = "partial"; cost["issues"].append(copy.deepcopy(record["issue"]))
                total_complete = increment_complete = False
            else:
                p = record["price"]
                groups[(p["provider_service"], p["sku"], p["unit"])].append((item, p))
        group_totals, group_increments = [], []
        fixed, variable = [], []
        for entries in groups.values():
            total, increment, complete, inc_complete, code, message = group_cost(entries)
            total_complete &= complete; increment_complete &= inc_complete
            group_totals.append(total); group_increments.append(increment)
            (fixed if entries[0][0]["cost_type"] == "fixed" else variable).append(total)
            prefix = (Decimal(0), Decimal(0))
            exact_total = sum(scaled(item["monthly_usage"], item["quantity"])[0] for item, _ in entries) if complete else None
            exact_total = exact_total if complete and all(Decimal(item["monthly_usage"]["min"]) == Decimal(item["monthly_usage"]["max"]) for item, _ in entries) else None
            removed = (Decimal(0), Decimal(0))
            baseline_values = [item["attributes"]["tier_baseline_usage"] for item, _ in entries if "tier_baseline_usage" in item["attributes"]]
            baseline = Decimal(baseline_values[0]) if baseline_values else Decimal(0)
            for item, p in entries:
                cost = item_outputs[item["item_id"]]
                def problem(error_code, error_message):
                    cost["issues"].append(issue(cid, item["item_id"], error_code, error_message))
                total_usage = scaled(item["monthly_usage"], item["quantity"])
                additional = scaled(item["incremental_usage"], item["quantity"])
                if code:
                    problem(code, message)
                else:
                    cost["total_usd"] = rendered(marginal(total_usage, prefix, p["tiers"], baseline))
                    if total_usage is None or total_usage[1] is None:
                        problem("unknown_usage", "Monthly usage is unknown or unbounded")
                    if additional is not None and len(p["tiers"]) == 1:
                        rate = Decimal(p["tiers"][0]["unit_price"])
                        cost["incremental_usd"] = rendered((additional[0] * rate, None if additional[1] is None else additional[1] * rate))
                    elif additional is not None and additional[1] is not None and exact_total is not None and removed[1] is not None:
                        low = marginal((additional[0], additional[0]), (exact_total - removed[1] - additional[0], exact_total - removed[0] - additional[0]), p["tiers"], baseline)[0]
                        high = marginal((additional[1], additional[1]), (exact_total - removed[1] - additional[1], exact_total - removed[0] - additional[1]), p["tiers"], baseline)[1]
                        cost["incremental_usd"] = rendered((low, high))
                    elif len(entries) == 1 and increment is not None:
                        cost["incremental_usd"] = rendered(increment)
                    if cost["incremental_usd"] is None or cost["incremental_usd"]["max"] is None:
                        problem("unknown_incremental_usage", "Incremental usage or correlation with total usage is unresolved")
                prefix = (prefix[0] + (total_usage[0] if total_usage else 0),
                          None if prefix[1] is None or total_usage is None or total_usage[1] is None else prefix[1] + total_usage[1])
                removed = (removed[0] + (additional[0] if additional else 0),
                           None if removed[1] is None or additional is None or additional[1] is None else removed[1] + additional[1])
                if cost["issues"]:cost["status"] = "partial"
        for cost in output["items"]:errors.extend(cost["issues"])
        # Empty onprem cloud inventory is an explicit zero-cloud-fee scenario.
        total = summed(group_totals, empty_zero=not candidate["items"])
        increment = summed(group_increments, empty_zero=not candidate["items"])
        fx = Decimal(data["fx"]["usd_to_krw"]) if data["fx"] else None
        to_krw = lambda amount, complete: rendered((amount[0] * fx, amount[1] * fx)) if amount is not None and complete and fx is not None else None
        output["summary"] = dict(fixed_usd=rendered(summed(fixed, empty_zero=not any(item["cost_type"] == "fixed" for item in candidate["items"]))),
                                 variable_usd=rendered(summed(variable, empty_zero=not any(item["cost_type"] == "variable" for item in candidate["items"]))),
                                 known_total_usd=rendered(total), known_incremental_usd=rendered(increment), total_complete=total_complete,
                                 incremental_complete=increment_complete, total_krw=to_krw(total,total_complete), incremental_krw=to_krw(increment,increment_complete))
        audit_errors = copy.deepcopy(audited[cid]["issues"]) if cid in audited else []
        if assessment is not None:
            output["assumptions"].append("Resource assessment SHA-256: " + input_hash(assessment))
        blocked = any(error["code"] != "unknown_incremental_usage" or data["budget_basis"] == "incremental" for error in audit_errors)
        errors.extend(audit_errors)
        output["assumptions"].append("Monthly-hours scenario: " + data["monthly_hours"] + "; resource usage is explicit. Public pre-tax prices exclude credits and negotiated discounts.")
        output["assumptions"].append("SKU usage is pooled once; item costs use input-order marginal attribution. Item range extrema need not sum to aggregate range extrema.")
        if data["fx"]:
            output["assumptions"].append("KRW conversion: " + data["fx"]["usd_to_krw"] + " KRW/USD as of " + data["fx"]["as_of"] + "; " + data["fx"]["source"])
        output["budget"] = judge_budget(data,total,increment,total_complete,increment_complete,blocked,candidate["target"])
        if errors or not total_complete or not increment_complete:result["status"]="partial"
        result["issues"].extend(errors); result["candidates"].append(output)
    return result


def validate_cost_snapshot(value):
    fields(value, "schema_version input_id input_sha256 prices_sha256 generated_at queried_at status candidates issues", "cost snapshot")
    require(value["schema_version"] in ("1", "2", "3") and value["status"] in ("complete", "partial"), "cost snapshot: unsupported version or status")
    utc_time(value["generated_at"], "generated_at"); utc_time(value["queried_at"], "queried_at")
    require(isinstance(value["candidates"], list) and value["candidates"], "cost snapshot: candidates required")
    result = {}
    for candidate in value["candidates"]:
        fields(candidate, "candidate_id target region configuration_status assumptions items summary budget", "cost snapshot candidate")
        cid = candidate["candidate_id"]; string(cid, "cost candidate_id")
        require(cid not in result, "cost snapshot: duplicate candidate")
        summary, budget = candidate["summary"], candidate["budget"]
        fields(summary, "fixed_usd variable_usd known_total_usd known_incremental_usd total_complete incremental_complete total_krw incremental_krw", "cost summary")
        fields(budget, "basis range_krw status reason", "cost budget")
        require(budget["basis"] in ("total", "incremental"), "cost snapshot: invalid comparison basis")
        for key in ("total_complete", "incremental_complete"):
            require(type(summary[key]) is bool, "cost summary: boolean completeness required")
        for key in ("known_total_usd", "known_incremental_usd"):
            bounds = usage(summary[key], "cost summary." + key)
            flag = "total_complete" if key == "known_total_usd" else "incremental_complete"
            require(not summary[flag] or (bounds is not None and bounds[1] is not None), "cost snapshot: completeness contradicts cost bounds")
        result[cid] = candidate
    return result


def compare_costs(baseline, alternative):
    with localcontext() as context:
        context.prec = 80
        before, after = validate_cost_snapshot(baseline), validate_cost_snapshot(alternative)
        require(set(before) == set(after), "comparison: candidate sets must match")
        result = dict(schema_version="1", baseline_sha256=input_hash(baseline), alternative_sha256=input_hash(alternative),
                      generated_at=timestamp(), status="complete", candidates=[], issues=[])
        for cid, initial in before.items():
            changed = after[cid]
            basis = initial["budget"]["basis"]
            require(basis == changed["budget"]["basis"], "comparison: budget bases must match")
            key, flag = ("known_total_usd", "total_complete") if basis == "total" else ("known_incremental_usd", "incremental_complete")
            low = usage(initial["summary"][key], "baseline cost")
            high = usage(changed["summary"][key], "alternative cost")
            ready = initial["summary"][flag] and changed["summary"][flag] and low is not None and high is not None and low[1] is not None and high[1] is not None
            row = dict(candidate_id=cid, basis=basis, currency="USD", status="complete" if ready else "partial",
                       monthly_savings=None, reason="Difference of resource quotes only; unpriced operating costs and KRW exchange-rate differences are excluded")
            if ready:
                row["monthly_savings"] = rendered((low[0] - high[1], low[1] - high[0]))
            else:
                result["status"] = "partial"
                result["issues"].append(issue(cid, None, "unknown_savings", "A complete baseline and alternative quote are required; no assumed saving percentage is used"))
            result["candidates"].append(row)
        return result
