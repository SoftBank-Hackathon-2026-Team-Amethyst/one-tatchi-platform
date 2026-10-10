import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("yolo_pr", HERE / "pr.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)


class PullRequestTest(unittest.TestCase):
    def setUp(self):
        self.report = dict(sha="a" * 40, environment="test", promoted=True, actor="tester",
                           target="aws", template_version="v1.14.0", compliance="regulated",
                           run_url="https://example.test/run/1")
        self.calls = []
        self.existing = []
        self.files = []
        self.runs = [dict(id=1, path=".github/workflows/deploy.yml", head_branch="yolo/example",
                          status="completed", conclusion="success", pull_requests=[{"number": 1}])]
        self.head = self.report["sha"]

    def gh(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "list"):
            return json.dumps(self.existing)
        if args[:2] == ("pr", "view"):
            return json.dumps({"files": self.files})
        if args[:2] in (("pr", "create"), ("pr", "edit")):
            self.body = Path(args[args.index("--body-file") + 1]).read_text()
        if args[:2] == ("pr", "create"):
            return "https://github.com/org/app/pull/1"
        if args[0] == "api":
            if "git/ref" in args[1]:
                return json.dumps({"object": {"sha": self.head}})
            return json.dumps({"workflow_runs": self.runs})
        return ""

    def run_pr(self):
        with patch.object(pr, "gh", self.gh):
            return pr.run(self.report, "yolo/example", "org/app", timeout=0)

    def merged(self):
        return [c for c in self.calls if c[:2] == ("pr", "merge")]

    def test_create_after_success(self):
        self.run_pr()
        self.assertIn("regulated", self.body)
        self.assertIn("--auto", self.merged()[0])
        self.assertIn("--rebase", self.merged()[0])
        self.assertEqual(self.merged()[0][-2:], ("--match-head-commit", self.report["sha"]))

    def test_preserve_existing_body_and_update_report(self):
        self.existing = [dict(number=1, headRefOid=self.head, body="User context\n\n"
                              "<!-- yolo-deploy:start -->old<!-- yolo-deploy:end -->\nFooter")]
        self.run_pr()
        self.assertTrue(self.body.startswith("User context"))
        self.assertTrue(self.body.endswith("Footer"))
        self.assertNotIn("old", self.body)
        self.assertFalse(any(c[:2] == ("pr", "create") for c in self.calls))

    def test_stale_head_does_not_mutate(self):
        self.head = "b" * 40
        with self.assertRaisesRegex(RuntimeError, "새 커밋"):
            self.run_pr()
        self.assertEqual(len(self.calls), 1)

    def test_failed_ci_does_not_merge(self):
        self.runs[0]["conclusion"] = "failure"
        with self.assertRaisesRegex(RuntimeError, "검사 실패"):
            self.run_pr()
        self.assertFalse(self.merged())

    def test_slow_successful_pr_ci_is_allowed_beyond_ten_minutes(self):
        self.runs[0].update(status="in_progress", conclusion=None)
        def finish(_):
            self.runs[0].update(status="completed", conclusion="success")
        with patch.object(pr, "gh", self.gh), patch.object(pr.time, "monotonic", side_effect=[0, 1200]), \
                patch.object(pr.time, "sleep", side_effect=finish):
            pr.run(self.report, "yolo/example", "org/app")
        self.assertTrue(self.merged())

    def test_pr_ci_wait_remains_bounded(self):
        self.runs[0].update(status="in_progress", conclusion=None)
        with patch.object(pr, "gh", self.gh), patch.object(pr.time, "monotonic", side_effect=[0, 2701]):
            with self.assertRaisesRegex(RuntimeError, "시간 초과"):
                pr.run(self.report, "yolo/example", "org/app")
        self.assertFalse(self.merged())

    def test_missing_pr_run_does_not_merge(self):
        self.runs = []
        with self.assertRaisesRegex(RuntimeError, "시간 초과"):
            self.run_pr()
        self.assertFalse(self.merged())

    def test_infra_change_requires_plan_run(self):
        self.files = [{"path": ".github/workflows/infra.yml"}]
        with self.assertRaisesRegex(RuntimeError, "시간 초과"):
            self.run_pr()
        self.assertFalse(self.merged())

    def test_old_pr_with_same_head_does_not_count(self):
        self.runs[0]["pull_requests"] = [{"number": 99}]
        with self.assertRaisesRegex(RuntimeError, "시간 초과"):
            self.run_pr()
        self.assertFalse(self.merged())

    def test_unpromoted_report_rejected(self):
        self.report["promoted"] = False
        with self.assertRaisesRegex(RuntimeError, "승격"):
            self.run_pr()
        self.assertFalse(self.calls)


class ShellTest(unittest.TestCase):
    def shell(self, name, env, fake_name, fake):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / fake_name
            executable.write_text("#!/usr/bin/env bash\n" + fake)
            executable.chmod(0o755)
            output = Path(tmp) / "output"
            result = subprocess.run(["bash", str(HERE / name)], env={**os.environ, **env,
                "PATH": tmp + os.pathsep + os.environ["PATH"], "GITHUB_OUTPUT": str(output)},
                text=True, capture_output=True)
            return result, output.read_text() if output.exists() else ""

    def test_routing(self):
        merged = dict(merged_at="today", merge_commit_sha="abc", base={"ref": "main"},
                      head={"ref": "yolo/example", "repo": {"full_name": "org/app"}},
                      labels=[{"name": "yolo"}])
        base = dict(MODE="branch", GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/main",
                    GITHUB_SHA="abc", GITHUB_REPOSITORY="org/app")
        for overrides, prs, expected in [({}, [merged], "auto"), ({}, [], "manual"),
                ({"GITHUB_SHA": "different"}, [merged], "manual"),
                ({"GITHUB_REF": "refs/heads/yolo/example"}, [], "auto"),
                ({"GITHUB_EVENT_NAME": "workflow_dispatch"}, [merged], "manual")]:
            with self.subTest(overrides=overrides, prs=prs):
                result, output = self.shell("mode.sh", {**base, **overrides}, "gh",
                                            "printf '%s' '" + json.dumps(prs) + "'\n")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(output.strip(), "mode=" + expected)

    def test_verify_requires_healthy_current_stable_image(self):
        rollout = {"status": {"phase": "Healthy", "stableRS": "hash", "currentPodHash": "hash"}}
        rs = {"items": [{"metadata": {"ownerReferences": [{"kind": "Rollout", "name": "app"}]},
                         "spec": {"template": {"spec": {"containers": [{"image": "repo:abc"}]}}}}]}
        base = dict(SERVICES='[{"name":"app"}]', NAMESPACE="test", TAG="abc", WAIT_SECONDS="0")
        for phase, tag, expected in [("Healthy", "abc", 0), ("Paused", "abc", 1),
                                     ("Healthy", "wrong", 1)]:
            with self.subTest(phase=phase, tag=tag):
                rollout["status"]["phase"] = phase
                fake = "if [ \"$2\" = rollout ]; then printf '%s' '" + json.dumps(rollout) + "'; "
                fake += "else printf '%s' '" + json.dumps(rs) + "'; fi\n"
                result, output = self.shell("verify.sh", {**base, "TAG": tag}, "kubectl", fake)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(output.strip(), "promoted=true" if expected == 0 else "")

    def test_digest_requires_exact_repository_and_promoted_stable(self):
        base = dict(SERVICES='[{"name":"app"}]', NAMESPACE="test", TAG="abc", WAIT_SECONDS="0",
                    IMAGES=json.dumps({"app": {"repository": "repo", "digest": "sha256:" + "a" * 64}}))
        desired = "repo@sha256:" + "a" * 64
        for image, phase, owner, expected in [(desired, "Healthy", "app", 0),
                ("repo:abc", "Healthy", "app", 1), (desired, "Paused", "app", 1),
                ("other@sha256:" + "a" * 64, "Healthy", "app", 1),
                ("repo@sha256:" + "b" * 64, "Healthy", "app", 1), (desired, "Healthy", "other", 1)]:
            with self.subTest(image=image, phase=phase, owner=owner):
                rollout = {"status": {"phase": phase, "stableRS": "hash", "currentPodHash": "hash"}}
                replicas = {"items": [{"metadata": {"ownerReferences": [{"kind": "Rollout", "name": owner}]},
                    "spec": {"template": {"spec": {"containers": [{"image": image}]}}}}]}
                fake = "if [ \"$2\" = rollout ]; then printf '%s' '" + json.dumps(rollout) + "'; "
                fake += "else printf '%s' '" + json.dumps(replicas) + "'; fi\n"
                result, _ = self.shell("verify.sh", base, "kubectl", fake)
                self.assertEqual(result.returncode, expected, result.stderr)


if __name__ == "__main__":
    unittest.main()
