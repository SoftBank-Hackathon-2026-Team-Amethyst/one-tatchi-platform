#!/usr/bin/env python3
"""Validate deployment answers and save a brief without changing existing policy."""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

FIELDS = {
    "expected_daily_users",
    "monthly_budget",
    "data_categories",
    "preferred_target",
    "availability",
}
DATA_LABELS = {"personal": "개인정보", "payment": "결제", "financial": "금융"}
TARGET_LABELS = {"aws": "AWS", "gcp": "GCP", "onprem": "온프레미스", "auto": "추천받기"}
AVAILABILITY_LABELS = {
    "demo": "시연용",
    "standard": "일반 운영",
    "high": "중단에 민감",
    "unknown": "미정",
}


class BriefError(ValueError):
    """An invalid answer or protected configuration must stop all writes."""


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BriefError(f"중복 JSON 키: {key}")
        result[key] = value
    return result


def validate_answers(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise BriefError(
            "답변에는 계약의 다섯 키가 모두 필요하며 추가 키는 허용하지 않습니다."
        )

    users = value["expected_daily_users"]
    if users is not None and (type(users) is not int or users < 0):
        raise BriefError("expected_daily_users는 0 이상의 정수 또는 null이어야 합니다.")

    budget = value["monthly_budget"]
    if budget is not None:
        if not isinstance(budget, dict) or set(budget) != {"amount", "currency"}:
            raise BriefError("monthly_budget에는 amount와 currency가 필요합니다.")
        amount = budget["amount"]
        if (
            type(amount) not in (int, float)
            or (isinstance(amount, float) and not math.isfinite(amount))
            or amount < 0
        ):
            raise BriefError("월 예산은 0 이상의 유한한 숫자여야 합니다.")
        currency = budget["currency"]
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise BriefError("통화는 KRW, USD, JPY 같은 대문자 3자리 코드여야 합니다.")

    categories = value["data_categories"]
    if categories is not None:
        if not isinstance(categories, list) or any(
            not isinstance(item, str) or item not in DATA_LABELS for item in categories
        ):
            raise BriefError(
                "data_categories는 personal/payment/financial 배열 또는 null입니다."
            )
        if len(categories) != len(set(categories)):
            raise BriefError("데이터 종류를 중복해서 지정할 수 없습니다.")

    for field, options in (
        ("preferred_target", TARGET_LABELS),
        ("availability", AVAILABILITY_LABELS),
    ):
        if not isinstance(value[field], str) or value[field] not in options:
            raise BriefError(f"{field}는 {' | '.join(options)} 중 하나여야 합니다.")

    # Keep canonical order for repeatable output, independent of question order.
    return {
        "expected_daily_users": users,
        "monthly_budget": None
        if budget is None
        else {"amount": budget["amount"], "currency": budget["currency"]},
        "data_categories": None if categories is None else sorted(categories),
        "preferred_target": value["preferred_target"],
        "availability": value["availability"],
    }


def classify_compliance(answers: dict) -> tuple[str, str]:
    categories = answers["data_categories"]
    if categories is None:
        return (
            "regulated",
            "데이터 취급 여부가 미정이므로 확인 전까지 승인 생략을 허용하지 않습니다.",
        )
    if categories:
        names = ", ".join(DATA_LABELS[item] for item in categories)
        return "regulated", f"사용자가 다음 데이터 취급을 명시했습니다: {names}."
    return (
        "none",
        "사용자가 개인정보·결제·금융 데이터를 모두 취급하지 않는다고 명시했습니다.",
    )


def defaulted_fields(answers: dict) -> list[str]:
    defaults = []
    for field in ("expected_daily_users", "monthly_budget", "data_categories"):
        if answers[field] is None:
            defaults.append(field)
    if answers["preferred_target"] == "auto":
        defaults.append("preferred_target")
    if answers["availability"] == "unknown":
        defaults.append("availability")
    return defaults


def render_brief(answers: dict, compliance: str, reason: str) -> str:
    users = answers["expected_daily_users"]
    user_text = "미정" if users is None else f"{users:,}명 / 일"
    budget = answers["monthly_budget"]
    budget_text = (
        "미정" if budget is None else f"{budget['amount']:,} {budget['currency']} / 월"
    )
    categories = answers["data_categories"]
    data_text = (
        "미정"
        if categories is None
        else (
            ", ".join(DATA_LABELS[item] for item in categories)
            or "모두 해당 없음 (사용자 명시)"
        )
    )
    defaults = defaulted_fields(answers)
    defaults_text = ", ".join(f"`{field}`" for field in defaults) or "없음"
    normalized = json.dumps(answers, ensure_ascii=False, indent=2, allow_nan=False)
    return (
        "# 배포 브리프\n\n"
        "사용자 답변으로 생성했습니다. 미정 값은 후속 분석에서 가정으로 구분합니다.\n\n"
        f"- 하루 예상 이용자: {user_text}\n"
        f"- 월 인프라 예산: {budget_text}\n"
        f"- 취급 데이터: {data_text}\n"
        f"- 선호 배포 대상: {TARGET_LABELS[answers['preferred_target']]}\n"
        f"- 가용성 요구: {AVAILABILITY_LABELS[answers['availability']]}\n\n"
        "## 규제 분류\n\n"
        f"- compliance: `{compliance}`\n"
        f"- 근거: {reason}\n"
        f"- 데이터 취급 여부 추가 확인: {'필요' if categories is None else '불필요'}\n\n"
        "## 기본값과 미정 항목\n\n"
        f"- {defaults_text}\n"
        "- 규모·예산 미정은 제한 없음이나 0을 뜻하지 않습니다.\n"
        "- `auto`는 대상 추천 요청, `unknown`은 가용성 미정입니다.\n\n"
        "## 정규화된 답변\n\n"
        f"```json\n{normalized}\n```\n"
    )


def prepare_config(path: Path, compliance: str) -> str | None:
    """Return initial YAML, or None when an existing policy can be reused."""
    yaml = YAML()
    yaml.preserve_quotes = True
    if path.exists():
        original = path.read_text(encoding="utf-8")
        try:
            config = yaml.load(original)
        except YAMLError as exc:
            raise BriefError(
                "config.yaml은 중복 키 없는 단일 YAML 매핑이어야 합니다."
            ) from exc
        if config is None:
            # An empty/comment-only configuration can be initialized.
            if any(
                line.strip() and not line.lstrip().startswith("#")
                for line in original.splitlines()
            ):
                raise BriefError("config.yaml의 최상위 값은 매핑이어야 합니다.")
            return (
                original
                + ("\n" if original and not original.endswith("\n") else "")
                + f"compliance: {compliance}\n"
            )
        if not isinstance(config, CommentedMap):
            raise BriefError("config.yaml의 최상위 값은 매핑이어야 합니다.")
        if "compliance" in config:
            existing = config["compliance"]
            if not isinstance(existing, str) or existing not in ("regulated", "none"):
                raise BriefError(
                    "기존 compliance가 유효하지 않습니다. 사람이 설정을 검토해야 합니다."
                )
            if existing != compliance:
                raise BriefError(
                    f"기존 compliance({existing})와 새 분류({compliance})가 다릅니다. "
                    "파일을 보존했습니다. 사람이 검토하는 설정 변경이 필요합니다."
                )
            return None
    else:
        config = CommentedMap()
    config["compliance"] = compliance
    output = io.StringIO()
    yaml.dump(config, output)
    return output.getvalue()


def atomic_write(path: Path, contents: str) -> None:
    """Replace one file only after its entire new contents have been written."""
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(contents)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_brief(project_root: Path, value: object, *, dry_run: bool = False) -> dict:
    answers = validate_answers(value)
    compliance, reason = classify_compliance(answers)
    root = project_root.expanduser().resolve()
    if not root.is_dir():
        raise BriefError("--project-root는 이미 존재하는 대상 앱 디렉터리여야 합니다.")
    deploy_dir = root / ".deploy"
    brief_path = deploy_dir / "brief.md"
    config_path = deploy_dir / "config.yaml"
    for path in (deploy_dir, brief_path, config_path):
        if path.is_symlink():
            raise BriefError(
                f"출력 경로의 심볼릭 링크는 허용하지 않습니다: {path.name}"
            )
    if deploy_dir.exists() and not deploy_dir.is_dir():
        raise BriefError(".deploy는 디렉터리여야 합니다.")
    for path in (brief_path, config_path):
        if path.exists() and not path.is_file():
            raise BriefError(f"{path.name}은 일반 파일이어야 합니다.")

    # Validate both output paths and policy before creating or replacing anything.
    config_text = prepare_config(config_path, compliance)
    brief_text = render_brief(answers, compliance, reason)
    if not dry_run:
        deploy_dir.mkdir(exist_ok=True)
        if config_text is not None:
            atomic_write(config_path, config_text)
        atomic_write(brief_path, brief_text)
    return {
        "compliance": compliance,
        "needs_review": answers["data_categories"] is None,
        "defaults_applied": defaulted_fields(answers),
        "brief_path": str(brief_path),
        "config_path": str(config_path),
        "dry_run": dry_run,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="배포 답변을 검증하고 브리프와 초기 compliance를 저장합니다."
    )
    parser.add_argument(
        "--project-root", type=Path, required=True, help="배포 대상 앱 루트"
    )
    parser.add_argument(
        "--answers", default="-", help="답변 JSON 파일 경로; 기본값 - 는 표준 입력"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="파일을 쓰지 않고 검증만 수행"
    )
    args = parser.parse_args()
    try:
        text = (
            sys.stdin.read()
            if args.answers == "-"
            else Path(args.answers).read_text(encoding="utf-8")
        )
        answers = json.loads(text, object_pairs_hook=unique_object)
        result = save_brief(args.project_root, answers, dry_run=args.dry_run)
    except (BriefError, json.JSONDecodeError, OSError, UnicodeError, YAMLError) as exc:
        print(f"브리프 저장 실패: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
