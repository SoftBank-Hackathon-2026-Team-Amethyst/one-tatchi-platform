#!/usr/bin/env python3
"""Fail if workload identities or restart counters changed during a lock test."""
import json
import sys
from pathlib import Path


def identity(snapshot):
    pods = {}
    for pod in snapshot["pods"]:
        # Completed bootstrap jobs do not provide an always-running service.
        if pod["status"].get("phase") == "Succeeded":
            continue
        pods[f"{pod['namespace']}/{pod['name']}"] = {
            "uid": pod["uid"], "created": pod["created"],
            "containers": [(c["name"], c.get("restartCount"), c.get("state", {}).get("running", {}).get("startedAt"))
                           for c in pod["status"].get("containerStatuses", [])],
        }
    return {"pods": pods, "nodes": sorted(snapshot.get("nodes", []), key=lambda n: n["name"])}


def compare(paths):
    snapshots = [json.loads(Path(p).read_text()) for p in paths]
    if len(snapshots) < 2:
        raise ValueError("at least two diagnostic snapshots are required")
    before = identity(snapshots[0])
    if not before["pods"] or not before["nodes"]:
        raise ValueError("workload/node evidence is missing")
    span = max(s["observed_at"] for s in snapshots) - min(s["observed_at"] for s in snapshots)
    if span < 1800:
        raise ValueError("less than 30 minutes of observations")
    for snapshot in snapshots:
        if snapshot.get("errors") or not snapshot.get("sleep_prevented") or not snapshot.get("ac_power"):
            raise ValueError("power/service diagnostic failed")
        if identity(snapshot) != before:
            raise ValueError("node/pod identity or restart counter changed during observation")
    print(json.dumps({"snapshots": len(snapshots), "seconds": round(span), "pods": len(before["pods"]), "restarts_or_replacements": 0}))


if __name__ == "__main__":
    compare(sys.argv[1:])
