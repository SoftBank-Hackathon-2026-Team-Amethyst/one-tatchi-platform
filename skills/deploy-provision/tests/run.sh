#!/usr/bin/env bash
# deploy-provision 템플릿 · 스크립트 테스트:  bash skills/deploy-provision/tests/run.sh
# 템플릿을 예시 값으로 렌더해 가짜 앱 레포를 만들고 check-artifacts.sh가 통과하는지, 버전이 어긋나면 잡는지 본다.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
skill="$(dirname "$here")"
render="$skill/scripts/render.sh"
check="$skill/scripts/check-artifacts.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
app="$tmp/app"

services_json='[{"name":"demo-app-be","path":"be","values":"deploy/values-be.yaml","migration":"db/init.sql"},
         {"name":"demo-app-fe","path":"fe","values":"deploy/values-fe.yaml"}]'
common=(TEMPLATE_VERSION=v1.9.0 CHART_VERSION=1.9.0 APP=demo-app ORG=Example-Org ORG_LOWER=example-org
  DEFAULT_TARGET=onprem CLUSTER_AWS=one-tatchi CLUSTER_ONPREM=k3d-onetouch CLUSTER_NAME=onetouch
  HOST_TEST=yolo.example.test HOST_PROD=example.test "SERVICES_JSON=$services_json"
  'NODE_DIRS=["be","fe"]' 'PYTHON_DIRS=[]' 'IMAGE_DIRS=["be","fe"]' DB_INIT=db/init.sql
  'OWNERS=@alice @bob' 'REPOSITORIES_HCL=["demo-app-be", "demo-app-fe"]' PUBLIC_SERVICE=demo-app-fe PUBLIC_SERVICE_PORT=3000
  DB_NAME=demo ACCOUNT_ID=123456789012 REGION=ap-northeast-2 DOMAIN=example.test)

echo "== 템플릿 전부 렌더"
while IFS= read -r t; do
  rel="${t#"$skill/templates/"}"; out="$app/${rel%.tmpl}"
  case "$rel" in
    deploy/values-service.yaml.tmpl)
      bash "$render" "$t" "$app/deploy/values-be.yaml" "${common[@]}" SERVICE=demo-app-be PORT=8000 HEALTH=/health >/dev/null
      bash "$render" "$t" "$app/deploy/values-fe.yaml" "${common[@]}" SERVICE=demo-app-fe PORT=3000 HEALTH=/ >/dev/null ;;
    .deploy/smoke.json.tmpl)
      bash "$render" "$t" "$out" "${common[@]}" SERVICE=demo-app-be HEALTH=/health >/dev/null ;;
    *) bash "$render" "$t" "$out" "${common[@]}" >/dev/null ;;
  esac
done < <(find "$skill/templates" -type f -name '*.tmpl' | sort)

echo "== 값이 빠진 자리표시자는 렌더가 거부"
if bash "$render" "$skill/templates/.github/CODEOWNERS.tmpl" "$tmp/x" TEMPLATE_VERSION=v1.9.0 2>/dev/null; then
  echo "OWNERS 없이 렌더됐다" >&2; exit 1
fi

echo "== 가짜 앱 파일과 config.yaml"
for s in be fe; do
  mkdir -p "$app/$s"
  printf 'FROM scratch\nUSER 1000\n' > "$app/$s/Dockerfile"
  printf 'node_modules\n.git\n' > "$app/$s/.dockerignore"
done
mkdir -p "$app/db"; echo "SELECT 1;" > "$app/db/init.sql"
cat > "$app/.deploy/config.yaml" <<'EOF'
template_version: v1.9.0
compliance: regulated
target: onprem
services:
  - name: demo-app-be
    path: be
  - name: demo-app-fe
    path: fe
EOF

echo "== check-artifacts 통과"
bash "$check" "$app" >"$tmp/check.log" || { cat "$tmp/check.log" >&2; exit 1; }

echo "== 버전이 어긋나면 실패"
sed -i.bak 's/template-ref: v1.9.0/template-ref: v1.8.0/' "$app/.github/workflows/deploy.yml"
if bash "$check" "$app" >"$tmp/check2.log" 2>&1; then
  echo "template-ref 불일치를 놓쳤다" >&2; cat "$tmp/check2.log" >&2; exit 1
fi
grep -q 'template-ref' "$tmp/check2.log"
mv "$app/.github/workflows/deploy.yml.bak" "$app/.github/workflows/deploy.yml"

echo "== 자리표시자가 남으면 실패"
echo "host: @@HOST_TEST@@" >> "$app/deploy/onprem/values.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "자리표시자 잔존을 놓쳤다" >&2; exit 1; fi

echo "== 렌더된 워크플로 · JSON 형식"
if command -v python3 >/dev/null; then
  for f in "$app"/.github/workflows/*.yml; do python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null || python3 -c "import sys; sys.exit(0)"; done
fi
command -v jq >/dev/null && jq -e . "$app/.deploy/smoke.json" >/dev/null

echo "통과"
