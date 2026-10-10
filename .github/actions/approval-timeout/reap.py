#!/usr/bin/env python3
"""Cancel workflow runs whose environment approval has been pending longer than MAX_WAIT_MINUTES."""
import datetime as dt
import json
import os
import subprocess


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()


def api(path):
    return json.loads(gh("api", path))


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def waiting_since(repo, run):
    """When the run started waiting for approval: the earliest waiting job, else the run start."""
    jobs = api(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
    stamps = [parse(j["created_at"]) for j in jobs if j.get("status") == "waiting" and j.get("created_at")]
    if stamps:
        return min(stamps)
    return parse(run.get("run_started_at") or run["created_at"])


def expired(repo, workflow, max_wait_minutes, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    runs = api(f"repos/{repo}/actions/runs?status=waiting&per_page=100")["workflow_runs"]
    found = []
    for run in runs:
        if not run.get("path", "").endswith("/" + workflow):
            continue
        since = waiting_since(repo, run)
        minutes = int((now - since).total_seconds() // 60)
        if minutes >= max_wait_minutes:
            found.append({"id": run["id"], "url": run["html_url"], "title": run.get("display_title", ""),
                          "sha": run["head_sha"][:7], "branch": run.get("head_branch", ""), "minutes": minutes})
    return found


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    workflow = os.environ.get("WORKFLOW", "deploy.yml")
    max_wait = int(float(os.environ.get("MAX_WAIT_MINUTES", "60")))
    dry_run = os.environ.get("DRY_RUN", "false").lower() == "true"
    targets = expired(repo, workflow, max_wait)
    lines = []
    for t in targets:
        if not dry_run:
            gh("run", "cancel", str(t["id"]), "--repo", repo)
        lines.append(f"- <{t['url']}|run {t['id']}> `{t['sha']}` ({t['branch']}) {t['title'][:60]} — {t['minutes']}분 대기"
                     + (" (dry-run)" if dry_run else ""))
        print(("대상(dry-run): " if dry_run else "취소: ") + t["url"])
    if not targets:
        print(f"{max_wait}분 넘게 승인 대기 중인 {workflow} 실행 없음")
    details = (f"{max_wait}분 안에 운영 승인이 처리되지 않아 취소했어요.\n" + "\n".join(lines)) if lines else ""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"count={len(targets)}\n")
            f.write("details<<__END__\n" + details + "\n__END__\n")
            f.write("cancelled=" + json.dumps([t["id"] for t in targets]) + "\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and targets:
        with open(summary, "a") as f:
            f.write("### 운영 승인 시간 초과로 취소\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
