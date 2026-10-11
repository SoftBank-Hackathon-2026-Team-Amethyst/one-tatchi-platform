import subprocess
import unittest
from pathlib import Path

CHART = Path(__file__).resolve().parents[1]


class RuntimeChartTests(unittest.TestCase):
    def render(self, *args):
        return subprocess.run(["helm", "template", "runtime-status", str(CHART), "--namespace", "test",
                               "--set", "serviceName=demo-app-be", *args],
                              capture_output=True, text=True)

    def test_requires_immutable_image(self):
        self.assertNotEqual(self.render().returncode, 0)

    def test_namespace_role_has_no_secret_or_cluster_permissions(self):
        rendered = self.render("--set", "image.digest=sha256:" + "a" * 64)
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        # Inspect the rendered role rather than the template's source.
        role = next(doc for doc in rendered.stdout.split("---") if "kind: Role\n" in doc)
        self.assertNotIn("ClusterRole", rendered.stdout)
        self.assertNotIn("secrets", role)
        self.assertNotIn("watch", role)
        self.assertIn("resourceNames:", role)
        self.assertIn('"demo-app-be-preview"', role)
        self.assertIn('apiGroups: [metrics.k8s.io]', role)
        self.assertIn('@sha256:' + 'a' * 64, rendered.stdout)
        self.assertIn('namespace: test', rendered.stdout)

    def test_rejects_invalid_service_selector(self):
        self.assertNotEqual(self.render("--set", "serviceName=../prod",
                                       "--set", "image.digest=sha256:" + "a" * 64).returncode, 0)

    def test_app_namespace_opt_in_and_version_without_scraping(self):
        result = subprocess.run(["helm", "template", "demo-app-be", str(CHART.parent / "app"),
                                 "--set", "image.repository=r", "--set", "image.tag=t",
                                 "--set", "env.APP_VERSION=v2", "--set", "podNamespaceEnv=true"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('one-tatchi.dev/app-version: "v2"', result.stdout)
        self.assertIn('fieldPath: metadata.namespace', result.stdout)
        self.assertIn('automountServiceAccountToken: false', result.stdout)


if __name__ == "__main__":
    unittest.main()
