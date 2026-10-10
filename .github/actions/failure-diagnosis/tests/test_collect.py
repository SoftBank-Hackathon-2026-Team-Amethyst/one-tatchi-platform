"""collect.py 테스트: 가짜 gh로 실행의 job 목록 · 로그를 꾸미고, 실제 demo-app 실패 로그(fixtures)로 증거 묶음을 만든다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
FIXTURES = HERE / "tests" / "fixtures"
SHA = "6ecd9f993b54c8502e2b92d9d084fdde8cb9b968"

try:
    from jsonschema import Draft202012Validator
    VALIDATOR = Draft202012Validator(json.loads((HERE / "evidence.schema.json").read_text()))
except ImportError:  # CI는 uv로 jsonschema를 넣고 돌린다 (ci.yml scripts)
    VALIDATOR = None

# 가짜 gh: FAKE_GH 폴더의 jobs.json(.jobs 배열) · log-<job id>.txt를 돌려준다. FAKE_GH_FAIL이면 API 실패.
FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
d = os.environ["FAKE_GH"]
with open(os.path.join(d, "calls.txt"), "a") as f:
    f.write(" ".join(sys.argv[1:]) + "\\n")
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit(print("HTTP 403: Resource not accessible by integration", file=sys.stderr) or 1)
path = sys.argv[-1] if sys.argv[-2] != "--jq" else sys.argv[-3]
if path.endswith("/jobs"):
    print(json.dumps(json.load(open(os.path.join(d, "jobs.json")))))
elif path.endswith("/logs"):
    # 최신 gh처럼 색 코드가 든 응답은 --allow-escape-sequences 없이 거절한다 (FAKE_GH_STRICT)
    if os.environ.get("FAKE_GH_STRICT") and "--allow-escape-sequences" not in sys.argv:
        sys.exit(print("the response contains terminal escape sequences; pass --allow-escape-sequences to output it anyway", file=sys.stderr) or 1)
    job = path.split("/")[-2]
    f = os.path.join(d, f"log-{job}.txt")
    if not os.path.exists(f):
        sys.exit(print("HTTP 410: Gone", file=sys.stderr) or 1)
    sys.stdout.write(open(f).read())
"""


def job(job_id, name, conclusion="failure", failed_step=None):
    steps = [{"name": "Set up job", "conclusion": "success"}]
    if failed_step:
        steps.append({"name": failed_step, "conclusion": conclusion})
    return {"id": job_id, "name": name, "conclusion": conclusion, "steps": steps}


class CollectTest(unittest.TestCase):
    def setUp(self):
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
        self.out = root / "evidence.json"
        self.cluster = root / "cluster.json"

    def jobs(self, *items):
        (self.fake / "jobs.json").write_text(json.dumps(list(items)))

    def log(self, job_id, text):
        (self.fake / f"log-{job_id}.txt").write_text(text)

    def collect(self, *extra, **env):
        args = [sys.executable, "-B", str(HERE / "collect.py"), "--output", str(self.out),
                "--target", "aws", "--target-label", "AWS (EKS)", "--environment", "test",
                "--namespace", "test", "--services", "demo-app-be demo-app-fe", *extra]
        full = {**os.environ, "PATH": self.path, "FAKE_GH": str(self.fake),
                "GITHUB_REPOSITORY": "SoftBank-Hackathon-2026-Team-Amethyst/demo-app",
                "GITHUB_RUN_ID": "38070479286", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": SHA,
                "GITHUB_REF": "refs/heads/yolo/test", "GITHUB_EVENT_NAME": "push", "GITHUB_ACTOR": "baekyutae", **env}
        proc = subprocess.run(args, env=full, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        evidence = json.loads(self.out.read_text())
        if VALIDATOR:
            errors = [f"{list(e.path)}: {e.message}" for e in VALIDATOR.iter_errors(evidence)]
            self.assertEqual(errors, [])
        return evidence

    def calls(self):
        return (self.fake / "calls.txt").read_text().splitlines()

    def test_migration_failure_with_cluster_state(self):
        """실제 마이그레이션 실패 로그(run 38070479286)와 클러스터 상태를 합친다."""
        self.jobs(job(1, "test / checks", "success"),
                  job(114267116459, "test / deploy", failed_step="Green 배포 (helm upgrade)"),
                  job(3, "test / yolo-report", "skipped"))
        self.log(114267116459, (FIXTURES / "job-deploy-migration.log").read_text())
        self.cluster.write_text(json.dumps({
            "cluster": {"rollouts": [], "events": [], "pods": [], "migration_jobs": [
                {"name": "demo-app-be-migration", "status": "Failed", "log_tail": 'ERROR:  relation "orders" already exists'}]},
            "collection": {"status": "ok", "detail": None}}))
        ev = self.collect("--cluster", str(self.cluster))
        [failed] = ev["failed_jobs"]
        self.assertEqual((failed["name"], failed["job_id"]), ("test / deploy", "114267116459"))
        self.assertEqual(failed["failed_steps"], ["Green 배포 (helm upgrade)"])
        self.assertTrue(any(e.startswith("Error: UPGRADE FAILED: pre-upgrade hooks failed") for e in failed["errors"]))
        self.assertTrue(any('msg="upgrade failed"' in e for e in failed["errors"]))
        # 타임스탬프 · ANSI 색을 지우고, 첫 ##[error] 앞뒤를 남긴다.
        self.assertIn("Job/test/demo-app-be-migration", failed["log_tail"])
        self.assertNotRegex(failed["log_tail"], r"(?m)^2026-10-10T")
        self.assertNotIn("\x1b", failed["log_tail"])
        self.assertNotIn("target: all@aws.test", failed["log_tail"])  # 오류 뒤 다른 step은 몇 줄만
        self.assertEqual(ev["cluster"]["migration_jobs"][0]["status"], "Failed")
        self.assertEqual(ev["collection"], {"actions_logs": {"status": "ok", "detail": None},
                                            "cluster": {"status": "ok", "detail": None}})
        self.assertEqual(ev["run"]["run_url"], "https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/demo-app"
                                               "/actions/runs/38070479286/attempts/1")
        self.assertEqual(ev["deploy"]["services"], ["demo-app-be", "demo-app-fe"])
        self.assertIn("api --paginate repos/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/runs/38070479286"
                      "/attempts/1/jobs --jq .jobs", self.calls())

    def test_escape_sequence_refusal_is_retried(self):
        """실제 러너(2026-10-11 run 38077153897)의 gh는 색 코드가 든 로그를 옵션 없이 출력하지 않았다."""
        self.jobs(job(114254400958, "test / publish", failed_step="Push images"))
        self.log(114254400958, (FIXTURES / "job-publish-digest.log").read_text())
        ev = self.collect(FAKE_GH_STRICT="1")
        self.assertEqual(ev["collection"]["actions_logs"]["status"], "ok")
        self.assertTrue(any("existing tag has different digest" in e for e in ev["failed_jobs"][0]["errors"]))
        calls = self.calls()
        self.assertIn("api repos/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/jobs/114254400958/logs", calls)
        self.assertIn("api --allow-escape-sequences repos/SoftBank-Hackathon-2026-Team-Amethyst/demo-app/actions/jobs/"
                      "114254400958/logs", calls)

    def test_publish_failure_has_no_cluster_state(self):
        """실제 이미지 발행 실패 로그(run 38066156334). publish는 클러스터에 접속하지 않는다."""
        self.jobs(job(114254400958, "test / publish", failed_step="Push images"),
                  job(5, "test / deploy", "skipped"))
        self.log(114254400958, (FIXTURES / "job-publish-digest.log").read_text())
        ev = self.collect()
        [failed] = ev["failed_jobs"]
        self.assertIn("##[error]existing tag has different digest: 993371732872.dkr.ecr.ap-northeast-2.amazonaws.com"
                      f"/demo-app-be:{SHA}", failed["errors"])
        self.assertEqual(ev["collection"]["cluster"]["status"], "not_collected")

    def test_deploy_failure_without_cluster_file(self):
        """deploy가 실패했는데 클러스터 상태 파일이 없으면 수집 실패로 남긴다."""
        self.jobs(job(7, "deploy", failed_step="helm"))
        self.log(7, "##[error]Process completed with exit code 1.\n")
        ev = self.collect("--cluster", str(self.cluster))
        self.assertEqual(ev["collection"]["cluster"]["status"], "failed")
        self.assertEqual(ev["failed_jobs"][0]["name"], "deploy")

    def test_broken_cluster_file(self):
        self.jobs(job(7, "test / deploy"))
        self.log(7, "x\n")
        self.cluster.write_text("{not json")
        ev = self.collect("--cluster", str(self.cluster))
        self.assertEqual(ev["collection"]["cluster"]["status"], "failed")
        self.assertEqual(ev["cluster"]["pods"], [])

    def test_only_deploy_and_publish_jobs(self):
        """검사 · 리포트 job의 실패는 진단 대상이 아니다. 대상 job은 최대 3개."""
        self.jobs(job(1, "test / checks"), job(2, "test / yolo-pr"),
                  *[job(10 + i, f"svc{i} / deploy") for i in range(4)])
        for i in range(4):
            self.log(10 + i, "##[error]boom\n")
        ev = self.collect()
        self.assertEqual([j["name"] for j in ev["failed_jobs"]], ["svc0 / deploy", "svc1 / deploy", "svc2 / deploy"])

    def test_script_source_is_not_an_error(self):
        """Run 그룹에 찍힌 스크립트 본문(echo "::error::…")은 오류 줄이 아니다."""
        self.jobs(job(8, "test / deploy"))
        self.log(8, '2026-10-10T17:10:26.9Z \x1b[36;1m  echo "::error::$1: 10분 안에 Paused · Healthy가 되지 않았다"\x1b[0m\n'
                    "2026-10-10T17:20:26.9Z ##[error]demo-app-be: 10분 안에 Paused · Healthy가 되지 않았다\n")
        ev = self.collect()
        self.assertEqual(ev["failed_jobs"][0]["errors"], ["##[error]demo-app-be: 10분 안에 Paused · Healthy가 되지 않았다"])

    def test_api_failure_is_recorded(self):
        """로그 권한이 없으면(봇 토큰 누락 등) 멈추지 않고 actions_logs를 failed로 남긴다."""
        ev = self.collect(FAKE_GH_FAIL="1")
        self.assertEqual(ev["failed_jobs"], [])
        self.assertEqual(ev["collection"]["actions_logs"]["status"], "failed")
        self.assertIn("Resource not accessible by integration", ev["collection"]["actions_logs"]["detail"])

    def test_no_failed_job_found(self):
        self.jobs(job(1, "test / deploy", "success"))
        ev = self.collect()
        self.assertEqual(ev["collection"]["actions_logs"]["status"], "failed")

    def test_limits_and_redaction(self):
        """오류 줄 30개 · 줄당 500자 · 로그 끝 12000자 상한을 지키고, 로그의 비밀값을 가린다."""
        lines = [f"Error: step {i} failed " + "y" * 600 for i in range(40)]
        lines += ["x" * 200 for _ in range(100)]
        lines += ["DATABASE_URL=postgresql://app:pl41nPass@10.0.0.5:5432/app",
                  "Authorization: Bearer abcdefghijklmnop.qrstuvwx", "##[error]Process completed with exit code 1."]
        self.jobs(job(9, "test / deploy"))
        self.log(9, "\n".join(lines) + "\n")
        ev = self.collect()
        [failed] = ev["failed_jobs"]
        self.assertEqual(len(failed["errors"]), 30)
        self.assertTrue(all(len(e) <= 500 for e in failed["errors"]))
        self.assertLessEqual(len(failed["log_tail"]), 12000)
        text = self.out.read_text()
        self.assertNotIn("pl41nPass", text)
        self.assertNotIn("abcdefghijklmnop.qrstuvwx", text)
        self.assertIn("postgresql://***@10.0.0.5", failed["log_tail"])

    def test_missing_run_info_fails_fast(self):
        env = {**os.environ, "PATH": self.path, "GITHUB_REPOSITORY": "", "GITHUB_RUN_ID": "", "GITHUB_SHA": ""}
        proc = subprocess.run([sys.executable, "-B", str(HERE / "collect.py"), "--output", str(self.out),
                               "--target", "aws", "--environment", "test", "--namespace", "test"],
                              env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("repository", proc.stderr)


if __name__ == "__main__":
    unittest.main()
