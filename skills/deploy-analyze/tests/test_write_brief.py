"""Observable persistence and policy guarantees for T15; no cloud access."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ruamel.yaml import YAML

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_brief.py"
SPEC = importlib.util.spec_from_file_location("write_brief", SCRIPT)
brief = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(brief)

ANSWERS = {
    "expected_daily_users": 100,
    "monthly_budget": {"amount": 100000, "currency": "KRW"},
    "data_categories": ["personal"],
    "preferred_target": "aws",
    "availability": "demo",
}


class BriefTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.deploy = self.root / ".deploy"
        self.config = self.deploy / "config.yaml"
        self.brief_path = self.deploy / "brief.md"
        self.answers = copy.deepcopy(ANSWERS)

    def save(self, **kwargs):
        return brief.save_brief(self.root, self.answers, **kwargs)

    def existing(self, config):
        self.deploy.mkdir(exist_ok=True)
        self.config.write_text(config, encoding="utf-8")
        self.brief_path.write_text("기존 브리프\n", encoding="utf-8")

    def snapshot(self):
        return {path.name: path.read_bytes() for path in self.deploy.iterdir()}

    def cli(self, payload, *arguments):
        return subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--project-root",
                str(self.root),
                *arguments,
            ],
            input=payload,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_each_data_category_requires_regulated(self):
        for category in ("personal", "payment", "financial"):
            with self.subTest(category=category):
                self.answers["data_categories"] = [category]
                result = self.save()
                self.assertEqual(result["compliance"], "regulated")
                self.assertFalse(result["needs_review"])
                self.assertEqual(
                    YAML(typ="safe").load(self.config), {"compliance": "regulated"}
                )
                self.assertIn(brief.DATA_LABELS[category], self.brief_path.read_text())

    def test_only_explicit_no_data_allows_none(self):
        self.answers["data_categories"] = []
        self.save()
        self.assertEqual(YAML(typ="safe").load(self.config)["compliance"], "none")
        self.assertIn(
            "사용자가 개인정보·결제·금융 데이터를 모두 취급하지",
            self.brief_path.read_text(),
        )

    def test_explicit_skips_are_recorded_without_inventing_capacity_or_budget(self):
        self.answers = {
            "expected_daily_users": None,
            "monthly_budget": None,
            "data_categories": None,
            "preferred_target": "auto",
            "availability": "unknown",
        }
        result = self.save()
        self.assertEqual(result["compliance"], "regulated")
        self.assertTrue(result["needs_review"])
        self.assertEqual(set(result["defaults_applied"]), brief.FIELDS)
        rendered = self.brief_path.read_text()
        self.assertIn("하루 예상 이용자: 미정", rendered)
        self.assertIn("월 인프라 예산: 미정", rendered)
        self.assertIn("데이터 취급 여부가 미정", rendered)

    def test_zero_values_and_decimal_budget_are_supported(self):
        self.answers["expected_daily_users"] = 0
        for amount in (0, 12.5):
            with self.subTest(amount=amount):
                self.answers["monthly_budget"] = {"amount": amount, "currency": "USD"}
                self.save()
                self.assertIn(f"{amount} USD / 월", self.brief_path.read_text())

    def test_same_policy_preserves_config_bytes_and_refreshes_brief(self):
        original = '# 기존 설정\r\ntemplate_version: "1.0.0"\r\ncompliance: regulated # 보호\r\nservices: [be, fe]\r\n'
        self.deploy.mkdir()
        self.config.write_bytes(original.encode())
        self.save()
        first_brief = self.brief_path.read_bytes()
        self.answers["expected_daily_users"] = 200
        self.save()
        self.assertEqual(self.config.read_bytes(), original.encode())
        self.assertNotEqual(first_brief, self.brief_path.read_bytes())
        self.assertIn("200명 / 일", self.brief_path.read_text())

    def test_initial_policy_keeps_unrelated_values_quotes_and_comments(self):
        self.existing(
            '# 팀 설정\ntemplate_version: "1.0.0"\nservices:\n  be:\n    replicas: 2 # 유지\n'
        )
        before = YAML(typ="safe").load(self.config)
        self.save()
        after = YAML(typ="safe").load(self.config)
        self.assertEqual(after.pop("compliance"), "regulated")
        self.assertEqual(after, before)
        self.assertIn("# 팀 설정", self.config.read_text())
        self.assertIn("# 유지", self.config.read_text())
        self.assertIn('"1.0.0"', self.config.read_text())

    def test_comment_only_config_keeps_comments(self):
        self.existing("# 다음 단계에서 서비스 추가")
        self.save()
        self.assertEqual(
            self.config.read_text(),
            "# 다음 단계에서 서비스 추가\ncompliance: regulated\n",
        )

    def test_policy_changes_in_both_directions_leave_both_files_untouched(self):
        for existing, categories in (
            ("regulated", []),
            ("none", ["personal"]),
            ("none", None),
        ):
            with self.subTest(existing=existing, categories=categories):
                self.existing(f"compliance: {existing}\n")
                self.answers["data_categories"] = categories
                before = self.snapshot()
                with self.assertRaisesRegex(brief.BriefError, "사람이 검토"):
                    self.save()
                self.assertEqual(self.snapshot(), before)

    def test_invalid_answers_never_write_files(self):
        invalid = [
            ("expected_daily_users", -1),
            ("expected_daily_users", True),
            ("expected_daily_users", 1.5),
            ("expected_daily_users", "100"),
            ("monthly_budget", {"amount": -1, "currency": "KRW"}),
            ("monthly_budget", {"amount": True, "currency": "KRW"}),
            ("monthly_budget", {"amount": float("inf"), "currency": "KRW"}),
            ("monthly_budget", {"amount": float("nan"), "currency": "KRW"}),
            ("monthly_budget", {"amount": 1, "currency": "krw"}),
            ("monthly_budget", {"amount": 1}),
            ("data_categories", "none"),
            ("data_categories", False),
            ("data_categories", ["none", "personal"]),
            ("data_categories", ["personal", "personal"]),
            ("data_categories", [{}]),
            ("preferred_target", "azure"),
            ("preferred_target", []),
            ("availability", "99.99%"),
            ("availability", {}),
        ]
        for field, value in invalid:
            with self.subTest(field=field, value=value):
                self.answers = copy.deepcopy(ANSWERS)
                self.answers[field] = value
                with self.assertRaises(brief.BriefError):
                    self.save()
                self.assertFalse(self.deploy.exists())

    def test_missing_answers_are_not_silently_skipped(self):
        for field in brief.FIELDS:
            with self.subTest(field=field):
                self.answers = {
                    key: value for key, value in ANSWERS.items() if key != field
                }
                with self.assertRaises(brief.BriefError):
                    self.save()
                self.assertFalse(self.deploy.exists())

    def test_caller_cannot_override_compliance(self):
        self.answers["compliance"] = "none"
        with self.assertRaises(brief.BriefError):
            self.save()
        self.assertFalse(self.deploy.exists())

    def test_invalid_existing_yaml_and_policy_are_not_repaired_automatically(self):
        invalid = [
            "compliance: regulated\ncompliance: none\n",
            "compliance: invalid\n",
            "compliance: null\n",
            "compliance: []\n",
            "compliance: true\n",
            "services: [\n",
            "- aws\n",
            "null\n",
            "---\ncompliance: regulated\n---\ncompliance: none\n",
        ]
        for contents in invalid:
            with self.subTest(contents=contents):
                self.existing(contents)
                before = self.snapshot()
                with self.assertRaises(brief.BriefError):
                    self.save()
                self.assertEqual(self.snapshot(), before)

    def test_output_symlinks_are_rejected(self):
        self.deploy.mkdir()
        outside = self.root / "untouched.txt"
        outside.write_text("원본")
        self.config.symlink_to(outside)
        with self.assertRaises(brief.BriefError):
            self.save()
        self.assertEqual(outside.read_text(), "원본")
        self.assertFalse(self.brief_path.exists())

    def test_deploy_directory_symlink_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.deploy.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(brief.BriefError):
            self.save()
        self.assertEqual(list(outside.iterdir()), [])

    def test_invalid_brief_output_path_does_not_create_config(self):
        self.brief_path.mkdir(parents=True)
        with self.assertRaises(brief.BriefError):
            self.save()
        self.assertFalse(self.config.exists())

    def test_repeated_input_is_idempotent(self):
        self.save()
        before = self.snapshot()
        self.save()
        self.assertEqual(self.snapshot(), before)

    def test_dry_run_checks_policy_without_writes(self):
        result = self.save(dry_run=True)
        self.assertEqual(result["compliance"], "regulated")
        self.assertFalse(self.deploy.exists())
        self.existing("compliance: none\n")
        before = self.snapshot()
        with self.assertRaises(brief.BriefError):
            self.save(dry_run=True)
        self.assertEqual(self.snapshot(), before)

    def test_cli_stdin_creates_both_outputs(self):
        result = self.cli(json.dumps(self.answers))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["compliance"], "regulated")
        self.assertTrue(self.brief_path.is_file())
        self.assertTrue(self.config.is_file())

    def test_cli_answers_file_supports_paths_with_spaces(self):
        answers_path = self.root / "배포 답변.json"
        answers_path.write_text(json.dumps(self.answers))
        result = self.cli("", "--answers", str(answers_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            json.loads(result.stdout)["brief_path"], str(self.brief_path.resolve())
        )

    def test_cli_bad_json_and_duplicate_keys_fail_without_writes(self):
        for payload in (
            "{broken",
            '{"data_categories": [], "data_categories": null}',
            "[]",
        ):
            with self.subTest(payload=payload):
                result = self.cli(payload)
                self.assertEqual(result.returncode, 2)
                self.assertIn("브리프 저장 실패", result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertFalse(self.deploy.exists())


if __name__ == "__main__":
    unittest.main()
