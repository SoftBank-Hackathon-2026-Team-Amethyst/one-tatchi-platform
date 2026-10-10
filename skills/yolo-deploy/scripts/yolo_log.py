#!/usr/bin/env python3
"""yolo-deploy 실행 기록 세 개(analyze · provision · yolo)의 뼈대를 한 번에 쓴다.

값은 모두 인자로 받는다. 추측해 채우지 않으며 비어 있는 항목은 "없음"으로 적는다.
분석을 재사용한 실행(--reuse)은 analyze · provision 기록을 짧은 형식으로 쓴다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path


def _lines(items: list[str] | None, empty: str = "없음") -> str:
    if not items:
        return f"  - {empty}"
    return "\n".join(f"  - {item}" for item in items)


def _read_yaml_scalar(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].split("#", 1)[0].strip().strip("\"'")
    return ""


def build(args: argparse.Namespace, now: dt.datetime) -> dict[str, str]:
    stamp = now.strftime("%Y%m%d-%H%M%S")
    started = args.started or now.strftime("%Y-%m-%d %H:%M")
    config = Path(args.repo) / ".deploy" / "config.yaml"
    compliance = args.compliance or _read_yaml_scalar(config, "compliance") or "unknown"
    template = _read_yaml_scalar(config, "template_version") or "unknown"
    reuse = bool(args.reuse)

    analyze = (
        "# deploy-analyze 실행 기록\n\n"
        f"- 모드: yolo (호출: /yolo-deploy, 브랜치 `{args.branch}`, 기준 origin/main {args.base})\n"
        f"- 실행자: {args.actor} · 시작 {started} (KST)\n"
        "- 브리프: 기존 `.deploy/brief.md` 확인 없이 재사용\n"
        + (
            f"- 분석기: **재사용** — {args.reuse}. 돌리지 않은 분석기: 코드베이스 · 서비스 · 트래픽 · 보안 · 예산"
            + (f" (예외: {args.rerun})" if args.rerun else "")
            + "\n- 비용: 기존 costs.json 재사용 (과금 자원 목록 동일, 원 조회 시각은 budget.md 참조)\n"
            if reuse
            else f"- 분석기: 5개 실행 — {args.analysis or '세부는 보고서 참조'}\n"
        )
        + f"- 결과: {args.recommendation or '보고서 참조'}\n"
        f"- compliance: `{compliance}` (config.yaml 변경 없음)\n"
    )

    provision = (
        "# deploy-provision 실행 기록\n\n"
        f"- 모드: yolo · 템플릿 버전 `{template}` 그대로 · 대상 {args.target}\n"
        f"- 고친 산출물 · 코드:\n{_lines(args.change)}\n"
        f"- 검증:\n{_lines(args.verify, '아직 없음 — push 전에 채운다')}\n"
        "- 반영된 것: 없음 (push는 yolo-deploy가 한다)\n"
    )

    yolo = (
        "# yolo-deploy 실행 기록\n\n"
        f"- 실행자: {args.actor}\n"
        f"- 시각: {started} 시작 (KST)\n"
        f"- 브랜치: `{args.branch}` (origin/main {args.base} 기준)\n"
        f"- 대상: {args.target}\n"
        f"- compliance: `{compliance}`. 운영 반영은 사람 승인. 이 실행은 `.deploy/config.yaml`을 건드리지 않음\n"
        "- 브리프: 기존 재사용(질문 없음)\n"
        f"- 분석: {'재사용 — ' + args.reuse if reuse else '분석기 5개 실행'} (기록 `{stamp}-analyze.md`)\n"
        f"- 가정:\n{_lines(args.assumption, '보고서 가정 절 참조')}\n"
        f"- 리뷰 지점 1 자동 승인: {args.recommendation or '보고서 추천 참조'}\n"
        f"- 경고(사람 몫):\n{_lines(args.warning)}\n"
        f"- 이번 push 변경:\n{_lines(args.change)}\n"
        "- 자동 수정: 최초 push 시 없음. 이후 수정은 `repair_loop.py retry` 기록에 남는다\n"
        "- SHA · 검사 · 승격 · 자동 PR 결과: Actions artifact와 자동 PR 본문\n"
    )
    return {f"{stamp}-analyze.md": analyze, f"{stamp}-provision.md": provision, f"{stamp}-yolo.md": yolo}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".", help="대상 앱 저장소 경로")
    parser.add_argument("--actor", required=True, help="실행자 GitHub 로그인")
    parser.add_argument("--branch", required=True, help="yolo/<기능> 브랜치")
    parser.add_argument("--base", required=True, help="기준 origin/main 짧은 SHA")
    parser.add_argument("--target", required=True, help="aws | gcp | onprem")
    parser.add_argument("--compliance", help="생략하면 .deploy/config.yaml에서 읽는다")
    parser.add_argument("--started", help="시작 시각 'YYYY-MM-DD HH:MM' (생략하면 지금)")
    parser.add_argument("--reuse", help="분석 재사용 근거 (기준 커밋, 확인한 diff 범위). 주면 재사용 모드")
    parser.add_argument("--rerun", help="재사용 모드에서 그래도 돌린 분석기")
    parser.add_argument("--analysis", help="전체 실행 모드의 분석기 요약")
    parser.add_argument("--recommendation", help="자동 승인한 추천 (대상 · 월 비용 · 예산 판정)")
    parser.add_argument("--assumption", action="append", help="가정 (반복 가능)")
    parser.add_argument("--warning", action="append", help="사람 몫 경고 (반복 가능)")
    parser.add_argument("--change", action="append", help="이번 push가 바꾸는 파일 (반복 가능)")
    parser.add_argument("--verify", action="append", help="로컬 검증 결과 (반복 가능)")
    parser.add_argument("--dry-run", action="store_true", help="쓰지 않고 내용만 출력")
    args = parser.parse_args(argv)

    files = build(args, dt.datetime.now())
    log_dir = Path(args.repo) / ".deploy" / "log"
    if args.dry_run:
        for name, body in files.items():
            print(f"===== {name}\n{body}")
        return 0
    log_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, body in files.items():
        path = log_dir / name
        if path.exists():
            print(f"이미 있다: {path}", file=sys.stderr)
            return 1
        path.write_text(body, encoding="utf-8")
        written.append(str(path))
    print(json.dumps({"written": written}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
