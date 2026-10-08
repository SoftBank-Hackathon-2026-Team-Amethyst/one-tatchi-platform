#!/usr/bin/env bash
# scripts/ 테스트. CI(ci.yml)와 로컬에서 같이 쓴다:  bash scripts/tests/run.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
scripts="$(dirname "$here")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "== bump-template-version: v1.0.0 → v1.1.0"
cp -r "$here/bump-template-version/before" "$tmp/repo"
bash "$scripts/bump-template-version.sh" v1.1.0 "$tmp/repo" >/dev/null
diff -r "$here/bump-template-version/after" "$tmp/repo"

echo "== bump-template-version: 잘못된 버전은 거부"
if bash "$scripts/bump-template-version.sh" 1.1.0 "$tmp/repo" 2>/dev/null; then
  echo "v 없는 버전을 받아들였다" >&2
  exit 1
fi

echo "== changelog-between: v1.0.0 초과 ~ v1.2.0 이하"
cat > "$tmp/CHANGELOG.md" <<'EOF'
# 변경 기록

## Unreleased

- 아직 안 나감

## v1.2.0

- 둘째

## v1.1.0

- 첫째

## v1.0.0

- 처음
EOF
expected=$'## v1.2.0\n\n- 둘째\n\n## v1.1.0\n\n- 첫째\n'
actual="$(bash "$scripts/changelog-between.sh" v1.0.0 v1.2.0 "$tmp/CHANGELOG.md")"$'\n'
[[ "$actual" == "$expected" ]] || { echo "기대:"; echo "$expected"; echo "실제:"; echo "$actual"; exit 1; } >&2

echo "통과"
