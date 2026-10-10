#!/usr/bin/env python3
"""배포 실패 원인 요약(diagnosis.json)을 남긴다 (T12): Actions 실행 요약 → PR 코멘트 → Slack 새 메시지.

- 실행 요약은 항상 남긴다.
- PR 코멘트는 실패한 커밋에 연결된 PR이 있을 때만 단다(열린 PR 우선, 없으면 이 커밋으로 머지된 PR).
  같은 커밋의 코멘트가 이미 있으면(재실행) 새로 달지 않고 고친다. 이슈는 만들지 않는다.
- Slack은 기존 실패 알림(slack-notify)을 고치지 않고 원인 요약을 새 메시지로 보낸다.
- 토큰이 없거나 게시가 실패해도 경고만 남기고 종료 코드는 0이다(배포 결과는 이미 정해졌다).
gh는 GH_TOKEN(봇 App 토큰, Pull requests 쓰기), Slack은 SLACK_BOT_TOKEN · SLACK_CHANNEL_ID를 쓴다.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from diagnose import fallback  # noqa: E402  진단 결과가 없을 때 같은 기본값을 쓴다

CATEGORY_NAMES = {"migration": "마이그레이션", "image_publish": "이미지 발행", "rollout_unhealthy": "새 버전 상태 이상",
                  "credentials": "인증", "timeout": "시간 초과", "configuration": "설정 · 값 파일",
                  "infrastructure": "인프라", "unknown": "알 수 없음"}
CONFIDENCE_NAMES = {"high": "높음", "medium": "보통", "low": "낮음"}
SLACK_ACTIONS = 3


class PublishError(Exception):
    pass


def gh(*args):
    try:
        return subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    except FileNotFoundError:
        raise PublishError("gh 실행 파일이 없다") from None
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or "").strip().splitlines()
        raise PublishError(f"gh {args[0]} 실패: {lines[-1] if lines else exc.returncode}") from None


def cell(text):
    """Markdown 표 칸에 넣을 수 있게 줄바꿈 · 세로선을 바꾼다."""
    return " ".join(str(text).split()).replace("|", "\\|")


def slack_escape(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def marker(evidence):
    return f"<!-- failure-diagnosis sha={evidence['run']['sha']} -->"


def where(evidence):
    jobs = evidence.get("failed_jobs") or []
    return ", ".join(j["name"] + (f" ({', '.join(j['failed_steps'])})" if j.get("failed_steps") else "")
                     for j in jobs) or "확인 못 함"


def source_line(diagnosis):
    if diagnosis["source"] == "ai":
        return f"AI 요약 ({diagnosis['model']}) · 확신도 {CONFIDENCE_NAMES[diagnosis['confidence']]}"
    return f"AI 요약 없음 — {diagnosis['error']}"


# ---- 실행 요약 · PR 코멘트 (Markdown) ------------------------------------------

def markdown(evidence, diagnosis, pr_url=None):
    run, deploy = evidence["run"], evidence["deploy"]
    parts = [
        "## 배포 실패 원인 진단 (T12)",
        f"**{CATEGORY_NAMES[diagnosis['category']]}** — {diagnosis['summary']}",
        f"_{source_line(diagnosis)}_",
        "\n".join([
            "| 항목 | 내용 |", "|---|---|",
            f"| 대상 · 환경 | {cell(deploy['target_label'])} / {deploy['environment']} (`{deploy['namespace']}`) |",
            f"| 커밋 | `{run['sha'][:12]}` · {cell(run['ref'])} |",
            f"| 실패한 단계 | {cell(where(evidence))} |",
            f"| 실행 | [{run['run_id']}]({run['run_url']}) |",
        ] + ([f"| PR 코멘트 | {pr_url} |"] if pr_url else [])),
    ]
    if diagnosis["evidence"]:
        lines = "\n".join(line.replace("```", "'''") for line in diagnosis["evidence"])
        parts.append(f"### 근거\n\n```text\n{lines}\n```")
    if diagnosis["actions"]:
        parts.append("### 확인 · 조치\n\n" + "\n".join(f"- {a}" for a in diagnosis["actions"]))
    collection = evidence.get("collection") or {}
    missing = [(k, v) for k, v in collection.items() if v.get("status") == "failed"]
    if missing:
        parts.append("### 수집하지 못한 것\n\n" + "\n".join(f"- `{k}`: {cell(v.get('detail') or '이유 없음')}"
                                                           for k, v in missing))
    parts.append("AI 요약은 실패 증거(오류 줄 · 클러스터 상태)만 보고 쓴 것이다. 조치 전에 실행 로그로 확인한다.")
    return "\n\n".join(parts) + "\n"


# ---- PR 코멘트 -----------------------------------------------------------------

def find_pr(repo, sha):
    prs = json.loads(gh("api", f"repos/{repo}/commits/{sha}/pulls"))
    opened = [p for p in prs if p.get("state") == "open"]
    merged = [p for p in prs if p.get("merge_commit_sha") == sha]
    return (opened or merged or [None])[0]


def comment(evidence, diagnosis):
    """PR이 있으면 코멘트를 달거나(같은 커밋 코멘트가 있으면) 고친다. PR이 없으면 None."""
    repo, sha = evidence["run"]["repository"], evidence["run"]["sha"]
    pr = find_pr(repo, sha)
    if not pr:
        return None
    # --paginate는 쪽마다 따로 출력하므로 jq로 표지가 있는 코멘트 id만 뽑는다.
    found = gh("api", "--paginate", f"repos/{repo}/issues/{pr['number']}/comments",
               "--jq", f".[] | select((.body // \"\") | contains({json.dumps(marker(evidence))})) | .id").split()
    with tempfile.TemporaryDirectory() as tmp:
        body = Path(tmp) / "body.md"
        body.write_text(marker(evidence) + "\n" + markdown(evidence, diagnosis))
        if found:
            result = gh("api", "-X", "PATCH", f"repos/{repo}/issues/comments/{found[0]}", "-F", f"body=@{body}")
        else:
            result = gh("api", "-X", "POST", f"repos/{repo}/issues/{pr['number']}/comments", "-F", f"body=@{body}")
    return json.loads(result).get("html_url") or pr.get("html_url")


# ---- Slack ---------------------------------------------------------------------

def slack_payload(channel, evidence, diagnosis, pr_url=None):
    run, deploy = evidence["run"], evidence["deploy"]
    text = (f":mag: *배포 실패 원인 요약* `{slack_escape(deploy['target_label'])}` {deploy['environment']}"
            f" @ `{run['sha'][:7]}`\n"
            f"*{CATEGORY_NAMES[diagnosis['category']]}* — {slack_escape(diagnosis['summary'])}\n"
            f"_{slack_escape(source_line(diagnosis))}_ · 실패한 단계: {slack_escape(where(evidence))}")
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": text}}]
    if diagnosis["actions"]:
        todo = "\n".join(f"• {slack_escape(a)}" for a in diagnosis["actions"][:SLACK_ACTIONS])
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*확인 · 조치*\n{todo}"}})
    links = [f"<{run['run_url']}|실행 요약 · 근거 보기>"] + ([f"<{pr_url}|PR 코멘트>"] if pr_url else [])
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": " · ".join(links)}]})
    return {"channel": channel, "text": text, "blocks": blocks}


def post_slack(token, payload, api_url):
    request = urllib.request.Request(
        f"{api_url.rstrip('/')}/chat.postMessage", data=json.dumps(payload, ensure_ascii=False).encode(),
        method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise PublishError(f"Slack 호출 실패: {str(exc)[:200]}") from None
    if not data.get("ok"):
        raise PublishError(f"Slack 오류: {data.get('error', 'unknown')}")


# ---- 실행 ----------------------------------------------------------------------

def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError, TypeError):
        return None


def append(path, text):
    if path:
        with open(path, "a") as f:
            f.write(text)


def main(argv=None):
    env = os.environ.get
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", required=True)
    p.add_argument("--diagnosis", required=True)
    p.add_argument("--slack-channel", default=env("SLACK_CHANNEL_ID", ""))
    p.add_argument("--no-pr-comment", action="store_true", help="PR 코멘트를 달지 않는다")
    args = p.parse_args(argv)

    evidence = load(args.evidence)
    if not evidence:
        print("::warning::증거 묶음(evidence.json)이 없어 원인 진단을 게시하지 못했다")
        return 0
    diagnosis = load(args.diagnosis) or {
        "schema_version": "1", "source": "fallback", "model": None,
        **fallback(evidence, "진단 결과 없음"), "error": "진단 결과(diagnosis.json)가 없다"}

    warnings, pr_url = [], None
    if args.no_pr_comment:
        pass
    elif not env("GH_TOKEN"):
        warnings.append("GH_TOKEN(봇 App 토큰)이 없어 PR 코멘트를 건너뛴다")
    else:
        try:
            pr_url = comment(evidence, diagnosis)
            print(f"PR 코멘트: {pr_url}" if pr_url else "커밋에 연결된 PR이 없어 코멘트를 달지 않는다")
        except (PublishError, ValueError, KeyError) as exc:
            warnings.append(f"PR 코멘트 실패: {exc}")

    append(env("GITHUB_STEP_SUMMARY"), markdown(evidence, diagnosis, pr_url))

    slack = "skipped"
    if not env("SLACK_BOT_TOKEN") or not args.slack_channel:
        print("Slack 설정(SLACK_BOT_TOKEN, SLACK_CHANNEL_ID)이 없어 알림을 건너뜁니다")
    else:
        try:
            post_slack(env("SLACK_BOT_TOKEN"), slack_payload(args.slack_channel, evidence, diagnosis, pr_url),
                       env("SLACK_API_URL") or "https://slack.com/api")
            slack = "sent"
        except PublishError as exc:
            slack = "failed"
            warnings.append(str(exc))

    append(env("GITHUB_OUTPUT"), f"pr-comment={pr_url or ''}\nslack={slack}\n")
    for warning in warnings:
        print(f"::warning::{warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
