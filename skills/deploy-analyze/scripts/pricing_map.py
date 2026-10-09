"""Resolve an explicit resource inventory into the pricing input; never run HCL."""

import copy
import json
from decimal import Decimal
from pathlib import Path

from pricing_contract import (
    InputError, decimal_value, fields, input_hash, issue, require, string,
    unique_object, usage, validate_input,
)

HEADERS = "schema_version input_id created_at template_version monthly_hours monthly_budget budget_basis fx"
TIERS = ("root", "module_default", "assumption")
REQUIRED_KINDS = {
    "aws": {"eks", "ec2", "ebs", "nat", "alb", "rds", "ecr", "logs", "internet_egress"},
    "gcp": {"gke", "gke_node", "gcp_disk", "cloud_nat", "gcp_load_balancer", "cloud_sql", "artifact_registry", "gcp_logs", "gcp_internet_egress"},
    "onprem": set(),
}
DIMENSIONS = {
    "eks": {"cluster_hours"}, "ec2": {"instance_hours"}, "ebs": {"storage"},
    "nat": {"gateway_hours", "processed_data"}, "alb": {"load_balancer_hours", "lcu_hours"},
    "rds": {"instance_hours", "storage"}, "ecr": {"storage"}, "logs": {"ingestion", "storage"},
    "internet_egress": {"transfer"}, "gke": {"cluster_hours"},
    "gke_node": {"cpu_hours", "memory_hours"}, "gcp_disk": {"storage"},
    "cloud_nat": {"gateway_hours", "processed_data"},
    "gcp_load_balancer": {"load_balancer_hours", "processed_data"},
    "cloud_sql": {"storage"}, "artifact_registry": {"storage"},
    "gcp_logs": {"ingestion", "storage"}, "gcp_internet_egress": {"transfer"},
}


def source(value, path, pinned=False, template=None):
    fields(value, "path ref note", path)
    string(value["path"], path + ".path")
    string(value["note"], path + ".note")
    if value["ref"] is not None:
        string(value["ref"], path + ".ref")
    require(not pinned or value["ref"] is not None, path + ": configuration source needs a ref")
    require(template is None or value["ref"] == template, path + ": module default must use the referenced template tag")


def resolve_values(values, template):
    require(isinstance(values, dict), "values: expected object")
    selected = {}
    for key, choices in values.items():
        string(key, "value name")
        require(isinstance(choices, dict) and choices and set(choices) <= set(TIERS), "values: expected root/module_default/assumption choices")
        for tier, entry in choices.items():
            fields(entry, "value source", "value choice")
            source(entry["source"], "value source", pinned=tier != "assumption",
                   template=template if tier == "module_default" else None)
        tier = next(tier for tier in TIERS if tier in choices)
        selected[key] = dict(tier=tier, **copy.deepcopy(choices[tier]))
    return selected


def bind(value, selected, used):
    if isinstance(value, dict):
        if "value_from" in value:
            require(set(value) in ({"value_from"}, {"value_from", "member"}), "binding: unknown fields")
            name = value["value_from"]
            string(name, "binding.value_from")
            require(name in selected, "binding: referenced value is missing")
            used.add(name)
            result = copy.deepcopy(selected[name]["value"])
            if "member" in value:
                member = value["member"]
                if isinstance(result, dict):
                    require(isinstance(member, str) and member in result, "binding: object member is missing")
                elif isinstance(result, list):
                    require(type(member) is int and 0 <= member < len(result), "binding: array member is missing")
                else:
                    raise InputError("binding: member requires object or array")
                result = copy.deepcopy(result[member])
            return result
        return {key: bind(item, selected, used) for key, item in value.items()}
    if isinstance(value, list):
        return [bind(item, selected, used) for item in value]
    return copy.deepcopy(value)


def traffic_demand(traffic):
    if traffic is None:
        return None
    fields(traffic, "scenario source workloads", "traffic")
    require(traffic["scenario"] in ("final", "default"), "traffic: invalid scenario")
    source(traffic["source"], "traffic.source")
    require(isinstance(traffic["workloads"], list) and traffic["workloads"], "traffic.workloads: expected nonempty array")
    demand = dict(cpu_millicores=0, memory_mib=Decimal(0), pod_slots=0)
    identities = set()
    for workload in traffic["workloads"]:
        fields(workload, "name replicas environments blue_green_multiplier cpu_millicores memory_mib", "workload")
        string(workload["name"], "workload.name")
        require(isinstance(workload["environments"], list) and workload["environments"], "workload: environments required")
        for env in workload["environments"]:
            string(env, "workload.environment")
            identity = (workload["name"], env)
            require(identity not in identities, "workload: duplicate service environment")
            identities.add(identity)
        for key in ("replicas", "blue_green_multiplier"):
            require(type(workload[key]) is int and workload[key] > 0, "workload: positive integer count required")
        require(type(workload["cpu_millicores"]) is int and workload["cpu_millicores"] >= 0, "workload: invalid CPU request")
        memory = decimal_value(workload["memory_mib"], "workload.memory_mib")
        copies = workload["replicas"] * workload["blue_green_multiplier"] * len(workload["environments"])
        demand["cpu_millicores"] += workload["cpu_millicores"] * copies
        demand["memory_mib"] += memory * copies
        demand["pod_slots"] += copies
    return demand


def capacity_available(capacity):
    if capacity is None:
        return None
    fields(capacity, "node_count per_node reserved source", "capacity")
    source(capacity["source"], "capacity.source")
    count = capacity["node_count"]
    require(type(count) is int and count > 0, "capacity: positive integer node_count required")
    for value in (capacity["per_node"], capacity["reserved"]):
        fields(value, "cpu_millicores memory_mib pod_slots", "capacity bounds")
        for key in ("cpu_millicores", "pod_slots"):
            require(type(value[key]) is int and value[key] >= 0, "capacity: invalid integer bounds")
        decimal_value(value["memory_mib"], "capacity.memory_mib")
    available = {}
    for key in ("cpu_millicores", "memory_mib", "pod_slots"):
        node = Decimal(str(capacity["per_node"][key]))
        reserve = Decimal(str(capacity["reserved"][key]))
        remaining = node * count - reserve
        require(remaining >= 0, "capacity: reserved resources exceed cluster capacity")
        available[key] = remaining
    return available


def capacity_assessment(traffic, capacity):
    demand, available = traffic_demand(traffic), capacity_available(capacity)
    if demand is None or available is None:
        return dict(check="unknown", node_expansion="review_required", demand=None, available=None,
                    reason="Traffic or supplied cluster capacity is unknown; node quantity is not changed automatically")
    fits = all(demand[key] <= available[key] for key in demand)
    def rendered(values):
        return {key: format(Decimal(value), "f") for key, value in values.items()}
    return dict(check="within_supplied_bounds" if fits else "exceeds_supplied_bounds",
                node_expansion="not_indicated" if fits else "review_required",
                demand=rendered(demand), available=rendered(available),
                reason="Aggregate requests only; placement, affinity, live allocatable capacity and other workloads require separate verification",
                source=capacity["source"], traffic_scenario=traffic["scenario"])


def map_inventory(inventory):
    fields(inventory, HEADERS + " candidates", "inventory")
    require(inventory["schema_version"] == "1", "inventory: unsupported schema version")
    require(isinstance(inventory["candidates"], list) and inventory["candidates"], "inventory.candidates: expected nonempty array")
    pricing = {key: copy.deepcopy(inventory[key]) for key in HEADERS.split()}
    pricing.update(schema_version="2", candidates=[])
    assessment = dict(schema_version="1", input_id=inventory["input_id"], inventory_sha256=input_hash(inventory),
                      input_sha256=None, status="complete", candidates=[], issues=[])
    for candidate in inventory["candidates"]:
        fields(candidate, "candidate_id target region configuration_status assumptions values resources excluded_resources traffic capacity operating_costs", "inventory candidate")
        selected = resolve_values(candidate["values"], inventory["template_version"])
        used = set()
        output = {key: copy.deepcopy(candidate[key]) for key in ("candidate_id", "target", "region", "configuration_status", "assumptions")}
        require(isinstance(output["assumptions"], list), "candidate.assumptions: expected array")
        output["items"] = []
        missing = []
        resources = candidate["resources"]
        require(isinstance(resources, list), "resources: expected array")
        physical_ids = set()
        shared = []
        for resource in resources:
            fields(resource, "resource_id resource_kind shared environments items", "resource")
            string(resource["resource_id"], "resource.resource_id")
            string(resource["resource_kind"], "resource.resource_kind")
            require(resource["resource_id"] not in physical_ids, "resources: duplicate physical resource_id")
            physical_ids.add(resource["resource_id"])
            require(type(resource["shared"]) is bool, "resource.shared: boolean required")
            envs = resource["environments"]
            require(isinstance(envs, list) and envs, "resource.environments: expected nonempty array")
            for env in envs:
                string(env, "resource.environment")
            require(len(set(envs)) == len(envs), "resource: duplicate environment")
            require(len(envs) == 1 or resource["shared"], "resource: multiple environments require shared=true")
            require(isinstance(resource["items"], list) and resource["items"], "resource: cost dimensions are required")
            dimensions = set()
            for item in resource["items"]:
                fields(item, "item_id billing_dimension attributes quantity unit cost_type monthly_usage incremental_usage source", "resource item")
                mapped = bind(item, selected, used)
                string(mapped["billing_dimension"], "billing_dimension")
                mapped.update(resource_id=resource["resource_id"], resource_kind=resource["resource_kind"], shared=resource["shared"])
                dimensions.add(mapped["billing_dimension"])
                output["items"].append(mapped)
            required = DIMENSIONS.get(resource["resource_kind"], set())
            require(required <= dimensions, "resource: a required billing dimension is missing")
            if resource["resource_kind"] == "cloud_sql":
                require("instance_hours" in dimensions or {"cpu_hours", "memory_hours"} <= dimensions,
                        "cloud_sql: require instance hours or both CPU and memory hours")
            if resource["shared"]:
                shared.append(dict(resource_id=resource["resource_id"], environments=envs, counted_once=True))
        excluded = candidate["excluded_resources"]
        require(isinstance(excluded, dict), "excluded_resources: expected object")
        kinds = {resource["resource_kind"] for resource in resources}
        require(isinstance(candidate["target"], str) and candidate["target"] in REQUIRED_KINDS, "inventory: unsupported target")
        for kind, explanation in excluded.items():
            string(kind, "excluded resource kind")
            source(explanation, "excluded resource source", pinned=True)
            require(kind not in kinds, "resource kind cannot be both included and excluded")
            output["assumptions"].append("Excluded resource " + kind + ": " + explanation["note"])
        require(REQUIRED_KINDS[candidate["target"]] <= kinds | set(excluded), "inventory: required resource kind is missing without explanation")
        require(candidate["target"] != "onprem" or not resources, "onprem: cloud resources are not part of this mapping")
        traffic = bind(candidate["traffic"], selected, used)
        capacity = bind(candidate["capacity"], selected, used)
        sizing = capacity_assessment(traffic, capacity)
        if capacity is not None:
            nodes = [item["quantity"] for item in output["items"] if
                     (item["resource_kind"], item["billing_dimension"]) in {( "ec2", "instance_hours"), ("gke_node", "cpu_hours")}]
            if nodes:
                require(all(type(count) is int and count > 0 for count in nodes) and sum(nodes) == capacity["node_count"],
                        "capacity node_count must match the quoted node quantity")
        if sizing["node_expansion"] == "review_required":
            missing.append(issue(output["candidate_id"], None, "unknown_capacity", sizing["reason"]))
        if traffic is None or traffic["scenario"] == "default":
            output["assumptions"].append("Traffic recommendation is missing or uses a default scenario; recalculate after final sizing")
            output["configuration_status"] = "assumed"
        costs = candidate["operating_costs"]
        require(isinstance(costs, dict), "operating_costs: expected object")
        if candidate["target"] == "onprem":
            require(set(costs) == {"power", "hardware", "labor"}, "onprem: power, hardware and labor must be distinguished")
            output["assumptions"].append("Existing onprem hardware has no cloud charge; power, hardware and labor are separate operating costs")
        else:
            require(not costs, "cloud candidates: onprem operating costs must be empty")
        for name, cost in costs.items():
            fields(cost, "monthly_krw source", "operating cost")
            usage(cost["monthly_krw"], "operating cost monthly_krw")
            source(cost["source"], "operating cost source")
            if cost["monthly_krw"] is None or cost["monthly_krw"]["max"] is None:
                missing.append(issue(output["candidate_id"], None, "unknown_operating_cost", "Onprem " + name + " operating cost is not estimated"))
        for key in sorted(used):
            if selected[key]["tier"] == "assumption":
                output["configuration_status"] = "assumed"
                output["assumptions"].append("Assumed input " + key + ": " + selected[key]["source"]["note"])
        validate_input(dict(pricing, candidates=[output]))
        # Keep an unconfirmed price selector as a visible item, never omit it.
        from pricing_aws import PROFILES as AWS_PROFILES, ALIASES as AWS_ATTRIBUTES
        from pricing_gcp import PROFILES as GCP_PROFILES, ATTRIBUTES as GCP_ATTRIBUTES
        for item in output["items"]:
            if item["monthly_usage"] is None or item["monthly_usage"]["max"] is None:
                missing.append(issue(output["candidate_id"], item["item_id"], "unknown_usage", "Monthly usage is unknown or unbounded"))
            if item["incremental_usage"] is None or item["incremental_usage"]["max"] is None:
                missing.append(issue(output["candidate_id"], item["item_id"], "unknown_incremental_usage", "App addition usage is unknown or unbounded"))
            profile = (item["resource_kind"], item["billing_dimension"])
            attrs = item["attributes"]
            if output["target"] == "aws":
                definition = AWS_PROFILES.get(profile)
                ready = definition is not None and all(key in attrs for key in definition[1]) and set(attrs) <= set(AWS_ATTRIBUTES) | {"rate_code"}
            elif output["target"] == "gcp":
                ready = profile in GCP_PROFILES and all(key in attrs for key in ("resource_family", "resource_group")) and any(key in attrs for key in ("description", "sku_id")) and set(attrs) <= GCP_ATTRIBUTES and attrs.get("usage_type", "OnDemand") == "OnDemand"
            else:
                ready = False
            if not ready:
                missing.append(issue(output["candidate_id"], item["item_id"], "unconfirmed_catalog", "Catalog selector is unconfirmed or unsupported; resolve before a complete quote"))
        pricing["candidates"].append(output)
        assessment["candidates"].append(dict(candidate_id=output["candidate_id"], selected_values=selected, used_values=sorted(used),
                                             shared_resources=shared, excluded_resources=excluded, sizing=sizing, operating_costs=costs, issues=missing))
        assessment["issues"].extend(missing)
    validate_input(pricing)
    assessment["input_sha256"] = input_hash(pricing)
    if assessment["issues"]:
        assessment["status"] = "partial"
    return pricing, assessment


def load_inventory(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError("inventory JSON: nonfinite number")))
    except (json.JSONDecodeError, UnicodeError):
        raise InputError("inventory: invalid UTF-8 JSON") from None
