#!/usr/bin/env python3
"""Connect an existing managed device to central metrics without persisting credentials."""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import onpremctl as ctl

ADDRESS = "module.observability.helm_release.metrics"
SECRET = "deploy-metrics-remote-write"


def https_url(value, path):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.query or parsed.fragment or parsed.path != path):
        raise ValueError(f"expected HTTPS URL ending in {path}, without credentials, query or fragment")
    return value


def settings(remote_url, dashboard_url):
    return {
        "metrics_remote_write_url": https_url(remote_url, "/api/v1/write"),
        "metrics_remote_write_secret_name": SECRET,
        "metrics_dashboard_url": https_url(dashboard_url, "/grafana/d/deploy-overview"),
    }


def check_plan(plan, expected):
    if plan.get("errored") or plan.get("complete") is False or plan.get("deferred_changes"):
        raise RuntimeError("Terraform plan is incomplete")
    for key, value in expected.items():
        if plan.get("variables", {}).get(key, {}).get("value") != value:
            raise RuntimeError(f"Terraform input differs from requested setting: {key}")
    changes = []
    for resource in plan.get("resource_changes", []):
        actions = resource["change"]["actions"]
        if actions in (["no-op"], ["read"]):
            continue
        if resource["address"] != ADDRESS or actions != ["update"]:
            raise RuntimeError(f"refusing unrelated, new or destructive resource change: {resource['address']}")
        changes.append(resource["address"])
    return changes


def command(args, *, env=None, input=None, timeout=600):
    # Child errors may include Secret bodies or provider credentials. Never forward them.
    result = subprocess.run([str(a) for a in args], input=input, capture_output=True,
                            text=True, env=env, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode}); no credential output retained")
    return result.stdout


def secret_payload(password):
    if not password or "\n" in password or "\r" in password:
        raise ValueError("a nonempty single-line METRICS_PASSWORD is required")
    return json.dumps({
        "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
        "metadata": {"name": SECRET, "namespace": "monitoring"},
        "data": {key: base64.b64encode(value.encode()).decode()
                 for key, value in {"username": "onprem", "password": password}.items()},
    })


def connect(config_path, requested, mode):
    if any(os.environ.get(key) for key in ("TF_LOG", "TF_LOG_CORE", "TF_LOG_PROVIDER", "TF_LOG_PATH")):
        raise RuntimeError("disable Terraform debug logging before handling credentials")
    config = ctl.load_config(config_path)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise RuntimeError("only a manual run on main may access the managed device")
        if (os.environ.get("ONPREM_PROFILE") != config["profile"]
                or os.environ.get("ONPREM_CLUSTER") != config["cluster"]):
            raise RuntimeError("runner identity differs from selected device")
    if not ctl.state_path(config).is_file():
        raise RuntimeError("existing device state is required; bootstrap is not supported")
    ctl.check_ownership(config, ctl.cluster_exists(config))
    state = json.loads(ctl.state_path(config).read_text())
    metrics = [r for r in state.get("resources", [])
               if r.get("module") == "module.observability" and r["type"] == "helm_release" and r["name"] == "metrics"]
    if len(metrics) != 1 or len(metrics[0].get("instances", [])) != 1:
        raise RuntimeError("existing metrics Helm release is required")
    release = metrics[0]["instances"][0]["attributes"]
    if (release.get("name"), release.get("namespace")) != ("deploy-metrics", "monitoring"):
        raise RuntimeError("metrics release identity differs")
    password = os.environ.get("METRICS_PASSWORD", "")
    payload = secret_payload(password) if mode == "apply" else None
    root = Path(config["terraform_root"])
    config_file = root / "t17-metrics.auto.tfvars.json"
    if config_file.is_symlink():
        raise RuntimeError("metrics settings must not be a symlink")
    previous = config_file.read_bytes() if config_file.exists() else None
    keep_settings = False
    # Provider and database credentials are supplied by the installed v2 wrapper.
    wrapper = Path(config["home"]) / "bin/onpremctl.py"
    env = {key: value for key, value in os.environ.items() if key != "METRICS_PASSWORD"}
    try:
        ctl.write_json(config_file, requested)
        with tempfile.TemporaryDirectory(prefix="t17-metrics-") as directory:
            plan_path = Path(directory) / "metrics.tfplan"
            command([sys.executable, wrapper, "--config", config_path, "terraform", "plan",
                     "-input=false", "-lock-timeout=5m", f"-out={plan_path}"], env=env)
            plan = json.loads(command(["terraform", f"-chdir={root}", "show", "-json", plan_path], env=env))
            changes = check_plan(plan, requested)
            print(json.dumps({"profile": config["profile"], "cluster": config["cluster"],
                              "mode": mode, "updates": changes}))
            if mode == "apply":
                current = json.loads(ctl.state_path(config).read_text())
                if any(current.get(key) != state.get(key) for key in ("lineage", "serial")):
                    raise RuntimeError("device state changed during review; run a fresh plan")
                ctl.prepare_kubeconfig(config)
                env["KUBECONFIG"] = os.environ["KUBECONFIG"]
                command(["kubectl", "apply", "--server-side", "--field-manager=t17-metrics", "-f", "-"], env=env, input=payload)
                # The v2 wrapper rejects saved-plan apply and rechecks ownership/credentials.
                command([sys.executable, wrapper, "--config", config_path, "terraform", "apply",
                         "-input=false", "-auto-approve", "-lock-timeout=5m"], env=env)
                keep_settings = True
                command(["kubectl", "-n", "monitoring", "rollout", "restart", "deployment/deploy-metrics"], env=env)
                command(["kubectl", "-n", "monitoring", "rollout", "status", "deployment/deploy-metrics", "--timeout=180s"], env=env)
                print("Remote-write configured; verify the cluster's series in central Grafana before closing T17.")
    finally:
        if not keep_settings:
            if previous is None:
                config_file.unlink(missing_ok=True)
            else:
                config_file.write_bytes(previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--remote-write-url", required=True)
    parser.add_argument("--dashboard-url", required=True)
    parser.add_argument("--mode", choices=["plan", "apply"], default="plan")
    args = parser.parse_args()
    connect(args.config, settings(args.remote_write_url, args.dashboard_url), args.mode)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, KeyError, OSError, subprocess.SubprocessError) as exc:
        # Do not render exception payloads from parsers or subprocesses containing secrets.
        print(str(exc) if isinstance(exc, RuntimeError) else f"observability setup failed ({type(exc).__name__})", file=sys.stderr)
        sys.exit(1)
