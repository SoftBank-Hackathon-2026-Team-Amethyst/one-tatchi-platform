#!/usr/bin/env python3
"""Open a yolo PR after promotion and wait for PR CI before requesting merge."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import quote


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True).strip()


def api(path):
    return json.loads(gh("api", path))


def current_head(repo, branch):
    return api(f"repos/{repo}/git/ref/heads/{quote(branch, safe='')}")["object"]["sha"]


def run(report, branch, repo, timeout=600):
    sha = report["sha"]
    if not branch.startswith("yolo/") or report["environment"] != "test" or not report["promoted"]:
        raise RuntimeError("test에서 승격한 yolo 커밋만 PR을 만들 수 있다")

    def assert_head():
        if current_head(repo, branch) != sha:
            raise RuntimeError("브랜치에 새 커밋이 있다. 새 배포 실행에서 PR을 갱신한다")

    assert_head()
    prs = json.loads(gh("pr", "list", "--repo", repo, "--head", branch, "--base", "main",
                        "--state", "open", "--json", "number,body,headRefOid"))
    existing = prs[0] if prs else None
    if existing and existing["headRefOid"] != sha:
        raise RuntimeError("PR head와 승격한 커밋이 다르다")
    summary = (
        "<!-- yolo-deploy:start -->\n"
        "## yolo test 배포 결과\n\n"
        f"- 승격한 커밋: `{sha}`\n"
        f"- 대상: `{report['target']}` / test\n"
        f"- 실행자: `{report['actor']}`\n"
        f"- 템플릿: `{report['template_version']}`\n"
        f"- compliance: `{report['compliance']}` (운영 승인 규칙 유지)\n"
        f"- [배포 실행 · AI 판단 artifact]({report['run_url']})\n"
        f"- [분석 보고서](https://github.com/{repo}/blob/{sha}/.deploy/report.md) · "
        f"[스킬 실행 기록](https://github.com/{repo}/tree/{sha}/.deploy/log)\n\n"
        "모든 서비스의 Healthy · stable 이미지 태그를 확인했습니다. PR 검사 통과 후 "
        "rebase 자동 머지를 요청합니다. main은 새 SHA로 test를 다시 검증하고 같은 이미지를 prod에 사용합니다.\n"
        "<!-- yolo-deploy:end -->"
    )
    body = existing["body"] if existing else ""
    start, end = "<!-- yolo-deploy:start -->", "<!-- yolo-deploy:end -->"
    if start in body and end in body:
        before, rest = body.split(start, 1)
        _, after = rest.split(end, 1)
        body = before + summary + after
    else:
        body = body.rstrip() + "\n\n" + summary

    gh("label", "create", "yolo", "--repo", repo, "--color", "FBCA04",
       "--description", "test 승격 뒤 자동 생성한 배포 PR", "--force")
    with tempfile.TemporaryDirectory() as tmp:
        body_file = Path(tmp) / "body.md"
        body_file.write_text(body)
        if existing:
            pr = str(existing["number"])
            gh("pr", "edit", pr, "--repo", repo, "--body-file", str(body_file), "--add-label", "yolo")
        else:
            pr = gh("pr", "create", "--repo", repo, "--base", "main", "--head", branch,
                    "--title", f"[T8] yolo 배포: {branch[5:]}", "--body-file", str(body_file), "--label", "yolo")

    number = int(pr.rstrip("/").rsplit("/", 1)[-1])

    # With no required status checks GitHub may merge immediately, even with --auto.
    # Require an actual pull_request deploy run, not the earlier push run with the same SHA.
    files = json.loads(gh("pr", "view", pr, "--repo", repo, "--json", "files"))["files"]
    expected = {".github/workflows/deploy.yml"}
    if report.get("infra_workflow", True) and any((f["path"].startswith("infra/") or f["path"] == ".github/workflows/infra.yml") for f in files):
        expected.add(".github/workflows/infra.yml")
    deadline = time.monotonic() + timeout
    while True:
        assert_head()
        runs = api(f"repos/{repo}/actions/runs?event=pull_request&head_sha={sha}&per_page=100")["workflow_runs"]
        latest = {}
        for item in sorted(runs, key=lambda item: item["id"], reverse=True):
            if item["head_branch"] == branch and any(p["number"] == number for p in item["pull_requests"]):
                latest.setdefault(item["path"].split("@", 1)[0], item)
        for path in expected:
            item = latest.get(path)
            if item and item["status"] == "completed" and item["conclusion"] != "success":
                raise RuntimeError(f"PR 검사 실패: {path}: {item['conclusion']}")
        if all(path in latest and latest[path]["status"] == "completed" and
               latest[path]["conclusion"] == "success" for path in expected):
            break
        if time.monotonic() >= deadline:
            raise RuntimeError("PR 검사 대기 시간 초과. PR은 남기고 자동 머지는 요청하지 않는다")
        time.sleep(10)
    assert_head()
    gh("pr", "merge", pr, "--repo", repo, "--auto", "--rebase", "--match-head-commit", sha)
    return pr


if __name__ == "__main__":
    report = json.loads(Path(os.environ["REPORT"]).read_text())
    pr = run(report, os.environ["GITHUB_REF_NAME"], os.environ["GITHUB_REPOSITORY"])
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as output:
        output.write(f"### yolo PR\n{pr}\n\nPR 검사 통과 · rebase 자동 머지 요청. 필요한 리뷰는 GitHub 규칙을 따릅니다.\n")
