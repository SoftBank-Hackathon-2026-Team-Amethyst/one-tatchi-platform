#!/usr/bin/env python3
"""배포 실패 증거 묶음을 만든다 (T12). 형식은 evidence.schema.json.

진단 job(ubuntu)에서 돈다. 실패한 job의 로그를 GitHub API로 받고(job이 끝나야 받을 수 있다),
실패한 deploy job이 올린 클러스터 상태(cluster.sh 결과)와 합친다. 마지막에 redact.sed로 비밀값을 가린다.
로그를 읽으려면 actions: read 권한이 있는 토큰이 필요하다(GH_TOKEN, 봇 App 토큰).
입력이 없거나 실패해도 멈추지 않고 collection을 failed로 남긴다. 표준 라이브러리만 쓴다.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
JOB_SUFFIXES = ("deploy", "publish")       # 진단하는 배포 단계 (재사용 워크플로의 job id)
MAX_JOBS = 3
MAX_ERRORS = 30
ERROR_LEN = 500
TAIL_LINES_BEFORE = 80
TAIL_CHARS = 12000
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z ?")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
ERROR_LINE = re.compile(r"##\[error\]|^Error[: ]|\blevel=(error|ERROR|fatal)\b|\bFATAL\b|\berror:|\bfailed\b.*\berror=")


class Missing(Exception):
    pass


def gh(*args):
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise Missing("gh 실행 파일이 없다") from None
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or "").strip().splitlines()
        raise Missing(f"gh {args[0]} 실패: {lines[-1] if lines else exc.returncode}") from None


def job_log(repo, job_id):
    """job 로그는 ANSI 색 코드를 담고 있다. 최신 gh는 그런 응답을 --allow-escape-sequences 없이 출력하지 않고,
    옛 gh에는 그 옵션이 없다. 거절당했을 때만 옵션을 붙여 다시 받는다 (색 코드는 clean()이 지운다)."""
    path = f"repos/{repo}/actions/jobs/{job_id}/logs"
    try:
        return gh("api", path)
    except Missing as exc:
        if "allow-escape-sequences" not in str(exc):
            raise
        return gh("api", "--allow-escape-sequences", path)


def clean(log):
    return [ANSI.sub("", TIMESTAMP.sub("", line)) for line in log.splitlines()]


def errors_of(lines):
    found = []
    for line in lines:
        # '::error::'가 그대로 남은 줄은 실행 전 출력된 스크립트 본문이다(실제 오류는 ##[error]로 바뀐다).
        if ERROR_LINE.search(line) and "::error::" not in line:
            text = line.strip()[:ERROR_LEN]
            if text and text not in found:
                found.append(text)
    return found[:MAX_ERRORS]


def tail_of(lines):
    """첫 ##[error] 앞 80줄부터 그 뒤 몇 줄까지. 오류 줄이 없으면 마지막 80줄."""
    first = next((i for i, line in enumerate(lines) if "##[error]" in line), None)
    window = lines[-TAIL_LINES_BEFORE:] if first is None else lines[max(0, first - TAIL_LINES_BEFORE):first + 5]
    text = "\n".join(window)
    return text[-TAIL_CHARS:]


def is_deploy_step(name):
    """재사용 워크플로 안 job 이름은 '<호출 job> / <job>' 또는 '<job>'이다."""
    return name.rsplit(" / ", 1)[-1] in JOB_SUFFIXES


def failed_jobs(repo, run_id, attempt):
    jobs = json.loads(gh("api", "--paginate", f"repos/{repo}/actions/runs/{run_id}/attempts/{attempt}/jobs",
                         "--jq", ".jobs"))
    chosen = [j for j in jobs if j.get("conclusion") == "failure" and is_deploy_step(j.get("name", ""))]
    result = []
    for job in chosen[:MAX_JOBS]:
        lines = clean(job_log(repo, job["id"]))
        result.append({
            "name": job["name"], "job_id": str(job["id"]),
            "failed_steps": [s["name"] for s in job.get("steps") or [] if s.get("conclusion") == "failure"],
            "errors": errors_of(lines), "log_tail": tail_of(lines),
        })
    return result


def cluster_state(path, jobs):
    empty = {"rollouts": [], "events": [], "pods": [], "migration_jobs": []}
    deploy_failed = any(j["name"].rsplit(" / ", 1)[-1] == "deploy" for j in jobs)
    if not path or not Path(path).is_file():
        if deploy_failed:
            return empty, {"status": "failed", "detail": "클러스터 상태(cluster.json)를 받지 못했다"}
        return empty, {"status": "not_collected", "detail": "클러스터에 접속하지 않는 단계(publish)만 실패했다"}
    try:
        data = json.loads(Path(path).read_text())
        cluster = {k: data["cluster"][k] for k in empty}
        collection = data["collection"]
        return cluster, {"status": collection["status"], "detail": collection.get("detail")}
    except (OSError, ValueError, KeyError, TypeError):
        return empty, {"status": "failed", "detail": "클러스터 상태(cluster.json) 형식이 잘못됐다"}


def redact(text):
    return subprocess.run(["sed", "-E", "-f", str(HERE / "redact.sed")], input=text,
                          check=True, capture_output=True, text=True).stdout


def build(args):
    run_url = f"{args.server_url}/{args.repository}/actions/runs/{args.run_id}/attempts/{args.run_attempt}"
    try:
        jobs = failed_jobs(args.repository, args.run_id, args.run_attempt)
        logs_state = {"status": "ok", "detail": None} if jobs else \
            {"status": "failed", "detail": "실패한 deploy · publish job을 찾지 못했다"}
    except (Missing, ValueError, KeyError, TypeError) as exc:
        jobs = []
        logs_state = {"status": "failed", "detail": str(exc)[:300] if isinstance(exc, Missing) else "job 목록 형식 오류"}
    cluster, cluster_state_ = cluster_state(args.cluster, jobs)
    evidence = {
        "schema_version": "1",
        "run": {"repository": args.repository, "run_id": str(args.run_id), "run_attempt": str(args.run_attempt),
                "run_url": run_url, "sha": args.sha, "ref": args.ref, "event": args.event, "actor": args.actor},
        "deploy": {"target": args.target, "target_label": args.target_label or args.target,
                   "environment": args.environment, "namespace": args.namespace, "services": args.services.split()},
        "failed_jobs": jobs,
        "cluster": cluster,
        "collection": {"actions_logs": logs_state, "cluster": cluster_state_},
    }
    # 마지막에 한 번 더 가린다(로그는 GitHub가 등록 시크릿만 가린 상태). 가린 뒤 JSON이 깨지면 로그를 버린다.
    try:
        return json.loads(redact(json.dumps(evidence, ensure_ascii=False)))
    except (ValueError, subprocess.CalledProcessError, OSError):
        evidence["failed_jobs"] = []
        evidence["cluster"] = {"rollouts": [], "events": [], "pods": [], "migration_jobs": []}
        evidence["collection"] = {"actions_logs": {"status": "failed", "detail": "비밀값 가리기에 실패해 로그를 버렸다"},
                                  "cluster": {"status": "failed", "detail": "비밀값 가리기에 실패해 상태를 버렸다"}}
        return evidence


def main(argv=None):
    env = os.environ.get
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--cluster", help="실패한 deploy job이 올린 cluster.json (없으면 수집 실패 또는 해당 없음)")
    p.add_argument("--target", required=True, choices=["aws", "gcp", "onprem"])
    p.add_argument("--target-label", default="")
    p.add_argument("--environment", required=True, choices=["test", "prod"])
    p.add_argument("--namespace", required=True)
    p.add_argument("--services", default="", help="서비스 이름들, 공백 구분")
    p.add_argument("--repository", default=env("GITHUB_REPOSITORY"))
    p.add_argument("--run-id", default=env("GITHUB_RUN_ID"))
    p.add_argument("--run-attempt", default=env("GITHUB_RUN_ATTEMPT", "1"))
    p.add_argument("--sha", default=env("GITHUB_SHA"))
    p.add_argument("--ref", default=env("GITHUB_REF", ""))
    p.add_argument("--event", default=env("GITHUB_EVENT_NAME", ""))
    p.add_argument("--actor", default=env("GITHUB_ACTOR", ""))
    p.add_argument("--server-url", default=env("GITHUB_SERVER_URL", "https://github.com"))
    args = p.parse_args(argv)
    missing = [k for k in ("repository", "run_id", "sha") if not getattr(args, k)]
    if missing:
        p.error("값이 없다: " + ", ".join(missing))
    evidence = build(args)
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    c = evidence["collection"]
    print(f"실패 증거: {args.output} (job {len(evidence['failed_jobs'])}개, 로그 {c['actions_logs']['status']}, 클러스터 {c['cluster']['status']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
