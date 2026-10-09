import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

spec = importlib.util.spec_from_file_location("publish", Path(__file__).parents[1] / "publish.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "demo-app-be"
        self.path.mkdir()
        self.metrics = {"release": "demo-app-be", "requests": 20, "failed": 1, "error_rate": 5,
                        "p95_ms": 19, "pods": {"count": 1, "ready": 1, "restarts": 0},
                        "thresholds": {"max_p95_ms": 2000}, "rule": {"verdict": "fail"}}
        self.context = {"repository": "team/app", "run_id": "12", "run_attempt": "1",
                        "target": "aws", "environment": "test", "cluster": "cluster", "sha": "abcdef"}

    def write(self):
        (self.path / "metrics.json").write_text(json.dumps(self.metrics))

    def test_preserves_exact_values_and_decision(self):
        self.write()
        window = {"started_at": "2026-10-09T00:00:00Z", "ended_at": "2026-10-09T00:01:00Z", "configured_seconds": 60}
        (self.path / "observation.json").write_text(json.dumps(window))
        (self.path / "judgment.json").write_text(json.dumps({"decision": "abort", "reason": "one failure"}))
        result = publish.record(self.path, self.context)
        self.assertEqual(result["metrics"]["p95_ms"], 19)
        self.assertEqual(result["metrics"]["error_rate"], 5)
        self.assertEqual(result["decision"], "abort")
        self.assertIsNone(result["executed"])
        self.assertEqual(result["observation"], window)

    def test_missing_is_not_zero(self):
        self.metrics = {"release": "demo-app-be", "rule": {"verdict": "fail"}}
        self.write()
        result = publish.record(self.path, self.context)
        self.assertIsNone(result["metrics"]["requests"])
        self.assertIsNone(result["metrics"]["pods"])
        self.assertIsNone(result["observation"])

    def test_run_and_attempt_identity(self):
        self.write()
        first = publish.record(self.path, self.context)["event_id"]
        self.assertEqual(first, publish.record(self.path, self.context)["event_id"])
        self.assertNotEqual(first, publish.record(self.path, {**self.context, "run_attempt": "2"})["event_id"])
        self.assertNotEqual(first, publish.record(self.path, {**self.context, "target": "onprem"})["event_id"])

    def test_rejects_mismatched_service_and_invalid_numbers(self):
        self.metrics["release"] = "another-service"
        self.write()
        with self.assertRaises(ValueError):
            publish.record(self.path, self.context)
        self.metrics["release"] = "demo-app-be"
        for value in [True, -1, float("nan"), float("inf"), "5"]:
            self.metrics["p95_ms"] = value
            self.write()
            with self.assertRaises(ValueError):
                publish.record(self.path, self.context)

    def test_does_not_export_request_payloads(self):
        self.metrics["failures"] = [{"body": "private-data"}]
        self.write()
        self.assertNotIn("private-data", json.dumps(publish.record(self.path, self.context)))

    def invoke(self, fake_aws):
        argv = ["publish.py", "--report-dir", self.tmp.name, "--log-group", "/evidence",
                "--target", "aws", "--environment", "test", "--cluster", "cluster", "--sha", "abcdef"]
        with patch("sys.argv", argv), patch.dict("os.environ", {
            "GITHUB_REPOSITORY": "team/app", "GITHUB_RUN_ID": "12", "GITHUB_RUN_ATTEMPT": "1"
        }), patch.object(publish, "aws", side_effect=fake_aws):
            publish.main()

    def test_existing_stream_retry_sends_exact_evidence(self):
        self.write()
        events = []
        def fake_aws(*args):
            if args[0] == "create-log-stream":
                raise subprocess.CalledProcessError(1, "aws", stderr=b"ResourceAlreadyExistsException")
            events.extend(json.loads(Path(args[-1].removeprefix("file://")).read_text()))
            return {}
        self.invoke(fake_aws)
        self.assertEqual(len(events), 1)
        self.assertEqual(json.loads(events[0]["message"])["metrics"]["requests"], 20)

    def test_permission_error_stops_publication(self):
        self.write()
        calls = []
        def fake_aws(*args):
            calls.append(args[0])
            raise subprocess.CalledProcessError(1, "aws", stderr=b"AccessDeniedException")
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(fake_aws)
        self.assertEqual(calls, ["create-log-stream"])

    def test_rejected_events_are_reported_as_failure(self):
        self.write()
        with self.assertRaises(ValueError):
            self.invoke(lambda *args: {"rejectedLogEventsInfo": {"tooNewLogEventStartIndex": 0}})


if __name__ == "__main__":
    unittest.main()
