import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("visibility", Path(__file__).resolve().parents[1] / "verify-helm-state.py")
visibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visibility)


class HelmVisibilityTests(unittest.TestCase):
    def state(self):
        return json.dumps({"values": {"root_module": {"child_modules": [{"resources": [{
            "address": "module.cluster_addons.helm_release.argo_rollouts", "mode": "managed", "type": "helm_release",
            "values": {"namespace": "argo-rollouts", "name": "argo-rollouts"},
        }]}]}}})

    def test_missing_release_fails_instead_of_accepting_creation(self):
        with patch.object(visibility, "read", side_effect=[self.state(), "yes", "[]"]):
            with self.assertRaisesRegex(RuntimeError, "not visible"):
                visibility.verify("root")

    def test_namespace_permission_denial_stops_lookup(self):
        with patch.object(visibility, "read", side_effect=[self.state(), "no"]) as read:
            with self.assertRaisesRegex(RuntimeError, "cannot list"):
                visibility.verify("root")
            self.assertEqual(read.call_count, 2)

    def test_child_module_release_is_checked(self):
        with patch.object(visibility, "read", side_effect=[self.state(), "yes", '[{"name":"argo-rollouts","status":"deployed"}]']) as read:
            visibility.verify("root")
            self.assertEqual(read.call_args.args[0][:2], ["helm", "list"])

    def test_provider_errors_are_redacted(self):
        with patch.object(visibility.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "token=private")):
            with self.assertRaises(RuntimeError) as error:
                visibility.read(["terraform", "show", "-json"])
            self.assertNotIn("private", str(error.exception))


if __name__ == "__main__":
    unittest.main()
