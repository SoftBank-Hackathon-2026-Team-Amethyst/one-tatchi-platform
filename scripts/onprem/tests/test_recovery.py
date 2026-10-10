import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import deadline
import onpremctl as ctl
import server_image
import reboot_observer


class RecoveryTests(unittest.TestCase):
    def test_installed_status_uses_managed_path_from_plain_terminal(self):
        with patch.object(sys, "argv", ["onpremctl", "--config", "/tmp/config.json", "status"]), \
                patch.object(ctl, "load_config", return_value={"path": "/managed/tools:/usr/bin"}), \
                patch.object(ctl, "status") as status, patch.dict(os.environ, {"PATH": "/usr/bin"}), patch("builtins.print"):
            def check(config):
                self.assertEqual(os.environ["PATH"], "/managed/tools:/usr/bin")
                return {"docker_ready": True, "errors": []}
            status.side_effect = check
            self.assertEqual(ctl.main(), 0)

    def test_nested_budget_and_queries_cannot_extend_outer_deadline(self):
        with patch.object(deadline.time, "monotonic", return_value=100):
            with deadline.budget(10):
                with deadline.budget(600):
                    self.assertEqual(deadline.remaining(20), 10)
                    with patch.object(deadline.time, "monotonic", return_value=111):
                        with self.assertRaisesRegex(RuntimeError, "deadline"):
                            ctl.run(["must-not-execute"])

    def test_refresh_failure_invalidates_previously_good_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"home": tmp}
            ctl.write_json(Path(tmp) / "endpoints.json", {"status": "ready", "urls": {"test": "https://old.trycloudflare.com/"}})
            with patch.object(ctl, "boot_id", return_value="new"), patch.object(ctl, "prepare_kubeconfig", side_effect=RuntimeError("denied")):
                ctl.refresh_urls(config)
            result = json.loads((Path(tmp) / "endpoints.json").read_text())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["urls"], {})
            self.assertEqual(result["boot_id"], "new")

    def test_failed_external_check_does_not_publish_address(self):
        with patch.object(ctl, "boot_id", return_value="new"), patch.object(ctl, "resolve", return_value="https://new.trycloudflare.com/"), \
                patch.object(ctl, "http_check", return_value={"ok": False}):
            result = ctl.endpoint_snapshot({"service": "app", "environments": ["test", "prod"]})
        self.assertEqual(result["urls"], {})
        self.assertEqual(len(result["errors"]), 2)

    def test_previous_boot_success_is_overwritten_even_if_docker_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {"home": tmp, "cluster": "lab"}
            path = Path(tmp) / "restore.json"
            ctl.write_json(path, {"boot_id": "old", "status": "ready"})
            with patch.object(ctl, "boot_id", return_value="new"), patch.object(ctl, "run", side_effect=RuntimeError("secret-output")):
                with self.assertRaisesRegex(RuntimeError, "docker"):
                    ctl.restore(config)
            result = json.loads(path.read_text())
            self.assertEqual(result["boot_id"], "new")
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["stages"][0]["status"], "failed")
            self.assertNotIn("secret-output", path.read_text())

    def test_maintenance_prevents_automatic_changes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(ctl, "run") as run:
            (Path(tmp) / "maintenance.json").write_text("{}")
            with self.assertRaisesRegex(RuntimeError, "maintenance"):
                ctl.restore({"home": tmp})
            run.assert_not_called()

    def test_terraform_record_cannot_claim_an_unapplied_image_upgrade(self):
        with patch.object(ctl, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps([{"Config": {"Image": "rancher/k3s:v1.33.4-k3s1"}}]))), \
                patch.object(ctl, "kube", return_value={"items": [{"status": {"nodeInfo": {"kubeletVersion": "v1.33.4+k3s1"}}}]}):
            with self.assertRaisesRegex(RuntimeError, "explicit image replacement"):
                ctl.verify_version({"cluster": "lab", "kubernetes_version": "v1.33.6-k3s1"})

    def test_url_agent_is_periodic_and_profile_scoped(self):
        cfg = {"profile": "secondary", "cluster": "lab", "home": "/tmp/profile", "path": "/bin"}
        agent = ctl.plists(cfg)["urls"]
        self.assertEqual(agent["StartInterval"], 30)
        self.assertEqual(agent["Label"], "dev.onetatchi.onprem.secondary.urls")
        self.assertEqual(agent["ProgramArguments"][-1], "refresh-urls")
        self.assertNotIn("KeepAlive", agent)


class ReplacementTests(unittest.TestCase):
    def info(self):
        return {"Name": "/k3d-lab-server-0", "Config": {"Image": "old", "Hostname": "k3d-lab-server-0", "Env": ["K3S_TOKEN=private"],
                "Labels": {"k3d.role": "server", "k3d.cluster": "lab"}, "Entrypoint": ["/bin/k3d-entrypoint.sh"]},
                "HostConfig": {"Privileged": True, "Tmpfs": {"/run": ""}, "RestartPolicy": {"Name": "unless-stopped"}},
                "Mounts": [{"Type": "volume", "Name": "anonymous-original", "Destination": "/var/lib/rancher/k3s", "RW": True}],
                "NetworkSettings": {"Networks": {"original-network": {"IPAddress": "172.20.0.3", "EndpointID": "old", "Aliases": ["server"]}}}}

    def test_image_change_keeps_auth_options_hostname_and_every_volume(self):
        info = self.info()
        spec = server_image.create_spec(info, "new")
        self.assertEqual(spec["Image"], "new")
        for key in ("Env", "Hostname", "Labels", "Entrypoint"):
            self.assertEqual(spec[key], info["Config"][key])
        self.assertIn("anonymous-original:/var/lib/rancher/k3s:rw", spec["HostConfig"]["Binds"])
        self.assertEqual(spec["HostConfig"]["RestartPolicy"], info["HostConfig"]["RestartPolicy"])
        self.assertNotIn("IPAddress", spec["NetworkingConfig"]["EndpointsConfig"]["original-network"])
        self.assertEqual(info["Config"]["Image"], "old")

    def test_clone_is_not_discoverable_by_k3d_and_has_no_published_ports(self):
        spec = server_image.create_spec(self.info(), "old", volumes={"anonymous-original": "copy"}, network="isolated", isolated=True)
        self.assertNotIn("k3d.cluster", spec["Labels"])
        self.assertEqual(spec["HostConfig"]["RestartPolicy"]["Name"], "no")
        self.assertEqual(spec["HostConfig"]["PortBindings"], {})
        self.assertEqual(spec["HostConfig"]["Binds"], ["copy:/var/lib/rancher/k3s:rw"])


class ObserverTests(unittest.TestCase):
    def test_http_success_cannot_replace_data_runner_and_boot_evidence(self):
        baseline = {"pvcs": ["uid"], "images": ["digest"], "charts": ["version"], "database": {"test": {"marker_count": 1}}}
        current = dict(baseline, errors=[], boot_id="new", last_restore={"boot_id": "old", "status": "ready"})
        current["database"] = {"test": {"marker_count": 0}}
        errors = reboot_observer.compare(baseline, current)
        self.assertIn("changed or missing: database", errors)
        self.assertIn("no successful restore from this boot", errors)
        self.assertIn("no live Kubernetes node version", errors)


if __name__ == "__main__":
    unittest.main()
