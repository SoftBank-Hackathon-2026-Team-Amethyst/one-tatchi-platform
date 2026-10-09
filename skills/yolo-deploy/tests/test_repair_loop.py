import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/repair_loop.py"
spec = importlib.util.spec_from_file_location("repair_loop", SCRIPT)
loop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loop)

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
p = Path(os.environ["T14_FAKE_GH_DATA"])
s = json.loads(p.read_text())
a = sys.argv[1:]
with p.with_suffix(".calls").open("a") as out:
    out.write(json.dumps(a) + "\n")
if a[:2] == ["repo", "view"]:
    print(json.dumps({"nameWithOwner": "test/app"}))
elif a[0] == "api":
    print(json.dumps({"id": 7, "path": ".github/workflows/deploy.yml"}))
elif a[:2] == ["run", "list"]:
    sequence = s.get("lists")
    if sequence:
        runs = sequence.pop(0)
        p.write_text(json.dumps(s))
    else:
        runs = s.get("runs", [])
    print(json.dumps(runs))
elif a[:2] == ["run", "watch"]:
    sys.exit(s.get("watch_exit", 0))
elif a[:2] == ["pr", "list"]:
    print(json.dumps(s.get("pulls", [])))
elif a[:2] == ["run", "view"]:
    if "--log-failed" in a:
        if s.get("log_error"):
            sys.exit(1)
        print(s.get("logs", "app/main.py: type error"))
    else:
        print(json.dumps(s["view"]))
else:
    sys.exit(99)
'''


class RepairLoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "app"
        self.root.mkdir()
        self.remote = self.base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)
        self.g("init", "-q", "-b", "main")
        self.g("config", "user.name", "T14 test")
        self.g("config", "user.email", "t14@example.invalid")
        self.g("config", "commit.gpgsign", "false")
        for path, content in {
            "app/main.py": "value = 1\n", "app/Dockerfile": "FROM scratch\n",
            "app/tests/test_main.py": "assert True\n", "app/sample.spec.ts": "test('works')\n",
            "app/fixtures/input.py": "value = 1\n", "app/package.json": '{"scripts":{"lint":"check"}}\n',
            "app/tsconfig.json": '{"strict":true}\n', "app/.dockerignore": "dist\n",
            "app/custom_checks/check.py": "assert True\n",
            ".deploy/config.yaml": "compliance: regulated\n", ".deploy/smoke.json": "{}\n",
            ".github/workflows/deploy.yml": "name: deploy\n", ".github/CODEOWNERS": "* @owner\n",
            "deploy/values-app.yaml": "replicas: 1\n", "infra/envs/aws/terraform.tfvars": "size = 1\n",
            ".trivyignore": "# reviewed exceptions\n", ".gitignore": "__pycache__/\n",
        }.items():
            self.write(path, content)
        self.g("add", ".")
        self.g("commit", "-qm", "fixture")
        self.g("switch", "-qc", "yolo/test")
        self.g("remote", "add", "origin", str(self.remote))
        self.g("push", "-qu", "origin", "HEAD")
        self.bin = self.base / "bin"
        self.bin.mkdir()
        fake = self.bin / "gh"
        fake.write_text(FAKE_GH)
        fake.chmod(0o755)
        self.scenario = self.base / "scenario.json"
        self.scenario.write_text("{}")
        self.env = patch.dict(os.environ, {"PATH": f"{self.bin}:{os.environ['PATH']}",
                                          "T14_FAKE_GH_DATA": str(self.scenario)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.temp.cleanup)
        self.s = loop.Session(self.root)
        with self.s.lock():
            self.s.init(self.options())
        self.initial = self.s.head()

    def options(self, **overrides):
        values = {"source": ["app"], "dockerfile": ["app/Dockerfile"],
                  "value": ["deploy/values-app.yaml", "infra/envs/aws/terraform.tfvars"],
                  "protect": ["app/custom_checks"], "check": [json.dumps([sys.executable, "-c", "pass"])]}
        values.update(overrides)
        return argparse.Namespace(**values)

    def g(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, text=True,
                              capture_output=True, check=True).stdout.strip()

    def write(self, path, content):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)

    def run_data(self, *, checks="failure", deployment="skipped", conclusion="failure", **extra):
        data = {"databaseId": 101 + self.s.state["repairs"], "headSha": self.s.state["sha"],
                "headBranch": "yolo/test", "event": "push", "workflowDatabaseId": 7,
                "attempt": 1, "status": "completed", "conclusion": conclusion,
                "url": "https://github.com/test/app/actions/runs/101",
                "jobs": [{"name": "checks / node (app)", "status": "completed", "conclusion": checks},
                         {"name": "checks / python", "status": "completed", "conclusion": "skipped"},
                         {"name": "test / deploy", "status": "completed", "conclusion": deployment}]}
        data.update(extra)
        return data

    def scenario_for(self, data=None, **extra):
        data = data or self.run_data()
        self.scenario.write_text(json.dumps({"runs": [data], "view": data, **extra}))
        return data

    def failure(self):
        self.scenario_for()
        self.s.watch(discovery_seconds=0, poll_seconds=0)
        self.assertEqual(self.s.state["status"], "checks_failed")

    def repair(self, number=2):
        self.write("app/main.py", f"value = {number}\n")
        self.s.retry(argparse.Namespace(reason="타입 오류를 수정", file=["app/main.py"]))

    def test_exact_run_and_delayed_creation(self):
        current = self.run_data()
        wrong = [dict(current, headSha="0" * 40), dict(current, headBranch="yolo/other"),
                 dict(current, event="pull_request"), dict(current, workflowDatabaseId=9)]
        self.scenario_for(current, lists=[wrong, [], [current]], watch_exit=1)
        self.s.watch(discovery_seconds=5, poll_seconds=0)
        self.assertEqual(self.s.state["run"]["headSha"], self.initial)
        calls = [json.loads(x) for x in self.scenario.with_suffix(".calls").read_text().splitlines()]
        watched = [x for x in calls if x[:2] == ["run", "watch"]]
        self.assertEqual(len(watched), 1)
        self.assertEqual(watched[0][2], str(current["databaseId"]))
        self.assertIn("--exit-status", watched[0])
        self.assertIn("--commit", next(x for x in calls if x[:2] == ["run", "list"]))

    def test_discovery_timeout_does_not_watch_or_cancel(self):
        self.scenario.write_text('{"runs": []}')
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)
        self.assertNotIn('"watch"', self.scenario.with_suffix(".calls").read_text())
        self.assertNotIn('"cancel"', self.scenario.with_suffix(".calls").read_text())

    def test_ambiguous_run_stops(self):
        data = self.run_data()
        self.scenario_for(data, runs=[data, dict(data, databaseId=999)])
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)

    def test_changed_attempt_stops(self):
        data = self.run_data()
        self.scenario_for(data, view=dict(data, attempt=2))
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)

    def test_watch_timeout_does_not_cancel(self):
        self.scenario_for()
        original = self.s.gh
        def gh(*args, **kwargs):
            if args[:2] == ("run", "watch"):
                raise loop.Stop("명령 시간 초과")
            return original(*args, **kwargs)
        with patch.object(self.s, "gh", side_effect=gh), self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)
        self.assertNotIn('"cancel"', self.scenario.with_suffix(".calls").read_text())

    def test_classification_and_non_repairable_failures(self):
        cases = [
            (self.run_data(), "checks_failed"),
            (self.run_data(checks="success", deployment="failure"), "stopped"),
            (self.run_data(checks="success", deployment="success", conclusion="success"), "complete"),
            (self.run_data(conclusion="cancelled"), "stopped"),
            (self.run_data(conclusion="startup_failure"), "stopped"),
            (self.run_data(checks="timed_out"), "stopped"),
            (self.run_data(checks="skipped", conclusion="success"), "stopped"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                self.assertEqual(loop.Session.classify(data)[0], expected)

    def test_failed_logs_are_local_and_required(self):
        self.failure()
        log = Path(self.s.state["run"]["log_path"])
        self.assertTrue(log.resolve().is_relative_to((self.root / ".git").resolve()))
        self.assertEqual(log.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.g("status", "--porcelain"), "")
        self.scenario_for(log_error=True)
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)
        self.assertNotEqual(self.s.state["status"], "checks_failed")

    def test_empty_failure_log_stops(self):
        self.scenario_for(logs="")
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)

    def test_protected_changes_never_commit_or_push(self):
        paths = ["app/tests/test_main.py", "app/fixtures/input.py", "app/sample.spec.ts",
                 "app/custom_checks/check.py", "app/package.json", "app/tsconfig.json", "app/.dockerignore",
                 ".github/workflows/deploy.yml", ".github/CODEOWNERS", ".deploy/config.yaml",
                 ".deploy/smoke.json", ".trivyignore", "app/new.test.py", "app/pnpm-lock.yaml"]
        self.failure()
        for path in paths:
            with self.subTest(path=path):
                original = (self.root / path).read_bytes() if (self.root / path).exists() else None
                self.write(path, "changed\n")
                with self.assertRaises(loop.Stop):
                    self.s.retry(argparse.Namespace(reason="bad fix", file=[path]))
                self.assertEqual(self.s.head(), self.initial)
                self.assertEqual(self.s.remote_sha(), self.initial)
                self.assertEqual(self.s.state["repairs"], 0)
                if original is None:
                    (self.root / path).unlink()
                else:
                    (self.root / path).write_bytes(original)

    def test_deleted_and_renamed_tests_are_protected(self):
        self.failure()
        self.g("mv", "app/tests/test_main.py", "app/rescued.py")
        with self.assertRaises(loop.Stop):
            self.s.retry(argparse.Namespace(reason="rename", file=["app/tests/test_main.py", "app/rescued.py"]))
        self.assertEqual(self.s.remote_sha(), self.initial)

    def test_staged_protected_change_cannot_hide_behind_worktree(self):
        self.failure()
        path = ".deploy/config.yaml"
        self.write(path, "compliance: none\n")
        self.g("add", path)
        self.write(path, "compliance: regulated\n")
        self.write("app/main.py", "value = 2\n")
        with self.assertRaises(loop.Stop):
            self.s.retry(argparse.Namespace(reason="hidden", file=["app/main.py"]))
        self.assertEqual(self.s.remote_sha(), self.initial)

    def test_unexpected_allowed_file_stops(self):
        self.failure()
        self.write("app/main.py", "value = 2\n")
        self.write("app/unrelated.py", "value = 3\n")
        with self.assertRaises(loop.Stop):
            self.s.retry(argparse.Namespace(reason="fix", file=["app/main.py"]))
        self.assertEqual(self.s.state["repairs"], 0)

    def test_symlinks_and_staged_symlinks_are_rejected(self):
        self.failure()
        (self.root / "app/link.py").symlink_to(self.root / ".deploy/config.yaml")
        self.g("add", "app/link.py")
        (self.root / "app/link.py").unlink()
        self.write("app/link.py", "value = 2\n")
        with self.assertRaises(loop.Stop):
            self.s.retry(argparse.Namespace(reason="link", file=["app/link.py"]))
        self.assertEqual(self.s.remote_sha(), self.initial)

    def test_parent_symlink_rejected(self):
        self.failure()
        external = self.base / "outside"
        external.mkdir()
        (self.root / "app/link").symlink_to(external)
        (external / "value.py").write_text("x=1\n")
        with self.assertRaises(loop.Stop):
            self.s.allowed("app/link/value.py")

    def test_source_dockerfile_and_values_changes_allowed(self):
        self.failure()
        files = ["app/main.py", "app/Dockerfile", "deploy/values-app.yaml", "infra/envs/aws/terraform.tfvars"]
        for path in files:
            with (self.root / path).open("a") as out:
                out.write("# fix\n")
        self.s.retry(argparse.Namespace(reason="allowed changes", file=files))
        self.assertEqual(self.s.state["repairs"], 1)
        self.assertEqual(self.s.remote_sha(), self.s.head())

    def test_three_repairs_and_resume_do_not_reset_budget(self):
        for i in range(3):
            self.failure()
            self.repair(i + 2)
            self.s = loop.Session(self.root)
            self.s.init(self.options())
            self.assertEqual(self.s.state["repairs"], i + 1)
        self.scenario_for()
        self.s.watch(discovery_seconds=0)
        self.assertEqual(self.s.state["status"], "stopped")
        sha = self.s.head()
        with self.assertRaises(loop.Stop):
            self.repair(10)
        self.assertEqual(self.s.head(), sha)
        self.assertEqual(self.s.remote_sha(), sha)
        self.assertEqual(self.g("rev-list", "--count", f"{self.initial}..HEAD"), "3")

    def test_pending_push_reuses_commit(self):
        self.failure()
        hook = self.remote / "hooks/pre-receive"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaises(loop.Stop):
            self.repair()
        sha = self.s.head()
        self.assertEqual(self.s.state["status"], "pending_push")
        self.assertEqual(self.s.state["repairs"], 1)
        hook.unlink()
        self.s = loop.Session(self.root)
        self.s.load()
        self.s.retry(argparse.Namespace(reason=None, file=[]))
        self.assertEqual(self.s.head(), sha)
        self.assertEqual(self.s.remote_sha(), sha)
        self.assertEqual(self.s.state["repairs"], 1)

    def test_already_delivered_push_is_not_duplicated(self):
        self.failure()
        self.repair()
        sha = self.s.head()
        self.s.state["status"] = "pending_push"
        self.s.save()
        self.s.retry(argparse.Namespace(reason=None, file=[]))
        self.assertEqual(self.s.head(), sha)
        self.assertEqual(self.s.state["repairs"], 1)

    def test_remote_change_blocks_repair(self):
        self.failure()
        changed = self.g("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "other worker")
        # Transfer the object, then move the remote ref, without moving local HEAD.
        self.g("push", "origin", f"{changed}:refs/heads/yolo/test")
        with self.assertRaises(loop.Stop):
            self.repair()
        self.assertEqual(self.s.head(), self.initial)

    def test_unexpected_local_commit_blocks_repair(self):
        self.failure()
        self.write("app/unrelated.py", "x = 1\n")
        self.g("add", ".")
        self.g("commit", "-qm", "unexpected")
        with self.assertRaises(loop.Stop):
            self.repair()
        self.assertEqual(self.s.remote_sha(), self.initial)

    def test_commit_hook_cannot_change_validated_tree(self):
        self.failure()
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nprintf 'compliance: none\\n' > .deploy/config.yaml\ngit add .deploy/config.yaml\n")
        hook.chmod(0o755)
        with self.assertRaises(loop.Stop):
            self.repair()
        self.assertEqual(self.s.state["status"], "committing")
        self.assertEqual(self.s.remote_sha(), self.initial)
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)

    def test_success_and_report_create_no_extra_commit(self):
        self.failure()
        self.repair()
        sha = self.s.head()
        self.scenario_for(self.run_data(checks="success", deployment="success", conclusion="success"))
        self.s.watch(discovery_seconds=0)
        report = self.s.report()
        self.assertEqual(report["status"], "complete")
        self.assertEqual(report["promotion"], "not_verified")
        self.assertEqual(self.s.head(), sha)
        self.assertEqual(self.s.remote_sha(), sha)
        self.assertTrue(self.s.clean())

    def test_t8_merge_and_branch_deletion_are_observed_without_push(self):
        data = self.run_data(checks="success", deployment="success", conclusion="success")
        data["jobs"].append({"name": "test / yolo-pr", "status": "completed", "conclusion": "success"})
        pull = {"url": "https://github.com/test/app/pull/1", "state": "MERGED", "headRefOid": self.initial}
        self.scenario_for(data, pulls=[pull])
        self.g("push", "origin", "--delete", "yolo/test")
        self.s.watch(discovery_seconds=0)
        self.assertEqual(self.s.report()["status"], "complete")
        self.assertEqual(self.s.report()["pull_request"], pull)
        self.assertIsNone(self.s.remote_sha(missing_ok=True))
        self.assertEqual(self.s.head(), self.initial)

    def test_unexplained_branch_deletion_stops(self):
        self.scenario_for(self.run_data(checks="success", deployment="success", conclusion="success"))
        self.g("push", "origin", "--delete", "yolo/test")
        with self.assertRaises(loop.Stop):
            self.s.watch(discovery_seconds=0)

    def test_t8_failure_is_not_an_app_repair(self):
        data = self.run_data(checks="success", deployment="success")
        data["jobs"].append({"name": "test / yolo-pr", "status": "completed", "conclusion": "failure"})
        self.scenario_for(data)
        self.s.watch(discovery_seconds=0)
        self.assertEqual(self.s.state["status"], "stopped")
        with self.assertRaises(loop.Stop):
            self.repair()

    def test_scope_and_corrupted_state_cannot_reset(self):
        with self.assertRaises(loop.Stop):
            self.s.init(self.options(source=["."]))
        self.s.path.write_text("not json")
        with self.assertRaises(loop.Stop):
            self.s.init(self.options())
        self.s.path.unlink()
        (self.s.directory / "previous.log").write_text("previous run")
        with self.assertRaises(loop.Stop):
            self.s.init(self.options())

    def test_failed_local_validation_does_not_consume_attempt(self):
        self.failure()
        self.s.state["checks"] = [[sys.executable, "-c", "raise SystemExit(1)"]]
        with self.assertRaises(loop.Stop):
            self.repair()
        self.assertEqual(self.s.state["repairs"], 0)
        self.assertEqual(self.s.head(), self.initial)
        self.assertEqual(self.s.remote_sha(), self.initial)

    def test_fixture_lint_and_test_failure_repaired_without_test_edits(self):
        # The fixed test and lint command are established before the repair session.
        self.write("app/main.py", "def add(a, b):\n    return a - b\n")
        self.write("app/tests/test_main.py", "import unittest\nfrom app.main import add\nclass TestAdd(unittest.TestCase):\n    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n")
        self.g("add", ".")
        self.g("commit", "-qm", "seed test failure")
        self.g("push", "-q", "origin", "HEAD")
        self.s.state["initial_sha"] = self.s.state["sha"] = self.s.head()
        test = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "app/tests"]
        self.assertNotEqual(loop.command(test, self.root, allow_failure=True).returncode, 0)
        original_test = (self.root / "app/tests/test_main.py").read_bytes()
        self.s.state["checks"] = [test]
        self.s.save()
        self.failure()
        self.write("app/main.py", "def add(a, b):\n    return a + b\n")
        self.s.retry(argparse.Namespace(reason="덧셈 구현의 연산자 오류 수정", file=["app/main.py"]))
        self.assertEqual((self.root / "app/tests/test_main.py").read_bytes(), original_test)
        self.assertEqual(loop.command(test, self.root).returncode, 0)
        # Use the same repository for a separate syntax/lint failure scenario.
        self.write("app/main.py", "def add(a, b)\n    return a + b\n")
        self.g("add", ".")
        self.g("commit", "-qm", "seed syntax failure")
        self.g("push", "-q", "origin", "HEAD")
        self.s.state["sha"] = self.s.head()
        lint = [sys.executable, "-c", "import ast,pathlib; ast.parse(pathlib.Path('app/main.py').read_text())"]
        self.assertNotEqual(loop.command(lint, self.root, allow_failure=True).returncode, 0)
        self.s.state["checks"] = [lint, test]
        self.s.save()
        self.failure()
        self.write("app/main.py", "def add(a, b):\n    return a + b\n")
        self.s.retry(argparse.Namespace(reason="함수 선언의 콜론 누락 수정", file=["app/main.py"]))
        self.assertEqual((self.root / "app/tests/test_main.py").read_bytes(), original_test)
        self.assertEqual(loop.command(lint, self.root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
