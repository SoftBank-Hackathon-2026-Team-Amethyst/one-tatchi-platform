#!/usr/bin/env bash
# 작업(T번호)의 GitHub 이슈를 프로젝트 보드에서 원하는 상태로 옮긴다.
# 사용법: board.sh T3 "In Progress"   (상태 이름은 대소문자 무시)
# 필요: gh auth refresh -s project
set -euo pipefail

OWNER=SoftBank-Hackathon-2026-Team-Amethyst
REPO=$OWNER/one-tatchi-platform
PROJECT=1

task="${1:?작업 번호 (예: T3)}"
want="${2:?상태 이름 (예: In Progress, Done)}"

# [T1]로 검색하면 [T10]도 걸리므로 제목 시작으로 거른다.
issue=$(gh issue list -R "$REPO" --state all --search "[$task] in:title" --limit 50 --json number,title \
  | jq -r --arg p "[$task]" 'map(select(.title|startswith($p)))|.[0].number // empty')
[ -n "$issue" ] || { echo "이슈를 못 찾음: [$task]" >&2; exit 1; }

project_id=$(gh project view "$PROJECT" --owner "$OWNER" --format json | jq -r .id)

item=$(gh project item-list "$PROJECT" --owner "$OWNER" --limit 500 --format json \
  | jq -r --argjson n "$issue" '.items[]|select(.content.number==$n and ((.content.repository // "")|test("one-tatchi-platform")))|.id' | head -1)
if [ -z "$item" ]; then
  item=$(gh project item-add "$PROJECT" --owner "$OWNER" --url "https://github.com/$REPO/issues/$issue" --format json | jq -r .id)
fi

fields=$(gh project field-list "$PROJECT" --owner "$OWNER" --format json)
field_id=$(jq -r '.fields[]|select(.name=="Status")|.id' <<<"$fields")
option_id=$(jq -r --arg w "$want" '.fields[]|select(.name=="Status")|.options[]|select((.name|ascii_downcase)==($w|ascii_downcase))|.id' <<<"$fields")
if [ -z "$option_id" ]; then
  echo "상태 '$want' 없음. 가능한 상태:" >&2
  jq -r '.fields[]|select(.name=="Status")|.options[].name' <<<"$fields" >&2
  exit 1
fi

gh project item-edit --project-id "$project_id" --id "$item" --field-id "$field_id" --single-select-option-id "$option_id" >/dev/null
echo "#$issue [$task] → $want"
