#!/usr/bin/env bash
# CHANGELOG에서 <from> 초과 ~ <to> 이하 버전의 항목만 출력한다. 업데이트 PR 본문에 붙인다.
#
#   changelog-between.sh <vFROM> <vTO> [CHANGELOG.md]
set -euo pipefail

from="${1:?시작 버전이 필요하다}"
to="${2:?끝 버전이 필요하다}"
file="${3:-CHANGELOG.md}"

awk -v from="$from" -v to="$to" '
  function key(v, a) { sub(/^v/, "", v); split(v, a, "."); return sprintf("%06d%06d%06d", a[1], a[2], a[3]) }
  BEGIN { f = key(from); t = key(to) }
  /^## / {
    p = ($2 ~ /^v[0-9]+\.[0-9]+\.[0-9]+$/) && key($2) > f && key($2) <= t
  }
  p
' "$file"
