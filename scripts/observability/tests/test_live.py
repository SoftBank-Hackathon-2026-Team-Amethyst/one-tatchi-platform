import copy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live
import grafana


def baseline():
    return {ns: {name: {"uid": ns + name, "active": "blue", "images": {"app": "r@sha256:old"},
                        "marker": None, "phase": "Healthy"} for name in live.SERVICES} for ns in ("test", "prod")}


def frame(fields, columns, status=None):
    return {"schema": {"fields": fields, "meta": {"custom": {"Status": status}}}, "data": {"values": columns}}


class SessionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"T17_DIR": self.temp.name, "NAMESPACE": "test", "TARGET": "aws", "CLUSTER": "one-tatchi",
            "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
            "GITHUB_SHA": "abc", "GITHUB_REPOSITORY": "example/demo", "IMAGES": "{}", "OBSERVABILITY_LOG_GROUP": "/evidence",
            "SERVICES": json.dumps([{"name": name} for name in live.SERVICES]), "OBSERVABILITY_URL": "https://example.com/grafana"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.session = live.Session()
        self.base = baseline()

    def seeded(self):
        self.session.state = {"baseline": self.base, "marker": "123-2", "green": {}, "chaos": None}
        return self.session

    def test_reject_prod_or_non_main_before_kubernetes(self):
        for change in ({"NAMESPACE": "prod"}, {"GITHUB_REF": "refs/heads/yolo/test"}, {"GITHUB_EVENT_NAME": "push"}):
            with self.subTest(change=change), patch.dict(os.environ, change), patch.object(live, "kube") as kubectl:
                with self.assertRaises(live.CheckFailed):
                    self.session.preflight()
                kubectl.assert_not_called()

    def test_reject_first_install_and_pending_release(self):
        for phase in ("Progressing", "Paused", "Degraded"):
            with self.subTest(phase=phase), patch.object(live, "snapshot", return_value={"phase": phase}):
                with self.assertRaisesRegex(live.CheckFailed, "existing healthy"):
                    self.session.preflight()
                self.assertFalse(self.session.path.exists())

    def test_grafana_spa_failure_prevents_saved_preflight(self):
        with patch.object(live, "snapshot", side_effect=lambda name, ns: self.base[ns][name]), \
                patch.object(grafana.Client, "preflight", side_effect=live.CheckFailed("routing")):
            with self.assertRaises(live.CheckFailed):
                self.session.preflight()
        self.assertFalse(self.session.path.exists())

    def test_preflight_saves_public_identity_without_state_or_credentials(self):
        with patch.object(live, "snapshot", side_effect=lambda name, ns: self.base[ns][name]), patch.object(grafana.Client, "preflight"):
            self.session.preflight()
        saved = json.loads(self.session.path.read_text())
        self.assertEqual(saved["marker"], "123-2")
        self.assertEqual(self.session.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(set(saved["baseline"]), {"test", "prod"})

    def test_guard_refuses_promoted_or_replaced_blue_and_foreign_run(self):
        s = self.seeded()
        for change in ({"active": "green"}, {"uid": "replacement"}, {"marker": "another-run"}):
            current = {**self.base["test"]["demo-app-be"], "marker": "123-2", **change}
            with self.subTest(change=change), patch.object(live, "snapshot", return_value=current):
                with self.assertRaises(live.CheckFailed):
                    live.guard(s.state, "demo-app-be", owned=True)

    def test_cleanup_partial_deploy_aborts_only_own_be(self):
        s = self.seeded()

        def snapshot(name, ns):
            result = copy.deepcopy(self.base[ns][name])
            if ns == "test" and name == "demo-app-be":
                result.update(marker="123-2", phase="Paused")
            return result

        blue = {"metadata": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        with patch.object(live, "snapshot", side_effect=snapshot), patch.object(live, "pods", return_value=[blue]), \
                patch.object(live, "kube", return_value={"items": []}), patch.object(live, "run") as run:
            s.cleanup()
        run.assert_called_once_with("kubectl", "argo", "rollouts", "abort", "demo-app-be", "-n", "test")
        report = json.loads((s.report / "cleanup.json").read_text())
        self.assertEqual(report["services"]["demo-app-fe"], "not_deployed")
        self.assertFalse(report["failures"])

    def test_cleanup_foreign_green_never_aborted(self):
        s = self.seeded()

        def snapshot(name, ns):
            return {**self.base[ns][name], **({"marker": "foreign"} if ns == "test" else {})}

        with patch.object(live, "snapshot", side_effect=snapshot), patch.object(live, "run") as run:
            with self.assertRaisesRegex(live.CheckFailed, "cleanup incomplete"):
                s.cleanup()
        run.assert_not_called()

    def test_unreachable_chaos_still_aborts_own_green(self):
        s = self.seeded()
        s.state["chaos"] = {"latencyMs": 0, "errorRate": 0, "dbError": False}
        s.state["green"]["demo-app-be"] = {"hash": "green", "name": "be-green"}

        def snapshot(name, ns):
            return {**self.base[ns][name], **({"marker": "123-2"} if ns == "test" and name.endswith("-be") else {})}

        blue = {"metadata": {}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}}
        with patch.object(live, "snapshot", side_effect=snapshot), patch.object(live, "pod_guard", side_effect=live.CheckFailed("gone")), \
                patch.object(live, "pods", return_value=[blue]), patch.object(live, "kube", return_value={"items": []}), patch.object(live, "run") as run:
            s.cleanup()
        self.assertEqual(run.call_count, 1)
        self.assertIn("restore", (s.report / "cleanup.json").read_text())

    def test_failure_during_traffic_restores_chaos_and_keeps_evidence(self):
        s = self.seeded()
        s.state["chaos"] = {"latencyMs": 0, "errorRate": 0, "dbError": False}
        for name in live.SERVICES:
            s.state["green"][name] = {"name": name, "before_smoke": {}}

        @contextmanager
        def forward(name, port):
            yield f"http://{name}:{port}"

        def request(url, **kwargs):
            if url.endswith("/metrics"):
                return ""
            if kwargs.get("expected") == 500:
                raise live.CheckFailed("unexpected HTTP status")
            return "{}"

        with patch.object(live, "forward", side_effect=forward), patch.object(live, "pod_guard"), \
                patch.object(live, "request", side_effect=request), patch.object(s, "set_chaos") as chaos, patch.object(live.time, "sleep"):
            with self.assertRaises(live.CheckFailed):
                s.traffic()
        self.assertEqual(chaos.call_args.args[1], s.state["chaos"])
        self.assertTrue((s.report / "traffic.json").exists())


class MetricsTest(unittest.TestCase):
    def test_label_order_and_escaped_values(self):
        a = live.metrics('app_http_response_count_total{method="GET",status="200"} 4\n')
        b = live.metrics('app_http_response_count_total{status="200",method="GET"} 24\nprocess_cpu_seconds_total 100\n')
        self.assertEqual(live.delta(a, b), 20)
        self.assertEqual(live.delta(a, b, status="500"), 0)

    def test_counter_reset_is_failure(self):
        with self.assertRaises(live.CheckFailed):
            live.delta(live.metrics('app_http_response_count_total 30'), live.metrics('app_http_response_count_total 5'))

    def test_histogram_bucket_not_double_counted_as_requests(self):
        data = live.metrics('app_http_response_count_total{status="200"} 10\n'
                            'app_http_response_time_seconds_hist_bucket{le="0.25"} 0\n'
                            'app_http_response_time_seconds_hist_bucket{le="+Inf"} 10\n'
                            'app_http_response_time_seconds_hist_count 10\n')
        self.assertEqual(live.total(data), 10)
        self.assertEqual(live.total(data, suffix="time_seconds_hist_bucket", le="0.25"), 0)

    def test_nonfinite_counter_rejected(self):
        with self.assertRaises(live.CheckFailed):
            live.metrics('app_http_response_count_total NaN')


class GrafanaTest(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"OBSERVABILITY_URL": "https://example.com/grafana", "TARGET": "aws"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = grafana.Client()
        self.client.sources = {"cloudwatch": {"jsonData": {"defaultRegion": "ap-northeast-2"}}}

    def test_spa_is_not_grafana_health(self):
        with patch.object(grafana, "request", return_value="<!doctype html><html>app</html>"):
            with self.assertRaisesRegex(live.CheckFailed, "non-JSON"):
                self.client.preflight()

    def test_http_or_embedded_credentials_rejected(self):
        for url in ("http://example.com/grafana", "https://user:secret@example.com/grafana", "https://example.com/"):
            with self.subTest(url=url), patch.dict(os.environ, {"OBSERVABILITY_URL": url}):
                with self.assertRaises(live.CheckFailed):
                    grafana.Client()

    def test_query_backend_error_is_not_empty_success(self):
        with patch.object(self.client, "api", return_value={"results": {"A": {"error": "access denied", "status": 403}}}):
            with self.assertRaises(live.CheckFailed):
                self.client.query({"datasource": {"uid": "cloudwatch"}}, 100, 200)

    def test_saved_panels_receive_frontend_query_defaults(self):
        with patch.object(self.client, "api", return_value={"results": {"A": {"frames": []}}}) as api:
            self.client.query({"datasource": {"uid": "prometheus"}, "expr": "up"}, 100, 200)
            self.assertTrue(api.call_args.args[1]["queries"][0]["range"])
            self.client.query({"datasource": {"uid": "cloudwatch"}, "queryMode": "Metrics", "expression": "SEARCH(...)"}, 100, 200)
            self.assertEqual(api.call_args.args[1]["queries"][0]["type"], "timeSeriesQuery")
            self.client.prom("up", uid="prometheus")
            self.assertFalse(api.call_args.args[1]["queries"][0]["range"])
            self.assertTrue(api.call_args.args[1]["queries"][0]["instant"])

    def test_logs_poll_until_complete(self):
        started = frame([{"name": "queryId", "type": "string"}], [["query-1"]], "Running")
        done = frame([{"name": "event_id", "type": "string"}], [["event-1"]], "Complete")
        with patch.object(self.client, "query", side_effect=[[started], [done]]) as query, patch.object(grafana.time, "sleep"):
            output = self.client.logs({"datasource": {"uid": "cloudwatch"}, "region": "default", "expression": "fields @message", "logGroupNames": ["/evidence"]}, 100, 200)
        self.assertEqual(list(grafana.rows(output)), [{"event_id": "event-1"}])
        self.assertEqual(query.call_args_list[1].args[0]["subtype"], "GetQueryResults")
        self.assertEqual(query.call_args_list[1].args[0]["queryId"], "query-1")

    def test_failed_logs_query_stopped_and_not_accepted(self):
        started = frame([{"name": "queryId", "type": "string"}], [["query-1"]], "Running")
        failed = frame([], [], "Failed")
        with patch.object(self.client, "query", side_effect=[[started], [failed], []]) as query, patch.object(grafana.time, "sleep"):
            with self.assertRaises(live.CheckFailed):
                self.client.logs({"datasource": {"uid": "cloudwatch"}, "region": "default", "expression": "fields @message", "logGroupNames": ["/evidence"]}, 100, 200)
        self.assertEqual(query.call_args.args[0]["subtype"], "StopQuery")

    def test_freshness_requires_finite_sample_at_recent_timestamp(self):
        data = [frame([{"type": "time"}, {"type": "number"}], [[1000, 990000], [5, None]])]
        self.assertFalse(grafana.fresh(data, 1000, 300))
        data[0]["data"]["values"][1][1] = 0
        self.assertTrue(grafana.fresh(data, 1000, 300))

    def test_template_interpolation_keeps_regex_and_cluster_literal_valid(self):
        actual = grafana.interpolate('x{target=~"${target:regex}",cluster=~"$cluster",pod_name=~"${service:regex}-.*"}[$__rate_interval]',
                                     {"target": "aws", "cluster": "one-tatchi", "service": "demo-app-be", "__rate_interval": "5m"})
        self.assertEqual(actual, 'x{target=~"aws",cluster=~"one-tatchi",pod_name=~"demo-app-be-.*"}[5m]')

    def test_gcp_dashboard_cpu_and_memory_filter_service(self):
        path = Path(__file__).resolve().parents[3] / "modules/observability/aws/dashboards/deploy-overview.json.tftpl"
        dashboard = json.loads(path.read_text().replace("${gcp_hidden}", "false"))
        panels = [p for p in dashboard["panels"] if p["title"].startswith("GCP 컨테이너")]
        self.assertEqual(len(panels), 2)
        for panel in panels:
            expr = panel["targets"][0]["promQLQuery"]["expr"]
            self.assertIn('pod_name=~"($${service:raw})-.*"', expr)
            for value in ("demo-app-be", "demo-app-.*", "demo-app-be|demo-app-fe"):
                expanded = grafana.interpolate(expr.replace("$$", "$"), {"service": value})
                pattern = re.search(r'pod_name=~"([^"]+)"', expanded)[1]
                self.assertIsNotNone(re.fullmatch(pattern, "demo-app-be-green-pod"))
                self.assertIsNone(re.fullmatch(pattern, "unrelated-green-pod"))


if __name__ == "__main__":
    unittest.main()
