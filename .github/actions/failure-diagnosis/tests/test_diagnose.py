"""diagnose.py 테스트: 가짜 Claude API(fake_claude.py)로 정상 · 실패 경우의 diagnosis.json을 본다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
EXAMPLES = HERE / "examples"

try:
    from jsonschema import Draft202012Validator
    VALIDATOR = Draft202012Validator(json.loads((HERE / "diagnosis.schema.json").read_text()))
except ImportError:  # CI는 uv로 jsonschema를 넣고 돌린다 (ci.yml scripts)
    VALIDATOR = None


class DiagnoseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.capture = self.root / "request.json"
        self.out = self.root / "diagnosis.json"
        self.github_output = self.root / "github_output"
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text((EXAMPLES / "evidence-migration.json").read_text())

    def start(self, mode):
        server = subprocess.Popen([sys.executable, str(HERE / "tests" / "fake_claude.py"), mode, str(self.capture)],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(self.stop, server)
        port = server.stdout.readline().strip().rsplit(":", 1)[1]
        return f"http://127.0.0.1:{port}"

    @staticmethod
    def stop(server):
        server.kill()
        server.wait()
        server.stdout.close()

    def diagnose(self, mode=None, *extra, key="test-key", **env):
        full = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        full.update(GITHUB_OUTPUT=str(self.github_output), API_TIMEOUT_SECONDS="2", **env)
        if key:
            full["ANTHROPIC_API_KEY"] = key
        if mode:
            full["ANTHROPIC_BASE_URL"] = self.start(mode)
        proc = subprocess.run([sys.executable, "-B", str(HERE / "diagnose.py"), "--evidence", str(self.evidence),
                               "--output", str(self.out), *extra], env=full, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(self.out.read_text())
        if VALIDATOR:
            self.assertEqual([f"{list(e.path)}: {e.message}" for e in VALIDATOR.iter_errors(result)], [])
        self.stdout = proc.stdout
        return result

    def request(self):
        return json.loads(self.capture.read_text())

    def assert_fallback(self, result, error_part):
        self.assertEqual((result["source"], result["model"], result["category"], result["confidence"]),
                         ("fallback", None, "unknown", "low"))
        self.assertIn(error_part, result["error"])
        self.assertIn("::warning::AI 원인 요약을 쓰지 못했다", self.stdout)

    def test_ai_summary(self):
        result = self.diagnose("ok")
        self.assertEqual((result["source"], result["model"], result["category"], result["confidence"], result["error"]),
                         ("ai", "claude-sonnet-5-5", "migration", "high", None))
        req = self.request()
        self.assertEqual((req["path"], req["api_key"], req["version"]), ("/v1/messages", "test-key", "2023-06-01"))
        body = req["body"]
        self.assertEqual(body["model"], "claude-sonnet-5-5")
        self.assertEqual(body["output_config"]["format"]["schema"]["properties"]["category"]["enum"][0], "migration")
        # 증거 묶음을 그대로 보낸다
        self.assertEqual(json.loads(body["messages"][0]["content"])["run"]["run_id"], "38070479286")
        self.assertIn("증거에 있는 내용만 근거로", body["system"])
        self.assertIn("source=ai", self.github_output.read_text())
        self.assertIn("category=migration", self.github_output.read_text())

    def test_model_can_be_changed(self):
        result = self.diagnose("ok", MODEL="claude-opus-5-5")
        self.assertEqual(result["model"], "claude-opus-5-5")
        self.assertEqual(self.request()["body"]["model"], "claude-opus-5-5")

    def test_long_answer_is_trimmed(self):
        """구조화 출력은 길이를 강제하지 않는다. 요약 600자 · 근거 8개 400자 · 조치 6개 300자로 자른다."""
        result = self.diagnose("long")
        self.assertEqual(result["source"], "ai")
        self.assertEqual(len(result["summary"]), 600)
        self.assertEqual(len(result["evidence"]), 8)
        self.assertTrue(all(len(x) <= 400 for x in result["evidence"]))
        self.assertEqual(len(result["actions"]), 6)
        self.assertTrue(all(len(x) <= 300 for x in result["actions"]))

    def test_secret_in_answer_is_redacted(self):
        result = self.diagnose("secret")
        self.assertNotIn("Leaked1Pass", self.out.read_text())
        self.assertIn("postgresql://***@db", result["summary"])

    def test_no_key(self):
        result = self.diagnose(key=None)
        self.assert_fallback(result, "API 키 없음")
        # 오류 줄을 그대로 보여 주고, 모든 실패에 붙는 줄은 뺀다
        self.assertTrue(any(e.startswith("Error: UPGRADE FAILED: pre-upgrade hooks failed") for e in result["evidence"]))
        self.assertEqual(len(result["evidence"]), 2)
        self.assertFalse(any("Process completed with exit code" in e for e in result["evidence"]))
        self.assertIn("실패한 단계: test / deploy", result["summary"])

    def test_http_error(self):
        self.assert_fallback(self.diagnose("err500"), "HTTP 500: boom")

    def test_timeout(self):
        self.assert_fallback(self.diagnose("slow"), "시간 초과 (2초)")

    def test_refusal(self):
        self.assert_fallback(self.diagnose("refusal"), "거절")

    def test_max_tokens(self):
        self.assert_fallback(self.diagnose("max_tokens"), "stop_reason: max_tokens")

    def test_bad_answer(self):
        self.assert_fallback(self.diagnose("badjson"), "응답 형식 오류")
        self.assert_fallback(self.diagnose("notjson"), "응답 형식 오류")

    def test_unreachable(self):
        self.assert_fallback(self.diagnose(ANTHROPIC_BASE_URL="http://127.0.0.1:9"), "호출 실패")

    def test_prod_is_not_sent_by_default(self):
        evidence = json.loads(self.evidence.read_text())
        evidence["deploy"]["environment"] = "prod"
        self.evidence.write_text(json.dumps(evidence))
        result = self.diagnose("ok")
        self.assert_fallback(result, "prod 실패는 외부 LLM으로 보내지 않는다")
        self.assertTrue(result["summary"].startswith("prod 실패는 AI 요약을 하지 않는다"))
        self.assertFalse(self.capture.exists())
        self.assertEqual(self.diagnose(None, "--allow-prod", ANTHROPIC_BASE_URL=self.start("ok"))["source"], "ai")

    def test_missing_evidence(self):
        self.evidence.unlink()
        result = self.diagnose("ok")
        self.assert_fallback(result, "증거 묶음(evidence.json)이 없거나")
        self.assertEqual(result["evidence"], [])
        self.assertFalse(self.capture.exists())

    def test_fallback_mentions_missing_collection(self):
        """수집하지 못한 항목이 있으면 사람이 직접 볼 곳을 조치에 넣는다."""
        evidence = json.loads(self.evidence.read_text())
        evidence["collection"]["cluster"] = {"status": "failed", "detail": "Unable to connect to the server"}
        self.evidence.write_text(json.dumps(evidence))
        result = self.diagnose(key=None)
        self.assertTrue(any("클러스터 상태를 모으지 못했다" in a for a in result["actions"]))

    def test_publish_example_fallback(self):
        self.evidence.write_text((EXAMPLES / "evidence-image-publish.json").read_text())
        result = self.diagnose(key=None)
        self.assertTrue(any("existing tag has different digest" in e for e in result["evidence"]))
        self.assertIn("test / publish", result["summary"])


if __name__ == "__main__":
    unittest.main()
