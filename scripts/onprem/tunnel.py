#!/usr/bin/env python3
"""Resolve a live Quick Tunnel for a declared public service, or fail closed."""
import argparse
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlparse
from deadline import remaining, budget


def kubectl(*args):
    try:
        seconds = remaining(10)
        result = subprocess.run(["kubectl", f"--request-timeout={seconds:.3f}s", *args], capture_output=True, text=True, timeout=remaining(12))
    except subprocess.TimeoutExpired:
        raise RuntimeError("tunnel query timed out") from None
    if result.returncode:
        raise RuntimeError(f"kubectl {' '.join(args[:3])} failed; check cluster access")
    return result.stdout


def origin_matches(args, service, namespace):
    try:
        origin = args[args.index("--url") + 1]
    except (ValueError, IndexError):
        return False
    parsed = urlparse(origin)
    return parsed.scheme in ("http", "https") and not parsed.username and not parsed.password and parsed.hostname in (
        f"{service}.{namespace}.svc.cluster.local", f"{service}.{namespace}.svc", f"{service}.{namespace}",
    )


def resolve(service, namespace, timeout=120, query=kubectl, sleep=time.sleep, clock=time.monotonic):
    # timeout=0 means one bounded observation, never an unbounded set of queries.
    with budget(timeout if timeout > 0 else 30):
        return _resolve(service, namespace, timeout, query, sleep, clock)


def _resolve(service, namespace, timeout, query, sleep, clock):
    deadline = clock() + timeout
    public = json.loads(query("get", "service", service, "-n", namespace, "-o", "json"))
    ports = {p["port"] for p in public["spec"]["ports"]}
    while True:
        deployments = json.loads(query("get", "deployments", "-n", "cloudflared", "-o", "json"))["items"]
        # Legacy singleton is supported, but never used if the environment-specific tunnel exists.
        candidates = [d for d in deployments if d["metadata"]["name"] == f"cloudflared-{namespace}"]
        if not candidates:
            candidates = [d for d in deployments if d["metadata"]["name"] == "cloudflared"]
        if len(candidates) != 1:
            raise RuntimeError(f"missing/ambiguous tunnel for {namespace}/{service}")
        deployment = candidates[0]
        containers = deployment["spec"]["template"]["spec"]["containers"]
        container = next((c for c in containers if c["name"] == "cloudflared"), None)
        if not container or not origin_matches(container.get("args", []), service, namespace):
            raise RuntimeError(f"tunnel origin mismatch for {namespace}/{service}")
        origin_args = container["args"]
        origin = urlparse(origin_args[origin_args.index("--url") + 1])
        if (origin.port or (443 if origin.scheme == "https" else 80)) not in ports:
            raise RuntimeError(f"tunnel origin port does not match Service: {namespace}/{service}")
        selector = ",".join(f"{k}={v}" for k, v in deployment["spec"]["selector"]["matchLabels"].items())
        pods = json.loads(query("get", "pods", "-n", "cloudflared", "-l", selector, "-o", "json"))["items"]
        active = [p for p in pods if not p["metadata"].get("deletionTimestamp") and p.get("status", {}).get("phase") == "Running"]
        status = deployment.get("status", {})
        # During a rolling restart one old pod may still be Ready while its replacement is Pending.
        # Only an observed, fully updated singleton deployment can provide the URL.
        complete = (status.get("observedGeneration", 0) >= deployment["metadata"].get("generation", 1)
                    and all(status.get(k) == 1 for k in ("replicas", "updatedReplicas", "availableReplicas")))
        if complete and len(active) == 1:
            pod = active[0]
            actual = next((c for c in pod.get("spec", {}).get("containers", []) if c["name"] == "cloudflared"), None)
            if not actual or not origin_matches(actual.get("args", []), service, namespace):
                raise RuntimeError("running tunnel pod points at a different service")
            # A stale pod must not supply an address for a changed target port.
            if actual.get("args") != container.get("args"):
                raise RuntimeError("running tunnel pod differs from the declared tunnel")
            statuses = pod.get("status", {}).get("containerStatuses", [])
            running = next((c for c in statuses if c["name"] == "cloudflared" and c.get("ready")), None)
            started = (running or {}).get("state", {}).get("running", {}).get("startedAt")
            if started:
                logs = query("logs", pod["metadata"]["name"], "-n", "cloudflared", "-c", "cloudflared", f"--since-time={started}")
                urls = re.findall(r"https://[a-z0-9]+(?:-[a-z0-9]+)*\.trycloudflare\.com\b", logs)
                if urls:
                    return urls[-1] + "/"
        if clock() >= deadline:
            raise RuntimeError(f"no current tunnel URL after {timeout}s: {namespace}/{service}")
        sleep(min(5, max(0, deadline - clock())))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("service")
    p.add_argument("namespace")
    p.add_argument("--timeout", type=int, default=120)
    a = p.parse_args()
    print(resolve(a.service, a.namespace, a.timeout))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        sys.exit(1)
