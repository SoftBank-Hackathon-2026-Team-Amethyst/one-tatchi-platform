#!/usr/bin/env bash
# skills/ 아래 스킬을 개인 스킬 경로에 심볼릭 링크로 설치한다.
#   install-skills.sh            이 체크아웃을 가리키는 링크를 건다 (이미 링크면 다시 건다)
#   install-skills.sh --auto     main 전용 클론(~/.one-tatchi/platform-skills)을 만들어 링크하고,
#                                Claude Code 세션 시작마다 그 클론을 fast-forward하는 SessionStart 훅을 등록한다.
#                                이후 platform main에 머지된 스킬 변경이 다음 세션부터 자동으로 반영된다.
#   install-skills.sh --remove   이 레포(또는 --auto 클론)를 가리키는 링크만 지운다
# 대상: ~/.claude/skills (Claude Code), ~/.agents/skills (Codex). 실제 폴더가 있으면 덮어쓰지 않고 건너뛴다.
set -euo pipefail

mode="${1:-install}"
targets=("$HOME/.claude/skills" "$HOME/.agents/skills")
auto_root="${ONE_TATCHI_SKILLS_CLONE:-$HOME/.one-tatchi/platform-skills}"
remote="https://github.com/SoftBank-Hackathon-2026-Team-Amethyst/one-tatchi-platform.git"
settings="$HOME/.claude/settings.json"
hook_cmd="git -C \"$auto_root\" pull --ff-only -q >/dev/null 2>&1 || true"

case "$mode" in
  install) root="$(cd "$(dirname "$0")/.." && pwd)" ;;
  --auto)
    if [ ! -d "$auto_root/.git" ]; then
      git clone -q --depth 1 --branch main "$remote" "$auto_root"
      echo "클론  $auto_root (main)"
    else
      git -C "$auto_root" pull --ff-only -q && echo "갱신  $auto_root"
    fi
    root="$auto_root" ;;
  --remove) root="$(cd "$(dirname "$0")/.." && pwd)" ;;
  *) echo "사용법: $0 [--auto|--remove]" >&2; exit 1 ;;
esac

link_skills() {
  local src name link
  for skill in "$root"/skills/*/; do
    [ -f "$skill/SKILL.md" ] || continue
    name="$(basename "$skill")"; src="${skill%/}"
    for dir in "${targets[@]}"; do
      link="$dir/$name"
      mkdir -p "$dir"
      if [ -e "$link" ] && [ ! -L "$link" ]; then
        echo "건너뜀  $link (링크가 아닌 실제 폴더가 있다)" >&2; continue
      fi
      ln -sfn "$src" "$link"; echo "설치  $link → $src"
    done
  done
}

remove_skills() {
  local target
  for skill in "$root"/skills/*/; do
    [ -f "$skill/SKILL.md" ] || continue
    for dir in "${targets[@]}"; do
      link="$dir/$(basename "$skill")"
      [ -L "$link" ] || continue
      target="$(readlink "$link")"
      case "$target" in "$root"/*|"$auto_root"/*) rm "$link"; echo "지움  $link" ;; esac
    done
  done
}

# ~/.claude/settings.json의 hooks.SessionStart에 fast-forward 명령을 한 번만 넣는다. 기존 훅 · 설정은 보존한다.
register_hook() {
  python3 - "$settings" "$hook_cmd" <<'PY'
import json, sys, pathlib
path, cmd = pathlib.Path(sys.argv[1]), sys.argv[2]
data = json.loads(path.read_text()) if path.is_file() else {}
hooks = data.setdefault("hooks", {}).setdefault("SessionStart", [])
for group in hooks:
    for h in group.get("hooks", []):
        if h.get("command") == cmd:
            print("훅 있음  SessionStart (platform-skills fast-forward)"); sys.exit(0)
hooks.append({"hooks": [{"type": "command", "command": cmd, "timeout": 20, "async": True,
                         "statusMessage": "one-tatchi 스킬 갱신"}]})
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
print("훅 등록  SessionStart → platform-skills fast-forward")
PY
}

case "$mode" in
  install) link_skills ;;
  --auto) link_skills; register_hook ;;
  --remove) remove_skills ;;
esac
