import copy
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import grafana
import live


def frames(records):
    return [{"schema": {"fields": [{"name": "@message", "type": "string"}]},
             "data": {"values": [[json.dumps(record) for record in records]]}}]


class EvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {"RUNNER_TEMP": self.temp.name, "T17_DIR": self.temp.name + "/t17",
            "OBSERVABILITY_URL": "https://example.com/grafana", "TARGET": "aws", "CLUSTER": "one-tatchi",
            "GITHUB_REPOSITORY": "example/demo", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2", "GITHUB_SHA": "abc",
            "OBSERVABILITY_LOG_GROUP": "/evidence"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.session = live.Session()
        now = dt.datetime.now(dt.timezone.utc)
        self.session.state = {"started_at": (now - dt.timedelta(seconds=180)).isoformat(), "green": {}}
        for name in live.SERVICES:
            directory = Path(self.temp.name) / "promote-judge" / name
            directory.mkdir(parents=True)
            (directory / "metrics.json").write_text(json.dumps({"release": name, "requests": 20, "failed": 0, "error_rate": 0,
                "p95_ms": 20, "max_ms": 30, "green_hash": "green", "pods": {"count": 1, "ready": 1, "restarts": 0},
                "thresholds": {"max_error_rate": 0, "max_p95_ms": 2000, "max_restarts": 0}, "rule": {"verdict": "pass", "reasons": []}}))
            (directory / "observation.json").write_text(json.dumps({"configured_seconds": 60,
                "started_at": (now - dt.timedelta(seconds=120)).isoformat(), "ended_at": (now - dt.timedelta(seconds=60)).isoformat()}))
            (directory / "judgment.json").write_text(json.dumps({"source": "ai", "decision": "promote", "reason": "healthy"}))
            self.session.state["green"][name] = {"hash": "green"}
        spec = importlib.util.spec_from_file_location("publisher_test", Path(__file__).resolve().parents[3] / ".github/actions/publish-metrics/publish.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        context = {"repository": "example/demo", "run_id": "123", "run_attempt": "2", "sha": "abc", "target": "aws",
                   "environment": "test", "cluster": "one-tatchi", "run_url": "https://github.com/example/demo/actions/runs/123/attempts/2"}
        self.records = [module.record(Path(self.temp.name) / "promote-judge" / name, context) for name in live.SERVICES]
        self.client = grafana.Client()
        self.client.dashboard = {"panels": [{"title": "AI에 전달한 smoke 결과와 판단", "targets": [{"datasource": {"uid": "cloudwatch"},
            "region": "default", "logGroupNames": ["/evidence"], "expression": "fields event_id, run_attempt, sha"}]}]}

    def run_compare(self, records=None):
        panel = [{"schema": {"fields": [{"name": k, "type": "string"} for k in ("event_id", "run_attempt", "sha")]},
                  "data": {"values": [[record[k] for record in self.records] for k in ("event_id", "run_attempt", "sha")]}}]
        with patch.object(self.client, "logs", side_effect=[frames(records or self.records), panel]):
            self.client.ai(self.session)

    def test_exact_artifact_and_panel_match(self):
        self.run_compare()
        self.assertTrue(json.loads((self.session.report / "ai-comparison.json").read_text())["matched"])

    def test_other_attempt_or_sha_or_rule_or_window_cannot_pass(self):
        for field, value in (("run_attempt", "1"), ("sha", "other"), ("rule", {"verdict": "fail"}), ("observation", {})):
            with self.subTest(field=field):
                changed = copy.deepcopy(self.records)
                changed[0][field] = value
                with self.assertRaisesRegex(live.CheckFailed, "differs from original"):
                    self.run_compare(changed)

    def test_rounded_or_recalculated_metric_cannot_pass(self):
        changed = copy.deepcopy(self.records)
        changed[0]["metrics"]["p95_ms"] = 21
        with self.assertRaisesRegex(live.CheckFailed, "differs from original"):
            self.run_compare(changed)

    def test_fallback_is_reported_as_incomplete_ai_validation(self):
        for name in live.SERVICES:
            path = Path(self.temp.name) / "promote-judge" / name / "judgment.json"
            path.write_text(json.dumps({"source": "fallback", "decision": "abort", "reason": "no API key"}))
        with self.assertRaisesRegex(live.CheckFailed, "AI response is missing"):
            self.run_compare()

    def test_missing_observation_end_fails(self):
        path = Path(self.temp.name) / "promote-judge" / live.SERVICES[0] / "observation.json"
        path.write_text(json.dumps({"configured_seconds": 60, "started_at": "2026-10-10T00:00:00Z", "ended_at": None}))
        with self.assertRaisesRegex(live.CheckFailed, "window is incomplete"):
            self.run_compare()

    def test_wrong_green_hash_fails(self):
        self.session.state["green"][live.SERVICES[0]]["hash"] = "another-green"
        with self.assertRaisesRegex(live.CheckFailed, "does not identify this green"):
            self.run_compare()

    def test_stale_or_short_actual_window_fails(self):
        path = Path(self.temp.name) / "promote-judge" / live.SERVICES[0] / "observation.json"
        for window in ({"configured_seconds": 60, "started_at": "2020-01-01T00:00:00Z", "ended_at": "2020-01-01T00:01:00Z"},
                       {"configured_seconds": 60, "started_at": self.session.state["started_at"], "ended_at": self.session.state["started_at"]}):
            with self.subTest(window=window):
                path.write_text(json.dumps(window))
                with self.assertRaisesRegex(live.CheckFailed, "stale or shorter"):
                    self.run_compare()


if __name__ == "__main__":
    unittest.main()
