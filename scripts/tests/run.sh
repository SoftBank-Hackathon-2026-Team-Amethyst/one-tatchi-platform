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

echo "== 명시적인 클라우드 루트 pin을 유지"
printf '\ninfra_versions:\n  aws: v1.1.0\n' >> "$tmp/repo/.deploy/config.yaml"
bash "$scripts/bump-template-version.sh" v2.0.0 "$tmp/repo" >/dev/null
grep -q 'template_version: v2.0.0' "$tmp/repo/.deploy/config.yaml"
grep -q '?ref=v1.1.0' "$tmp/repo/infra/envs/aws/main.tf"

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

echo "== promote-judge 액션 (T7)"
bash "$(dirname "$scripts")/.github/actions/promote-judge/tests/run.sh" >/dev/null

echo "== deploy-provision 템플릿 · 산출물 검사 (T13)"
bash "$(dirname "$scripts")/skills/deploy-provision/tests/run.sh" >/dev/null

echo "== yolo 자동 수정 루프 (T14)"
python3 -B -m unittest discover -s "$(dirname "$scripts")/skills/yolo-deploy/tests"

echo "통과"
python3 -B -m unittest discover -s "$(dirname "$scripts")/.github/actions/publish-metrics/tests"
bash "$(dirname "$scripts")/.github/actions/image-push/tests/run.sh"

python3 -B -m unittest discover -s "$(dirname "$scripts")/scripts/onprem/tests"
python3 -B -m unittest discover -s "$(dirname "$scripts")/scripts/tests" -p 'test_*.py'
python3 -B -m unittest discover -s "$(dirname "$scripts")/scripts/observability/tests"
