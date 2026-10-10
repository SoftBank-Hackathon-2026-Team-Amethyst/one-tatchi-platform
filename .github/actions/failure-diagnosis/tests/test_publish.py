"""publish.py 테스트: 가짜 gh(PR · 코멘트 상태를 파일에 둔다)와 가짜 Slack API로 게시 결과를 본다."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

HERE = Path(__file__).resolve().parents[1]
EXAMPLES = HERE / "examples"
REPO = "SoftBank-Hackathon-2026-Team-Amethyst/demo-app"

# 가짜 gh: FAKE_GH 폴더의 prs.json(커밋에 연결된 PR) · comments.json(PR 코멘트)을 읽고 쓴다.
# FAKE_GH_FAIL에 든 낱말이 경로에 있으면 그 호출은 실패한다.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, subprocess, sys
d = os.environ["FAKE_GH"]
args = sys.argv[1:]
with open(os.path.join(d, "calls.txt"), "a") as f:
    f.write(" ".join(args) + "\n")
path = next(a for a in args[1:] if a.startswith("repos/"))
fail = os.environ.get("FAKE_GH_FAIL")
if fail and fail in path:
    sys.exit(print("HTTP 403: Resource not accessible by integration", file=sys.stderr) or 1)
store = os.path.join(d, "comments.json")
comments = json.load(open(store)) if os.path.exists(store) else []
def body():
    value = args[args.index("-F") + 1]
    return open(value.split("=@", 1)[1]).read()
if path.endswith("/pulls"):
    prs = os.path.join(d, "prs.json")
    print(open(prs).read() if os.path.exists(prs) else "[]")
elif "-X" in args and args[args.index("-X") + 1] == "PATCH":
    cid = int(path.rsplit("/", 1)[1])
    for c in comments:
        if c["id"] == cid:
            c["body"] = body()
    json.dump(comments, open(store, "w"))
    print(json.dumps({"id": cid, "html_url": f"https://github.com/x/pull/7#issuecomment-{cid}"}))
elif "-X" in args and args[args.index("-X") + 1] == "POST":
    cid = 100 + len(comments)
    comments.append({"id": cid, "body": body()})
    json.dump(comments, open(store, "w"))
    print(json.dumps({"id": cid, "html_url": f"https://github.com/x/pull/7#issuecomment-{cid}"}))
else:
    expr = args[args.index("--jq") + 1]
    print(subprocess.run(["jq", "-r", expr], input=json.dumps(comments), capture_output=True, text=True, check=True).stdout, end="")
"""


class FakeSlack(BaseHTTPRequestHandler):
    requests = []
    reply = {"ok": True}

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        FakeSlack.requests.append({"path": self.path, "auth": self.headers.get("Authorization"), "body": body})
        data = json.dumps(FakeSlack.reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class PublishTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.slack = ThreadingHTTPServer(("127.0.0.1", 0), FakeSlack)
        threading.Thread(target=cls.slack.serve_forever, daemon=True).start()
        cls.slack_url = f"http://127.0.0.1:{cls.slack.server_address[1]}/api"

    @classmethod
    def tearDownClass(cls):
        cls.slack.shutdown()
        cls.slack.server_close()

    def setUp(self):
        FakeSlack.requests, FakeSlack.reply = [], {"ok": True}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.fake = root / "gh"
        self.fake.mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        self.path = f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
        self.evidence = root / "evidence.json"
        self.evidence.write_text((EXAMPLES / "evidence-migration.json").read_text())
        self.sha = json.loads(self.evidence.read_text())["run"]["sha"]
        self.diagnosis = root / "diagnosis.json"
        self.diagnosis.write_text((EXAMPLES / "diagnosis-migration.json").read_text())
        self.summary = root / "summary.md"
        self.output = root / "output"

    def prs(self, *items):
        (self.fake / "prs.json").write_text(json.dumps(list(items)))

    def comments(self):
        store = self.fake / "comments.json"
        return json.loads(store.read_text()) if store.exists() else []

    def publish(self, *extra, gh_token="bot-token", slack_token="xoxb-test", channel="C123", **env):
        full = {k: v for k, v in os.environ.items() if k not in ("GH_TOKEN", "SLACK_BOT_TOKEN", "SLACK_CHANNEL_ID")}
        full.update({"PATH": self.path, "FAKE_GH": str(self.fake), "SLACK_API_URL": self.slack_url,
                     "GITHUB_STEP_SUMMARY": str(self.summary), "GITHUB_OUTPUT": str(self.output), **env})
        for key, value in (("GH_TOKEN", gh_token), ("SLACK_BOT_TOKEN", slack_token), ("SLACK_CHANNEL_ID", channel)):
            if value:
                full[key] = value
        proc = subprocess.run([sys.executable, "-B", str(HERE / "publish.py"), "--evidence", str(self.evidence),
                               "--diagnosis", str(self.diagnosis), *extra], env=full, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.stdout = proc.stdout
        return self.summary.read_text() if self.summary.exists() else ""

    def output_values(self):
        return dict(line.split("=", 1) for line in self.output.read_text().splitlines())

    def test_open_pr_gets_comment_and_slack(self):
        self.prs({"number": 7, "state": "open", "html_url": "https://github.com/x/pull/7"})
        summary = self.publish()
        [c] = self.comments()
        self.assertTrue(c["body"].startswith(f"<!-- failure-diagnosis sha={self.sha} -->"))
        self.assertIn("**마이그레이션** — demo-app-be 배포 전에 도는 마이그레이션 Job이", c["body"])
        self.assertIn("```text\nError: UPGRADE FAILED", c["body"])
        self.assertIn("- kubectl -n test logs job/demo-app-be-migration", c["body"])
        # 실행 요약에는 PR 코멘트 주소가 붙는다
        self.assertIn("## 배포 실패 원인 진단 (T12)", summary)
        self.assertIn("| PR 코멘트 | https://github.com/x/pull/7#issuecomment-100 |", summary)
        self.assertIn("| 실패한 단계 | test / deploy", summary)
        self.assertEqual(self.output_values(), {"pr-comment": "https://github.com/x/pull/7#issuecomment-100",
                                                "slack": "sent"})
        [req] = FakeSlack.requests
        self.assertEqual((req["path"], req["auth"], req["body"]["channel"]),
                         ("/api/chat.postMessage", "Bearer xoxb-test", "C123"))
        text = json.dumps(req["body"], ensure_ascii=False)
        self.assertIn("배포 실패 원인 요약", text)
        self.assertIn("*마이그레이션*", text)
        self.assertIn("<https://github.com/x/pull/7#issuecomment-100|PR 코멘트>", text)
        self.assertIn("AI 요약 (claude-sonnet-5-5) · 확신도 보통", text)

    def test_rerun_updates_same_comment(self):
        """같은 커밋을 다시 실행하면 코멘트를 새로 달지 않고 고친다."""
        self.prs({"number": 7, "state": "open"})
        (self.fake / "comments.json").write_text(json.dumps([{"id": 55, "body": "사람이 단 코멘트"}]))
        self.publish()
        self.diagnosis.write_text((EXAMPLES / "diagnosis-fallback.json").read_text())
        self.publish()
        comments = self.comments()
        self.assertEqual([c["id"] for c in comments], [55, 101])
        self.assertIn("AI 요약 없음 — Claude API 시간 초과 (60초)", comments[1]["body"])
        self.assertIn(f"repos/{REPO}/issues/comments/101", (self.fake / "calls.txt").read_text())

    def test_merged_pr_for_main_deploy(self):
        """main 배포처럼 열린 PR이 없으면 이 커밋으로 머지된 PR에 단다. 커밋을 포함만 한 다른 PR에는 달지 않는다."""
        self.prs({"number": 3, "state": "closed", "merge_commit_sha": "0" * 40},
                 {"number": 9, "state": "closed", "merge_commit_sha": self.sha})
        self.publish()
        self.assertIn(f"repos/{REPO}/issues/9/comments", (self.fake / "calls.txt").read_text())
        self.prs({"number": 3, "state": "closed", "merge_commit_sha": "0" * 40})
        before = len(self.comments())
        self.publish()
        self.assertEqual(len(self.comments()), before)

    def test_no_pr(self):
        """yolo 첫 push · 수동 실행처럼 PR이 없으면 코멘트 없이 실행 요약 · Slack만 남긴다."""
        summary = self.publish()
        self.assertEqual(self.comments(), [])
        self.assertNotIn("PR 코멘트", summary)
        self.assertIn("커밋에 연결된 PR이 없어", self.stdout)
        self.assertEqual(self.output_values(), {"pr-comment": "", "slack": "sent"})
        self.assertNotIn("PR 코멘트", json.dumps(FakeSlack.requests[0]["body"], ensure_ascii=False))

    def test_no_tokens(self):
        """토큰이 없으면 경고만 남기고 실행 요약은 남긴다."""
        summary = self.publish(gh_token=None, slack_token=None)
        self.assertIn("## 배포 실패 원인 진단", summary)
        self.assertIn("::warning::GH_TOKEN(봇 App 토큰)이 없어 PR 코멘트를 건너뛴다", self.stdout)
        self.assertIn("Slack 설정(SLACK_BOT_TOKEN, SLACK_CHANNEL_ID)이 없어", self.stdout)
        self.assertFalse((self.fake / "calls.txt").exists())
        self.assertEqual(FakeSlack.requests, [])
        self.assertEqual(self.output_values()["slack"], "skipped")

    def test_failures_are_warnings(self):
        self.prs({"number": 7, "state": "open"})
        FakeSlack.reply = {"ok": False, "error": "channel_not_found"}
        summary = self.publish(FAKE_GH_FAIL="/commits/")
        self.assertIn("::warning::PR 코멘트 실패: gh api 실패: HTTP 403", self.stdout)
        self.assertIn("::warning::Slack 오류: channel_not_found", self.stdout)
        self.assertIn("## 배포 실패 원인 진단", summary)
        self.assertEqual(self.output_values()["slack"], "failed")

    def test_slack_unreachable(self):
        summary = self.publish(SLACK_API_URL="http://127.0.0.1:9/api")
        self.assertIn("::warning::Slack 호출 실패", self.stdout)
        self.assertTrue(summary)

    def test_no_pr_comment_option(self):
        self.prs({"number": 7, "state": "open"})
        self.publish("--no-pr-comment")
        self.assertFalse((self.fake / "calls.txt").exists())

    def test_missing_diagnosis_uses_fallback(self):
        self.diagnosis.unlink()
        summary = self.publish()
        self.assertIn("**알 수 없음** — AI 요약을 받지 못했다", summary)
        self.assertIn("AI 요약 없음 — 진단 결과(diagnosis.json)가 없다", summary)
        self.assertIn("Error: UPGRADE FAILED", summary)

    def test_missing_evidence(self):
        self.evidence.unlink()
        summary = self.publish()
        self.assertEqual(summary, "")
        self.assertIn("::warning::증거 묶음(evidence.json)이 없어", self.stdout)
        self.assertEqual(FakeSlack.requests, [])

    def test_escaping(self):
        """Markdown 표 · 코드 블록과 Slack 링크 문법을 깨지 않는다."""
        diagnosis = json.loads(self.diagnosis.read_text())
        diagnosis["summary"] = "값 <a|b> & 끝"
        diagnosis["evidence"] = ["```끝내기```"]
        self.diagnosis.write_text(json.dumps(diagnosis, ensure_ascii=False))
        evidence = json.loads(self.evidence.read_text())
        evidence["deploy"]["target_label"] = "AWS | EKS"
        evidence["collection"]["cluster"] = {"status": "failed", "detail": "Unable to connect\nto server"}
        self.evidence.write_text(json.dumps(evidence, ensure_ascii=False))
        summary = self.publish()
        self.assertIn("| 대상 · 환경 | AWS \\| EKS / test", summary)
        self.assertIn("'''끝내기'''", summary)
        self.assertIn("- `cluster`: Unable to connect to server", summary)
        self.assertIn("값 &lt;a|b&gt; &amp; 끝", FakeSlack.requests[0]["body"]["text"])


if __name__ == "__main__":
    unittest.main()
