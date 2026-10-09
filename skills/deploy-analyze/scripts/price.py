#!/usr/bin/env python3
"""Single entry point for validated price lookup (calculation follows in C5)."""

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


def write_result(path, result):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pricing-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
        parser = Parser(description="Validate a pricing input or look up AWS/GCP public On-Demand prices")
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
        data = load_input(args.input)
        if args.command == "validate":
            response, code = dict(status="complete", output=None, issues=[]), 0
        else:
            path = output_path(args.input, args.output)
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
