import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kube_auth
import onpremctl as ctl
import state_migration as migration
import tunnel
import target
import compare
import probe


class TunnelTests(unittest.TestCase):
    def setUp(self):
        self.deployment = {"metadata": {"name": "cloudflared-test"}, "spec": {
            "selector": {"matchLabels": {"tunnel": "test"}}, "template": {"spec": {"containers": [
                {"name": "cloudflared", "args": ["tunnel", "--url", "http://app-fe.test.svc.cluster.local:80"]}
            ]}}}}
        self.pod = {"metadata": {"name": "current"}, "status": {"phase": "Running", "containerStatuses": [
            {"name": "cloudflared", "ready": True, "state": {"running": {"startedAt": "2026-10-09T00:00:00Z"}}}
        ]}}
        self.deployment["metadata"]["generation"] = 1
        self.deployment["status"] = dict(observedGeneration=1, replicas=1, updatedReplicas=1, availableReplicas=1)
        self.pod["spec"] = self.deployment["spec"]["template"]["spec"]
        self.logs = "connected https://current-address.trycloudflare.com"
        self.calls = []

    def query(self, *args):
        self.calls.append(args)
        if args[:2] == ("get", "service"):
            return '{"spec":{"ports":[{"port":80}]}}'
        if args[:2] == ("get", "deployments"):
            return json.dumps({"items": [self.deployment] if self.deployment else []})
        if args[:2] == ("get", "pods"):
            return json.dumps({"items": [self.pod]})
        return self.logs

    def test_uses_current_container_logs_only(self):
        self.assertEqual(tunnel.resolve("app-fe", "test", 0, self.query), "https://current-address.trycloudflare.com/")
        self.assertIn("--since-time=2026-10-09T00:00:00Z", self.calls[-1])

    def test_missing_tunnel_fails(self):
        self.deployment = None
        with self.assertRaisesRegex(RuntimeError, "missing"):
            tunnel.resolve("app-fe", "test", 0, self.query)

    def test_wrong_origin_fails(self):
        with self.assertRaisesRegex(RuntimeError, "origin"):
            tunnel.resolve("app-be", "test", 0, self.query)

    def test_wrong_service_port_fails(self):
        self.deployment["spec"]["template"]["spec"]["containers"][0]["args"][-1] = "http://app-fe.test.svc.cluster.local:9999"
        with self.assertRaisesRegex(RuntimeError, "port"):
            tunnel.resolve("app-fe", "test", 0, self.query)

    def test_empty_logs_fail(self):
        self.logs = "not connected"
        with self.assertRaisesRegex(RuntimeError, "no current"):
            tunnel.resolve("app-fe", "test", 0, self.query)

    def test_terminating_pod_is_not_reused(self):
        self.pod["metadata"]["deletionTimestamp"] = "now"
        with self.assertRaises(RuntimeError):
            tunnel.resolve("app-fe", "test", 0, self.query)

    def test_old_ready_pod_during_rollout_is_not_reused(self):
        self.deployment["status"]["updatedReplicas"] = 0
        with self.assertRaisesRegex(RuntimeError, "no current"):
            tunnel.resolve("app-fe", "test", 0, self.query)

    def test_api_error_is_not_a_missing_tunnel(self):
        def denied(*args):
            raise RuntimeError("forbidden")
        with self.assertRaisesRegex(RuntimeError, "forbidden"):
            tunnel.resolve("app-fe", "test", 0, denied)

    def test_waits_for_current_startup(self):
        now = [0]
        self.logs = ""
        def sleep(n):
            now[0] += n
            self.logs = "https://new.trycloudflare.com"
        self.assertEqual(tunnel.resolve("app-fe", "test", 10, self.query, sleep, lambda: now[0]), "https://new.trycloudflare.com/")
        self.assertEqual(now[0], 5)


class LifecycleTests(unittest.TestCase):
    def config(self, root):
        return {"profile": "secondary", "cluster": "test-cluster", "service": "demo-app", "terraform_root": str(root),
                "runner_dir": str(root / "runner"), "home": str(root / "service"), "path": "/usr/bin:/bin"}

    def test_no_private_key_in_public_kubeconfig(self):
        cfg = kube_auth.public_config("demo", {"endpoint": "https://127.0.0.1:6550", "ca_certificate": "public", "client_key": "PRIVATE"})
        text = json.dumps(cfg)
        self.assertNotIn("PRIVATE", text)
        self.assertNotIn("client-key-data", text)
        self.assertEqual(cfg["users"][0]["user"]["exec"]["interactiveMode"], "Never")

    def test_sleep_prevention_allows_display_sleep_and_uses_stable_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.config(Path(tmp))
            plists = ctl.plists(config)
            self.assertEqual(plists["awake"]["ProgramArguments"], ["/usr/bin/caffeinate", "-s"])
            self.assertTrue(plists["awake"]["KeepAlive"])
            self.assertTrue(plists["runner"]["KeepAlive"])
            self.assertIn(str(Path(config["home"]) / "bin/onpremctl.py"), plists["restore"]["ProgramArguments"])

    def test_existing_cluster_without_state_is_not_adopted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "state is missing"):
                ctl.check_ownership(self.config(Path(tmp)), True)

    def test_runner_and_absolute_work_paths_must_not_contain_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for dirname, work in (("runner space", "_work"), ("runner", str(root / "work space"))):
                runner = root / dirname
                runner.mkdir(exist_ok=True)
                (runner / ".runner").write_text(json.dumps({"workFolder": work}), encoding="utf-8-sig")
                with self.subTest(dirname=dirname), self.assertRaisesRegex(RuntimeError, "whitespace"):
                    ctl.validate_runner_paths(runner)
            (root / "runner/.runner").write_text('{"workFolder":"_work"}', encoding="utf-8-sig")
            ctl.validate_runner_paths(root / "runner")

    def test_state_must_match_cluster(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = self.config(Path(tmp))
            (Path(tmp) / "terraform.tfstate").write_text(json.dumps({"resources": [{"module": "module.cluster", "type": "terraform_data",
                "instances": [{"attributes": {"input": {"value": {"name": "another"}}}}]}]}))
            with self.assertRaisesRegex(RuntimeError, "does not own"):
                ctl.check_ownership(config, True)

    def test_stop_only_unloads_owned_services(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ctl, "run") as run:
            stopped = set()
            def launchctl(args, **kwargs):
                if args[1] == "bootout":
                    stopped.add(args[2])
                return subprocess.CompletedProcess(args, int(args[1] == "print" and args[2] in stopped))
            run.side_effect = launchctl
            config = self.config(Path(tmp))
            ctl.stop_services(config)
            calls = [c.args[0] for c in run.call_args_list]
            self.assertEqual(sum(c[1] == "bootout" for c in calls), 4)
            self.assertEqual(sum(c[1] == "print" for c in calls), 8)
            self.assertTrue(all(c[0] == "launchctl" for c in calls))

    def test_existing_database_password_is_preserved(self):
        live = {"data": {k: base64.b64encode(v.encode()).decode() for k, v in {"username": "app", "password": "old-password"}.items()}}
        with patch.object(ctl, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(live))):
            self.assertEqual(ctl.database_passwords({"environments": ["test"], "secret_namespace": "platform", "service": "demo-app"}), {"test": "old-password"})

    def test_missing_password_with_existing_volume_fails(self):
        outputs = [subprocess.CompletedProcess([], 0, ""), subprocess.CompletedProcess([], 0, json.dumps({"items": [{"metadata": {"name": "data-demo-app-db-test-0"}}]}))]
        with patch.object(ctl, "run", side_effect=outputs), self.assertRaisesRegex(RuntimeError, "volume exists"):
            ctl.database_passwords({"environments": ["test"], "secret_namespace": "platform", "service": "demo-app"})

    def test_device_identity_cannot_cross_runners(self):
        target.validate("onprem", "onprem", "onprem", "k3d-onetouch")
        target.validate("onprem", "onprem-secondary", "onprem-secondary", "k3d-onetouch-secondary")
        for label, runner, cluster in [("onprem-secondary", "onprem", "k3d-onetouch"),
                ("onprem-typo", "onprem", "k3d-onetouch"),
                ("onprem", "onprem", "invalid-context")]:
            with self.subTest(label=label), self.assertRaises(ValueError):
                target.validate("onprem", label, runner, cluster)

    def test_start_does_not_bootstrap_loaded_services_twice(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ctl, "run") as run:
            run.return_value.returncode = 0
            ctl.start_services(self.config(Path(tmp)))
            self.assertFalse(any(c.args[0][1] == "bootstrap" for c in run.call_args_list))
            self.assertEqual(sum(c.args[0][1] == "kickstart" for c in run.call_args_list), 4)

    def test_docker_delay_retries_without_creating_cluster(self):
        config = {"home": "", "cluster": "demo", "environments": ["test", "prod"]}
        calls, attempts = [], [0]
        def run(args, **kwargs):
            calls.append(args)
            if args[:2] == ["docker", "inspect"]:
                return subprocess.CompletedProcess(args, 0, json.dumps([{"Config": {"Labels": {"k3d.cluster": "demo", "k3d.role": "loadbalancer"}}}]))
            if args[:2] == ["docker", "info"]:
                attempts[0] += 1
                return subprocess.CompletedProcess(args, int(attempts[0] < 3))
            return subprocess.CompletedProcess(args, 0)
        with tempfile.TemporaryDirectory() as tmp:
            config["home"] = tmp
            with patch.object(ctl, "run", run), patch.object(ctl, "cluster_exists", return_value=True), \
                    patch.object(ctl, "check_ownership"), patch.object(ctl, "prepare_kubeconfig"), patch.object(ctl.time, "sleep"), \
                    patch.object(ctl, "boot_id", return_value="boot-new"), patch.object(ctl, "workloads_ready", return_value=True), \
                    patch.object(ctl, "endpoint_snapshot", return_value={"status": "ready", "urls": {}}):
                ctl.restore(config)
            self.assertEqual(attempts[0], 3)
            self.assertTrue(any(c[:3] == ["k3d", "cluster", "start"] for c in calls))
            self.assertFalse(any("create" in c or "apply" in c for c in calls))

    def test_new_database_generates_password_only_without_data(self):
        outputs = [subprocess.CompletedProcess([], 0, ""), subprocess.CompletedProcess([], 0, '{"items":[]}')]
        with patch.object(ctl, "run", side_effect=outputs):
            passwords = ctl.database_passwords({"environments": ["test"], "secret_namespace": "platform", "service": "demo-app"})
            self.assertGreaterEqual(len(passwords["test"]), 32)


class ContinuityTests(unittest.TestCase):
    def snapshot(self, observed_at):
        return {"observed_at": observed_at, "ac_power": True, "sleep_prevented": True, "errors": [],
                "nodes": [{"name": "server-0", "started": "before-lock", "restarts": 0}],
                "pods": [{"namespace": "test", "name": "app", "uid": "original", "created": "before-lock",
                          "status": {"phase": "Running", "containerStatuses": [{"name": "app", "restartCount": 0,
                              "state": {"running": {"startedAt": "before-lock"}}}]}}]}

    def check_snapshots(self, before, after):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / "before.json", Path(tmp) / "after.json"]
            for path, snapshot in zip(paths, (before, after)):
                path.write_text(json.dumps(snapshot))
            compare.compare(paths)

    def test_unchanged_services_for_thirty_minutes_pass(self):
        self.check_snapshots(self.snapshot(0), self.snapshot(1800))

    def test_restart_replacement_and_short_window_fail(self):
        for kind in ("restart", "replacement", "short", "power", "diagnostic"):
            after = self.snapshot(1800)
            if kind == "restart":
                after["pods"][0]["status"]["containerStatuses"][0]["restartCount"] = 1
            elif kind == "replacement":
                after["pods"][0]["uid"] = "replaced"
            elif kind == "short":
                after["observed_at"] = 1799
            elif kind == "power":
                after["ac_power"] = False
            else:
                after["errors"] = ["tunnel missing"]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.check_snapshots(self.snapshot(0), after)

    def test_probe_requires_original_db_marker_without_logging_body(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"message":"original-db-marker"}'
        with patch.object(probe.urllib.request, "urlopen", return_value=response):
            result = probe.probe("https://example.trycloudflare.com/api/guestbook", "original-db-marker")
            self.assertTrue(result["ok"])
            self.assertNotIn("original-db-marker", json.dumps(result))
            self.assertFalse(probe.probe("https://example.trycloudflare.com/api/guestbook", "lost-marker")["ok"])


class StateTests(unittest.TestCase):
    def test_reformatted_backup_is_allowed_but_changed_secret_is_not(self):
        original = {"lineage": "fixture", "serial": 2, "resources": [{"mode": "managed", "type": "secret", "name": "one",
            "instances": [{"attributes": {"id": "one", "password": "original"}}]}]}
        raw = json.dumps(original).encode()
        original["resources"][0]["instances"][0].update(sensitive_attributes=[], identity_schema_version=0)
        self.assertTrue(migration.archived_equivalent(json.dumps(original, indent=2).encode(), [raw]))
        original["resources"][0]["instances"][0]["attributes"]["password"] = "changed"
        self.assertFalse(migration.archived_equivalent(json.dumps(original).encode(), [raw]))

    def test_migration_keeps_db_and_volume_identity_and_clears_known_secrets(self):
        state = {"lineage": "local", "serial": 12, "resources": [
            {"module": 'module.database["test"]', "type": "random_password", "name": "this", "instances": [{"attributes": {"result": "test-password-value"}}]},
            {"module": 'module.database["test"]', "type": "kubernetes_secret_v1", "name": "credentials", "instances": [{"attributes": {"id": "platform/demo-app-db-test-credentials", "data": {"password": "test-password-value"}}}]},
            {"module": "module.cluster", "mode": "data", "type": "external", "name": "kubeconfig", "instances": [{"attributes": {"result": {"client_key": "test-private-material"}}}]},
            {"module": 'module.database["test"]', "type": "kubernetes_stateful_set_v1", "name": "this", "instances": [{"attributes": {"id": "platform/demo-app-db-test"}}]},
        ]}
        clean, changed = migration.scrub(state)
        self.assertEqual(clean["serial"], 13)
        self.assertEqual(clean["lineage"], "local")
        self.assertEqual(clean["resources"][-1], state["resources"][-1])
        self.assertEqual(clean["resources"][0]["instances"][0]["attributes"]["data_wo_revision"], 1)
        migration.assert_clean(json.dumps(clean).encode(), migration.secret_values(state))
        self.assertEqual(state["serial"], 12)
        self.assertEqual(len(changed), 3)

    def test_unknown_secret_makes_migration_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "secret material remains"):
            migration.assert_clean(b'{"unknown": "do-not-remove-blindly"}', {"do-not-remove-blindly"})


if __name__ == "__main__":
    unittest.main()
