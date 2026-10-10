import base64
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import observability as obs


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.settings = obs.settings("https://metrics.example.com/api/v1/write",
                                     "https://example.com/grafana/d/deploy-overview")

    def plan(self, address=obs.ADDRESS, actions=None):
        return {"complete": True, "variables": {key: {"value": value} for key, value in self.settings.items()},
                "resource_changes": [{"address": address, "change": {"actions": actions or ["update"]}}]}

    def test_only_existing_collector_update_is_allowed(self):
        self.assertEqual(obs.check_plan(self.plan(), self.settings), [obs.ADDRESS])
        for actions in (["create"], ["delete"], ["delete", "create"]):
            with self.assertRaises(RuntimeError):
                obs.check_plan(self.plan(actions=actions), self.settings)
        with self.assertRaises(RuntimeError):
            obs.check_plan(self.plan(address='module.database["prod"].kubernetes_secret_v1.credentials'), self.settings)

    def test_configuration_override_and_incomplete_plan_are_rejected(self):
        plan = self.plan()
        plan["variables"]["metrics_remote_write_url"]["value"] = "https://unexpected.example.com/api/v1/write"
        with self.assertRaises(RuntimeError):
            obs.check_plan(plan, self.settings)
        plan = self.plan()
        plan["complete"] = False
        with self.assertRaises(RuntimeError):
            obs.check_plan(plan, self.settings)

    def test_noop_is_valid(self):
        self.assertEqual(obs.check_plan(self.plan(actions=["no-op"]), self.settings), [])

    def test_receiver_requires_tls_without_embedded_credentials(self):
        for url in ("http://example.com/api/v1/write", "https://user:pass@example.com/api/v1/write",
                    "https://example.com/query", "https://example.com/api/v1/write?password=x"):
            with self.assertRaises(ValueError):
                obs.settings(url, "https://example.com/grafana/d/deploy-overview")

    def test_secret_body_has_only_remote_write_credentials(self):
        data = json.loads(obs.secret_payload("private-example"))
        self.assertEqual(data["metadata"], {"name": obs.SECRET, "namespace": "monitoring"})
        self.assertEqual(base64.b64decode(data["data"]["password"]).decode(), "private-example")
        with self.assertRaises(ValueError):
            obs.secret_payload("")

    def test_failed_child_does_not_expose_stdin_or_provider_output(self):
        child = subprocess.CompletedProcess(["kubectl"], 1, "private-example", "credential=private-example")
        with patch.object(obs.subprocess, "run", return_value=child):
            with self.assertRaises(RuntimeError) as error:
                obs.command(["kubectl", "apply", "-f", "-"], input="private-example")
        self.assertNotIn("private-example", str(error.exception))

    @contextmanager
    def device(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {"serial": 4, "lineage": "fixture", "resources": [{
                "module": "module.observability", "type": "helm_release", "name": "metrics",
                "instances": [{"attributes": {"name": "deploy-metrics", "namespace": "monitoring"}}],
            }]}
            (root / "terraform.tfstate").write_text(json.dumps(state))
            settings_path = root / "t17-metrics.auto.tfvars.json"
            settings_path.write_text('{"previous": true}\n')
            config = {"terraform_root": str(root), "home": str(root), "cluster": "fixture", "profile": "secondary"}
            with patch.object(obs.ctl, "load_config", return_value=config), \
                 patch.object(obs.ctl, "cluster_exists", return_value=True), \
                 patch.object(obs.ctl, "check_ownership"), \
                 patch.object(obs.ctl, "prepare_kubeconfig"), \
                 patch.dict(obs.os.environ, {"GITHUB_ACTIONS": "false", "KUBECONFIG": "fixture",
                                             "METRICS_PASSWORD": "private-example"}):
                yield root, settings_path

    def test_plan_restores_settings_and_never_writes_a_secret(self):
        with self.device() as (root, settings_path), \
             patch.object(obs, "command", side_effect=["", json.dumps(self.plan())]) as command:
            obs.connect(root / "config.json", self.settings, "plan")
            self.assertEqual(command.call_count, 2)
            self.assertFalse(any(call.args[0][0] == "kubectl" for call in command.call_args_list))
            self.assertEqual(settings_path.read_text(), '{"previous": true}\n')

    def test_apply_uses_only_the_plan_that_was_checked(self):
        with self.device() as (root, settings_path), \
             patch.object(obs, "command", side_effect=["", json.dumps(self.plan()), "", "", "", ""]) as command:
            obs.connect(root / "config.json", self.settings, "apply")
            calls = command.call_args_list
            checked_plan = calls[1].args[0][-1]
            self.assertEqual(calls[3].args[0], ["terraform", f"-chdir={root}", "apply", "-input=false",
                                              "-lock-timeout=5m", checked_plan])
            self.assertFalse(checked_plan.parent.exists())
            self.assertTrue(all("METRICS_PASSWORD" not in call.kwargs["env"] for call in calls))
            self.assertEqual(json.loads(settings_path.read_text()), self.settings)

    def test_apply_refuses_unrelated_changes_before_writing_secret(self):
        with self.device() as (root, settings_path), \
             patch.object(obs, "command", side_effect=["", json.dumps(self.plan(address="module.database.db"))]) as command:
            with self.assertRaisesRegex(RuntimeError, "refusing unrelated"):
                obs.connect(root / "config.json", self.settings, "apply")
            self.assertEqual(command.call_count, 2)
            self.assertEqual(settings_path.read_text(), '{"previous": true}\n')

    def test_apply_refuses_state_change_before_writing_secret(self):
        with self.device() as (root, settings_path):
            def changed_state(args, **kwargs):
                if args[0] == "terraform":
                    path = root / "terraform.tfstate"
                    state = json.loads(path.read_text())
                    state["serial"] += 1
                    path.write_text(json.dumps(state))
                    return json.dumps(self.plan())
                return ""
            with patch.object(obs, "command", side_effect=changed_state) as command:
                with self.assertRaisesRegex(RuntimeError, "state changed"):
                    obs.connect(root / "config.json", self.settings, "apply")
                self.assertEqual(command.call_count, 2)
            self.assertEqual(settings_path.read_text(), '{"previous": true}\n')


if __name__ == "__main__":
    unittest.main()
