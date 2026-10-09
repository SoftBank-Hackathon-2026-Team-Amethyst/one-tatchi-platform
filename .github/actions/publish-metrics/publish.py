#!/usr/bin/env python3
"""Publish the judge's exact evidence; never calculate or change its decision."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile


def number(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("invalid metric value")
    return value


def record(directory, context):
    metrics = json.loads((directory / "metrics.json").read_text())
    judgment_file = directory / "judgment.json"
    judgment = json.loads(judgment_file.read_text()) if judgment_file.exists() else {}
    release = directory.name
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", release) or metrics.get("release") != release:
        raise ValueError("release does not match evidence directory")
    # Whitelist fields: smoke request bodies, credentials and raw logs never leave the artifact.
    evidence = {key: number(metrics.get(key)) for key in ("requests", "failed", "error_rate", "p95_ms", "max_ms")}
    pods = metrics.get("pods")
    evidence["pods"] = None if pods is None else {key: number(pods.get(key)) for key in ("count", "ready", "restarts")}
    evidence["thresholds"] = {key: number(metrics.get("thresholds", {}).get(key)) for key in ("max_error_rate", "max_p95_ms", "max_restarts")}
    evidence["green_hash"] = metrics.get("green_hash")
    window_file = directory / "observation.json"
    window = json.loads(window_file.read_text()) if window_file.exists() else None
    identity = {**context, "service": release}
    event_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {"schema_version": 1, "event_id": event_id, **identity, "source": "smoke",
            "published_at": dt.datetime.now(dt.timezone.utc).isoformat(), "observation": window,
            "metrics": evidence, "rule": metrics.get("rule"),
            "decision": judgment.get("decision"), "decision_source": judgment.get("source"),
            "reason": judgment.get("reason"), "executed": None}


def aws(*args):
    result = subprocess.run(["aws", "logs", *args, "--no-cli-pager", "--output", "json"],
                            check=True, timeout=30, capture_output=True)
    return json.loads(result.stdout or b"{}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report-dir", type=Path, required=True)
    ap.add_argument("--log-group", required=True)
    ap.add_argument("--target", choices=["aws", "gcp", "onprem"], required=True)
    ap.add_argument("--environment", choices=["test", "prod"], required=True)
    ap.add_argument("--cluster", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    context = {"repository": os.environ["GITHUB_REPOSITORY"], "run_id": os.environ["GITHUB_RUN_ID"],
               "run_attempt": os.environ["GITHUB_RUN_ATTEMPT"], "sha": args.sha,
               "target": args.target, "environment": args.environment, "cluster": args.cluster}
    context["run_url"] = f"https://github.com/{context['repository']}/actions/runs/{context['run_id']}/attempts/{context['run_attempt']}"
    records = [record(p.parent, context) for p in sorted(args.report_dir.glob("*/metrics.json"))]
    if not records:
        raise ValueError("no AI evidence to publish")
    if args.dry_run:
        print(json.dumps(records, ensure_ascii=False, allow_nan=False))
        return
    stream = f"{context['repository']}/{context['target']}/{context['environment']}/{context['run_id']}-{context['run_attempt']}"
    try:
        aws("create-log-stream", "--log-group-name", args.log_group, "--log-stream-name", stream)
    except subprocess.CalledProcessError as exc:
        if b"ResourceAlreadyExistsException" not in exc.stderr:
            raise
    events = [{"timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000),
               "message": json.dumps(row, ensure_ascii=False, allow_nan=False)} for row in records]
    # A request retry may duplicate a log event. Grafana deduplicates by stable event_id.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.json"
        path.write_text(json.dumps(events, ensure_ascii=False))
        response = aws("put-log-events", "--log-group-name", args.log_group, "--log-stream-name", stream,
                       "--log-events", f"file://{path}")
        if response.get("rejectedLogEventsInfo"):
            raise ValueError("CloudWatch rejected evidence events")
    print(f"Published {len(records)} evidence records to {args.log_group}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        # Do not dump CLI stderr: it may contain authentication details.
        raise SystemExit(f"Evidence publication failed ({type(exc).__name__}); original Actions artifact is preserved") from None
