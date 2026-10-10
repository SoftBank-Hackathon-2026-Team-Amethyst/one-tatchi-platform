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

    def test_helm_list_uses_helm4_flags(self):
        with patch.object(visibility, "read", side_effect=[self.state(), "yes", '[{"name":"argo-rollouts","status":"deployed"}]']) as read:
            visibility.verify("root")
            self.assertNotIn("--all", read.call_args.args[0])

    def test_can_i_no_with_exit_code_one_reports_permission(self):
        results = [subprocess.CompletedProcess([], 0, self.state(), ""), subprocess.CompletedProcess([], 1, "no\n", "")]
        with patch.object(visibility.subprocess, "run", side_effect=results):
            with self.assertRaisesRegex(RuntimeError, "cannot list"):
                visibility.verify("root")

    def test_real_can_i_denial_reports_namespace(self):
        for stdout in ("no\n", 'no - requires one of ["container.secrets.list"] permission(s).\n'):
            results = [subprocess.CompletedProcess([], 0, self.state(), ""),
                       subprocess.CompletedProcess([], 1, stdout, "private diagnostic")]
            with self.subTest(stdout=stdout), patch.object(visibility.subprocess, "run", side_effect=results):
                with self.assertRaisesRegex(RuntimeError, "cannot list Helm release records in namespace argo-rollouts"):
                    visibility.verify("root")

    def test_can_i_transport_or_authentication_failure_is_not_permission_denial(self):
        results = [subprocess.CompletedProcess([], 0, self.state(), ""),
                   subprocess.CompletedProcess([], 1, "", "private credential")]
        with patch.object(visibility.subprocess, "run", side_effect=results):
            with self.assertRaises(RuntimeError) as error:
                visibility.verify("root")
            self.assertIn("kubectl read failed", str(error.exception))
            self.assertNotIn("private", str(error.exception))

    def test_empty_or_wrong_backend_is_not_a_successful_visibility_check(self):
        with patch.object(visibility, "read", return_value='{"values": {"root_module": {}}}'):
            with self.assertRaisesRegex(RuntimeError, "no state-owned Helm"):
                visibility.verify("root")

    def test_provider_errors_are_redacted(self):
        with patch.object(visibility.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "token=private")):
            with self.assertRaises(RuntimeError) as error:
                visibility.read(["terraform", "show", "-json"])
            self.assertNotIn("private", str(error.exception))


if __name__ == "__main__":
    unittest.main()
