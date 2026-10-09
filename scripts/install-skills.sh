#!/usr/bin/env bash
# skills/ 아래 스킬을 개인 스킬 경로에 심볼릭 링크로 설치한다.
#   install-skills.sh            설치 (이미 링크면 다시 건다)
#   install-skills.sh --remove   이 레포를 가리키는 링크만 지운다
# 대상: ~/.claude/skills (Claude Code), ~/.agents/skills (Codex). 실제 폴더가 있으면 덮어쓰지 않고 건너뛴다.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
mode="${1:-install}"
targets=("$HOME/.claude/skills" "$HOME/.agents/skills")

for skill in "$root"/skills/*/; do
  [ -f "$skill/SKILL.md" ] || continue
  name="$(basename "$skill")"
  src="${skill%/}"
  for dir in "${targets[@]}"; do
    link="$dir/$name"
    case "$mode" in
      --remove)
        if [ -L "$link" ] && [ "$(readlink "$link")" = "$src" ]; then
          rm "$link"; echo "지움  $link"
        fi ;;
      install)
        mkdir -p "$dir"
        if [ -e "$link" ] && [ ! -L "$link" ]; then
          echo "건너뜀  $link (링크가 아닌 실제 폴더가 있다)" >&2; continue
        fi
        ln -sfn "$src" "$link"; echo "설치  $link → $src" ;;
      *) echo "사용법: $0 [--remove]" >&2; exit 1 ;;
    esac
  done
done
