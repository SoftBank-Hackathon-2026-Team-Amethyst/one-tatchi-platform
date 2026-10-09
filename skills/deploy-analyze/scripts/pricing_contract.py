"""Validation and serialization shared by price lookup and future calculation."""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

UNITS = {"hour", "gb_month", "gib_month", "gb", "gib", "request", "vcpu_hour", "gib_hour", "lcu_hour", "secret_month", "metric_month", "sample"}
GCP_DIRECT_UNITS = {"hour":"h", "vcpu_hour":"h", "gib_hour":"GiBy.h", "gib_month":"GiBy.mo", "gb_month":"GBy.mo", "gib":"GiBy", "gb":"GBy", "request":"count", "sample":"count", "secret_month":"mo"}
DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
BUDGETS = {(0, 100000), (100001, 500000), (500001, 1000000), (1000001, None)}


class InputError(ValueError):
    """Invalid input without echoing potentially sensitive values."""


def require(condition, message):
    if not condition:
        raise InputError(message)


def fields(value, names, path):
    require(isinstance(value, dict), f"{path}: expected object")
    require(set(value) == set(names.split()), f"{path}: missing or unknown fields")


def string(value, path):
    require(isinstance(value, str) and bool(value.strip()), f"{path}: expected nonempty string")


def decimal_value(value, path, positive=False):
    require(isinstance(value, str) and DECIMAL.fullmatch(value) is not None, f"{path}: expected decimal string")
    result = Decimal(value)
    require(not positive or result > 0, f"{path}: expected positive value")
    return result


def utc_time(value, path):
    string(value, path)
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", value) is not None,
            f"{path}: expected UTC RFC 3339 timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise InputError(f"{path}: invalid timestamp") from None


def usage(value, path):
    if value is None:
        return None
    fields(value, "min max", path)
    low = decimal_value(value["min"], path + ".min")
    high = None if value["max"] is None else decimal_value(value["max"], path + ".max")
    require(high is None or low <= high, f"{path}: inverted range")
    return low, high


def validate_input(data):
    fields(data, "schema_version input_id created_at template_version monthly_hours monthly_budget budget_basis fx candidates", "input")
    require(data["schema_version"] in ("1", "2", "3"), "schema_version: unsupported version")
    string(data["input_id"], "input_id")
    utc_time(data["created_at"], "created_at")
    require(isinstance(data["template_version"], str) and re.fullmatch(r"v\d+\.\d+\.\d+", data["template_version"]) is not None,
            "template_version: expected vX.Y.Z")
    hours = decimal_value(data["monthly_hours"], "monthly_hours", positive=True)
    require(data["budget_basis"] in ("total", "incremental"), "budget_basis: unsupported value")
    budget = data["monthly_budget"]
    if budget is not None:
        fields(budget, "min max currency", "monthly_budget")
        require(type(budget["min"]) is int and (budget["max"] is None or type(budget["max"]) is int),
                "monthly_budget: expected integer bounds")
        require(budget["currency"] == "KRW" and (budget["min"], budget["max"]) in BUDGETS,
                "monthly_budget: expected T15 KRW range")
    fx = data["fx"]
    if fx is not None:
        fields(fx, "usd_to_krw as_of source", "fx")
        decimal_value(fx["usd_to_krw"], "fx.usd_to_krw", positive=True)
        string(fx["source"], "fx.source")
        require(isinstance(fx["as_of"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", fx["as_of"]) is not None,
                "fx.as_of: expected date")
        try:
            date.fromisoformat(fx["as_of"])
        except ValueError:
            raise InputError("fx.as_of: invalid date") from None
    require(isinstance(data["candidates"], list) and bool(data["candidates"]), "candidates: expected nonempty array")
    candidate_ids = set()
    for ci, candidate in enumerate(data["candidates"]):
        path = f"candidates[{ci}]"
        fields(candidate, "candidate_id target region configuration_status assumptions items", path)
        string(candidate["candidate_id"], path + ".candidate_id")
        require(candidate["candidate_id"] not in candidate_ids, path + ": duplicate candidate_id")
        candidate_ids.add(candidate["candidate_id"])
        require(candidate["target"] in ("aws", "gcp", "onprem"), path + ".target: aws | gcp | onprem only")
        if candidate["target"] == "onprem":
            require(candidate["region"] is None, path + ".region: onprem requires null")
        else:
            string(candidate["region"], path + ".region")
        require(candidate["configuration_status"] in ("confirmed", "assumed"), path + ": invalid configuration_status")
        require(isinstance(candidate["assumptions"], list), path + ".assumptions: expected array")
        for assumption in candidate["assumptions"]:
            string(assumption, path + ".assumptions")
        require(candidate["configuration_status"] != "assumed" or bool(candidate["assumptions"]), path + ": assumed configuration needs explanation")
        require(data["budget_basis"] != "incremental" or bool(candidate["assumptions"]), path + ": incremental budget needs explanation")
        require(isinstance(candidate["items"], list), path + ".items: expected array")
        require(bool(candidate["items"]) or (candidate["target"] == "onprem" and bool(candidate["assumptions"])),
                path + ": empty items require onprem operating-cost explanation")
        item_ids, resources = set(), set()
        for ii, item in enumerate(candidate["items"]):
            ip = f"{path}.items[{ii}]"
            fields(item, "item_id resource_id resource_kind billing_dimension attributes quantity shared cost_type unit monthly_usage incremental_usage source", ip)
            for name in ("item_id", "resource_id", "resource_kind", "billing_dimension"):
                string(item[name], ip + "." + name)
            require(item["item_id"] not in item_ids, ip + ": duplicate item_id")
            item_ids.add(item["item_id"])
            identity = (item["resource_id"], item["billing_dimension"])
            require(identity not in resources, ip + ": duplicate resource billing dimension")
            resources.add(identity)
            require(type(item["quantity"]) is int and item["quantity"] > 0, ip + ": quantity must be positive integer")
            require(type(item["shared"]) is bool, ip + ": shared must be boolean")
            require(item["cost_type"] in ("fixed", "variable"), ip + ": invalid cost_type")
            require(isinstance(item["unit"], str) and item["unit"] in UNITS, ip + ": unsupported unit")
            require(isinstance(item["attributes"], dict), ip + ": attributes must be object")
            for key, value in item["attributes"].items():
                string(key, ip + ".attributes key")
                string(value, ip + ".attributes value")
            total = usage(item["monthly_usage"], ip + ".monthly_usage")
            increment = usage(item["incremental_usage"], ip + ".incremental_usage")
            if total is not None and increment is not None:
                require(increment[0] <= total[0], ip + ": incremental minimum exceeds total minimum")
                if total[1] is not None and increment[1] is not None:
                    require(increment[1] <= total[1], ip + ": incremental maximum exceeds total maximum")
            if item["cost_type"] == "fixed" and item["unit"] == "hour" and total is not None:
                require(total == (hours, hours), ip + ": fixed hourly usage must equal monthly_hours")
            fields(item["source"], "path ref note", ip + ".source")
            for key in ("path", "note"):
                string(item["source"][key], ip + ".source." + key)
            if item["source"]["ref"] is not None:
                string(item["source"]["ref"], ip + ".source.ref")
    return data


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "JSON: duplicate key")
        result[key] = value
    return result


def load_input(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text, object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError("JSON: nonfinite number")))
    except (json.JSONDecodeError, UnicodeError):
        raise InputError("input: invalid UTF-8 JSON") from None
    return validate_input(data)


def input_hash(data):
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def issue(candidate_id, item_id, code, message, retryable=False):
    return dict(candidate_id=candidate_id, item_id=item_id, code=code, message=message, retryable=retryable)
