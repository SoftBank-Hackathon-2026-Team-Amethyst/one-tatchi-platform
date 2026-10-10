"""cluster.sh 테스트: 가짜 kubectl(fake-kubectl)로 실패 시점의 클러스터 상태를 꾸며 수집 결과를 본다."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / "cluster.sh"
FAKE = HERE / "tests" / "fake-kubectl"
SCHEMA = json.loads((HERE / "evidence.schema.json").read_text())

try:
    from jsonschema import Draft202012Validator
    # cluster.sh 결과는 증거 묶음의 cluster · collection.cluster 부분이다.
    defs = {"$defs": SCHEMA.get("$defs", {})}
    CLUSTER = Draft202012Validator({**defs, **SCHEMA["properties"]["cluster"]})
    STATE = Draft202012Validator({**defs, **SCHEMA["properties"]["collection"]["properties"]["cluster"]})
except ImportError:  # CI는 uv로 jsonschema를 넣고 돌린다 (ci.yml scripts)
    CLUSTER = STATE = None

MIGRATION_LOG = """\
psql:/migration/init.sql:12: ERROR:  relation "orders" already exists
DATABASE_URL=postgresql://app:S3cretPass@db.internal:5432/app
"""


def pod(name, ready, restarts=0, reason=None, release="demo-app-be"):
    state = {"waiting": {"reason": reason}} if reason else {"running": {}}
    return {
        "metadata": {"name": name, "labels": {"app.kubernetes.io/name": release}},
        "status": {
            "phase": "Running",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
            "containerStatuses": [{"name": "app", "restartCount": restarts, "state": state}],
        },
    }


class ClusterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fake = Path(self.tmp.name) / "fake"
        self.fake.mkdir()
        self.out = Path(self.tmp.name) / "out" / "cluster.json"
        self.calls = Path(self.tmp.name) / "calls.txt"

    def put(self, name, value):
        path = self.fake / name
        path.write_text(value if isinstance(value, str) else json.dumps(value))

    def run_script(self, releases="demo-app-be demo-app-fe", **env):
        full = {**os.environ, "NAMESPACE": "test", "RELEASES": releases, "OUT": str(self.out),
                "KUBECTL": str(FAKE), "FAKE_DIR": str(self.fake), "FAKE_CALLS": str(self.calls), **env}
        proc = subprocess.run(["bash", str(SCRIPT)], env=full, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(self.out.read_text())
        if CLUSTER:
            CLUSTER.validate(result["cluster"])
            STATE.validate(result["collection"])
        return result

    def calls_made(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_migration_failure(self):
        """helm pre-upgrade 마이그레이션 Job이 실패하면 Job 상태와 Job 로그(원인)가 남는다."""
        self.put("rollout-demo-app-be.json", {"status": {"phase": "Healthy"}})
        self.put("rollout-demo-app-fe.json", {"status": {"phase": "Healthy"}})
        self.put("job-demo-app-be-migration.json", {"status": {"failed": 3}})
        self.put("logs-job-demo-app-be-migration.txt", MIGRATION_LOG)
        self.put("events.json", {"items": [{
            "reason": "BackoffLimitExceeded", "message": "Job has reached the specified backoff limit",
            "involvedObject": {"kind": "Job", "name": "demo-app-be-migration"},
            "count": 1, "lastTimestamp": "2026-10-10T17:18:02Z"}]})
        result = self.run_script()
        self.assertEqual(result["collection"], {"status": "ok", "detail": None})
        [job] = result["cluster"]["migration_jobs"]
        self.assertEqual((job["name"], job["status"]), ("demo-app-be-migration", "Failed"))
        self.assertIn('relation "orders" already exists', job["log_tail"])
        # 앱 로그의 접속 문자열 비밀번호는 가린다.
        self.assertNotIn("S3cretPass", self.out.read_text())
        self.assertIn("postgresql://***@db.internal", job["log_tail"])
        self.assertEqual(result["cluster"]["events"][0]["object"], "Job/demo-app-be-migration")
        # fe는 마이그레이션 Job이 없다(NotFound는 실패가 아니다).
        self.assertIn("get job demo-app-fe-migration -n test -o json --request-timeout=20s", self.calls_made())

    def test_degraded_rollout_reads_previous_logs(self):
        """재시작한 파드는 직전 컨테이너 로그(--previous)를, Ready만 아닌 파드는 현재 로그를 읽는다."""
        self.put("rollout-demo-app-be.json", {"status": {"phase": "Degraded", "message": "RolloutAborted: Rollout aborted update to revision 3"}})
        self.put("rollout-demo-app-fe.json", {"status": {"phase": "Healthy"}})
        self.put("pods.json", {"items": [
            pod("be-crash", ready=False, restarts=4, reason="CrashLoopBackOff"),
            pod("be-slow", ready=False),
            pod("fe-ok", ready=True, release="demo-app-fe"),
        ]})
        self.put("logs-be-crash.previous.txt", "panic: missing env DB_HOST\n")
        self.put("logs-be-slow.txt", "listening on :8080\n")
        result = self.run_script()
        pods = {p["name"]: p for p in result["cluster"]["pods"]}
        self.assertEqual(set(pods), {"be-crash", "be-slow"})
        self.assertEqual((pods["be-crash"]["reason"], pods["be-crash"]["restarts"]), ("CrashLoopBackOff", 4))
        self.assertIn("missing env DB_HOST", pods["be-crash"]["log_tail"])
        self.assertIn("listening on :8080", pods["be-slow"]["log_tail"])
        self.assertEqual(result["cluster"]["rollouts"][0]["phase"], "Degraded")
        self.assertIn("get pods -n test -l app.kubernetes.io/name in (demo-app-be,demo-app-fe) -o json --request-timeout=20s",
                      self.calls_made())
        self.assertEqual(result["collection"]["status"], "ok")

    def test_unreadable_pod_log_is_noted(self):
        self.put("pods.json", {"items": [pod("be-pending", ready=False, reason="ContainerCreating")]})
        result = self.run_script(releases="demo-app-be")
        [p] = result["cluster"]["pods"]
        self.assertIn("로그를 읽지 못했다", p["log_tail"])

    def test_limits(self):
        """이벤트 40개 · 파드 10개 · 로그 4000자 상한을 지킨다. 이벤트는 최근 것부터."""
        self.put("events.json", {"items": [
            {"reason": f"R{i}", "message": "m", "involvedObject": {"kind": "Pod", "name": f"p{i}"},
             "lastTimestamp": f"2026-10-10T17:{i:02d}:00Z"} for i in range(50)]})
        self.put("pods.json", {"items": [pod(f"be-{i}", ready=False) for i in range(12)]})
        for i in range(12):
            self.put(f"logs-be-{i}.txt", "x" * 5000 + "END")
        result = self.run_script(releases="demo-app-be")
        events = result["cluster"]["events"]
        self.assertEqual(len(events), 40)
        self.assertEqual(events[0]["reason"], "R49")
        self.assertEqual(len(result["cluster"]["pods"]), 10)
        self.assertTrue(all(len(p["log_tail"]) == 4000 and p["log_tail"].endswith("END")
                            for p in result["cluster"]["pods"]))

    def test_cluster_unreachable(self):
        """클러스터에 접속하지 못하면 빈 상태와 failed · 이유를 남기고, 종료 코드는 0이다."""
        result = self.run_script(FAKE_DOWN="1")
        self.assertEqual(result["cluster"], {"rollouts": [], "events": [], "pods": [], "migration_jobs": []})
        self.assertEqual(result["collection"]["status"], "failed")
        self.assertIn("Unable to connect to the server", result["collection"]["detail"])
        self.assertLessEqual(len(result["collection"]["detail"]), 300)

    def test_missing_rollout_is_reported(self):
        self.put("rollout-demo-app-fe.json", {"status": {"phase": "Healthy"}})
        result = self.run_script()
        self.assertEqual(result["collection"]["status"], "failed")
        self.assertIn("rollout demo-app-be", result["collection"]["detail"])
        self.assertEqual([r["name"] for r in result["cluster"]["rollouts"]], ["demo-app-fe"])

    def test_no_releases(self):
        """서비스 목록이 비어도(bash 3.2의 빈 배열 포함) 이벤트만 모으고 끝난다."""
        result = self.run_script(releases="")
        self.assertEqual(result["collection"]["status"], "ok")
        self.assertEqual(self.calls_made(), ["get events -n test --field-selector type=Warning -o json --request-timeout=20s"])

    def test_secrets_in_events_and_messages(self):
        self.put("rollout-demo-app-be.json", {"status": {"phase": "Degraded",
                                                         "message": "token: ghp_abcdefghijklmnopqrstuvwxyz0123456789"}})
        self.put("events.json", {"items": [{
            "reason": "Failed", "involvedObject": {"kind": "Pod", "name": "be"},
            "message": 'Error: secret "db" has password="hunter2-very-secret"'}]})
        result = self.run_script(releases="demo-app-be")
        text = self.out.read_text()
        for secret in ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", "hunter2-very-secret"):
            self.assertNotIn(secret, text)
        self.assertEqual(result["cluster"]["rollouts"][0]["phase"], "Degraded")


if __name__ == "__main__":
    unittest.main()
