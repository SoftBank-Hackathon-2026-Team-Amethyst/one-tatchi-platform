#!/usr/bin/env python3
"""T17 demo-app verification. Only a run-owned, private test green may be mutated.

Run on the deployment runner after kube-access. No kubeconfig, token, Terraform
state, HTTP body or subprocess stderr is copied into the public evidence artifact.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request

SERVICES = ("demo-app-be", "demo-app-fe")
HASH = "rollouts-pod-template-hash"
MARKER = "T17_VALIDATION_RUN_ID"
SMOKE = "one-tatchi-smoke"
TRAFFIC = "one-tatchi-t17-validation"


class CheckFailed(Exception):
    pass


def require(ok, message):
    if not ok:
        raise CheckFailed(message)


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=60).stdout


def kube(kind, name=None, namespace="test", selector=None):
    args = ["kubectl", "get", kind, "-n", namespace, "-o", "json"]
    if name:
        args.append(name)
    if selector:
        args += ["-l", selector]
    return json.loads(run(*args))


def marker(spec):
    return next((e.get("value") for c in spec["containers"] if c["name"] == "app"
                 for e in c.get("env", []) if e["name"] == MARKER), None)


def snapshot(name, namespace):
    rollout = kube("rollout", name, namespace)
    service = kube("service", name, namespace)
    bg = rollout["spec"].get("strategy", {}).get("blueGreen", {})
    require(bg.get("activeService") == name and bg.get("previewService") == name + "-preview"
            and bg.get("autoPromotionEnabled") is False, "manual blue-green strategy required")
    active = service["spec"]["selector"].get(HASH)
    require(active and active == rollout.get("status", {}).get("blueGreen", {}).get("activeSelector"),
            "active service and rollout disagree")
    spec = rollout["spec"]["template"]["spec"]
    return {"uid": rollout["metadata"]["uid"], "active": active,
            "images": {c["name"]: c["image"] for c in spec["containers"]},
            "marker": marker(spec), "phase": rollout["status"].get("phase")}


def ready(pod):
    return not pod["metadata"].get("deletionTimestamp") and any(
        c["type"] == "Ready" and c["status"] == "True" for c in pod.get("status", {}).get("conditions", []))


def pods(name, revision):
    return kube("pods", selector=f"app.kubernetes.io/name={name},{HASH}={revision}")["items"]


def guard(state, name, owned=False):
    """Re-read ownership and active selection immediately before any mutation."""
    current = snapshot(name, "test")
    before = state["baseline"]["test"][name]
    require(current["uid"] == before["uid"] and current["active"] == before["active"],
            f"{name}: original blue changed; refusing mutation")
    if owned:
        require(current["marker"] == state["marker"], f"{name}: green belongs to another run")
    return current


def pod_guard(state, name):
    guard(state, name, owned=True)
    private_preview(name)
    saved = state["green"][name]
    pod = kube("pod", saved["name"])
    require(pod["metadata"]["uid"] == saved["uid"]
            and pod["metadata"]["labels"].get(HASH) == saved["hash"]
            and marker(pod["spec"]) == state["marker"] and ready(pod), "green pod changed or is not ready")
    require(all(c.get("restartCount", 0) == 0 for c in pod["status"].get("containerStatuses", [])),
            "green pod restarted during verification")
    return pod


def private_preview(name):
    # SSO users must not be able to reach the fault-injected green either.
    # T31 routes allow the FE proxy to reach BE green, so check both services.
    for ingress in kube("ingress")["items"]:
        require(not any(service + "-preview" in json.dumps(ingress["spec"]) for service in SERVICES),
                "public preview ingress exists")
    for service in kube("services")["items"]:
        require(service["metadata"]["name"] not in {item + "-preview-auth" for item in SERVICES},
                "SSO preview proxy still exists")


@contextmanager
def forward(pod, remote):
    # Bind loopback only. A port collision fails closed; never forward a public service.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(["kubectl", "port-forward", "-n", "test", "pod/" + pod,
                                f"{port}:{remote}", "--address", "127.0.0.1"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            require(process.poll() is None, "private port-forward failed")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise CheckFailed("private port-forward timed out")
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CheckFailed("unexpected HTTP redirect")


def request(url, body=None, agent=SMOKE, expected=200):
    headers = {"User-Agent": agent, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        response = urllib.request.build_opener(NoRedirect).open(req, timeout=30)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        require(response.code == expected, f"unexpected HTTP status (expected {expected})")
        return response.read().decode()


def metrics(text):
    """Parse only the shared BE / nginx exporter application metric contract."""
    found = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(app_http_response_(?:count_total|time_seconds_hist_(?:bucket|count|sum)))(\{.*\})?\s+(\S+)(?:\s+\S+)?', line)
        if not match:
            continue
        labels = dict((k, json.loads('"' + v + '"')) for k, v in
                      re.findall(r'(\w+)="((?:[^"\\]|\\.)*)"', match[2] or ""))
        value = float(match[3])
        require(math.isfinite(value) and value >= 0, "invalid application metric")
        # Keep labels canonical so label order cannot look like a counter reset.
        key = match[1] + json.dumps(labels, sort_keys=True, separators=(",", ":"))
        found[key] = value
    return found


def total(samples, suffix="count_total", **labels):
    value = 0
    for key, sample in samples.items():
        name, encoded = key.split("{", 1)
        actual = json.loads("{" + encoded)
        if name == "app_http_response_" + suffix and all(actual.get(k) == v for k, v in labels.items()):
            value += sample
    return value


def delta(before, after, **labels):
    require(all(after.get(k, 0) >= v for k, v in before.items()), "application counters reset")
    return total(after, **labels) - total(before, **labels)


class Session:
    def __init__(self):
        self.root = Path(os.environ["T17_DIR"])
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "state.json"
        self.report = self.root / "evidence"
        self.report.mkdir(exist_ok=True)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2, allow_nan=False) + "\n")
        tmp.chmod(0o600)
        tmp.replace(self.path)

    def evidence(self, name, data):
        (self.report / (name + ".json")).write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")

    def preflight(self):
        require(os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
                and os.environ.get("GITHUB_REF") == "refs/heads/main"
                and os.environ.get("NAMESPACE") == "test", "verification requires main / workflow_dispatch / test")
        services = json.loads(os.environ["SERVICES"])
        require(sorted(s["name"] for s in services) == sorted(SERVICES), "demo-app BE and FE are required")
        require(os.environ.get("TARGET") in ("aws", "onprem", "gcp"), "unsupported target")
        require(re.fullmatch(r"[A-Za-z0-9_-]+", os.environ["CLUSTER"]), "unsupported cluster label")
        require(os.environ.get("OBSERVABILITY_LOG_GROUP"), "OBSERVABILITY_LOG_GROUP is required")
        require(not self.state, "verification state already exists; use a new workflow attempt")
        baseline = {ns: {name: snapshot(name, ns) for name in SERVICES} for ns in ("test", "prod")}
        require(all(v["phase"] == "Healthy" for env in baseline.values() for v in env.values()),
                "existing healthy test blue and prod are required; initial or pending deployments are unsupported")
        self.state = {"started_at": utc(), "marker": os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"],
                      "baseline": baseline, "green": {}, "chaos": None,
                      "identity": {k: os.environ[k] for k in ("GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
                                                             "GITHUB_SHA", "TARGET", "CLUSTER")},
                      "images": json.loads(os.environ["IMAGES"])}
        # Fail before Helm if /grafana is still the demo SPA, or data sources are absent.
        from grafana import Client
        Client().preflight()
        self.save()
        self.evidence("baseline", self.state)

    def prepare(self):
        for name in SERVICES:
            current = guard(self.state, name, owned=True)
            require(current["phase"] == "Paused", "a fresh paused green is required")
            image = self.state["images"][name]
            require(current["images"]["app"] == image["repository"] + "@" + image["digest"],
                    "green does not use the checked image digest")
            preview = kube("service", name + "-preview")
            revision = preview["spec"]["selector"].get(HASH)
            require(preview["spec"].get("type", "ClusterIP") == "ClusterIP"
                    and not preview["spec"].get("externalIPs") and revision
                    and revision != current["active"], "preview must be private and separate from blue")
            private_preview(name)
            selected = [p for p in pods(name, revision) if ready(p)]
            require(selected and all(marker(p["spec"]) == self.state["marker"] for p in selected),
                    "no ready run-owned green pod")
            p = selected[0]
            require(all(c.get("restartCount", 0) == 0 for c in p["status"].get("containerStatuses", [])),
                    "green pod has restarted")
            self.state["green"][name] = {"name": p["metadata"]["name"], "uid": p["metadata"]["uid"],
                                         "hash": revision, "images": {c["name"]: c.get("imageID")
                                             for c in p["status"].get("containerStatuses", [])}}
            port = 8000 if name.endswith("-be") else 4040
            with forward(p["metadata"]["name"], port) as url:
                self.state["green"][name]["before_smoke"] = metrics(request(url + "/metrics"))
                if name.endswith("-be"):
                    health = json.loads(request(url + "/health"))
                    require(health.get("database") == "connected", "test database is not connected")
                    chaos = json.loads(request(url + "/api/chaos"))
                    require(chaos.get("enabled") is True and chaos.get("latencyMs") == 0
                            and chaos.get("errorRate") == 0 and chaos.get("dbError") is False,
                            "chaos must be enabled and initially zero")
                    self.state["chaos"] = {k: chaos[k] for k in ("latencyMs", "errorRate", "dbError")}
            self.save()
        self.evidence("green", self.state["green"])

    def set_chaos(self, url, values):
        pod_guard(self.state, "demo-app-be")
        result = json.loads(request(url + "/api/chaos", body=values))
        require(all(result.get(k) == v for k, v in values.items()), "chaos update was not applied")

    def traffic(self):
        for name in SERVICES:
            pod_guard(self.state, name)
            with forward(self.state["green"][name]["name"], 8000 if name.endswith("-be") else 4040) as url:
                after = metrics(request(url + "/metrics"))
            require(delta(self.state["green"][name]["before_smoke"], after) == 0,
                    "AI smoke leaked into runtime counters or unexpected green traffic arrived")
        be = self.state["green"]["demo-app-be"]["name"]
        fe = self.state["green"]["demo-app-fe"]["name"]
        evidence = {"started_at": utc(), "requests": [], "snapshots": {}}
        try:
            with forward(be, 8000) as backend, forward(fe, 3000) as frontend, forward(fe, 4040) as exporter:
                def scrape():
                    return {"be": metrics(request(backend + "/metrics")), "fe": metrics(request(exporter + "/metrics"))}

                def hit(url, status):
                    # Check active selection before every generated user request, including faults.
                    for name in SERVICES:
                        pod_guard(self.state, name)
                    started = time.monotonic()
                    request(url, agent=TRAFFIC, expected=status)
                    evidence["requests"].append({"at": utc(), "service": "be" if url.startswith(backend) else "fe",
                                                  "status": status, "elapsed_ms": (time.monotonic() - started) * 1000})

                try:
                    hit(backend + "/api/info", 200)
                    time.sleep(1)
                    hit(frontend + "/", 200)
                    time.sleep(1)
                    # Materialize the 5xx series before baseline; Prometheus cannot infer its first increment.
                    self.set_chaos(backend, {"errorRate": 1})
                    hit(backend + "/api/info", 500)
                    self.set_chaos(backend, self.state["chaos"])
                    time.sleep(45)  # >= two 15s scrapes, also drains nginx's async syslog exporter
                    evidence["window_started_at"] = utc()
                    before = scrape()
                    evidence["snapshots"]["baseline"] = before
                    for _ in range(20):
                        hit(backend + "/api/info", 200)
                        time.sleep(1)
                        hit(frontend + "/", 200)
                        time.sleep(1)
                    self.set_chaos(backend, {"errorRate": 1})
                    for _ in range(5):
                        hit(backend + "/api/info", 500)
                        time.sleep(10)
                    self.set_chaos(backend, {"errorRate": 0, "latencyMs": 300})
                    delay_start = scrape()["be"]
                    for _ in range(10):
                        hit(backend + "/api/info", 200)
                        time.sleep(1)
                    after = scrape()
                    evidence["snapshots"]["after"] = after
                    evidence["window_ended_at"] = utc()
                    require(delta(before["be"], after["be"]) == 35 and delta(before["fe"], after["fe"]) == 20,
                            "runtime request counts differ from 35 BE / 20 FE")
                    require(delta(before["be"], after["be"], status="500") == 5
                            and delta(before["fe"], after["fe"], status="500") == 0, "runtime 5xx counts differ")
                    require(delta(delay_start, after["be"], suffix="time_seconds_hist_count") == 10
                            and delta(delay_start, after["be"], suffix="time_seconds_hist_bucket", le="0.25") == 0,
                            "300ms delay is missing from histogram")
                finally:
                    self.set_chaos(backend, self.state["chaos"])
                time.sleep(45)  # let the receiver observe the final deltas
        finally:
            evidence["ended_at"] = utc()
            self.evidence("traffic", evidence)

    def verify(self):
        from grafana import Client
        Client().verify(self)

    def cleanup(self):
        if not self.state:
            self.evidence("cleanup", {"status": "not_started"})
            return
        results = {}
        failures = []
        # Treat each service independently so a failed FE deployment cannot prevent BE cleanup.
        for name in SERVICES:
            try:
                current = guard(self.state, name)
                if current["marker"] != self.state["marker"]:
                    require(current == self.state["baseline"]["test"][name], "foreign deployment detected")
                    results[name] = "not_deployed"
                    continue
                if name.endswith("-be") and self.state.get("chaos") and name in self.state["green"]:
                    try:
                        if pods(name, self.state["green"][name]["hash"]):
                            pod_guard(self.state, name)
                            with forward(self.state["green"][name]["name"], 8000) as url:
                                self.set_chaos(url, self.state["chaos"])
                    except (CheckFailed, OSError, ValueError, KeyError, subprocess.SubprocessError):
                        # An unreachable pod still needs termination. Abort below is independently
                        # guarded; success requires every run-owned pod to have terminated.
                        results[name + "/restore"] = "unreachable; removing own green instead"
                guard(self.state, name, owned=True)
                run("kubectl", "argo", "rollouts", "abort", name, "-n", "test")
                # Abort keeps stable blue. Never undo/promote or roll back a foreign Helm revision.
                for _ in range(60):
                    guard(self.state, name, owned=True)
                    active = pods(name, self.state["baseline"]["test"][name]["active"])
                    owned = [p for p in kube("pods", selector=f"app.kubernetes.io/name={name}")["items"]
                             if marker(p["spec"]) == self.state["marker"] and not p["metadata"].get("deletionTimestamp")]
                    if active and all(ready(p) for p in active) and not owned:
                        break
                    time.sleep(3)
                else:
                    raise CheckFailed("green cleanup or blue readiness timed out")
                results[name] = "aborted_own_green_blue_ready"
            except (CheckFailed, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
                results[name] = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
                failures.append(name)
        for name in SERVICES:
            try:
                require(snapshot(name, "prod") == self.state["baseline"]["prod"][name], "prod metadata changed")
            except (CheckFailed, OSError, ValueError, KeyError, subprocess.SubprocessError):
                failures.append("prod/" + name)
        self.evidence("cleanup", {"ended_at": utc(), "services": results, "failures": failures})
        require(not failures, "cleanup incomplete or baseline changed; inspect cleanup artifact")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("preflight", "prepare", "verify", "cleanup"))
    args = parser.parse_args()
    session = Session()
    try:
        getattr(session, args.command)()
        session.evidence(args.command + "-result", {"status": "passed", "at": utc()})
    except (CheckFailed, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        message = str(exc) if isinstance(exc, CheckFailed) else type(exc).__name__
        session.evidence(args.command + "-result", {"status": "failed", "at": utc(), "reason": message})
        raise SystemExit(f"T17 {args.command} failed: {message}") from None


if __name__ == "__main__":
    # grafana imports these helpers; keep one exception type when invoked as a script.
    import sys
    sys.modules["live"] = sys.modules[__name__]
    main()
