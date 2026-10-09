#!/usr/bin/env bash
# 대상 레포의 배포 산출물을 정적으로 검사한다. 문제를 모두 출력하고, 하나라도 있으면 1로 끝난다.
#   check-artifacts.sh [대상 레포 경로]
# 검사: 자리표시자 잔존 · .deploy/config.yaml 형식 · 버전 표기 일치 · 필수 파일 · smoke.json 형식 · Dockerfile · terraform fmt
# macOS 기본 bash(3.2)에서도 돌아야 한다. yq · terraform이 없으면 그 항목은 건너뛰고 알린다.
set -uo pipefail

root="${1:-.}"
cd "$root" || { echo "경로가 없다: $root" >&2; exit 1; }
problems=0
fail() { echo "✗ $*"; problems=$((problems + 1)); }
skip() { echo "– $* (건너뜀)"; }
semver='v[0-9][0-9]*\.[0-9][0-9]*\.[0-9][0-9]*'

# 1. 자리표시자
left="$(/usr/bin/grep -rn --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.terraform '@@[A-Z][A-Z0-9_]*@@' .github .deploy deploy infra 2>/dev/null || true)"
[ -z "$left" ] || fail "자리표시자가 남았다:"$'\n'"$left"

# 2. config.yaml
cfg=.deploy/config.yaml
if [ ! -f "$cfg" ]; then
  fail "$cfg 가 없다"; version=""
else
  version="$(sed -n 's/^template_version:[[:space:]]*["'"'"']*\('"$semver"'\).*/\1/p' "$cfg" | head -1)"
  compliance="$(sed -n 's/^compliance:[[:space:]]*\([a-z]*\).*/\1/p' "$cfg" | head -1)"
  [ -n "$version" ] || fail "$cfg: template_version은 vX.Y.Z 형식이어야 한다"
  case "$compliance" in regulated|none) ;; *) fail "$cfg: compliance는 regulated | none 이어야 한다 (지금: '$compliance')" ;; esac
fi

# 3. 버전 표기 일치
if [ -n "$version" ]; then
  ver="${version#v}"
  for f in .github/workflows/*.yml; do
    [ -f "$f" ] || continue
    case "$(basename "$f")" in template-update.yml) continue ;; esac
    bad="$(/usr/bin/grep -n "one-tatchi-platform/[^@[:space:]]*@$semver" "$f" | /usr/bin/grep -v "@$version" || true)"
    [ -z "$bad" ] || fail "$f: uses@ 버전이 $version 과 다르다:"$'\n'"$bad"
    bad="$(/usr/bin/grep -n "template-ref:[[:space:]]*$semver" "$f" | /usr/bin/grep -v "template-ref:[[:space:]]*$version" || true)"
    [ -z "$bad" ] || fail "$f: template-ref가 $version 과 다르다:"$'\n'"$bad"
    bad="$(/usr/bin/grep -n 'chart-version:[[:space:]]*[0-9]' "$f" | /usr/bin/grep -v "chart-version:[[:space:]]*$ver\$" || true)"
    [ -z "$bad" ] || fail "$f: chart-version이 $ver 과 다르다:"$'\n'"$bad"
  done
  bad="$(/usr/bin/grep -rn --include='*.tf' --exclude-dir=.terraform "one-tatchi-platform.git//[^?]*?ref=$semver" infra 2>/dev/null | /usr/bin/grep -v "?ref=$version" || true)"
  [ -z "$bad" ] || fail "모듈 ?ref= 버전이 $version 과 다르다:"$'\n'"$bad"
fi

# 4. 필수 파일
for f in .github/workflows/deploy.yml .github/workflows/template-update.yml .github/CODEOWNERS .deploy/smoke.json; do
  [ -f "$f" ] || fail "$f 가 없다"
done
ls deploy/values-*.yaml >/dev/null 2>&1 || fail "deploy/values-<서비스>.yaml 이 없다"
if [ -f .github/workflows/deploy.yml ]; then
  /usr/bin/grep -q 'yolo/\*\*' .github/workflows/deploy.yml || fail "deploy.yml: push 트리거에 yolo/** 가 없다"
  /usr/bin/grep -q 'environment: prod' .github/workflows/deploy.yml || fail "deploy.yml: prod 환경 job이 없다"
fi

# 5. smoke.json
if [ -f .deploy/smoke.json ]; then
  if command -v jq >/dev/null; then
    jq -e 'type == "object" and all(.[]; type == "array" and all(.[]; has("path")))' .deploy/smoke.json >/dev/null 2>&1 \
      || fail ".deploy/smoke.json: {\"<서비스>\": [{\"path\": …}, …]} 형식이 아니다"
  else skip "jq가 없어 smoke.json 형식"; fi
fi

# 6. 서비스별 Dockerfile · 값 파일 (config.yaml의 services)
if [ -f "$cfg" ] && command -v yq >/dev/null; then
  while IFS=$'\t' read -r name path; do
    [ -n "$name" ] || continue
    [ -f "$path/Dockerfile" ] || fail "$name: $path/Dockerfile 이 없다"
    [ -s "$path/.dockerignore" ] || fail "$name: $path/.dockerignore 가 없거나 비어 있다"
    short="${name##*-}"   # demo-app-be → be
    [ -f "deploy/values-$short.yaml" ] || [ -f "deploy/values-$name.yaml" ] || fail "$name: deploy/values-$short.yaml 이 없다"
    if [ -f "$path/Dockerfile" ]; then
      /usr/bin/grep -Eq '^USER[[:space:]]+[0-9]+' "$path/Dockerfile" || fail "$name: Dockerfile에 숫자 UID의 USER 가 없다 (App Chart runAsNonRoot)"
    fi
  done < <(yq -r '.services[]? | [.name, .path] | @tsv' "$cfg" 2>/dev/null)
else
  skip "yq가 없거나 config.yaml이 없어 서비스별 Dockerfile 검사"
fi

# 7. terraform fmt
if [ -d infra ]; then
  if command -v terraform >/dev/null; then
    out="$(terraform fmt -check -recursive infra 2>&1)" || fail "terraform fmt:"$'\n'"$out"
  else skip "terraform이 없어 fmt 검사"; fi
fi

if [ "$problems" -eq 0 ]; then echo "✓ 산출물 검사 통과"; exit 0; fi
echo "문제 $problems 건"; exit 1
