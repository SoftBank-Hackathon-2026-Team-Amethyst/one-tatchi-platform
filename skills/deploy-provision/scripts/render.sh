#!/usr/bin/env bash
# 템플릿의 @@KEY@@ 자리표시자를 바꿔 대상 경로에 쓴다.
#   render.sh <템플릿.tmpl> <대상 경로> KEY=값 [KEY=값 …]
# 값에 줄바꿈이 있어도 된다. 남은 자리표시자가 있으면 실패한다 (빈 값은 KEY= 로 명시한다).
set -euo pipefail

tmpl="${1:?템플릿 경로}"; out="${2:?대상 경로}"; shift 2
[ -f "$tmpl" ] || { echo "템플릿이 없다: $tmpl" >&2; exit 1; }

content="$(cat "$tmpl"; printf x)"; content="${content%x}"
version=""
for kv in "$@"; do
  key="${kv%%=*}"; val="${kv#*=}"
  [[ "$key" =~ ^[A-Z][A-Z0-9_]*$ ]] || { echo "키 형식은 대문자 · 숫자 · _ : $key" >&2; exit 1; }
  content="${content//"@@$key@@"/"$val"}"
  [ "$key" != TEMPLATE_VERSION ] || version="$val"
done

# Generated callers must only pass inputs supported by their pinned template tag.
if [[ "$tmpl" == */.github/workflows/deploy.yml.tmpl ]] && [[ "$version" =~ ^v1\.([0-9]+)\.[0-9]+$ ]]; then
  minor="${BASH_REMATCH[1]}"
  if [ "$minor" -lt 14 ]; then
    content="$(printf '%s' "$content" | sed '/^[[:space:]]*yolo-auto-merge:/d')"
    content="${content//promote-mode: branch/promote-mode: \$\{\{ startsWith(github.ref, \'refs/heads/yolo/\') \&\& \'auto\' \|\| \'manual\' \}\}}"
  fi
  if [ "$minor" -lt 9 ]; then
    content="$(printf '%s' "$content" | sed '/^[[:space:]]*promote-mode:/d')"
  fi
fi

if left="$(printf '%s' "$content" | /usr/bin/grep -o '@@[A-Z][A-Z0-9_]*@@' | sort -u)" && [ -n "$left" ]; then
  echo "값이 없는 자리표시자: $(echo "$left" | tr '\n' ' ')" >&2; exit 1
fi

mkdir -p "$(dirname "$out")"
printf '%s' "$content" > "$out"
echo "$out"
