import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("resource_metrics", Path(__file__).resolve().parents[1] / "resource_metrics.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class ResourceMetricsTests(unittest.TestCase):
    def test_registered_api_with_real_pod_samples(self):
        def read(args):
            value = {"status": {"conditions": [{"type": "Available", "status": "True"}]}} if "apiservice" in args else {
                "items": [{"timestamp": "2026-10-11T00:00:00Z", "window": "15s",
                           "containers": [{"usage": {"cpu": "1m", "memory": "32Mi"}}]}]}
            return subprocess.CompletedProcess([], 0, json.dumps(value), "")
        result = metrics.inspect_metrics(["test", "prod"], read)
        self.assertTrue(result["available"])
        self.assertEqual(result["namespaces"]["prod"]["samples"], 1)

    def test_empty_samples_are_not_success(self):
        def read(args):
            value = {"status": {"conditions": [{"type": "Available", "status": "True"}]}} if "apiservice" in args else {"items": []}
            return subprocess.CompletedProcess([], 0, json.dumps(value), "")
        self.assertFalse(metrics.inspect_metrics(["test"], read)["available"])

    def test_unavailable_or_denied_never_exposes_credentials(self):
        for code, stdout in [(1, "private token"), (0, "{}"), (0, "invalid JSON")]:
            result = metrics.inspect_metrics(["test"], lambda _: subprocess.CompletedProcess([], code, stdout, "private token"))
            self.assertFalse(result["available"])
            self.assertNotIn("private", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
