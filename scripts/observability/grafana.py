"""Read the provisioned dashboard and query its actual Grafana data sources.

CloudWatch logs use the same StartQuery / GetQueryResults logAction protocol as
Grafana's CloudWatchLogsQueryRunner. Authentication stays in Grafana (Pod Identity
and WIF); the verifier needs no administrator token or downloaded cloud key.
"""
import copy
import datetime as dt
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from live import CheckFailed, SERVICES, request, require, total, utc


def rows(frames):
    for frame in frames:
        fields = frame["schema"]["fields"]
        for values in zip(*frame.get("data", {}).get("values", [])):
            yield {field["name"]: value for field, value in zip(fields, values)}


def numbers(frames):
    for frame in frames:
        for field, values in zip(frame["schema"]["fields"], frame.get("data", {}).get("values", [])):
            if field["type"] == "number":
                for value in values:
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                        yield field.get("labels", {}), value


def fresh(frames, now, max_age):
    for frame in frames:
        fields = frame["schema"]["fields"]
        columns = frame.get("data", {}).get("values", [])
        times = next((column for field, column in zip(fields, columns) if field["type"] == "time"), [])
        for field, column in zip(fields, columns):
            if field["type"] == "number":
                for timestamp, value in zip(times, column):
                    if isinstance(value, (int, float)) and math.isfinite(value) and 0 <= now - timestamp / 1000 <= max_age:
                        return True
    return False


def interpolate(value, variables):
    if isinstance(value, dict):
        return {k: interpolate(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, variables) for v in value]
    if isinstance(value, str):
        for key, replacement in variables.items():
            value = value.replace("${" + key + ":regex}", replacement).replace("${" + key + "}", replacement)
            value = value.replace("${" + key + ":raw}", replacement)
            value = re.sub(r"\$" + re.escape(key) + r"\b", lambda _: replacement, value)
    return value


class Client:
    def __init__(self):
        self.url = os.environ["OBSERVABILITY_URL"].rstrip("/")
        parsed = urlsplit(self.url)
        require(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                and parsed.path == "/grafana" and not parsed.query and not parsed.fragment,
                "OBSERVABILITY_URL must be an HTTPS /grafana base URL without credentials")
        self.queries = []
        self.sources = {}
        self.dashboard = {}

    def api(self, path, body=None):
        try:
            return json.loads(request(self.url + path, body=body))
        except json.JSONDecodeError:
            raise CheckFailed("Grafana returned non-JSON (check ALB /grafana routing)") from None

    def preflight(self):
        require(self.api("/api/health").get("database") == "ok", "Grafana database health failed")
        self.sources = {source["uid"]: source for source in self.api("/api/datasources")}
        for uid, kind in (("cloudwatch", "cloudwatch"), ("prometheus", "prometheus")):
            require(self.sources.get(uid, {}).get("type") == kind, f"Grafana {uid} data source missing")
        if os.environ["TARGET"] == "gcp":
            require(self.sources.get("cloud-monitoring", {}).get("type") == "stackdriver", "Grafana WIF data source missing")
        self.dashboard = self.api("/api/dashboards/uid/deploy-overview")["dashboard"]

    def query(self, model, start, end):
        model = copy.deepcopy(model)
        uid = model["datasource"]["uid"]
        model.update(refId="A", intervalMs=15000, maxDataPoints=1000)
        # Saved panel models omit fields normally supplied by Grafana's frontend.
        if uid == "prometheus":
            model.setdefault("range", True)
            model.setdefault("instant", False)
            model.setdefault("format", "time_series")
        if uid == "cloudwatch" and model.get("queryMode") == "Metrics":
            model.setdefault("type", "timeSeriesQuery")
            model.setdefault("period", "60")
            model.setdefault("statistic", "Average")
            model.setdefault("dimensions", {})
        if model.get("region") == "default":
            model["region"] = self.sources[uid]["jsonData"]["defaultRegion"]
        model.pop("hide", None)
        body = {"from": str(int(start * 1000)), "to": str(int(end * 1000)), "queries": [model]}
        response = self.api("/api/ds/query", body)
        result = response.get("results", {}).get("A", {})
        require(result and not result.get("error") and result.get("status", 200) == 200,
                f"Grafana {uid} query failed")
        frames = result.get("frames", [])
        self.queries.append({"at": utc(), "request": body, "frames": frames})
        return frames

    def prom(self, expression, end=None, uid=None):
        end = end or time.time()
        uid = uid or ("cloud-monitoring" if os.environ["TARGET"] == "gcp" else "prometheus")
        if uid == "cloud-monitoring":
            model = {"datasource": {"type": "stackdriver", "uid": uid}, "queryType": "promQL",
                     "promQLQuery": {"projectName": self.sources[uid]["jsonData"]["defaultProject"],
                                     "expr": expression, "step": "15s"}}
        else:
            model = {"datasource": {"type": "prometheus", "uid": uid}, "expr": expression,
                     "instant": True, "range": False, "format": "time_series"}
        return self.query(model, end - 60, end)

    def logs(self, model, start, end):
        base = {"datasource": model["datasource"], "queryMode": "Logs", "type": "logAction",
                "region": model["region"]}
        frames = self.query({**base, "subtype": "StartQuery", "queryString": model["expression"],
                             "logGroupNames": model["logGroupNames"]}, start, end)
        require(len(frames) == 1, "CloudWatch query did not return one result")
        if frames[0]["schema"].get("meta", {}).get("custom", {}).get("Status") == "Complete":
            return frames
        query_id = frames[0]["data"]["values"][0][0]
        require(isinstance(query_id, str) and query_id, "CloudWatch query id missing")
        complete = False
        try:
            for _ in range(30):
                time.sleep(2)
                frames = self.query({**base, "subtype": "GetQueryResults", "queryId": query_id}, start, end)
                statuses = [f["schema"].get("meta", {}).get("custom", {}).get("Status") for f in frames]
                require(not any(s in ("Failed", "Cancelled", "Timeout") for s in statuses), "CloudWatch log query failed")
                if statuses and all(s == "Complete" for s in statuses):
                    complete = True
                    return frames
            raise CheckFailed("CloudWatch log query timed out")
        finally:
            if not complete:
                self.query({**base, "subtype": "StopQuery", "queryId": query_id}, start, end)

    def panel(self, title):
        matches = [p for p in self.dashboard["panels"] if p.get("title") == title]
        require(len(matches) == 1, f"dashboard panel missing or duplicated: {title}")
        return matches[0]

    def ai(self, session):
        spec = importlib.util.spec_from_file_location("publish", Path(__file__).resolve().parents[2] /
                                                     ".github/actions/publish-metrics/publish.py")
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        env = os.environ
        context = {"repository": env["GITHUB_REPOSITORY"], "run_id": env["GITHUB_RUN_ID"],
                   "run_attempt": env["GITHUB_RUN_ATTEMPT"], "sha": env["GITHUB_SHA"],
                   "target": env["TARGET"], "environment": "test", "cluster": env["CLUSTER"]}
        context["run_url"] = f"https://github.com/{context['repository']}/actions/runs/{context['run_id']}/attempts/{context['run_attempt']}"
        expected = [publisher.record(Path(env["RUNNER_TEMP"]) / "promote-judge" / name, context) for name in SERVICES]
        start = dt.datetime.fromisoformat(session.state["started_at"]).timestamp()
        end = time.time()
        variables = {"target": env["TARGET"], "environment": "test", "service": "demo-app-.*",
                     "cluster": env["CLUSTER"], "run": env["GITHUB_RUN_ID"]}
        model = interpolate(self.panel("AI에 전달한 smoke 결과와 판단")["targets"][0], variables)
        require(model["logGroupNames"] == [env["OBSERVABILITY_LOG_GROUP"]], "dashboard uses a different evidence log group")
        # Read the raw record through Grafana's CloudWatch identity. No new runner IAM permission.
        raw = {**model, "expression": 'fields @message | filter run_id = ' + json.dumps(context["run_id"])
               + ' and run_attempt = ' + json.dumps(context["run_attempt"])
               + ' and target = ' + json.dumps(context["target"])
               + ' and cluster = ' + json.dumps(context["cluster"])
               + ' and environment = "test" | sort @timestamp desc | limit 100'}
        records = [json.loads(row["@message"]) for row in rows(self.logs(raw, start, end)) if row.get("@message")]
        for record in expected:
            window = record["observation"] or {}
            require(window.get("configured_seconds") == 60 and window.get("ended_at") and window.get("started_at"),
                    "AI observation window is incomplete")
            window_start = dt.datetime.fromisoformat(window["started_at"].replace("Z", "+00:00")).timestamp()
            window_end = dt.datetime.fromisoformat(window["ended_at"].replace("Z", "+00:00")).timestamp()
            # smoke.sh records whole UTC seconds and uses Bash SECONDS; allow one second rounding.
            require(start <= window_start and window_end - window_start >= 59 and window_end <= end + 5,
                    "AI observation window is stale or shorter than 60 seconds")
            require(record["metrics"]["requests"] > 0 and record["metrics"]["green_hash"] ==
                    session.state["green"][record["service"]]["hash"], "AI evidence does not identify this green")
            require(record["decision_source"] == "ai", "AI response is missing; fallback is not a completed AI validation")
            wanted = {k: v for k, v in record.items() if k != "published_at"}
            require(any({k: v for k, v in actual.items() if k != "published_at"} == wanted for actual in records),
                    "Grafana / CloudWatch record differs from original metrics, window, rule or decision")
        panel_rows = list(rows(self.logs(model, start, end)))
        for record in expected:
            matches = [row for row in panel_rows if row.get("event_id") == record["event_id"]]
            require(len(matches) == 1 and str(matches[0].get("run_attempt")) == record["run_attempt"]
                    and matches[0].get("sha") == record["sha"], "AI panel does not show this exact attempt and SHA")
        session.evidence("ai-comparison", {"matched": True, "records": expected, "panel_rows": panel_rows})

    def runtime(self, session):
        env = os.environ
        traffic = json.loads((session.report / "traffic.json").read_text())
        now = time.time()
        # Evidence for T17's AWS + onprem single-screen criterion, even on a GCP run.
        fleet = list(numbers(self.prom('min by(target,service) (time() - timestamp(app_http_response_count_total{'
                                       'target=~"aws|onprem",environment="test",service=~"demo-app-(be|fe)"}))', uid="prometheus")))
        for target in ("aws", "onprem"):
            for name in SERVICES:
                require(any(labels.get("target") == target and labels.get("service") == name and 0 <= age <= 300
                            for labels, age in fleet), f"{target}/{name}: missing fresh central sample")
        uid = "cloud-monitoring" if env["TARGET"] == "gcp" else "prometheus"
        results = []
        for name in SERVICES:
            green = session.state["green"][name]
            selector = ','.join(k + '=' + json.dumps(v) for k, v in
                                {"target": env["TARGET"], "cluster": env["CLUSTER"], "environment": "test",
                                 "service": name, "pod": green["name"]}.items())
            expected = total(traffic["snapshots"]["after"]["be" if name.endswith("-be") else "fe"])
            raw_samples = traffic["snapshots"]["after"]["be" if name.endswith("-be") else "fe"]
            bucket_bounds = {json.loads("{" + key.split("{", 1)[1])["le"] for key in raw_samples
                             if key.startswith("app_http_response_time_seconds_hist_bucket{")}
            expected_buckets = {bound: total(raw_samples, suffix="time_seconds_hist_bucket", le=bound) for bound in bucket_bounds}
            require(expected_buckets and "+Inf" in expected_buckets, "raw application histogram is missing")
            # GCP ingestion can lag. Fixed 5m query windows remain anchored to traffic completion.
            deadline = time.monotonic() + (600 if uid == "cloud-monitoring" else 120)
            while True:
                values = list(numbers(self.prom('sum(app_http_response_count_total{' + selector + '})')))
                buckets = {labels["le"]: value for labels, value in numbers(self.prom(
                    'sum by(le) (app_http_response_time_seconds_hist_bucket{' + selector + '})')) if "le" in labels}
                if values and values[-1][1] == expected and buckets == expected_buckets:
                    break
                require(time.monotonic() < deadline, f"{name}: receiver counters or buckets differ from raw pod metrics")
                time.sleep(15)
            ages = list(numbers(self.prom('max(time() - timestamp(app_http_response_count_total{' + selector + '}))')))
            require(ages and 0 <= ages[-1][1] <= (600 if uid == "cloud-monitoring" else 300), "stale green sample")
            variables = {"target": env["TARGET"], "environment": "test", "service": name,
                         "cluster": env["CLUSTER"], "__rate_interval": "5m"}
            for title in ("요청 / 초", "HTTP 5xx 비율", "응답시간 p95"):
                model = next(t for t in self.panel(title)["targets"] if t["datasource"]["uid"] == uid)
                model = interpolate(model, variables)
                # Same deployed panel expression, narrowed to the selected private green pod.
                obj = model["promQLQuery"] if uid == "cloud-monitoring" else model
                obj["expr"] = re.sub(r'(app_http_response_[a-z_]+)\{',
                                     lambda m: m[1] + '{pod=' + json.dumps(green["name"]) + ',', obj["expr"])
                samples = list(numbers(self.query(model, now - 60, now)))
                require(samples and all(value >= 0 for _, value in samples), f"{title}: no finite panel value")
                value = samples[-1][1]
                if title == "요청 / 초":
                    require(value > 0, "request rate is missing")
                if title == "HTTP 5xx 비율":
                    require((0 < value <= 100) if name.endswith("-be") else value == 0, "error panel does not reflect controlled errors")
                if title == "응답시간 p95" and name.endswith("-be"):
                    require(value >= 250, "histogram p95 does not reflect 300ms delay")
                results.append({"service": name, "panel": title, "value": value, "evaluation_time": now})
        # Read resource panels through their real backing sources. GCP must honor service selection.
        for title in ("AWS CPU · Container Insights", "AWS 메모리 · Container Insights"):
            frames = self.query(self.panel(title)["targets"][0], now - 600, now)
            require(fresh(frames, now, 300), "CloudWatch Container Insights has no fresh resource data")
        resource_titles = ("GCP 컨테이너 CPU", "GCP 컨테이너 메모리") if env["TARGET"] == "gcp" else ("CPU 사용량", "메모리 사용량")
        for name in SERVICES:
            variables = {"target": env["TARGET"], "environment": "test", "service": name, "cluster": env["CLUSTER"]}
            for title in resource_titles:
                model = interpolate(self.panel(title)["targets"][0], variables)
                if env["TARGET"] == "gcp":
                    require(f'pod_name=~"({name})-.*"' in model["promQLQuery"]["expr"], "GCP resource service filter missing")
                frames = self.query(model, now - 600, now)
                require(fresh(frames, now, 600 if env["TARGET"] == "gcp" else 300), f"{name}/{title}: no fresh resource data")
        session.evidence("runtime-comparison", {"fleet_sample_ages": fleet, "panels": results})

    def verify(self, session):
        self.preflight()
        try:
            self.ai(session)
            session.traffic()
            self.runtime(session)
        finally:
            session.evidence("grafana-queries", self.queries)
