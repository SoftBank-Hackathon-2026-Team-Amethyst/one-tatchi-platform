import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scan_warnings", HERE / "scan_warnings.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
FAKE = str(HERE / "tests" / "fake-trivy")


def run(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def vuln(vid, sev, fixed="1.2.3", pkg="lib", target="be/pnpm-lock.yaml"):
    return {"Target": target, "Vulnerabilities": [
        {"VulnerabilityID": vid, "PkgName": pkg, "Severity": sev, "FixedVersion": fixed, "Title": f"{vid} 설명"}]}


class ScanWarningsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        run(self.repo, "git", "init", "-q", "-b", "main")
        run(self.repo, "git", "config", "user.email", "t@example.test")
        run(self.repo, "git", "config", "user.name", "tester")
        (self.repo / "infra").mkdir()
        (self.repo / "infra" / "main.tf").write_text("# tf\n")
        self.write("fake-vuln-license.json", {"Results": [vuln("CVE-OLD", "MEDIUM")]})
        self.write("fake-misconfig.json", {"Results": [{"Target": "infra/main.tf", "Misconfigurations": [
            {"ID": "AWS-0038", "Severity": "MEDIUM", "Status": "FAIL", "Title": "로그"},
            {"ID": "AWS-0099", "Severity": "LOW", "Status": "PASS", "Title": "통과"}]}]})
        (self.repo / ".trivyignore").write_text(
            "# 파일 머리말\n\n# EKS API 공개\n# 접근은 IAM으로 제한\nAWS-0040\nAWS-0041\n")
        self.commit("초기")
        run(self.repo, "git", "switch", "-q", "-c", "yolo/x")

    def write(self, name, data):
        (self.repo / name).write_text(json.dumps(data))

    def commit(self, message):
        run(self.repo, "git", "add", "-A")
        run(self.repo, "git", "commit", "-q", "-m", message)
        return run(self.repo, "git", "rev-parse", "HEAD")

    def scan(self, sha=None, **env):
        out = Path(self.tmp.name) / "warnings.json"
        argv = ["--output", str(out), "--repo-root", str(self.repo), "--sha", sha or run(self.repo, "git", "rev-parse", "HEAD"),
                "--base-ref", "main", "--iac-path", "infra", "--trivy", FAKE]
        with patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            scan.main(argv)
        return json.loads(out.read_text())

    def test_unchanged_branch_has_no_new_warnings(self):
        result = self.scan()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["base_sha"], run(self.repo, "git", "rev-parse", "main"))
        self.assertEqual(result["scanner"], {"name": "trivy", "version": "0.75.0", "db_updated_at": "2026-10-10T01:03:02Z"})
        kinds = sorted((i["source"], i["id"]) for i in result["items"])
        self.assertEqual(kinds, [("misconfiguration", "AWS-0038"), ("scan_exception", "AWS-0040"),
                                 ("scan_exception", "AWS-0041"), ("vulnerability", "CVE-OLD")])
        self.assertFalse(any(i["new_on_branch"] for i in result["items"]))

    def test_new_findings_are_marked(self):
        self.write("fake-vuln-license.json", {"Results": [
            vuln("CVE-OLD", "MEDIUM"), vuln("CVE-NEW", "LOW"),
            vuln("CVE-HIGH-FIXED", "HIGH"), vuln("CVE-HIGH-UNFIXED", "HIGH", fixed=""),
            {"Target": "fe/pnpm-lock.yaml", "Licenses": [
                {"Severity": "MEDIUM", "Category": "reciprocal", "Name": "MPL-2.0", "PkgName": "x", "FilePath": "fe/node_modules/x"},
                {"Severity": "LOW", "Category": "notice", "Name": "MIT", "PkgName": "y"}]}]})
        with open(self.repo / ".trivyignore", "a") as f:
            f.write("\n# 패치 대기\nCVE-2099-0001 exp:2026-12-31\n")
        result = self.scan(self.commit("변경"))
        new = sorted((i["source"], i["id"]) for i in result["items"] if i["new_on_branch"])
        self.assertEqual(new, [("license", "MPL-2.0"), ("scan_exception", "CVE-2099-0001"),
                               ("vulnerability", "CVE-HIGH-UNFIXED"), ("vulnerability", "CVE-NEW")])
        unfixed = next(i for i in result["items"] if i["id"] == "CVE-HIGH-UNFIXED")
        self.assertTrue(unfixed["title"].startswith("수정판 없음"))
        self.assertNotIn("CVE-HIGH-FIXED", [i["id"] for i in result["items"]])  # 막혔어야 하는 것

    def test_exception_reasons_follow_comment_blocks(self):
        reasons = {i["id"]: i["title"] for i in self.scan()["items"] if i["source"] == "scan_exception"}
        self.assertEqual(reasons, {"AWS-0040": "EKS API 공개 접근은 IAM으로 제한",
                                   "AWS-0041": "EKS API 공개 접근은 IAM으로 제한"})
        (self.repo / ".trivyignore").write_text("CVE-1\n# 사유\nCVE-2\nCVE-3\n# 다른 사유\nCVE-4\n")
        reasons = {i["id"]: i["title"] for i in self.scan(self.commit("예외"))["items"] if i["source"] == "scan_exception"}
        self.assertEqual(reasons, {"CVE-1": "사유 주석 없음", "CVE-2": "사유", "CVE-3": "사유", "CVE-4": "다른 사유"})

    def test_scan_failure_is_reported(self):
        result = self.scan(FAKE_TRIVY_FAIL="misconfig")
        self.assertEqual(result["status"], "failed")
        self.assertIn("실패", result["detail"])
        self.assertEqual(result["items"], [])
        self.assertEqual(run(self.repo, "git", "worktree", "list").count("\n"), 0)  # 임시 worktree 정리

    def test_missing_trivy_and_bad_base(self):
        self.assertEqual(self.scan()["status"], "ok")
        out = Path(self.tmp.name) / "w.json"
        with contextlib.redirect_stdout(io.StringIO()):
            scan.main(["--output", str(out), "--repo-root", str(self.repo), "--sha", "a" * 40, "--trivy", FAKE])
        self.assertEqual(json.loads(out.read_text())["status"], "failed")
        with contextlib.redirect_stdout(io.StringIO()):
            scan.main(["--output", str(out), "--repo-root", str(self.repo), "--sha", "HEAD", "--base-ref", "main",
                       "--trivy", "/no/such/trivy"])
        self.assertEqual(json.loads(out.read_text())["status"], "failed")

    def test_without_iac_path_skips_misconfig(self):
        out = Path(self.tmp.name) / "w.json"
        with contextlib.redirect_stdout(io.StringIO()):
            scan.main(["--output", str(out), "--repo-root", str(self.repo), "--sha", "HEAD", "--base-ref", "main",
                       "--trivy", FAKE])
        sources = {i["source"] for i in json.loads(out.read_text())["items"]}
        self.assertNotIn("misconfiguration", sources)


if __name__ == "__main__":
    unittest.main()
