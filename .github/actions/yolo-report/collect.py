#!/usr/bin/env python3
"""yolo 배포 리포트를 만든다 (T10). 형식은 schema.json, 규칙은 README.

입력이 없거나 깨지면 멈추지 않고 그 항목을 collection.<항목> = failed로 남긴다.
수집 실패를 '문제 없음'으로 바꾸지 않는다. 표준 라이브러리만 쓴다.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

REPAIR_SUBJECT = re.compile(r"^\[yolo\] 검사 실패 자동 수정 ([1-3])/3$")
HISTORY_FILE = re.compile(r"^\.deploy/log/[^/]+-yolo\.md$")
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"}
WARNING_SOURCES = {"vulnerability", "misconfiguration", "license", "scan_exception"}
NEAR_RATIO = 0.8
LIMITS = {"repair_reason": 1000, "warning_title": 300, "judgment_reason": 2000,
          "service_reason": 1000, "detail": 300}
LINT_DETAIL = "린트 경고는 구조화된 출력이 없어 수집 범위 밖"
IMAGE_DETAIL = "이미지(OS 패키지) 비차단 취약점은 수집 범위 밖. 차단 검사는 checks.yml image-scan이 한다"


class Missing(Exception):
    """수집 실패. 메시지가 collection detail이 된다."""


def clip(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def ok():
    return {"status": "ok", "detail": None}


def failed(detail):
    return {"status": "failed", "detail": clip(detail, LIMITS["detail"])}


def not_collected(detail):
    return {"status": "not_collected", "detail": clip(detail, LIMITS["detail"])}


def read_json(path, what):
    if not path:
        raise Missing(f"{what} 경로가 없다")
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise Missing(f"{what}이(가) 없다") from None
    except (OSError, ValueError) as exc:
        raise Missing(f"{what}을(를) 읽지 못했다: {type(exc).__name__}") from None


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout


def config_values(root):
    """.deploy/config.yaml의 최상위 compliance · template_version. 파일이나 값이 없으면 None."""
    path = Path(root) / ".deploy" / "config.yaml"
    values = {"compliance": None, "template_version": None}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        m = re.match(r"^(compliance|template_version):\s*([^#\s]+)", line)
        if m:
            values[m.group(1)] = m.group(2).strip("'\"")
    if values["compliance"] not in ("regulated", "none"):
        values["compliance"] = None
    return values


# ---- 항목별 수집 -------------------------------------------------------------

def collect_deploy(args, config):
    deploy = {
        "actor": args.actor, "branch": args.branch, "sha": args.sha,
        "target": args.target, "target_label": args.target_label or args.target,
        "environment": "test", "compliance": config["compliance"],
        "template_version": config["template_version"],
        "run_url": args.run_url, "promoted": False,
    }
    if not args.promotion:
        return deploy, ok()  # test 승격 확인 결과가 없으면 승격하지 않은 배포다
    try:
        promotion = read_json(args.promotion, "test 승격 확인 결과(yolo-promotion.json)")
        if promotion.get("sha") != args.sha:
            raise Missing("test 승격 확인 결과의 SHA가 배포 SHA와 다르다")
        deploy["promoted"] = promotion.get("promoted") is True
        return deploy, ok()
    except Missing as exc:
        return deploy, failed(exc)


def collect_repairs(args):
    """yolo 브랜치가 갈라진 지점부터 배포 SHA까지의 수정 커밋 (yolo 수정 루프, T14)."""
    repairs = {"count": 0, "max": 3, "items": [], "history_file": None}
    try:
        base = git(args.repo_root, "merge-base", args.sha, args.base_ref).strip()
        log = git(args.repo_root, "log", "--reverse", "--format=%H%x1f%s%x1f%b%x1e",
                  f"{base}..{args.sha}")
    except (subprocess.CalledProcessError, OSError) as exc:
        lines = (getattr(exc, "stderr", "") or "").strip().splitlines()
        return repairs, failed("git 이력을 읽지 못했다: " + (lines[-1] if lines else type(exc).__name__))
    for record in filter(str.strip, log.split("\x1e")):
        commit, subject, body = (record.strip("\n").split("\x1f") + ["", ""])[:3]
        m = REPAIR_SUBJECT.match(subject.strip())
        if not m:
            continue
        try:
            changed = git(args.repo_root, "diff-tree", "--no-commit-id", "--name-only",
                          "-r", "--no-renames", commit.strip())
        except (subprocess.CalledProcessError, OSError):
            return repairs, failed(f"수정 커밋 {commit.strip()[:12]}의 파일 목록을 읽지 못했다")
        files = [f for f in changed.split("\n") if f]
        history = [f for f in files if HISTORY_FILE.match(f)]
        if history:
            repairs["history_file"] = history[-1]
        repairs["items"].append({
            "number": int(m.group(1)), "commit": commit.strip(),
            "files": [f for f in files if not HISTORY_FILE.match(f)],
            "reason": clip(body.strip() or "(사유 없음)", LIMITS["repair_reason"]),
        })
    repairs["count"] = len(repairs["items"])
    return repairs, ok()


def collect_warnings(args):
    """비차단 경고 파일: warnings.py 출력 (README '비차단 경고 입력')."""
    empty = {"total": 0, "new_total": 0, "base_sha": None, "items": [], "scanner": None}
    try:
        data = read_json(args.warnings, "비차단 경고 결과")
        if data.get("status") != "ok":
            raise Missing(data.get("detail") or "비차단 경고 수집이 끝나지 않았다")
        items = []
        for raw in data.get("items", []):
            if raw.get("source") not in WARNING_SOURCES or raw.get("severity") not in SEVERITIES \
                    or not isinstance(raw.get("new_on_branch"), bool):
                raise Missing("비차단 경고 항목 형식이 잘못됐다")
            items.append({"source": raw["source"], "severity": raw["severity"],
                          "id": str(raw["id"]), "target": str(raw["target"]),
                          "package": raw.get("package"),
                          "title": clip(raw.get("title") or raw["id"], LIMITS["warning_title"]),
                          "new_on_branch": raw["new_on_branch"]})
        scanner = data.get("scanner")
        if scanner is not None and not (isinstance(scanner, dict) and scanner.get("name") == "trivy"):
            raise Missing("비차단 경고의 scanner 형식이 잘못됐다")
        base = data.get("base_sha")
        if not (isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base)):
            raise Missing("비차단 경고의 비교 기준(base_sha)이 없다")
        return {"total": len(items), "new_total": sum(i["new_on_branch"] for i in items),
                "base_sha": base, "items": items, "scanner": scanner}, ok()
    except (Missing, KeyError, TypeError, AttributeError) as exc:
        detail = str(exc) if isinstance(exc, Missing) else "비차단 경고 항목 형식이 잘못됐다"
        return empty, failed(detail)


def near_threshold(metrics, thresholds):
    near = []
    for label, value, limit, unit in (
        ("에러율", metrics.get("error_rate"), thresholds.get("max_error_rate"), "%"),
        ("p95", metrics.get("p95_ms"), thresholds.get("max_p95_ms"), "ms"),
        ("재시작", metrics.get("restarts"), thresholds.get("max_restarts"), "회"),
    ):
        if isinstance(value, (int, float)) and isinstance(limit, (int, float)) and limit > 0 \
                and NEAR_RATIO * limit <= value <= limit:
            near.append(f"{label} {value:g}{unit} ≥ 기준 {limit:g}{unit}의 {NEAR_RATIO:.0%}")
    return near


def service_metrics(raw):
    if not isinstance(raw, dict) or "requests" not in raw:
        return None, None
    pods = raw.get("pods") or {}
    metrics = {"requests": int(raw.get("requests") or 0), "failed": int(raw.get("failed") or 0),
               "error_rate": raw.get("error_rate"), "p95_ms": raw.get("p95_ms"),
               "restarts": pods.get("restarts")}
    t = raw.get("thresholds")
    thresholds = None
    if isinstance(t, dict):
        thresholds = {"max_error_rate": t.get("max_error_rate"), "max_p95_ms": t.get("max_p95_ms"),
                      "max_restarts": t.get("max_restarts")}
    return metrics, thresholds


def collect_judgment(args):
    empty = {"decision": None, "reason": None, "services": {}}
    if args.judge_outcome == "skipped":
        # 첫 배포처럼 승격 대기(Paused) 서비스가 없으면 판단 단계가 돌지 않는다.
        return empty, not_collected("승격 대기 서비스가 없어 AI 승격 판단이 돌지 않았다")
    try:
        root = Path(args.judgment_dir) if args.judgment_dir else None
        if root is None or not root.is_dir():
            raise Missing("AI 판단 근거(promote-judgment artifact)를 받지 못했다")
        group = read_json(root / "judgment.json", "묶음 판단(judgment.json)")
        if group.get("decision") not in ("promote", "abort"):
            raise Missing("묶음 판단에 decision이 없다")
        services = {}
        for name in sorted(group.get("services") or {}):
            detail = read_json(root / name / "judgment.json", f"{name} 판단")
            metrics, thresholds = service_metrics(detail.get("metrics"))
            services[name] = {
                "decision": detail["decision"], "source": detail["source"],
                "reason": clip(detail.get("reason") or "", LIMITS["service_reason"]),
                "metrics": metrics, "thresholds": thresholds,
                "near_threshold": near_threshold(metrics or {}, thresholds or {}),
            }
        return {"decision": group["decision"],
                "reason": clip(group.get("reason") or "", LIMITS["judgment_reason"]),
                "services": services}, ok()
    except (Missing, KeyError, TypeError, AttributeError) as exc:
        detail = str(exc) if isinstance(exc, Missing) else "AI 판단 근거 형식이 잘못됐다"
        return empty, failed(detail)


def collect_approval(deploy):
    if not deploy["promoted"]:
        return {"status": "not_reached", "stage": "expected",
                "basis": "test에서 승격하지 않아 prod로 가지 않는다"}, ok()
    if deploy["compliance"] == "none":
        return {"status": "skipped", "stage": "expected",
                "basis": "compliance=none → main 반영 후 승인 없이 prod-auto"}, ok()
    shown = deploy["compliance"] or "값 없음"
    return {"status": "required", "stage": "expected",
            "basis": f"compliance={shown} → prod 반영 전 사람 승인(environment prod)"}, ok()


def decide_debt(report):
    reasons = []
    if report["repairs"]["count"]:
        reasons.append(f"AI 자동 수정 {report['repairs']['count']}회")
    if report["warnings"]["new_total"]:
        counts = {}
        for item in report["warnings"]["items"]:
            if not item["new_on_branch"]:
                continue
            key = {"vulnerability": f"취약점 {item['severity']}", "misconfiguration": f"IaC {item['severity']}",
                   "license": "라이선스", "scan_exception": "검사 예외"}[item["source"]]
            counts[key] = counts.get(key, 0) + 1
        parts = ", ".join(f"{k} {v}" for k, v in counts.items())
        reasons.append(f"이 브랜치가 새로 들여온 비차단 경고 {report['warnings']['new_total']}건 ({parts})")
    for name, state in report["collection"].items():
        if state["status"] == "failed":
            reasons.append(f"수집 실패: {name} ({state['detail']})")
    return {"open_issue": bool(reasons), "reasons": reasons}


def build(args):
    config = config_values(args.repo_root)
    deploy, deploy_state = collect_deploy(args, config)
    repairs, repairs_state = collect_repairs(args)
    warnings, warnings_state = collect_warnings(args)
    judgment, judgment_state = collect_judgment(args)
    approval, approval_state = collect_approval(deploy)
    report = {
        "schema_version": "1",
        "report_id": f"{args.run_id}-{args.run_attempt}",
        "generated_at": args.now or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repository": args.repository,
        "deploy": deploy, "repairs": repairs, "warnings": warnings,
        "judgment": judgment, "approval": approval,
        "collection": {"deploy": deploy_state, "repairs": repairs_state,
                       "warnings": warnings_state, "judgment": judgment_state,
                       "approval": approval_state, "lint": not_collected(LINT_DETAIL),
                       "image": not_collected(IMAGE_DETAIL)},
    }
    report["debt"] = decide_debt(report)
    return report


def parse(argv):
    env = os.environ.get
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--repo-root", default=".", help="배포한 커밋을 checkout한 대상 레포 (전체 이력 필요)")
    p.add_argument("--base-ref", default="origin/main", help="yolo 브랜치가 갈라진 지점을 찾을 기준")
    p.add_argument("--promotion", help="yolo-promotion.json. 없으면 test에서 승격하지 않은 배포")
    p.add_argument("--judgment-dir", help="promote-judgment artifact 폴더")
    p.add_argument("--judge-outcome", default="success", help="판단 단계 결과 (skipped면 판단 미실행)")
    p.add_argument("--warnings", help="비차단 경고 결과 JSON")
    p.add_argument("--target", required=True, choices=["aws", "gcp", "onprem"])
    p.add_argument("--target-label", default="")
    p.add_argument("--sha", default=env("GITHUB_SHA"))
    p.add_argument("--branch", default=env("GITHUB_REF_NAME"))
    p.add_argument("--actor", default=env("GITHUB_ACTOR"))
    p.add_argument("--repository", default=env("GITHUB_REPOSITORY"))
    p.add_argument("--run-id", default=env("GITHUB_RUN_ID"))
    p.add_argument("--run-attempt", default=env("GITHUB_RUN_ATTEMPT", "1"))
    p.add_argument("--run-url", default=None)
    p.add_argument("--now", help="테스트용 생성 시각 (UTC, ...Z)")
    args = p.parse_args(argv)
    if not args.run_url and env("GITHUB_SERVER_URL"):
        args.run_url = (f"{env('GITHUB_SERVER_URL')}/{args.repository}/actions/runs/"
                        f"{args.run_id}/attempts/{args.run_attempt}")
    missing = [k for k in ("sha", "branch", "actor", "repository", "run_id", "run_url")
               if not getattr(args, k)]
    if missing:
        p.error("값이 없다: " + ", ".join(missing))
    if not args.branch.startswith("yolo/"):
        p.error("yolo/* 브랜치 배포만 리포트한다")
    return args


def main(argv=None):
    args = parse(argv)
    report = build(args)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"yolo 리포트: {args.output} (이슈 {'연다' if report['debt']['open_issue'] else '열지 않는다'})")
    for reason in report["debt"]["reasons"]:
        print(f"  - {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
