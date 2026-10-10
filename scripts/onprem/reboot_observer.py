#!/usr/bin/env python3
"""Read-only reboot acceptance: SQL + public API data, PVCs, images, runner and 5m stability.

This observer never starts/restarts services, applies manifests, promotes or repairs.
Run baseline once, then install its observe invocation as a login LaunchAgent.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

from deadline import budget, remaining, pause
import onpremctl as ctl


def runner_connection(config, after):
    for path in sorted((Path(config["runner_dir"]) / "_diag").glob("Runner_*.log"), reverse=True)[:3]:
        if path.stat().st_mtime < after:
            continue
        with path.open("rb") as stream:
            stream.seek(max(0, path.stat().st_size - 2_000_000))
            text = stream.read().decode(errors="replace")
        for stamp in re.findall(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)Z INFO Terminal\] WRITE LINE: [^\n]*Listening for Jobs", text):
            epoch = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
            if epoch >= after:
                return epoch
    return None


def sample(config, markers, repository, after):
    result = ctl.status(config)
    if not result["docker_ready"]:
        raise RuntimeError("Docker is unavailable")
    result["pvcs"] = sorted([{"namespace": p["metadata"]["namespace"], "name": p["metadata"]["name"],
                             "uid": p["metadata"]["uid"], "volume": p["spec"].get("volumeName"), "phase": p["status"]["phase"]}
                            for p in ctl.kube("get", "pvc", "-A")["items"]], key=lambda p: (p["namespace"], p["name"]))
    result["images"], result["database"] = {}, {}
    for env in config["environments"]:
        rollouts = ctl.kube("get", "rollouts", "-n", env)["items"]
        result["images"][env] = {r["metadata"]["name"]: [c["image"] for c in r["spec"]["template"]["spec"]["containers"]] for r in rollouts}
        marker = markers[env]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", marker):
            raise ValueError("marker must contain only letters, numbers, underscore or hyphen")
        sql = f"SELECT count(*) FROM guestbook WHERE message = '{marker}';"
        count = int(ctl.run(["kubectl", "--request-timeout=8s", "exec", "-n", config["secret_namespace"],
                            f"{config['service']}-db-{env}-0", "--", "psql", "-U", "app", "-d", "demo", "-Atc", sql], timeout=remaining(10)).stdout.strip())
        secret = ctl.kube("get", "secret", f"{config['service']}-db-{env}-credentials", "-n", config["secret_namespace"])["data"]
        fingerprint = hashlib.sha256(json.dumps(secret, sort_keys=True).encode()).hexdigest()
        url = result["urls"].get(env)
        public = ctl.http_check(url + "api/guestbook", marker) if url else {"ok": False}
        result["database"][env] = {"marker_count": count, "credentials_sha256": fingerprint, "public_marker": public["ok"]}
        if count < 1 or not public["ok"]:
            result["errors"].append(f"SQL/public API marker missing: {env}")
    result["charts"] = {r["namespace"] + "/" + r["name"]: r["chart"] for r in json.loads(ctl.run(["helm", "list", "-A", "-o", "json"]).stdout)
                        if r["namespace"] in config["environments"]}
    runner = json.loads((Path(config["runner_dir"]) / ".runner").read_text(encoding="utf-8-sig"))["agentName"]
    runners = json.loads(ctl.run(["gh", "api", f"repos/{repository}/actions/runners"], timeout=remaining(10)).stdout)["runners"]
    result["runner_online"] = any(r["name"] == runner and r["status"] == "online" for r in runners)
    result["runner_connected_at"] = runner_connection(config, after)
    if not result["runner_online"] or not result["runner_connected_at"]:
        result["errors"].append("runner is not online with a fresh connection")
    if not ctl.workloads_ready(config):
        result["errors"].append("database/app rollout is not ready")
    return result


def compare(baseline, current):
    errors = list(current.get("errors", []))
    for key in ("pvcs", "images", "charts", "database"):
        if current.get(key) != baseline.get(key):
            errors.append(f"changed or missing: {key}")
    restore = current.get("last_restore", {})
    if restore.get("status") != "ready" or restore.get("boot_id") != current.get("boot_id"):
        errors.append("no successful restore from this boot")
    expected = baseline.get("versions", {}).get("configured")
    versions = current.get("versions", {})
    nodes = versions.get("nodes", [])
    if not nodes:
        errors.append("no live Kubernetes node version")
    for node in nodes:
        if expected and node["version"].replace("+", "-") != expected:
            errors.append("unexpected live Kubernetes version")
        container = next((c for c in versions.get("containers", []) if c["name"].lstrip("/") == node["name"]), {})
        internal = [a["address"] for a in node["addresses"] if a["type"] == "InternalIP"]
        if not internal or not set(internal).issubset(set(container.get("addresses", []))):
            errors.append("Docker and Kubernetes Node IP differ")
        if expected and container.get("image") != "rancher/k3s:" + expected:
            errors.append("unexpected live Docker image")
    return errors


def baseline_errors(current, allow_unpowered=False):
    # Preparing a data reference while unplugged must not relax reboot acceptance.
    pending = []
    if allow_unpowered and current.get("ac_power") is False:
        pending = [error for error in current["errors"] if error in (
            "AC power is disconnected; continuous operation is not guaranteed",
            "the managed caffeinate assertion is absent")]
    return [error for error in current["errors"] if error not in pending], pending


def observe(config, directory, repository):
    started, began = time.time(), time.monotonic()
    baseline = json.loads((directory / "baseline.json").read_text())
    boot = ctl.boot_id()
    if boot == baseline["boot_id"]:
        print("Armed for the next boot; no services changed.")
        return
    if (directory / "result.json").exists():
        print("Existing reboot result preserved.")
        return
    launch = {"boot_id": boot, "started_at": started, "recovery_budget_seconds": 600, "stability_seconds": 300,
              "timing_basis": "login LaunchAgent start approximates login time", "http_origin": "Mac via public Cloudflare URL"}
    # A launchd restart must not reset the original observation deadline.
    if (directory / "started.json").exists():
        launch = json.loads((directory / "started.json").read_text())
        if launch["boot_id"] != boot:
            raise RuntimeError("preserve the previous attempt before arming another reboot")
        started = launch["started_at"]
        began -= max(0, time.time() - started)
    else:
        ctl.write_json(directory / "started.json", launch)
    first_ready = None
    errors = ["not observed"]
    number = len(list(directory.glob("sample-*.json")))
    while time.monotonic() - began < (600 if first_ready is None else first_ready + 355):
        end = 600 if first_ready is None else first_ready + 355
        try:
            with budget(min(55, end - (time.monotonic() - began))):
                current = sample(config, baseline["markers"], repository, started)
                errors = compare(baseline, current)
        except Exception as exc:
            current, errors = {}, [f"observation unavailable: {type(exc).__name__}"]
        elapsed = time.monotonic() - began
        ctl.write_json(directory / f"sample-{number:04d}.json", {"elapsed_seconds": elapsed, "checks": current, "pending": errors})
        number += 1
        print(json.dumps({"elapsed_seconds": round(elapsed), "pending": errors}), flush=True)
        if first_ready is None and not errors and elapsed <= 600:
            first_ready = elapsed
        elif first_ready is not None and errors:
            # The required five-minute window must be continuously healthy.
            break
        if first_ready is not None and not errors and elapsed >= first_ready + 300:
            break
        left = (600 if first_ready is None else first_ready + 300) - (time.monotonic() - began)
        if left > 0:
            time.sleep(min(10, left))
    elapsed = time.monotonic() - began
    passed = first_ready is not None and not errors and elapsed >= first_ready + 300
    result = dict(launch, result="passed" if passed else "failed", first_ready_seconds=first_ready,
                  observed_seconds=round(elapsed, 2), samples=number, pending=errors,
                  manual_intervention_confirmed_absent=False)
    ctl.write_json(directory / "result.json", result)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["baseline", "observe", "probe"])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--test-marker", default="T27-lock10-test-20261010")
    parser.add_argument("--prod-marker", default="T27-lock10-prod-20261010")
    parser.add_argument("--allow-unpowered-baseline", action="store_true",
                        help="save only a data baseline before AC is connected; observe still requires AC")
    args = parser.parse_args()
    if args.allow_unpowered_baseline and args.mode != "baseline":
        parser.error("--allow-unpowered-baseline is only valid with baseline")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("invalid repository")
    config = ctl.load_config(args.config)
    os.environ["PATH"] = config["path"]
    if args.mode == "observe":
        return observe(config, args.evidence, args.repository)
    markers = {"test": args.test_marker, "prod": args.prod_marker}
    with budget(90):
        current = sample(config, markers, args.repository, int(ctl.boot_id().split("-")[-1]))
    errors, pending = baseline_errors(current, args.allow_unpowered_baseline)
    if errors:
        raise RuntimeError("baseline/probe failed: " + "; ".join(errors))
    current["markers"] = markers
    current["preconditions_pending"] = pending
    if args.mode == "baseline":
        if (args.evidence / "baseline.json").exists():
            raise RuntimeError("baseline exists; preserve previous evidence")
        ctl.write_json(args.evidence / "baseline.json", current)
    print(json.dumps({"result": "data-baseline-only" if pending else "ready", "preconditions_pending": pending,
                      "urls": current["urls"], "database": current["database"], "runner_online": current["runner_online"]}))


if __name__ == "__main__":
    main()
