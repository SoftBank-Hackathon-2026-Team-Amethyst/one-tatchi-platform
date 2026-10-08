#!/usr/bin/env python3
"""Validate deployment answers and save a brief without changing existing policy."""

from __future__ import annotations

import argparse
import io
import json
import os
import stat
import sys
import tempfile
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.error import YAMLError

QUESTION_PATH = Path(__file__).resolve().parents[1] / "references/brief-questions.json"
QUESTIONS = json.loads(QUESTION_PATH.read_text(encoding="utf-8"))["questions"]
FIELDS = {question["field"] for question in QUESTIONS}


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

    # Compare serialized values so nested booleans/floats cannot pass as integers.
    normalized = {}
    for question in QUESTIONS:
        field = question["field"]
        allowed = [option["value"] for option in question["options"]]
        allowed.append(question["skip_value"])
        try:
            encoded = json.dumps(value[field], sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise BriefError(f"{field}의 답변 형식이 유효하지 않습니다.") from exc
        for choice in allowed:
            if encoded == json.dumps(choice, sort_keys=True, allow_nan=False):
                normalized[field] = json.loads(json.dumps(choice))
                break
        else:
            raise BriefError(f"{field}는 질문 계약에 정의된 선택값만 허용합니다.")
    return normalized


def question_batches() -> list[dict]:
    """Emit native AskUserQuestion payloads without regenerating Korean text."""
    questions = [
        {
            "header": question["header"],
            "question": question["question"],
            "multiSelect": False,
            "options": [
                {"label": option["label"], "description": option["description"]}
                for option in question["options"]
            ],
        }
        for question in QUESTIONS
    ]
    # Claude Code supports at most four questions per native tool call.
    return [
        {"questions": questions[index : index + 4]}
        for index in range(0, len(questions), 4)
    ]


def answer_label(field: str, value: object) -> str:
    question = next(item for item in QUESTIONS if item["field"] == field)
    return next(
        (option["label"] for option in question["options"] if option["value"] == value),
        "미정",
    )


def classify_compliance(answers: dict) -> tuple[str, str]:
    sensitive_data = answers["handles_sensitive_data"]
    if sensitive_data == "unknown":
        return (
            "regulated",
            "데이터 취급 여부가 미정이므로 확인 전까지 승인 생략을 허용하지 않습니다.",
        )
    if sensitive_data == "yes":
        return "regulated", "사용자가 민감한 데이터를 저장하거나 처리한다고 답했습니다."
    return (
        "none",
        "사용자가 민감한 데이터를 저장하거나 처리하지 않는다고 명시했습니다.",
    )


def defaulted_fields(answers: dict) -> list[str]:
    return [
        question["field"]
        for question in QUESTIONS
        if answers[question["field"]] == question["skip_value"]
    ]


def render_brief(answers: dict, compliance: str, reason: str) -> str:
    labels = {field: answer_label(field, value) for field, value in answers.items()}
    needs_review = answers["handles_sensitive_data"] == "unknown"
    defaults = defaulted_fields(answers)
    defaults_text = ", ".join(f"`{field}`" for field in defaults) or "없음"
    normalized = json.dumps(answers, ensure_ascii=False, indent=2, allow_nan=False)
    return (
        "# 배포 브리프\n\n"
        "사용자 답변으로 생성했습니다. 미정 값은 후속 분석에서 가정으로 구분합니다.\n\n"
        f"- 하루 예상 이용자: {labels['expected_daily_users']}\n"
        f"- 월 인프라 예산 (KRW): {labels['monthly_budget']}\n"
        f"- 민감 데이터 취급: {labels['handles_sensitive_data']}\n"
        f"- 선호 배포 대상: {labels['preferred_target']}\n"
        f"- 가용성 요구: {labels['availability']}\n\n"
        "## 규제 분류\n\n"
        f"- compliance: `{compliance}`\n"
        f"- 근거: {reason}\n"
        f"- 데이터 취급 여부 추가 확인: {'필요' if needs_review else '불필요'}\n\n"
        "## 기본값과 미정 항목\n\n"
        f"- {defaults_text}\n"
        "- 규모·예산 미정은 제한 없음이나 0을 뜻하지 않습니다.\n"
        "- 사용자 수와 예산은 선택한 범위를 유지합니다. 범위 상한을 정확한 답변으로 바꾸지 않습니다.\n"
        "- 범위의 min/max는 포함 경계이며, max: null은 상한 미정입니다. 예산 무제한을 뜻하지 않습니다.\n"
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
        "needs_review": answers["handles_sensitive_data"] == "unknown",
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
        "--project-root", type=Path, help="배포 대상 앱 루트; 저장 시 필수"
    )
    parser.add_argument(
        "--answers", help="답변 JSON 파일 경로; 생략 또는 - 는 표준 입력"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="파일을 쓰지 않고 검증만 수행"
    )
    parser.add_argument(
        "--questions", action="store_true", help="선택형 질문 도구에 전달할 JSON 출력"
    )
    args = parser.parse_args()
    if args.questions:
        if args.project_root is not None or args.answers is not None or args.dry_run:
            parser.error("--questions는 저장 옵션과 함께 사용할 수 없습니다.")
        print(json.dumps({"batches": question_batches()}, ensure_ascii=False, indent=2))
        return 0
    if args.project_root is None:
        parser.error("저장하려면 --project-root가 필요합니다.")
    try:
        text = (
            sys.stdin.read()
            if args.answers in (None, "-")
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
