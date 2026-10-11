#!/usr/bin/env python3
"""Read-only resource Metrics API verification for EKS, GKE and K3s."""
import argparse
import json
import subprocess
import time


def inspect_metrics(namespaces, read=None):
    if read is None:
        def read(args):
            return subprocess.run(["kubectl", *args, "--request-timeout=5s"],
                                  capture_output=True, text=True, timeout=6)
    result = {"available": False, "namespaces": {}}
    try:
        response = read(["get", "apiservice", "v1beta1.metrics.k8s.io", "-o", "json"])
        if response.returncode:
            raise ValueError("apiservice")
        api = json.loads(response.stdout)
        if not any(c.get("type") == "Available" and c.get("status") == "True"
                   for c in api.get("status", {}).get("conditions", [])):
            raise ValueError("apiservice")
        for namespace in namespaces:
            response = read(["get", "--raw", f"/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods"])
            if response.returncode:
                raise ValueError("podmetrics")
            items = json.loads(response.stdout)["items"]
            samples = [m for m in items if m.get("timestamp") and m.get("window") and
                       m.get("containers") and all("cpu" in c.get("usage", {}) and
                                                   "memory" in c.get("usage", {}) for c in m["containers"])]
            result["namespaces"][namespace] = {"samples": len(samples)}
            if not samples:
                raise ValueError("no samples")
        result["available"] = True
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, subprocess.SubprocessError):
        # Do not echo kubectl output: authentication errors can include credentials.
        result["error"] = "Metrics API is unavailable or has no Pod CPU/memory samples"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", action="append", required=True)
    parser.add_argument("--wait-seconds", type=int, default=0, choices=range(0, 91), metavar="0..90")
    args = parser.parse_args()
    deadline = time.monotonic() + args.wait_seconds
    while True:
        result = inspect_metrics(args.namespace)
        if result["available"] or time.monotonic() >= deadline:
            print(json.dumps(result))
            return 0 if result["available"] else 1
        time.sleep(min(5, max(0, deadline - time.monotonic())))


if __name__ == "__main__":
    raise SystemExit(main())
