import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "verify-t26-evidence.py"
spec = importlib.util.spec_from_file_location("t26_evidence", SCRIPT)
evidence = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evidence)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE / "t26-fixtures/ordinary.json").read_text())

    def report(self):
        return evidence.Review(self.data).run()

    def check(self, name):
        return next(c for c in self.report()["checks"] if c["check"] == name)

    def test_complete_ordinary_pr(self):
        report = self.report()
        self.assertEqual(report["status"], evidence.CONFIRMED)
        self.assertEqual(report["route"], "ordinary-pr")
        self.assertNotIn("janto", report["route"])

    def test_recommendation_or_job_success_without_promotion_is_incomplete(self):
        self.data.pop("test_rollout")
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)
        self.assertEqual(self.check("test Slack 승격 요청")["status"], evidence.UNKNOWN)

    def test_previous_image_is_not_proved_by_matching_run_sha(self):
        job = self.data["prod_rollout"]["jobs"][0]
        job["log"] = job["log"].replace("sha256:" + "1" * 64, "sha256:" + "f" * 64)
        self.assertEqual(self.check("prod be 활성 버전")["status"], evidence.MISMATCH)

    def test_early_promotion_is_rejected(self):
        run = self.data["prod_rollout"]
        run["jobs"][0]["log"] = run["jobs"][0]["log"].replace("01:08:", "01:06:")
        run["jobs"][0]["started_at"] = "2026-10-11T01:06:00Z"
        self.assertEqual(self.check("prod be 활성 버전")["status"], evidence.MISMATCH)

    def test_command_before_ready_is_not_fixed_by_later_healthy_snapshot(self):
        job = self.data["prod_rollout"]["jobs"][0]
        job["started_at"] = "2026-10-11T01:06:00Z"
        job["log"] = job["log"].replace("01:08:00Z rollout", "01:06:00Z rollout")
        self.assertEqual(self.check("prod be 활성 버전")["status"], evidence.MISMATCH)

    def test_test_and_prod_different_artifacts_are_rejected(self):
        job = self.data["deploy"]["jobs"][1]
        job["log"] = job["log"].replace("sha256:" + "2" * 64, "sha256:" + "e" * 64)
        self.assertEqual(self.check("test → prod 이미지")["status"], evidence.MISMATCH)

    def test_wrong_image_source_sha_is_unknown(self):
        job = self.data["deploy"]["jobs"][1]
        job["log"] = job["log"].replace('"source_sha": "' + "a" * 40, '"source_sha": "' + "b" * 40)
        self.assertEqual(self.check("prod 검사 이미지")["status"], evidence.UNKNOWN)

    def test_approval_required_only_when_regulated(self):
        self.data["approval_comments"] = []
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)
        self.data["compliance"] = "none"
        self.assertEqual(self.report()["status"], evidence.CONFIRMED)

    def test_unknown_compliance_cannot_skip_approval(self):
        self.data.pop("compliance")
        self.assertEqual(self.check("운영 승인")["status"], evidence.UNKNOWN)

    def test_approval_actor_must_match_audit(self):
        self.data["approval_comments"][0]["body"] = self.data["approval_comments"][0][
            "body"
        ].replace("U1", "U2")
        self.assertEqual(self.check("운영 승인")["status"], evidence.UNKNOWN)

    def test_earlier_attempt_approval_cannot_be_reused(self):
        self.data["deploy"]["meta"]["run_started_at"] = "2026-10-11T01:05:30Z"
        self.assertEqual(self.check("운영 승인")["status"], evidence.UNKNOWN)

    def test_approval_after_production_started_is_not_proof(self):
        self.data["approval_comments"][0]["created_at"] = "2026-10-11T01:08:00Z"
        self.assertEqual(self.check("운영 승인")["status"], evidence.UNKNOWN)

    def test_wrong_attempt_metadata_is_rejected(self):
        self.data["deploy"]["meta"]["run_attempt"] = 2
        self.assertEqual(self.report()["status"], evidence.MISMATCH)

    def test_wrong_attempt_audit_is_rejected(self):
        job = self.data["deploy"]["jobs"][1]
        job["log"] = job["log"].replace("runs/100/attempts/1", "runs/100/attempts/2")
        self.assertEqual(self.check("prod deploy 감사 기록")["status"], evidence.MISMATCH)

    def test_job_from_other_run_is_not_used(self):
        self.data["deploy"]["jobs"][1]["run_id"] = 999
        self.assertEqual(self.check("prod")["status"], evidence.UNKNOWN)

    def test_wrong_environment_or_target_is_not_mixed(self):
        for old, new in [("prod", "staging"), ("aws", "gcp")]:
            with self.subTest(new=new):
                modified = copy.deepcopy(self.data)
                modified["prod_rollout"]["jobs"][0]["log"] = modified["prod_rollout"]["jobs"][0][
                    "log"
                ].replace(old, new)
                self.assertNotEqual(evidence.Review(modified).run()["status"], evidence.CONFIRMED)

    def test_duplicate_target_jobs_are_ambiguous(self):
        self.data["deploy"]["jobs"].append(copy.deepcopy(self.data["deploy"]["jobs"][1]))
        self.assertEqual(self.check("prod")["status"], evidence.UNKNOWN)

    def test_matrix_job_names_are_supported_by_target_not_position(self):
        self.data["deploy"]["jobs"][0]["name"] = "test (aws) / deploy"
        self.data["deploy"]["jobs"][1]["name"] = "prod (aws) / deploy"
        self.assertEqual(self.report()["status"], evidence.CONFIRMED)

    def test_partial_service_health_is_incomplete(self):
        job = self.data["prod_rollout"]["jobs"][0]
        job["log"] = job["log"].replace("✔ Healthy", "Ⅱ Paused")
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def test_missing_service_cannot_be_silently_ignored(self):
        self.data["services"].append("worker")
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def test_missing_digest_or_log_is_incomplete(self):
        self.data["prod_rollout"]["jobs"][0]["log"] = ""
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def test_failed_rollout_is_not_confirmed_even_with_healthy_output(self):
        self.data["prod_rollout"]["jobs"][0]["conclusion"] = "failure"
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def test_protected_file_requires_slack_review_evidence(self):
        self.data["pr_files"] = [{"filename": ".deploy/config.yaml"}]
        self.assertEqual(self.check("Slack 코드 리뷰")["status"], evidence.UNKNOWN)
        self.data["pr_reviews"] = [
            {
                "state": "APPROVED",
                "submitted_at": "2026-10-11T00:58:00Z",
                "body": "Slack에서 `slack:reviewer(U2)`이 승인했다.",
            }
        ]
        self.assertEqual(self.report()["status"], evidence.CONFIRMED)

    def test_manual_dispatch_is_not_called_janto_or_yolo(self):
        self.data["deploy"]["meta"]["event"] = "workflow_dispatch"
        self.assertEqual(self.report()["route"], "manual")
        self.assertIn("janto 스킬 완료 증거가 아님", self.check("배포 경로")["detail"])

    def test_observability_cleanup_is_not_a_deployment_proof(self):
        self.data["deploy"]["jobs"][0]["log"] = self.data["deploy"]["jobs"][0]["log"].replace(
            "VERIFY_OBSERVABILITY: false", "VERIFY_OBSERVABILITY: true"
        )
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def yolo(self):
        head = "b" * 40
        self.data["pr"]["head"].update(ref="yolo/example", sha=head)
        self.data["pr"]["labels"] = [{"name": "yolo"}]
        run = copy.deepcopy(self.data["deploy"])
        run.update(requested_id=90)
        run["meta"].update(
            id=90,
            head_sha=head,
            head_branch="yolo/example",
            created_at="2026-10-11T00:00:00Z",
            run_started_at="2026-10-11T00:00:00Z",
        )
        job = run["jobs"][0]
        job.update(run_id=90, head_sha=head)
        job["log"] += self.data["test_rollout"]["jobs"][0]["log"].replace("runs/200/", "runs/100/")
        job["log"] = job["log"].replace("a" * 40, head).replace("runs/100/", "runs/90/")
        job["log"] = (
            job["log"]
            .replace("MODE: manual", "MODE: auto")
            .replace('"requested_by": "slack:tester(U1)"', '"requested_by": "ai-judge"')
        )
        job["log"] = job["log"].replace("T01:", "T00:")
        job["started_at"] = job["started_at"].replace("T01:", "T00:")
        job["completed_at"] = job["completed_at"].replace("T01:", "T00:")
        run["jobs"] = [job]
        self.data["yolo"] = run

    def test_yolo_rebase_sha_change_is_valid(self):
        self.yolo()
        self.assertNotEqual(
            self.data["yolo"]["meta"]["head_sha"], self.data["deploy"]["meta"]["head_sha"]
        )
        self.assertEqual(self.report()["route"], "yolo")
        self.assertEqual(self.report()["status"], evidence.CONFIRMED)

    def test_yolo_wrong_pr_head_is_rejected(self):
        self.yolo()
        self.data["pr"]["head"]["sha"] = "c" * 40
        self.assertEqual(self.check("yolo → 병합 PR")["status"], evidence.MISMATCH)

    def test_yolo_missing_run_is_incomplete(self):
        self.yolo()
        self.data.pop("yolo")
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)

    def test_echoed_shell_is_not_observed_evidence(self):
        log = self.data["prod_rollout"]["jobs"][0]["log"]
        framed = (
            "2026-10-11T01:08:00Z ##[group]Run echo fake\n"
            + "\n".join(
                line
                for line in log.splitlines()
                if "##[group]" not in line and "##[endgroup]" not in line
            )
            + "\n2026-10-11T01:09:00Z ##[endgroup]\n"
        )
        parsed = evidence.parse_log(framed)
        self.assertEqual(parsed["snapshots"], [])
        self.assertEqual(parsed["audits"], [])
        self.assertEqual(parsed["promotions"], [])

    def test_colored_command_echo_without_group_is_not_observation(self):
        parsed = evidence.parse_log("2026-10-11T01:08:00Z \x1b[36;1mName: be\x1b[0m\n")
        self.assertEqual(parsed["snapshots"], [])

    def test_audit_json_without_upload_anchor_is_not_accepted(self):
        job = self.data["deploy"]["jobs"][1]
        job["log"] = job["log"].replace("audit log: s3://", "echo audit log: s3://")
        self.assertEqual(self.check("prod deploy 감사 기록")["status"], evidence.UNKNOWN)

    def test_transport_is_get_only_and_does_not_expose_errors(self):
        client = evidence.GitHub("example/app")
        with patch.object(
            evidence.subprocess,
            "run",
            return_value=subprocess.CompletedProcess([], 1, "", "secret-token"),
        ) as call:
            self.assertIsNone(client.get("repos/example/app/actions/runs/100"))
        argv = call.call_args.args[0]
        self.assertEqual(argv[argv.index("--method") + 1], "GET")
        self.assertNotIn("secret-token", json.dumps(client.errors))

    def test_failed_lookup_prevents_full_confirmation(self):
        self.data["errors"] = ["repos/example/app/pulls/9/reviews"]
        self.assertEqual(self.report()["status"], evidence.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
