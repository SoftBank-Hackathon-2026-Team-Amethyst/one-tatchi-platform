import datetime as dt
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("reap", HERE / "reap.py")
reap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reap)

NOW = dt.datetime(2026, 10, 11, 1, 0, tzinfo=dt.timezone.utc)


def ts(minutes_ago):
    return (NOW - dt.timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class ReapTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.runs = []
        self.jobs = {}

    def gh(self, *args):
        self.calls.append(args)
        if args[0] == "api":
            if "/jobs" in args[1]:
                run_id = int(args[1].split("/runs/")[1].split("/")[0])
                return json.dumps({"jobs": self.jobs.get(run_id, [])})
            return json.dumps({"workflow_runs": self.runs})
        return ""

    def run_main(self, env):
        with patch.object(reap, "gh", self.gh), patch.object(reap.dt, "datetime", FakeDatetime), \
                tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            with patch.dict(os.environ, {"GITHUB_REPOSITORY": "org/app", "GITHUB_OUTPUT": str(out), **env}, clear=False):
                reap.main()
            return out.read_text()

    def run_obj(self, id_, path=".github/workflows/deploy.yml", started=120):
        return {"id": id_, "path": path, "html_url": f"https://x/{id_}", "display_title": f"run {id_}",
                "head_sha": "a" * 40, "head_branch": "main", "run_started_at": ts(started), "created_at": ts(started)}

    def cancelled(self):
        return [c[2] for c in self.calls if c[:2] == ("run", "cancel")]

    def test_cancels_only_expired_waiting_jobs(self):
        self.runs = [self.run_obj(1), self.run_obj(2)]
        self.jobs = {1: [{"status": "completed", "created_at": ts(119)}, {"status": "waiting", "created_at": ts(90)}],
                     2: [{"status": "waiting", "created_at": ts(10)}]}
        out = self.run_main({"MAX_WAIT_MINUTES": "60"})
        self.assertEqual(self.cancelled(), ["1"])
        self.assertIn("count=1", out)
        self.assertIn("90분 대기", out)
        self.assertIn("cancelled=[1]", out)

    def test_ignores_other_workflows_and_uses_run_start_without_waiting_job(self):
        self.runs = [self.run_obj(3, path=".github/workflows/infra.yml"), self.run_obj(4, started=61)]
        self.jobs = {4: [{"status": "completed", "created_at": ts(61)}]}
        out = self.run_main({"MAX_WAIT_MINUTES": "60"})
        self.assertEqual(self.cancelled(), ["4"])
        self.assertIn("count=1", out)

    def test_dry_run_cancels_nothing(self):
        self.runs = [self.run_obj(5)]
        self.jobs = {5: [{"status": "waiting", "created_at": ts(200)}]}
        out = self.run_main({"MAX_WAIT_MINUTES": "60", "DRY_RUN": "true"})
        self.assertEqual(self.cancelled(), [])
        self.assertIn("count=1", out)
        self.assertIn("dry-run", out)

    def test_nothing_waiting(self):
        out = self.run_main({"MAX_WAIT_MINUTES": "60"})
        self.assertIn("count=0", out)
        self.assertIn("details<<__END__\n\n__END__", out)


class FakeDatetime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


if __name__ == "__main__":
    unittest.main()
