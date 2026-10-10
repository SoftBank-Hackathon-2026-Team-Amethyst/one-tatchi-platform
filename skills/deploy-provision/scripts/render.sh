#!/usr/bin/env bash
# 템플릿의 @@KEY@@ 자리표시자를 바꿔 대상 경로에 쓴다.
#   render.sh <템플릿.tmpl> <대상 경로> KEY=값 [KEY=값 …]
# 값에 줄바꿈이 있어도 된다. 남은 자리표시자가 있으면 실패한다 (빈 값은 KEY= 로 명시한다).
set -euo pipefail
# Bash 5's replacement '&' expansion is incompatible with literal template values.
shopt -u patsub_replacement 2>/dev/null || true

tmpl="${1:?템플릿 경로}"; out="${2:?대상 경로}"; shift 2
[ -f "$tmpl" ] || { echo "템플릿이 없다: $tmpl" >&2; exit 1; }
# v2 removes credentials from state; older tags still need their old provider contract.
for kv in "$@"; do
  if [[ "$kv" =~ ^TEMPLATE_VERSION=v1\.([0-9]+)\.[0-9]+$ ]]; then
    if [[ "$tmpl" == */infra/envs/onprem/*.tmpl ]]; then
      legacy="$(cd "$(dirname "$0")/../references/onprem-pre-v2" && pwd)/$(basename "$tmpl")"
      [ ! -f "$legacy" ] || tmpl="$legacy"
    fi
  fi
done


content="$(cat "$tmpl"; printf x)"; content="${content%x}"
version=""
for kv in "$@"; do
  key="${kv%%=*}"; val="${kv#*=}"
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "키 형식은 대문자 · 숫자 · _ : $key" >&2; exit 1; }
  needle="@@${key}@@"
  content="${content//$needle/$val}"
  [ "$key" != TEMPLATE_VERSION ] || version="$val"
done

# Generated callers must only pass inputs supported by their pinned template tag.
if [[ "$tmpl" == */.github/workflows/deploy.yml.tmpl ]] && [[ "$version" =~ ^v1\.([0-9]+)\.[0-9]+$ ]]; then
  minor="${BASH_REMATCH[1]}"
  content="$(printf '%s' "$content" | sed '/# T27-input/d')"
  if [ "$minor" -lt 14 ]; then
    content="$(printf '%s' "$content" | sed '/^[[:space:]]*yolo-auto-merge:/d')"
    content="${content//promote-mode: branch/promote-mode: \$\{\{ startsWith(github.ref, \'refs/heads/yolo/\') \&\& \'auto\' \|\| \'manual\' \}\}}"
  fi
  if [ "$minor" -lt 9 ]; then
    content="$(printf '%s' "$content" | sed '/^[[:space:]]*promote-mode:/d')"
  fi
fi

# 조건부 블록: `# [if FLAG]` · `# [if !FLAG]` ~ `# [end]` 줄 사이를 FLAG 값에 따라 남기거나 뺀다(중첩 가능).
# FLAG는 KEY=true로 켠다. 주지 않은 FLAG는 false다(기존 호출은 그대로). 표지 줄은 항상 지운다.
# 예: 계층별 배포 위치(T32) — DB_LINK=true면 db_link 연결을 넣고, NO_RDS=true면 RDS 블록을 뺀다.
if printf '%s' "$content" | /usr/bin/grep -Eq '^[[:space:]]*#[[:space:]]*\[(if|end)'; then
  flags=" "
  for kv in "$@"; do [ "${kv#*=}" != true ] || flags="$flags${kv%%=*} "; done
  content="$(printf '%sx' "$content" | awk -v flags="$flags" '
    function on(name) { return index(flags, " " name " ") > 0 }
    /^[[:space:]]*#[[:space:]]*\[if !?[A-Z][A-Z0-9_]*\][[:space:]]*$/ {
      cond = $0; sub(/^[[:space:]]*#[[:space:]]*\[if /, "", cond); sub(/\][[:space:]]*$/, "", cond)
      neg = (substr(cond, 1, 1) == "!"); if (neg) cond = substr(cond, 2)
      depth++; keep[depth] = (neg ? !on(cond) : on(cond)); next
    }
    /^[[:space:]]*#[[:space:]]*\[end\][[:space:]]*$/ {
      if (depth == 0) { print "render: 짝이 없는 [end]" > "/dev/stderr"; bad = 1; exit 1 }
      depth--; next
    }
    { show = 1; for (i = 1; i <= depth; i++) if (!keep[i]) show = 0; if (show) print }
    END { if (!bad && depth != 0) { print "render: 닫히지 않은 [if]" > "/dev/stderr"; exit 1 } }
  ')" || { echo "조건부 블록 오류: $tmpl" >&2; exit 1; }
  content="${content%x}"
fi

if left="$(printf '%s' "$content" | /usr/bin/grep -o '@@[A-Z][A-Z0-9_]*@@' | sort -u)" && [ -n "$left" ]; then
  echo "값이 없는 자리표시자: $(echo "$left" | tr '\n' ' ')" >&2; exit 1
fi

mkdir -p "$(dirname "$out")"
printf '%s' "$content" > "$out"
echo "$out"
