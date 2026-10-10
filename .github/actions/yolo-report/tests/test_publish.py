import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publish", HERE / "publish.py")
publish = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish)

REPO = "SoftBank-Hackathon-2026-Team-Amethyst/demo-app"


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.summary = self.dir / "summary.md"
        self.output = self.dir / "output.txt"
        self.calls = []
        self.issues = []          # gh issue list 결과
        self.fail = set()         # 실패시킬 명령 이름: s3 · list · create · assignee · comment
        self.bodies = []

    def use(self, example, **change):
        report = json.loads((HERE / "examples" / example).read_text())
        for path, value in change.items():
            target = report
            *parents, last = path.split(".")
            for name in parents:
                target = target[name]
            target[last] = value
        path = self.dir / "report.json"
        path.write_text(json.dumps(report, ensure_ascii=False))
        return path, report

    def aws(self, *args):
        self.calls.append(("aws",) + args)
        if "s3" in self.fail:
            raise publish.PublishError("aws s3api 실패: AccessDenied")
        return "{}"

    def gh(self, *args):
        self.calls.append(("gh",) + args)
        if "--body-file" in args:
            self.bodies.append(Path(args[args.index("--body-file") + 1]).read_text())
        if args[:2] == ("issue", "list"):
            if "list" in self.fail:
                raise publish.PublishError("gh issue 실패: HTTP 403")
            return json.dumps(self.issues)
        if args[:2] == ("issue", "create"):
            if "create" in self.fail or ("assignee" in self.fail and "--assignee" in args):
                raise publish.PublishError("gh issue 실패")
            return f"https://github.com/{REPO}/issues/7"
        if args[:2] == ("issue", "comment") and "comment" in self.fail:
            raise publish.PublishError("gh issue 실패")
        return ""

    def run_publish(self, path, bucket="audit-bucket"):
        env = {"GITHUB_STEP_SUMMARY": str(self.summary), "GITHUB_OUTPUT": str(self.output)}
        with patch.object(publish, "aws", self.aws), patch.object(publish, "gh", self.gh), \
                patch.dict(os.environ, env), contextlib.redirect_stdout(io.StringIO()):
            return publish.main(["--report", str(path), "--bucket", bucket])

    def names(self, tool, *prefix):
        return [c for c in self.calls if c[0] == tool and c[1:1 + len(prefix)] == prefix]

    def outputs(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_debt_saves_and_opens_issue(self):
        path, report = self.use("report-debt.json")
        self.assertEqual(self.run_publish(path), 0)
        put = self.names("aws", "s3api", "put-object")[0]
        key = put[put.index("--key") + 1]
        self.assertEqual(key, "reports/yolo/2026/10/10/2026-10-10T05:12:40Z-4f1c2b7e9d0a-37950112233-1.json")
        self.assertIn("SHA256", put)
        create = self.names("gh", "issue", "create")[0]
        self.assertEqual(create[create.index("--title") + 1], "[yolo-debt] yolo/guestbook-limit · 4f1c2b7")
        self.assertEqual(create[create.index("--assignee") + 1], "baekyutae")
        self.assertEqual(create[create.index("--label") + 1], "yolo-debt")
        body = self.bodies[-1]
        self.assertTrue(body.startswith(publish.marker(report)))
        self.assertIn("**기한:** 다음 정석(janto) 배포 전까지", body)
        self.assertIn("**담당자가 할 일**", body)
        self.assertNotIn("빚", body)
        self.assertIn("CVE-2026-00001", body)              # 새 경고는 상세
        self.assertNotIn("CVE-2026-00002", body)           # 원래 있던 경고는 건수만
        self.assertIn("main에 원래 있던 비차단 경고 2건", body)
        self.assertIn("s3://audit-bucket/reports/yolo/", body)
        self.assertEqual(self.outputs()["issue"], f"https://github.com/{REPO}/issues/7")
        self.assertIn("yolo-debt: 있음", self.summary.read_text())

    def test_same_branch_gets_a_comment(self):
        path, report = self.use("report-debt.json")
        self.issues = [{"number": 3, "url": f"https://github.com/{REPO}/issues/3", "body": publish.marker(report) + "\n..."},
                       {"number": 4, "url": "other", "body": "<!-- yolo-debt repository=x branch=yolo/other -->"}]
        self.assertEqual(self.run_publish(path), 0)
        self.assertEqual(self.names("gh", "issue", "create"), [])
        comment = self.names("gh", "issue", "comment")[0]
        self.assertEqual(comment[3], "3")
        self.assertIn("같은 브랜치의 새 yolo 배포", self.bodies[-1])
        self.assertEqual(self.outputs()["issue"], f"https://github.com/{REPO}/issues/3")

    def test_other_branch_issue_is_not_reused(self):
        path, _ = self.use("report-debt.json")
        self.issues = [{"number": 4, "url": "other", "body": f"<!-- yolo-debt repository={REPO} branch=yolo/other -->"}]
        self.run_publish(path)
        self.assertEqual(len(self.names("gh", "issue", "create")), 1)

    def test_clean_report_opens_nothing(self):
        path, _ = self.use("report-clean.json")
        self.assertEqual(self.run_publish(path), 0)
        self.assertEqual(self.names("gh"), [])
        self.assertEqual(len(self.names("aws", "s3api", "put-object")), 1)
        self.assertIn("yolo-debt: 없음", self.summary.read_text())
        self.assertEqual(self.outputs()["open-issue"], "false")

    def test_s3_failure_fails_but_still_opens_issue(self):
        path, _ = self.use("report-debt.json")
        self.fail = {"s3"}
        self.assertEqual(self.run_publish(path), 1)
        self.assertEqual(len(self.names("gh", "issue", "create")), 1)
        self.assertIn("저장 실패", self.bodies[-1])
        self.assertIn("저장 실패", self.summary.read_text())
        self.assertEqual(self.outputs()["location"], "")

    def test_missing_bucket_fails(self):
        path, _ = self.use("report-clean.json")
        self.assertEqual(self.run_publish(path, bucket=""), 1)
        self.assertEqual(self.names("aws"), [])

    def test_unassignable_actor_opens_without_assignee(self):
        path, _ = self.use("report-debt.json", **{"deploy.actor": "github-actions[bot]"})
        self.fail = {"assignee"}
        self.assertEqual(self.run_publish(path), 0)
        creates = self.names("gh", "issue", "create")
        self.assertEqual(len(creates), 2)
        self.assertNotIn("--assignee", creates[-1])

    def test_issue_failure_fails(self):
        path, _ = self.use("report-debt.json")
        self.fail = {"list"}
        self.assertEqual(self.run_publish(path), 1)
        self.assertIn("이슈: 생성 실패", self.summary.read_text())

    def test_partial_report_lists_collection_failures(self):
        path, _ = self.use("report-partial.json")
        self.assertEqual(self.run_publish(path), 0)
        body = self.bodies[-1]
        self.assertIn("### 수집 실패", body)
        self.assertIn("`judgment`", body)

    def test_markdown_cells_are_escaped(self):
        path, _ = self.use("report-debt.json")
        report = json.loads(path.read_text())
        report["warnings"]["items"][0]["title"] = "a | b\nc"
        path.write_text(json.dumps(report, ensure_ascii=False))
        self.run_publish(path)
        self.assertIn("a \\| b c", self.bodies[-1])


if __name__ == "__main__":
    unittest.main()
