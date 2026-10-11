"""Run the real workflow/composite scripts offline; curl only captures JSON."""

import copy
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[4]
ACTION = ROOT / ".github/actions/slack-notify"


def read_yaml(path):
    return yaml.safe_load(path.read_text())


def outputs(text):
    result = {}
    lines = iter(text.splitlines())
    for line in lines:
        if "<<" in line:
            name, delimiter = line.split("<<", 1)
            value = []
            for part in lines:
                if part == delimiter:
                    break
                value.append(part)
            result[name] = "\n".join(value)
        elif "=" in line:
            name, value = line.split("=", 1)
            result[name] = value
    return result


def resolve(value, context):
    """Resolve only scalar references/defaults used by the composite env."""
    if not isinstance(value, str) or not value.startswith("${{"):
        return str(value)
    expression = value[3:-2].strip()
    for ref in expression.split(" || "):
        if ref.startswith("'"):
            resolved = ref.strip("'")
        else:
            resolved = context[ref]
        if resolved:
            return str(resolved)
    return ""


def contract_errors(workflow):
    errors = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            uses = step.get("uses", "")
            if not uses.startswith("./.platform/.github/actions/"):
                continue
            definition = read_yaml(ROOT / uses.removeprefix("./.platform/") / "action.yml")
            declared = definition.get("inputs", {})
            unknown = set(step.get("with", {})) - set(declared)
            if unknown:
                errors.append((uses, sorted(unknown)))
    return errors


class NotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = read_yaml(ROOT / ".github/workflows/deploy.yml")
        cls.steps = cls.workflow["jobs"]["deploy"]["steps"]
        cls.notify = next(s for s in cls.steps if s.get("id") == "notify")
        cls.send = next(s for s in cls.steps if s.get("uses", "").endswith("/slack-notify"))
        cls.action = read_yaml(ACTION / "action.yml")

    def prepare(self, **changes):
        context = {
            "job.status": "success",
            "needs.gate.outputs.mode": "manual",
            "steps.deploy.outputs.slack": "*app* active: https://example.test/",
            "steps.deploy.outputs.paused": "app",
            "steps.judge.outputs.decision": "promote",
            "steps.judge.outputs.reason": "smoke passed",
            "steps.judge.outputs.executed": "",
            "steps.t17-cleanup.outcome": "",
        }
        context.update(changes)
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            env = {
                **os.environ,
                "VERIFY_OBSERVABILITY": changes.get("verify", "false"),
                "GITHUB_OUTPUT": str(output),
            }
            env.update(
                {name: resolve(value, context) for name, value in self.notify["env"].items()}
            )
            subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", self.notify["run"]],
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )
            return outputs(output.read_text())

    def render(self, prepared=None, **changes):
        values = {name: "" for name in self.action["inputs"]}
        values.update(
            token="test-token",
            channel="test-channel",
            action="deploy",
            target="all@aws.test",
            service="all@aws.test",
            version="a" * 40,
            result="success",
            flow="Janto / 일반 배포",
            environment="test",
            stage="Green 배포·검사 결과",
        )
        if prepared:
            values.update({k: prepared[k] for k in ("buttons", "details", "next-action")})
        values.update(changes)
        context = {"inputs." + k: v for k, v in values.items()}
        context.update({"github.head_ref": "", "github.ref_name": "main"})
        # RUN_URL is an interpolated string; all other env values are simple references.
        step = self.action["runs"]["steps"][0]
        env = {
            name: resolve(value, context)
            for name, value in step["env"].items()
            if name != "RUN_URL"
        }
        with tempfile.TemporaryDirectory() as tmp:
            curl = Path(tmp) / "curl"
            curl.write_text(
                '#!/usr/bin/env bash\nwhile [ "$#" -gt 0 ]; do\n'
                '  if [ "$1" = -d ]; then printf "%s" "$2" > "$CAPTURE"; break; fi\n'
                '  shift\ndone\nprintf "%s" "${FAKE_RESPONSE:-{\\"ok\\":true}}"\n'
            )
            curl.chmod(0o755)
            capture = Path(tmp) / "payload.json"
            env = {
                **os.environ,
                **env,
                "PATH": tmp + os.pathsep + os.environ["PATH"],
                "CAPTURE": str(capture),
                "GITHUB_ACTION_PATH": str(ACTION),
                "GITHUB_ACTOR": "bot",
                "RUN_URL": "https://github.com/org/repo/actions/runs/123/attempts/1",
            }
            result = subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
                env=env,
                capture_output=True,
                text=True,
                check=True,
            )
            return (json.loads(capture.read_text()) if capture.exists() else None), result.stdout

    def test_workflow_action_contracts_and_original_regression(self):
        for name in ("deploy", "pr-ready", "rollout"):
            with self.subTest(name=name):
                self.assertEqual(
                    contract_errors(read_yaml(ROOT / f".github/workflows/{name}.yml")), []
                )
        broken = copy.deepcopy(self.workflow)
        audit = next(
            s for s in broken["jobs"]["deploy"]["steps"] if s.get("uses", "").endswith("/audit-log")
        )
        audit["with"]["next-action"] = "misrouted"
        self.assertTrue(contract_errors(broken))

    def test_result_context_is_wired_to_notification(self):
        expected = {
            "flow": "${{ needs.gate.outputs.flow }}",
            "environment": "${{ inputs.environment }}",
            "stage": "Green 배포·검사 결과",
            "next-action": "${{ steps.notify.outputs.next-action }}",
        }
        for key, value in expected.items():
            self.assertEqual(self.send["with"].get(key), value)

    def test_manual_wait_and_payload_preserve_buttons_and_details(self):
        prepared = self.prepare()
        self.assertIn("승격 또는 Green 취소", prepared["next-action"])
        for environment in ("test", "prod"):
            with self.subTest(environment=environment):
                payload, _ = self.render(
                    prepared, environment=environment, service=f"all@aws.{environment}"
                )
                self.assertIn("*배포 환경:* " + environment, payload["text"])
                self.assertIn(prepared["next-action"], payload["text"])
                self.assertIn("Janto / 일반 배포", payload["text"])
                buttons = payload["blocks"][-1]["elements"]
                self.assertEqual(
                    [(b["action_id"], b["value"]) for b in buttons],
                    [
                        ("rollout_promote", f"all@aws.{environment}"),
                        ("rollout_abort", f"all@aws.{environment}"),
                    ],
                )
                self.assertIn("https://example.test/", json.dumps(payload))
                self.assertIn("/attempts/1", json.dumps(payload))

    def test_auto_promoted(self):
        prepared = self.prepare(
            **{"needs.gate.outputs.mode": "auto", "steps.judge.outputs.executed": "promote"}
        )
        self.assertEqual(prepared["buttons"], "undo")
        self.assertIn("자동 트래픽 승격", prepared["next-action"])
        payload, _ = self.render(prepared, flow="Yolo")
        self.assertEqual(payload["blocks"][-1]["elements"][0]["action_id"], "rollout_undo")

    def test_failed_or_cancelled_partial_actions_never_claim_completion(self):
        for status in ("failure", "cancelled"):
            for executed in ("abort", "promote", ""):
                with self.subTest(status=status, executed=executed):
                    prepared = self.prepare(
                        **{
                            "job.status": status,
                            "needs.gate.outputs.mode": "auto",
                            "steps.judge.outputs.executed": executed,
                        }
                    )
                    self.assertEqual(prepared["buttons"], "")
                    self.assertIn("전체 완료", prepared["next-action"])
                    if executed:
                        self.assertIn(executed, prepared["next-action"])

    def test_already_healthy_is_not_described_as_pending_promotion(self):
        for mode in ("manual", "auto"):
            prepared = self.prepare(
                **{
                    "needs.gate.outputs.mode": mode,
                    "steps.deploy.outputs.paused": "",
                    "steps.judge.outputs.decision": "",
                }
            )
            self.assertIn("승격 대기 서비스가 없어요", prepared["next-action"])
            self.assertNotIn("선택하세요", prepared["next-action"])
            # Existing button selection is intentionally preserved.
            self.assertEqual(prepared["buttons"], "promote abort" if mode == "manual" else "")

    def test_auto_without_execution_does_not_offer_manual_promotion(self):
        prepared = self.prepare(**{"needs.gate.outputs.mode": "auto"})
        self.assertEqual(prepared["buttons"], "")
        self.assertIn("자동 승격 실행 기록이 없어요", prepared["next-action"])

    def test_observability_cleanup_takes_priority(self):
        for status in ("success", "failure"):
            prepared = self.prepare(
                **{"verify": "true", "job.status": status, "steps.t17-cleanup.outcome": status}
            )
            self.assertEqual(prepared["buttons"], "")
            self.assertIn("실측", prepared["next-action"])
            self.assertIn("정리=" + status, prepared["next-action"])
            self.assertNotIn("선택하세요", prepared["next-action"])

    def test_missing_configuration_skips_curl(self):
        for changes in ({"token": ""}, {"channel": ""}):
            payload, output = self.render(**changes)
            self.assertIsNone(payload)
            self.assertIn("건너뜁니다", output)

    def test_review_approval_and_rollout_payload_contracts(self):
        for buttons, extra, expected in [
            ("review merge", {"pr": "83"}, [("pr_approve", "83"), ("pr_merge", "83")]),
            (
                "approve reject",
                {"approval": "123@prod"},
                [("deploy_approve", "123@prod"), ("deploy_reject", "123@prod")],
            ),
        ]:
            payload, _ = self.render(buttons=buttons, **extra)
            self.assertEqual(
                [(b["action_id"], b["value"]) for b in payload["blocks"][-1]["elements"]], expected
            )


if __name__ == "__main__":
    unittest.main()
