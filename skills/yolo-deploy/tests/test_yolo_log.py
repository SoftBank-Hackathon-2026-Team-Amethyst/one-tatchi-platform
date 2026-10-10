import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "yolo_log.py"
spec = importlib.util.spec_from_file_location("yolo_log", SCRIPT)
yolo_log = importlib.util.module_from_spec(spec)
spec.loader.exec_module(yolo_log)


class YoloLogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / ".deploy").mkdir()
        (self.repo / ".deploy" / "config.yaml").write_text("template_version: v2.5.0\ncompliance: regulated\n")
        self.base = ["--repo", str(self.repo), "--actor", "someone", "--branch", "yolo/x",
                     "--base", "abc1234", "--target", "aws", "--started", "2026-10-10 17:20"]

    def tearDown(self):
        self.tmp.cleanup()

    def test_reuse_mode_writes_three_short_logs(self):
        rc = yolo_log.main(self.base + ["--reuse", "기준 커밋 abc1234: be/fe/db/deploy 변경 없음",
                                        "--change", "deploy/values-be.yaml APP_VERSION v2.0.1",
                                        "--warning", "config.yaml 버전 정합은 사람 몫"])
        self.assertEqual(rc, 0)
        logs = sorted((self.repo / ".deploy" / "log").iterdir())
        self.assertEqual([p.name.split("-", 2)[2] for p in logs], ["analyze.md", "provision.md", "yolo.md"])
        analyze, provision, yolo = [p.read_text() for p in logs]
        self.assertIn("**재사용**", analyze)
        self.assertIn("compliance: `regulated`", analyze)
        self.assertIn("v2.5.0", provision)
        self.assertIn("APP_VERSION v2.0.1", provision)
        self.assertIn("아직 없음", provision)
        self.assertIn("config.yaml 버전 정합", yolo)
        self.assertIn("재사용 — 기준 커밋 abc1234", yolo)
        self.assertNotIn("@@", yolo)

    def test_full_mode_and_no_overwrite(self):
        self.assertEqual(yolo_log.main(self.base + ["--analysis", "4개 병렬 + 예산"]), 0)
        yolo = next((self.repo / ".deploy" / "log").glob("*-yolo.md")).read_text()
        self.assertIn("분석기 5개 실행", yolo)
        self.assertIn("- 경고(사람 몫):\n  - 없음", yolo)
        self.assertEqual(yolo_log.main(self.base + ["--analysis", "다시"]), 1)

    def test_dry_run_writes_nothing(self):
        self.assertEqual(yolo_log.main(self.base + ["--dry-run"]), 0)
        self.assertFalse((self.repo / ".deploy" / "log").exists())


if __name__ == "__main__":
    unittest.main()
