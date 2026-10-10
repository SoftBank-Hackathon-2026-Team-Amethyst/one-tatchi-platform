import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live
import grafana


def sample(value, labels=None):
    return {"schema": {"fields": [{"name": "Time", "type": "time"}, {"name": "Value", "type": "number", "labels": labels or {}}]},
            "data": {"values": [[1000000], [value]]}}


class RuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"T17_DIR": self.temp.name, "OBSERVABILITY_URL": "https://example.com/grafana", "TARGET": "aws", "CLUSTER": "one-tatchi"})
        env.start()
        self.addCleanup(env.stop)
        self.session = live.Session()
        self.session.state = {"green": {name: {"name": name + "-green"} for name in live.SERVICES}}
        self.raw = {}
        for service, count, fast in (("be", 37, 27), ("fe", 21, 21)):
            self.raw[service] = live.metrics(f'app_http_response_count_total{{status="200"}} {count}\n'
                f'app_http_response_time_seconds_hist_bucket{{le="0.25"}} {fast}\n'
                f'app_http_response_time_seconds_hist_bucket{{le="+Inf"}} {count}\n')
        self.session.evidence("traffic", {"snapshots": {"after": self.raw}})
        path = Path(__file__).resolve().parents[3] / "modules/observability/aws/dashboards/deploy-overview.json.tftpl"
        self.client = grafana.Client()
        self.client.dashboard = json.loads(path.read_text().replace("${gcp_hidden}", "false").replace("$$", "$"))

    def prom(self, expr, **kwargs):
        if "min by(target,service)" in expr:
            return [sample(10, {"target": target, "service": name}) for target in ("aws", "onprem") for name in live.SERVICES]
        be = 'service="demo-app-be"' in expr
        if "timestamp" in expr:
            return [sample(5)]
        if "sum by(le)" in expr:
            return [sample(27 if be else 21, {"le": "0.25"}), sample(37 if be else 21, {"le": "+Inf"})]
        return [sample(37 if be else 21)]

    def query(self, model, start, end):
        expr = model.get("expr", "")
        if "app_http_response_" in expr:
            self.assertIn('pod="demo-app-', expr)
            self.assertNotIn("$", expr)
        if "histogram_quantile" in expr:
            return [sample(400)]
        if 'status=~"5.."' in expr:
            return [sample(16 if "demo-app-be" in expr else 0)]
        return [sample(1)]

    def test_raw_counts_buckets_panels_and_fleet_match(self):
        with patch.object(self.client, "prom", side_effect=self.prom), patch.object(self.client, "query", side_effect=self.query), patch.object(grafana.time, "time", return_value=1000):
            self.client.runtime(self.session)
        report = json.loads((self.session.report / "runtime-comparison.json").read_text())
        self.assertEqual(len(report["panels"]), 6)
        self.assertEqual(len(report["fleet_sample_ages"]), 4)

    def test_matching_counter_with_wrong_histogram_cannot_pass(self):
        def wrong_bucket(expr, **kwargs):
            values = self.prom(expr, **kwargs)
            if "sum by(le)" in expr:
                values[0]["data"]["values"][1][0] = 999
            return values

        with patch.object(self.client, "prom", side_effect=wrong_bucket), patch.object(grafana.time, "monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(live.CheckFailed, "counters or buckets differ"):
                self.client.runtime(self.session)

    def test_onprem_context_and_canonical_bucket_bounds(self):
        for service, count in (("be", 37), ("fe", 21)):
            self.raw[service].update(live.metrics(f'app_http_response_time_seconds_hist_bucket{{le="1"}} {count}\n'))
        self.session.evidence("traffic", {"snapshots": {"after": self.raw}})

        def receiver(expr, **kwargs):
            if 'min by(target,service)' not in expr:
                self.assertIn('cluster="onetouch-hyeongrae"', expr)
                self.assertNotIn('k3d-', expr)
            values = self.prom(expr, **kwargs)
            if 'sum by(le)' in expr:
                values.append(sample(37 if 'demo-app-be' in expr else 21, {"le": "1.0"}))
                # GCP returns a range; only its latest point represents the raw snapshot.
                for value in values:
                    value["data"]["values"] = [[999000, 1000000], [0, value["data"]["values"][1][0]]]
            return values

        def panel(model, start, end):
            self.assertNotIn('k3d-', json.dumps(model))
            return self.query(model, start, end)

        with patch.dict(os.environ, {"TARGET": "onprem", "CLUSTER": "k3d-onetouch-hyeongrae"}), \
                patch.object(self.client, "prom", side_effect=receiver), patch.object(self.client, "query", side_effect=panel), \
                patch.object(grafana.time, "time", return_value=1000):
            self.client.runtime(self.session)
            self.assertEqual(os.environ["CLUSTER"], "k3d-onetouch-hyeongrae")

    def test_bucket_bounds_reject_ambiguous_or_invalid_values(self):
        for samples in ([("1", 1), ("1.0", 1)], [("NaN", 1)], [("invalid", 1)]):
            with self.subTest(samples=samples), self.assertRaises(live.CheckFailed):
                grafana.bucket_values(samples)

    def test_cloud_cluster_names_are_not_rewritten(self):
        for target in ("aws", "gcp"):
            self.assertEqual(grafana.metrics_cluster(target, "k3d-example"), "k3d-example")


if __name__ == "__main__":
    unittest.main()
