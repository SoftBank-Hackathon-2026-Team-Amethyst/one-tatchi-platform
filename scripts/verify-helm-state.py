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


def read(args, ok=(0,)):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode not in ok:
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
        # can-i exits 1 when the answer is "no"; that is a permission result, not a read failure.
        # Exit 1 without a "no" answer is a transport or authentication failure.
        answer = read(["kubectl", "auth", "can-i", "list", "secrets", "-n", namespace], ok=(0, 1)).strip()
        if re.match(r"^no(?:\s+-|$)", answer):
            raise RuntimeError(f"CI identity cannot list Helm release records in namespace {namespace}")
        if answer != "yes":
            raise RuntimeError("kubectl read failed; inspect this job's identity and cluster access")
    for address, namespace, name in owned:
        # Helm 4 lists every status by default and no longer accepts --all.
        found = json.loads(read(["helm", "list", "--namespace", namespace,
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
