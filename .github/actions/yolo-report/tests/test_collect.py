import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("collect", HERE / "collect.py")
collect = importlib.util.module_from_spec(spec)
spec.loader.exec_module(collect)

try:
    from jsonschema import Draft202012Validator
    VALIDATOR = Draft202012Validator(json.loads((HERE / "schema.json").read_text()))
except ImportError:  # CI는 uv로 jsonschema를 넣고 돌린다 (ci.yml scripts)
    VALIDATOR = None


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        run(self.repo, "git", "init", "-q", "-b", "main")
        run(self.repo, "git", "config", "user.email", "t@example.test")
        run(self.repo, "git", "config", "user.name", "tester")
        (self.repo / ".deploy").mkdir()
        self.write_config("regulated")
        (self.repo / "app.ts").write_text("v1\n")
        self.commit("초기")
        run(self.repo, "git", "switch", "-q", "-c", "yolo/example")
        (self.repo / "app.ts").write_text("v2\n")
        self.sha = self.commit("[yolo] 기능 추가")
        self.work = root / "work"
        self.work.mkdir()
        self.promotion = self.work / "yolo-promotion.json"
        self.write_promotion(self.sha)
        self.judgment = self.work / "promote-judge"
        self.write_judgment("promote", p95=140)
        self.warnings = self.work / "warnings.json"
        self.write_warnings([])

    # ---- 입력 만들기 ----
    def commit(self, message, body=None):
        run(self.repo, "git", "add", "-A")
        args = ["git", "commit", "-q", "-m", message] + (["-m", body] if body else [])
        run(self.repo, *args)
        return run(self.repo, "git", "rev-parse", "HEAD")

    def write_config(self, compliance):
        lines = ["# 배포 설정", "template_version: v2.2.0"]
        if compliance:
            lines.append(f"compliance: {compliance}  # 주석")
        (self.repo / ".deploy" / "config.yaml").write_text("\n".join(lines) + "\n")

    def write_promotion(self, sha):
        self.promotion.write_text(json.dumps({"sha": sha, "promoted": True, "environment": "test"}))

    def write_judgment(self, decision, p95=140, source=None):
        self.judgment.mkdir(exist_ok=True)
        services = {}
        for name in ("demo-app-be", "demo-app-fe"):
            (self.judgment / name).mkdir(exist_ok=True)
            metrics = {"requests": 100, "failed": 0 if decision == "promote" else 3,
                       "error_rate": 0 if decision == "promote" else 3, "p95_ms": p95,
                       "pods": {"count": 1, "ready": 1, "restarts": 0},
                       "thresholds": {"max_error_rate": 0, "max_p95_ms": 2000, "max_restarts": 0},
                       "rule": {"verdict": "pass" if decision == "promote" else "fail", "reasons": []}}
            detail = {"release": name, "decision": decision,
                      "source": source or ("ai" if decision == "promote" else "rule"),
                      "reason": f"{name} 근거", "metrics": metrics}
            (self.judgment / name / "judgment.json").write_text(json.dumps(detail))
            services[name] = {"decision": decision, "source": detail["source"], "reason": detail["reason"]}
        (self.judgment / "judgment.json").write_text(json.dumps(
            {"decision": decision, "reason": "묶음 근거", "services": services}))

    def write_warnings(self, items, status="ok", detail=None):
        self.warnings.write_text(json.dumps({
            "status": status, "detail": detail, "items": items,
            "scanner": {"name": "trivy", "version": "0.75.0", "db_updated_at": "2026-10-10T00:00:00Z"}}))

    def build(self, *extra, **override):
        argv = ["--output", str(self.work / "report.json"), "--repo-root", str(self.repo),
                "--base-ref", "main", "--target", "aws", "--sha", self.sha,
                "--branch", "yolo/example", "--actor", "tester", "--repository", "org/demo-app",
                "--run-id", "100", "--run-attempt", "1", "--run-url", "https://example.test/run/100",
                "--now", "2026-10-10T00:00:00Z"]
        inputs = {"--promotion": self.promotion, "--judgment-dir": self.judgment, "--warnings": self.warnings}
        inputs.update(override)
        for flag, value in inputs.items():
            if value is not None:
                argv += [flag, str(value)]
        report = collect.build(collect.parse(argv + list(extra)))
        if VALIDATOR is not None:
            errors = [f"{e.json_path}: {e.message}" for e in VALIDATOR.iter_errors(report)]
            self.assertEqual(errors, [], "스키마 위반")
        return report

    # ---- 상황별 ----
    def test_clean_deploy_opens_no_issue(self):
        report = self.build()
        self.assertTrue(report["deploy"]["promoted"])
        self.assertEqual(report["deploy"]["compliance"], "regulated")
        self.assertEqual(report["deploy"]["template_version"], "v2.2.0")
        self.assertEqual(report["approval"]["status"], "required")
        self.assertEqual(report["judgment"]["decision"], "promote")
        self.assertEqual(report["collection"]["lint"]["status"], "not_collected")
        self.assertEqual(report["debt"], {"open_issue": False, "reasons": []})

    def test_repairs_are_listed_without_history_file(self):
        for n in (1, 2):
            (self.repo / "app.ts").write_text(f"fix{n}\n")
            (self.repo / ".deploy" / "log").mkdir(exist_ok=True)
            (self.repo / ".deploy" / "log" / "20261010-000000-abcd1234-yolo.md").write_text(f"{n}\n")
            self.sha = self.commit(f"[yolo] 검사 실패 자동 수정 {n}/3", f"테스트 실패 {n} 수정")
        self.write_promotion(self.sha)
        report = self.build()
        self.assertEqual(report["repairs"]["count"], 2)
        self.assertEqual([i["number"] for i in report["repairs"]["items"]], [1, 2])
        self.assertEqual(report["repairs"]["items"][0]["files"], ["app.ts"])
        self.assertEqual(report["repairs"]["items"][1]["reason"], "테스트 실패 2 수정")
        self.assertEqual(report["repairs"]["history_file"], ".deploy/log/20261010-000000-abcd1234-yolo.md")
        self.assertEqual(report["debt"]["reasons"], ["AI 자동 수정 2회"])

    def test_other_commits_are_not_repairs(self):
        (self.repo / "app.ts").write_text("v3\n")
        self.sha = self.commit("[yolo] 검사 실패 자동 수정 4/3")  # 형식 밖
        self.write_promotion(self.sha)
        self.assertEqual(self.build()["repairs"]["count"], 0)

    def test_warnings_open_issue(self):
        self.write_warnings([
            {"source": "vulnerability", "severity": "MEDIUM", "id": "CVE-1", "target": "be/pnpm-lock.yaml",
             "package": "lib", "title": "x" * 500},
            {"source": "scan_exception", "severity": "UNKNOWN", "id": "CVE-2", "target": ".trivyignore",
             "package": None, "title": "패치 대기"}])
        report = self.build()
        self.assertEqual(report["warnings"]["total"], 2)
        self.assertEqual(len(report["warnings"]["items"][0]["title"]), 300)
        self.assertEqual(report["debt"]["reasons"], ["차단하지 않은 경고 2건 (취약점 MEDIUM 1, 검사 예외 1)"])

    def test_missing_judgment_is_a_failure(self):
        report = self.build(**{"--judgment-dir": self.work / "없음"})
        self.assertEqual(report["collection"]["judgment"]["status"], "failed")
        self.assertIsNone(report["judgment"]["decision"])
        self.assertTrue(report["debt"]["open_issue"])
        self.assertIn("수집 실패: judgment", report["debt"]["reasons"][0])

    def test_skipped_judgment_is_not_a_failure(self):
        report = self.build("--judge-outcome", "skipped", **{"--judgment-dir": None})
        self.assertEqual(report["collection"]["judgment"]["status"], "not_collected")
        self.assertFalse(report["debt"]["open_issue"])

    def test_abort_without_promotion(self):
        self.write_judgment("abort")
        report = self.build(**{"--promotion": None})
        self.assertFalse(report["deploy"]["promoted"])
        self.assertEqual(report["approval"]["status"], "not_reached")
        self.assertEqual(report["judgment"]["services"]["demo-app-be"]["source"], "rule")
        self.assertFalse(report["debt"]["open_issue"])  # abort만으로는 이슈를 열지 않는다

    def test_promotion_for_other_sha_is_a_failure(self):
        self.write_promotion("b" * 40)
        report = self.build()
        self.assertEqual(report["collection"]["deploy"]["status"], "failed")
        self.assertFalse(report["deploy"]["promoted"])
        self.assertTrue(report["debt"]["open_issue"])

    def test_failed_or_missing_warning_scan(self):
        self.write_warnings([], status="failed", detail="Trivy DB 다운로드 실패")
        self.assertEqual(self.build()["collection"]["warnings"],
                         {"status": "failed", "detail": "Trivy DB 다운로드 실패"})
        report = self.build(**{"--warnings": None})
        self.assertEqual(report["collection"]["warnings"]["status"], "failed")
        self.assertIsNone(report["warnings"]["scanner"])

    def test_malformed_warning_item(self):
        self.write_warnings([{"source": "lint", "severity": "MEDIUM", "id": "x", "target": "y"}])
        self.assertEqual(self.build()["collection"]["warnings"]["status"], "failed")

    def test_compliance_none_and_missing(self):
        self.write_config("none")
        self.assertEqual(self.build()["approval"]["status"], "skipped")
        self.write_config(None)
        report = self.build()
        self.assertIsNone(report["deploy"]["compliance"])
        self.assertEqual(report["approval"]["status"], "required")
        self.assertIn("값 없음", report["approval"]["basis"])

    def test_near_threshold_is_shown_not_debt(self):
        self.write_judgment("promote", p95=1720)
        report = self.build()
        self.assertEqual(report["judgment"]["services"]["demo-app-be"]["near_threshold"],
                         ["p95 1720ms ≥ 기준 2000ms의 80%"])
        self.assertFalse(report["debt"]["open_issue"])

    def test_unreadable_git_history_is_a_failure(self):
        report = self.build("--base-ref", "no-such-ref")
        self.assertEqual(report["collection"]["repairs"]["status"], "failed")
        self.assertTrue(report["debt"]["open_issue"])

    def test_only_yolo_branches(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            collect.parse(["--output", "x", "--target", "aws", "--sha", "a" * 40, "--branch", "main",
                           "--actor", "a", "--repository", "o/r", "--run-id", "1", "--run-url", "https://x"])

    def test_cli_writes_report(self):
        out = self.work / "cli.json"
        subprocess.run(["python3", str(HERE / "collect.py"), "--output", str(out), "--repo-root", str(self.repo),
                        "--base-ref", "main", "--target", "aws", "--sha", self.sha, "--branch", "yolo/example",
                        "--actor", "tester", "--repository", "org/demo-app", "--run-id", "1",
                        "--run-url", "https://example.test/run/1", "--promotion", str(self.promotion),
                        "--judgment-dir", str(self.judgment), "--warnings", str(self.warnings)],
                       check=True, capture_output=True, text=True)
        self.assertFalse(json.loads(out.read_text())["debt"]["open_issue"])


class ExamplesTest(unittest.TestCase):
    def test_examples_match_schema(self):
        if VALIDATOR is None:
            self.skipTest("jsonschema 없음")
        for path in sorted((HERE / "examples").glob("*.json")):
            errors = [e.message for e in VALIDATOR.iter_errors(json.loads(path.read_text()))]
            self.assertEqual(errors, [], path.name)


if __name__ == "__main__":
    unittest.main()
