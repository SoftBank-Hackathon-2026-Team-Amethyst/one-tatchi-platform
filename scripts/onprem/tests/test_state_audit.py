import base64
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kube_auth
import onpremctl as ctl
import state_audit as audit
import state_migration as migration


def zipped(**entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return stream.getvalue()


class ArtifactAuditTests(unittest.TestCase):
    def test_escaped_credentials_block_migration(self):
        for value in ('quote-"-and-slash-\\-secret', '줄바꿈\n비밀'):
            for ascii_only in (True, False):
                payload = json.dumps({"unexpected_copy": value}, ensure_ascii=ascii_only).encode()
                with self.subTest(ascii_only=ascii_only), self.assertRaises(RuntimeError):
                    migration.assert_clean(payload, {value})

    def test_saved_plan_previous_state_and_base64_connection_are_inspected(self):
        value = 'fixture-db-"-password'
        connection = f"postgresql://app:{quote(value, safe='')}@db/demo"
        payload = json.dumps({"PG_URL": base64.b64encode(connection.encode()).decode()})
        plan = zipped(tfplan="opaque plan", tfstate=zipped(previous=payload))
        self.assertTrue(audit.contains_secret(plan, {value}))

    def test_pem_private_key_fails_even_if_no_longer_in_live_cluster(self):
        self.assertTrue(audit.contains_secret(b'-----BEGIN PRIVATE KEY-----\nfixture', set()))
        encoded = base64.b64encode(b'-----BEGIN PRIVATE KEY-----\nold-key').decode()
        self.assertTrue(audit.contains_secret(json.dumps({"old_key": encoded}).encode(), set()))

    def test_legacy_storage_is_detected_after_credential_rotation(self):
        for kind, attrs in (("random_password", {"result": "old-password"}),
                            ("kubernetes_secret_v1", {"data": {"password": "old-password"}}),
                            ("external", {"result": {"client_key": "old-encoded-key"}})):
            state = {"resources": [{"type": kind, "instances": [{"attributes": attrs}]}]}
            plan = {"resource_changes": [{"type": kind, "change": {"before": attrs, "after": None}}]}
            with self.subTest(kind=kind):
                self.assertTrue(audit.contains_secret(json.dumps(state).encode(), {"new-password"}))
                self.assertTrue(audit.contains_secret(json.dumps(plan).encode(), {"new-password"}))

    def test_nested_json_escaped_secret_is_found(self):
        value = 'fixture-"-secret'
        self.assertTrue(audit.contains_secret(json.dumps({"values": json.dumps({"password": value})}).encode(), {value}))

    def test_public_ca_and_exec_config_are_allowed(self):
        config = {"users": [{"exec": {"command": "kube_auth.py"}}], "certificate-authority-data": "public-ca"}
        self.assertFalse(audit.contains_secret(json.dumps(config).encode(), {"private-fixture"}))

    def test_artifact_inventory_includes_copies_but_preserves_t17_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("terraform.tfstate", "terraform.tfstate.backup", "old.tfplan"):
                (root / name).write_text('{}')
            (root / "saved-without-suffix").write_bytes(zipped(tfplan="binary"))
            (root / "show.json").write_text(json.dumps({"terraform_version": "1.16.5", "planned_values": {}}))
            (root / "state-copy.json").write_text(json.dumps({"terraform_version": "1.16.5", "resources": []}))
            settings = root / "t17-metrics.auto.tfvars.json"
            settings.write_text('{"metrics_remote_write_secret_name":"deploy-metrics-remote-write"}')
            files = audit.artifact_files(root)
            self.assertEqual(len(files), 6)
            self.assertNotIn(settings, files)  # Migration must not delete live configuration.

    def test_symlink_or_missing_explicit_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "terraform.tfstate").write_text('{}')
            link = root / "bad.tfplan"
            link.symlink_to(root / "terraform.tfstate")
            with self.assertRaises(RuntimeError):
                audit.artifact_files(root)
            link.unlink()
            with self.assertRaises(RuntimeError):
                audit.artifact_files(root, [root / "missing"])

    def test_nested_archive_limit_fails_closed(self):
        payload = b"no secrets"
        for _ in range(4):
            payload = zipped(inner=payload)
        with self.assertRaisesRegex(RuntimeError, "incomplete"):
            audit.contains_secret(payload, {"fixture-secret"})

    def test_audit_fails_without_disclosing_secret_and_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "terraform.tfstate").write_text('{}')
            settings = root / "t17-metrics.auto.tfvars.json"
            settings.write_text(json.dumps({"password": 'secret-"-fixture'}))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            config = {"profile": "secondary", "home": directory, "terraform_root": directory}
            output = io.StringIO()
            with patch.object(audit, "live_values", return_value=({'secret-"-fixture'}, [])), redirect_stdout(output):
                code = audit.audit(config, [])
            self.assertEqual(code, 1)
            self.assertNotIn('secret-', output.getvalue())
            report = json.loads(output.getvalue())
            self.assertFalse(report["passed"])
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


class CredentialCollectionTests(unittest.TestCase):
    def collect(self, missing=None, fail=False):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "kubeconfig.json").write_text('{}')
            config = {"cluster": "fixture", "home": directory, "secret_namespace": "platform",
                      "service": "demo-app", "environments": ["test", "prod"]}
            secrets = {
                "demo-app-db-test-credentials": {"username": "app", "password": "test-password"},
                "demo-app-db-prod-credentials": {"username": "app", "password": "prod-password"},
                "deploy-metrics-remote-write": {"username": "onprem", "password": "metrics-password"},
                "operator-oauth": {"client_id": "public-id", "client_secret": "oauth-password"},
            }
            secrets.pop(missing, None)
            def query(args):
                if fail:
                    raise RuntimeError("kubectl failed (exit 1)")
                data = secrets.get(args[5])
                raw = json.dumps({"data": {k: base64.b64encode(v.encode()).decode() for k, v in data.items()}}) if data else ""
                return subprocess.CompletedProcess(args, 0, stdout=raw)
            auth = {key: base64.b64encode(key.encode()).decode() for key in ("client_key", "client_certificate")}
            with patch.object(ctl, "check_ownership"), patch.object(ctl, "cluster_exists", return_value=True), \
                 patch.object(kube_auth, "credentials", return_value=auth), patch.object(ctl, "run", side_effect=query), \
                 patch.object(ctl, "prepare_kubeconfig", side_effect=AssertionError("must not rewrite kubeconfig")):
                return audit.live_values(config)

    def test_t17_and_t33_credentials_are_included_without_public_ids(self):
        values, sources = self.collect()
        self.assertTrue({"test-password", "prod-password", "metrics-password", "oauth-password"} <= values)
        self.assertNotIn("public-id", values)
        self.assertEqual(len(sources), 4)

    def test_optional_tailscale_absence_is_allowed(self):
        _, sources = self.collect(missing="operator-oauth")
        self.assertEqual(len(sources), 3)

    def test_missing_db_or_failed_query_is_not_a_clean_audit(self):
        with self.assertRaises(RuntimeError):
            self.collect(missing="demo-app-db-prod-credentials")
        with self.assertRaises(RuntimeError):
            self.collect(fail=True)


if __name__ == "__main__":
    unittest.main()
