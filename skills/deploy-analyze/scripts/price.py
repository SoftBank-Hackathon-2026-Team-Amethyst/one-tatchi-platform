#!/usr/bin/env python3
"""Single entry point for resource mapping, price lookup and offline costing."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from pricing_contract import InputError, input_hash, issue, load_input, timestamp


class Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's raw message can contain user-supplied values.
        raise InputError("CLI: missing or invalid arguments")


def output_path(input_path, destination):
    destination = Path(os.path.abspath(destination))
    if destination.resolve() == Path(input_path).resolve():
        raise InputError("output: must differ from input")
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise InputError("output: symbolic links are not supported")
    if destination.exists() and not destination.is_file():
        raise OSError("output is not a regular file")
    if not destination.parent.is_dir():
        raise OSError("output parent does not exist")
    return destination


def write_text(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pricing-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_result(path, result):
    write_text(path, json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def lookup(data, provider=None, gcp_provider=None):
    from pricing_aws import AWSPrices
    from pricing_gcp import GCPPrices
    from pricing_errors import LookupError

    provider = provider or AWSPrices()
    gcp_provider = gcp_provider or GCPPrices()
    result = {"schema_version": "2", "input_id": data["input_id"], "input_sha256": input_hash(data),
              "queried_at": timestamp(), "status": "complete", "candidates": [], "issues": []}
    for candidate in data["candidates"]:
        output = {key: candidate[key] for key in ("candidate_id", "target", "region")}
        output["items"] = []
        for item in candidate["items"]:
            try:
                if candidate["target"] == "aws":
                    price = provider.lookup(candidate, item)
                elif candidate["target"] == "gcp":
                    price = gcp_provider.lookup(candidate, item)
                else:
                    raise LookupError("unsupported_resource", "Onprem operating costs do not have a cloud catalog price")
                output["items"].append(dict(item_id=item["item_id"], status="available", price=price, issue=None))
            except LookupError as exc:
                error = issue(candidate["candidate_id"], item["item_id"], exc.code, exc.message, exc.retryable)
                output["items"].append(dict(item_id=item["item_id"], status="unavailable", price=None, issue=error))
                result["issues"].append(error)
        result["candidates"].append(output)
    if result["issues"]:
        result["status"] = "partial"
    return result


def main(argv=None):
    try:
        parser = Parser(description="Map resources, look up prices, calculate, compare and report monthly costs")
        commands = parser.add_subparsers(dest="command", required=True)
        validate = commands.add_parser("validate")
        validate.add_argument("--input", required=True)
        query = commands.add_parser("lookup")
        query.add_argument("--input", required=True)
        query.add_argument("--output", required=True)
        mapping = commands.add_parser("map")
        mapping.add_argument("--inventory", required=True)
        mapping.add_argument("--output", required=True)
        mapping.add_argument("--assessment", required=True)
        calculation = commands.add_parser("calculate")
        calculation.add_argument("--input", required=True)
        calculation.add_argument("--prices", required=True)
        calculation.add_argument("--output", required=True)
        calculation.add_argument("--assessment")
        comparison = commands.add_parser("compare")
        comparison.add_argument("--baseline", required=True)
        comparison.add_argument("--alternative", required=True)
        comparison.add_argument("--output", required=True)
        reporting = commands.add_parser("report")
        reporting.add_argument("--input", required=True)
        reporting.add_argument("--prices", required=True)
        reporting.add_argument("--costs", required=True)
        reporting.add_argument("--candidate", required=True)
        reporting.add_argument("--budget-output", required=True)
        reporting.add_argument("--summary-output", required=True)
        reporting.add_argument("--assessment")
        reporting.add_argument("--savings")
        reporting.add_argument("--alternative-costs")
        reporting.add_argument("--report")
        args = parser.parse_args(argv)
        if args.command == "map":
            from pricing_map import load_inventory, map_inventory
            path = output_path(args.inventory, args.output)
            audit_path = output_path(args.inventory, args.assessment)
            if path == audit_path:
                raise InputError("map: output and assessment must differ")
            mapped, assessment = map_inventory(load_inventory(args.inventory))
            write_result(path, mapped)
            write_result(audit_path, assessment)
            print(json.dumps(dict(status=assessment["status"], output=str(path), issues=assessment["issues"]), ensure_ascii=False))
            return 3 if assessment["status"] == "partial" else 0
        if args.command == "report":
            if bool(args.savings) != bool(args.alternative_costs):
                raise InputError("report: savings and alternative costs must be provided together")
            from pricing_calculate import load_document
            from pricing_report import render_reports, update_report
            data = load_input(args.input)
            prices, costs = load_document(args.prices), load_document(args.costs)
            assessment = load_document(args.assessment) if args.assessment else None
            alternative = load_document(args.alternative_costs) if args.alternative_costs else None
            savings = load_document(args.savings) if args.savings else None
            sources = [args.input, args.prices, args.costs, args.assessment, args.savings, args.alternative_costs]
            destinations = [args.budget_output, args.summary_output] + ([args.report] if args.report else [])
            paths = []
            for destination in destinations:
                path = output_path(args.input, destination)
                if path.suffix != ".md" or path.name in {"brief.md", "plan.yaml", "config.yaml"}:
                    raise InputError("report: outputs must be report Markdown, not configuration or brief")
                for source in sources:
                    if source:
                        output_path(source, destination)
                paths.append(path)
            if len(set(paths)) != len(paths):
                raise InputError("report: output paths must differ")
            if any(path.name == "report.md" for path in paths[:2]):
                raise InputError("report.md must use the managed --report block")
            budget, summary = render_reports(data, prices, costs, args.candidate, assessment, alternative, savings)
            updated = None
            if args.report:
                try:
                    existing = paths[2].read_text(encoding="utf-8")
                except UnicodeError:
                    raise InputError("report: expected UTF-8 Markdown") from None
                updated = update_report(existing, summary)
            write_text(paths[0], budget)
            write_text(paths[1], summary)
            if updated is not None:
                write_text(paths[2], updated)
            partial = costs["status"] == "partial" or (savings is not None and savings["status"] == "partial")
            print(json.dumps(dict(status="partial" if partial else "complete", output=str(paths[0]), issues=costs["issues"]), ensure_ascii=False))
            return 3 if partial else 0
        if args.command == "compare":
            from pricing_calculate import compare_costs, load_document
            path = output_path(args.baseline, args.output)
            output_path(args.alternative, args.output)
            result = compare_costs(load_document(args.baseline), load_document(args.alternative))
            write_result(path, result)
            print(json.dumps(dict(status=result["status"], output=str(path), issues=result["issues"]), ensure_ascii=False))
            return 3 if result["status"] == "partial" else 0
        data = load_input(args.input)
        if args.command == "validate":
            response, code = dict(status="complete", output=None, issues=[]), 0
        else:
            path = output_path(args.input, args.output)
            if args.command == "calculate":
                from pricing_calculate import calculate, load_document
                output_path(args.prices, args.output)
                if args.assessment:
                    output_path(args.assessment, args.output)
                result = calculate(data, load_document(args.prices), load_document(args.assessment) if args.assessment else None)
            else:
                result = lookup(data)
            write_result(path, result)
            code = 3 if result["status"] == "partial" else 0
            response = dict(status=result["status"], output=str(path), issues=result["issues"])
    except InputError as exc:
        response = dict(status="error", output=None, issues=[issue(None, None, "invalid_input", str(exc))])
        code = 2
    except OSError:
        response = dict(status="error", output=None, issues=[issue(None, None, "io_error", "Pricing input or output could not be accessed")])
        code = 1
    except Exception:
        # Never emit raw SDK exceptions, input values, credentials, or traceback.
        response = dict(status="error", output=None, issues=[issue(None, None, "internal_error", "Unexpected pricing tool error; check installation and runtime")])
        code = 1
    print(json.dumps(response, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
