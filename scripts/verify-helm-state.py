#!/usr/bin/env python3
"""Fail before Terraform plan when this CI identity cannot see state-owned Helm releases."""
import argparse
import json
import re
import subprocess
import sys


def releases(module):
    for resource in module.get("resources", []):
        if resource.get("mode") == "managed" and resource.get("type") == "helm_release":
            values = resource["values"]
            yield resource["address"], values["namespace"], values["name"]
    for child in module.get("child_modules", []):
        yield from releases(child)


def read(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode:
        # An ordinary authorization denial is exit 1 / no, not a transport failure.
        if (args[:3] == ["kubectl", "auth", "can-i"] and result.returncode == 1
                and re.match(r"^no(?:\s+-|$)", result.stdout.strip())):
            return "no"
        raise RuntimeError(f"{args[0]} read failed; inspect this job's identity and cluster access")
    return result.stdout


def verify(root):
    # Terraform state may contain credentials. Parse it in memory and emit names/status only.
    state = json.loads(read(["terraform", f"-chdir={root}", "show", "-json"]))
    owned = list(releases(state.get("values", {}).get("root_module", {})))
    if not owned:
        raise RuntimeError("no state-owned Helm releases; verify the existing cluster's backend before planning")
    namespaces = sorted({namespace for _, namespace, _ in owned})
    for namespace in namespaces:
        if read(["kubectl", "auth", "can-i", "list", "secrets", "-n", namespace]).strip() != "yes":
            raise RuntimeError(f"CI identity cannot list Helm release records in namespace {namespace}")
    for address, namespace, name in owned:
        found = json.loads(read(["helm", "list", "--all", "--namespace", namespace,
                                 "--filter", f"^{re.escape(name)}$", "--output", "json"]))
        if len(found) != 1 or found[0].get("name") != name:
            raise RuntimeError(f"state-owned release is not visible: {address}; do not assume it was deleted")
        print(json.dumps({"address": address, "namespace": namespace, "name": name, "status": found[0]["status"]}))
    print(f"Verified {len(owned)} state-owned Helm releases with the current CI identity")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root")
    args = parser.parse_args()
    try:
        verify(args.root)
    except (RuntimeError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else f"Helm visibility check failed ({type(exc).__name__})", file=sys.stderr)
        sys.exit(1)
