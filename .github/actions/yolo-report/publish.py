#!/usr/bin/env python3
"""yolo 리포트를 남긴다 (T10): S3 감사 로그 저장 → Actions 실행 요약 → 문제가 있으면 yolo-debt 이슈.

- 이슈는 yolo 브랜치당 하나다. 같은 브랜치의 열린 이슈가 있으면 코멘트를 단다.
- 이슈는 자동으로 닫지 않는다. 실행자를 담당자로 지정한다(지정할 수 없으면 담당자 없이 연다).
- S3 저장이나 이슈 생성이 실패하면 종료 코드 1이다. 기록 없이 성공으로 보고하지 않는다.
gh는 GH_TOKEN(봇 App 토큰, Issues 쓰기), aws는 감사 로그 버킷에 쓸 수 있는 자격증명을 쓴다.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

LABEL = "yolo-debt"
# 기한은 docs/tasks.md 0단계의 현재 가정(yolo-debt 이슈 처리 기한)을 따른다.
DEADLINE = "다음 정석(janto) 배포 전까지"
SOURCE_NAMES = {"vulnerability": "취약점", "misconfiguration": "IaC 설정", "license": "라이선스",
                "scan_exception": "검사 예외"}
APPROVAL_NAMES = {"required": "필요", "skipped": "생략 예정", "not_reached": "해당 없음"}


class PublishError(Exception):
    pass


def command(*args):
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()
    except FileNotFoundError:
        raise PublishError(f"{args[0]} 실행 파일이 없다") from None
    except subprocess.CalledProcessError as exc:
        lines = (exc.stderr or "").strip().splitlines()
        raise PublishError(f"{args[0]} {args[1] if len(args) > 1 else ''} 실패: "
                           f"{lines[-1] if lines else exc.returncode}") from None


def aws(*args):
    return command("aws", *args)


def gh(*args):
    return command("gh", *args)


def cell(text):
    """Markdown 표 칸에 넣을 수 있게 줄바꿈 · 세로선을 바꾼다."""
    return " ".join(str(text).split()).replace("|", "\\|")


def marker(report):
    return f"<!-- yolo-debt repository={report['repository']} branch={report['deploy']['branch']} -->"


def s3_key(report):
    ts = report["generated_at"]  # 2026-10-10T05:12:40Z
    day = ts[:10].replace("-", "/")
    return f"reports/yolo/{day}/{ts}-{report['deploy']['sha'][:12]}-{report['report_id']}.json"


def save(report_path, report, bucket):
    if not bucket:
        raise PublishError("감사 로그 버킷(AUDIT_LOG_BUCKET)이 없다")
    key = s3_key(report)
    # Object Lock 버킷은 체크섬이 있어야 쓸 수 있다 (audit-log 액션과 같다).
    aws("s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(report_path),
        "--checksum-algorithm", "SHA256", "--content-type", "application/json")
    return f"s3://{bucket}/{key}"


# ---- 사람이 읽는 내용 ----------------------------------------------------------

def overview(report, location):
    d = report["deploy"]
    j = report["judgment"]
    lines = [
        "| 항목 | 내용 |", "|---|---|",
        f"| 실행자 · 시각 | `{d['actor']}` · {report['generated_at']} |",
        f"| 브랜치 · 커밋 | `{d['branch']}` · `{d['sha'][:12]}` |",
        f"| 대상 | {d['target_label']} / {d['environment']} · test 승격 {'확인' if d['promoted'] else '안 됨'} |",
        f"| compliance · 템플릿 | {d['compliance'] or '값 없음'} · {d['template_version'] or '값 없음'} |",
        f"| AI 자동 수정 | {report['repairs']['count']}회 |",
        f"| 비차단 경고 | 새로 들여온 {report['warnings']['new_total']}건 / 전체 {report['warnings']['total']}건 |",
        f"| AI 승격 판단 | {j['decision'] or '없음'}{' — ' + cell(j['reason']) if j['reason'] else ''} |",
        f"| 운영 승인 | {APPROVAL_NAMES[report['approval']['status']]} — {cell(report['approval']['basis'])} |",
        f"| 리포트 원본 | {location or '저장 실패'} |",
        f"| 실행 | [{report['report_id']}]({d['run_url']}) |",
    ]
    return "\n".join(lines)


def details(report):
    parts = []
    repairs = report["repairs"]["items"]
    if repairs:
        parts += ["### AI 자동 수정", "", "| 회차 | 커밋 | 파일 | 사유 |", "|---|---|---|---|"]
        parts += [f"| {r['number']}/3 | `{r['commit'][:12]}` | {cell(', '.join(r['files']) or '-')} | {cell(r['reason'])} |"
                  for r in repairs]
        parts.append("")
    new = [w for w in report["warnings"]["items"] if w["new_on_branch"]]
    if new:
        parts += ["### 이 브랜치가 새로 들여온 비차단 경고", "",
                  "| 종류 | 심각도 | ID | 대상 | 패키지 | 설명 |", "|---|---|---|---|---|---|"]
        parts += [f"| {SOURCE_NAMES[w['source']]} | {w['severity']} | {cell(w['id'])} | {cell(w['target'])} | "
                  f"{cell(w['package'] or '-')} | {cell(w['title'])} |" for w in new]
        parts.append("")
    existing = report["warnings"]["total"] - report["warnings"]["new_total"]
    if existing:
        counts = {}
        for w in report["warnings"]["items"]:
            if not w["new_on_branch"]:
                counts[SOURCE_NAMES[w["source"]]] = counts.get(SOURCE_NAMES[w["source"]], 0) + 1
        parts += [f"main에 원래 있던 비차단 경고 {existing}건은 기록만 했다 "
                  f"({', '.join(f'{k} {v}' for k, v in counts.items())}). 목록은 리포트 원본에 있다.", ""]
    failed = [(k, v["detail"]) for k, v in report["collection"].items() if v["status"] == "failed"]
    if failed:
        parts += ["### 수집 실패", ""] + [f"- `{k}`: {cell(v)}" for k, v in failed] + [""]
    near = [(name, n) for name, s in report["judgment"]["services"].items() for n in s["near_threshold"]]
    if near:
        parts += ["### 기준에 가까운 지표 (참고)", ""] + [f"- {name}: {n}" for name, n in near] + [""]
    return "\n".join(parts)


def summary(report, location, issue):
    head = "## yolo 배포 리포트 (T10)"
    debt = report["debt"]
    if debt["open_issue"]:
        verdict = f"**yolo-debt: 있음** — {'; '.join(debt['reasons'])}"
        verdict += f"\n\n이슈: {issue}" if issue else "\n\n이슈: 생성 실패"
    else:
        verdict = "**yolo-debt: 없음**"
    return "\n\n".join([head, verdict, overview(report, location), details(report)]).rstrip() + "\n"


def issue_body(report, location):
    debt = report["debt"]
    return "\n\n".join([
        marker(report),
        "**이 yolo 배포는 사람 리뷰 없이 test에 반영됐고, 아래 문제가 확인됐습니다.**\n"
        "배포를 막을 정도는 아니었지만 누군가 확인해야 하는 항목입니다.",
        "**확인된 문제**\n" + "\n".join(f"- {r}" for r in debt["reasons"]),
        "**담당자가 할 일**\n"
        "- 각 항목을 고치거나(예: 패키지 업데이트, 검사 예외 제거, AI가 고친 코드 검토), "
        "문제없다고 판단한 이유를 코멘트로 남깁니다.\n"
        "- 다 처리했으면 이 이슈를 닫습니다.",
        f"**기한:** {DEADLINE}",
        "`yolo-debt`는 \"리뷰 없이 들어와서 나중에 처리해야 하는 문제(기술 부채)\"라는 뜻의 라벨입니다.",
        overview(report, location),
        details(report),
    ]).rstrip() + "\n"


def comment_body(report, location):
    d = report["deploy"]
    return "\n\n".join([
        f"같은 브랜치의 새 yolo 배포 `{d['sha'][:12]}` ([{report['report_id']}]({d['run_url']}))",
        "**이유**\n" + "\n".join(f"- {r}" for r in report["debt"]["reasons"]),
        details(report),
        f"리포트 원본: {location or '저장 실패'}",
    ]).rstrip() + "\n"


# ---- 이슈 ---------------------------------------------------------------------

def open_issue(report, location):
    repo = report["repository"]
    found = json.loads(gh("issue", "list", "--repo", repo, "--label", LABEL, "--state", "open",
                          "--limit", "100", "--json", "number,url,body"))
    existing = next((i for i in found if marker(report) in (i.get("body") or "")), None)
    with tempfile.TemporaryDirectory() as tmp:
        body = Path(tmp) / "body.md"
        if existing:
            body.write_text(comment_body(report, location))
            gh("issue", "comment", str(existing["number"]), "--repo", repo, "--body-file", str(body))
            return existing["url"]
        body.write_text(issue_body(report, location))
        gh("label", "create", LABEL, "--repo", repo, "--color", "D93F0B",
           "--description", "yolo 배포가 리뷰 없이 안고 들어온 문제 (T10)", "--force")
        d = report["deploy"]
        title = f"[yolo-debt] {d['branch']} · {d['sha'][:7]}"
        base = ["issue", "create", "--repo", repo, "--title", title, "--body-file", str(body), "--label", LABEL]
        try:
            return gh(*base, "--assignee", d["actor"])
        except PublishError:
            # 실행자가 봇이거나 담당자로 지정할 수 없는 계정이면 담당자 없이 연다.
            return gh(*base)


def append(path, text):
    if path:
        with open(path, "a") as f:
            f.write(text)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", required=True)
    p.add_argument("--bucket", default=os.environ.get("AUDIT_LOG_BUCKET", ""))
    args = p.parse_args(argv)

    report = json.loads(Path(args.report).read_text())
    errors, location, issue = [], None, None
    try:
        location = save(args.report, report, args.bucket)
        print(f"리포트 저장: {location}")
    except PublishError as exc:
        errors.append(f"S3 저장 실패: {exc}")
    if report["debt"]["open_issue"]:
        try:
            issue = open_issue(report, location)
            print(f"yolo-debt 이슈: {issue}")
        except PublishError as exc:
            errors.append(f"yolo-debt 이슈 실패: {exc}")
    append(os.environ.get("GITHUB_STEP_SUMMARY"), summary(report, location, issue))
    append(os.environ.get("GITHUB_OUTPUT"),
           f"location={location or ''}\nissue={issue or ''}\nopen-issue={str(report['debt']['open_issue']).lower()}\n")
    for error in errors:
        print(f"::error::{error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
