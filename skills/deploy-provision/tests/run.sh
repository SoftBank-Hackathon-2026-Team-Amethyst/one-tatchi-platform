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
EOF
cat > "$app/.deploy/plan.yaml" <<'EOF'
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
cp -r "$app" "$tmp/pinned-app"
printf '\ninfra_versions:\n  aws: v1.8.0\n' >> "$tmp/pinned-app/.deploy/config.yaml"
mkdir -p "$tmp/pinned-app/infra/envs/aws"
cat > "$tmp/pinned-app/infra/envs/aws/pinned.tf" <<'EOF'
module "preview_auth" {
  source = "git::https://github.com/example/one-tatchi-platform.git//modules/preview_auth/aws?ref=v1.9.0"
}
module "db_link" {
  source = "git::https://github.com/example/one-tatchi-platform.git//modules/db_link/tailscale?ref=v1.9.0"
}
EOF
# Existing fixture roots are rendered at v1.9.0. Pin those infrastructure modules only.
find "$tmp/pinned-app/infra/envs/aws" -name '*.tf' ! -name pinned.tf -exec sed -i.bak 's/ref=v1.9.0/ref=v1.8.0/g' {} \;
bash "$check" "$tmp/pinned-app" >"$tmp/pin.log" || { cat "$tmp/pin.log" >&2; exit 1; }
sed -i.bak '/modules\/db_link\/tailscale/s/ref=v1.9.0/ref=v1.8.0/' "$tmp/pinned-app/infra/envs/aws/pinned.tf"
if bash "$check" "$tmp/pinned-app" >"$tmp/db-pin-bad.log" 2>&1; then
  echo "db_link가 cloud pin으로 내려간 것을 놓쳤다" >&2; exit 1
fi
mv "$tmp/pinned-app/infra/envs/aws/pinned.tf.bak" "$tmp/pinned-app/infra/envs/aws/pinned.tf"
sed -i.bak 's/ref=v1.9.0/ref=v1.8.0/g' "$tmp/pinned-app/infra/envs/aws/pinned.tf"
if bash "$check" "$tmp/pinned-app" >"$tmp/pin-bad.log" 2>&1; then
  echo "preview_auth가 cloud pin으로 내려간 것을 놓쳤다" >&2; exit 1
fi

sed -i.bak 's/template-ref: v1.9.0/template-ref: v1.8.0/' "$app/.github/workflows/deploy.yml"
if bash "$check" "$app" >"$tmp/check2.log" 2>&1; then
  echo "template-ref 불일치를 놓쳤다" >&2; cat "$tmp/check2.log" >&2; exit 1
fi
grep -q 'template-ref' "$tmp/check2.log"
mv "$app/.github/workflows/deploy.yml.bak" "$app/.github/workflows/deploy.yml"

echo "== 템플릿 버전보다 새 입력(promote-mode < v1.9.0)이면 실패"
sed -i.bak 's/template_version: v1.9.0/template_version: v1.8.0/' "$app/.deploy/config.yaml"
sed -i.bak -E 's/(@|template-ref: |\?ref=)v1\.9\.0/\1v1.8.0/g; s/chart-version: 1\.9\.0/chart-version: 1.8.0/' "$app"/.github/workflows/*.yml "$app"/infra/envs/*/*.tf
if bash "$check" "$app" >"$tmp/check3.log" 2>&1; then echo "promote-mode 버전 불일치를 놓쳤다" >&2; cat "$tmp/check3.log" >&2; exit 1; fi
grep -q 'promote-mode' "$tmp/check3.log"
sed -i.bak 's/template_version: v1.8.0/template_version: v1.9.0/' "$app/.deploy/config.yaml"
sed -i.bak -E 's/(@|template-ref: |\?ref=)v1\.8\.0/\1v1.9.0/g; s/chart-version: 1\.8\.0/chart-version: 1.9.0/' "$app"/.github/workflows/*.yml "$app"/infra/envs/*/*.tf
find "$app" -name '*.bak' -delete
bash "$check" "$app" >/dev/null || { echo "되돌린 뒤 통과해야 한다" >&2; exit 1; }

echo "== config.yaml에 인계값이 들어가면 실패"
echo "target: onprem" >> "$app/.deploy/config.yaml"
if bash "$check" "$app" >"$tmp/check4.log" 2>&1; then echo "config.yaml의 target을 놓쳤다" >&2; exit 1; fi
grep -q 'plan.yaml' "$tmp/check4.log"
sed -i.bak '/^target: onprem$/d' "$app/.deploy/config.yaml"; rm -f "$app/.deploy/config.yaml.bak"
bash "$check" "$app" >/dev/null || { echo "되돌린 뒤 통과해야 한다" >&2; exit 1; }

echo "== 참조 버전에 맞게 T8 입력을 렌더"
for version in v1.8.0 v1.13.0 v1.14.0; do
  common[0]="TEMPLATE_VERSION=$version"
  common[1]="CHART_VERSION=${version#v}"
  bash "$render" "$skill/templates/.github/workflows/deploy.yml.tmpl" "$tmp/compat.yml" "${common[@]}" >/dev/null
  case "$version" in
    v1.8.0) ! grep -q 'promote-mode:' "$tmp/compat.yml"; ! grep -q 'yolo-auto-merge:' "$tmp/compat.yml" ;;
    v1.13.0) grep -q "promote-mode:.*startsWith" "$tmp/compat.yml"; ! grep -q 'yolo-auto-merge:' "$tmp/compat.yml" ;;
    v1.14.0) grep -q 'promote-mode: branch' "$tmp/compat.yml"; grep -q 'yolo-auto-merge: true' "$tmp/compat.yml" ;;
  esac
  if command -v actionlint >/dev/null; then actionlint -shellcheck='' "$tmp/compat.yml"; fi
done

echo "== 비어 있는 서비스 · 보호 값이 들어간 plan은 실패"
cp "$app/.deploy/plan.yaml" "$tmp/plan-original.yaml"
printf 'target: onprem\nservices: []\n' > "$app/.deploy/plan.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "빈 서비스를 놓쳤다" >&2; exit 1; fi
cp "$tmp/plan-original.yaml" "$app/.deploy/plan.yaml"
echo 'compliance: none' >> "$app/.deploy/plan.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "plan의 보호 값을 놓쳤다" >&2; exit 1; fi
cp "$tmp/plan-original.yaml" "$app/.deploy/plan.yaml"

echo "== 장애 주입 플래그는 test 덧붙임 파일에만 (T35)"
cp "$app/deploy/values-be.yaml" "$tmp/values-be-original.yaml"
printf 'env:\n  CHAOS_ENABLED: "true"\n' >> "$app/deploy/values-be.yaml"
if bash "$check" "$app" >"$tmp/check7.log" 2>&1; then echo "기본 값 파일의 CHAOS_ENABLED를 놓쳤다" >&2; cat "$tmp/check7.log" >&2; exit 1; fi
grep -q 'CHAOS_ENABLED' "$tmp/check7.log"
cp "$tmp/values-be-original.yaml" "$app/deploy/values-be.yaml"
printf 'env:\n  CHAOS_ENABLED: "true"\n' > "$app/deploy/values-be.prod.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "prod 덧붙임 파일의 CHAOS_ENABLED를 놓쳤다" >&2; exit 1; fi
rm -f "$app/deploy/values-be.prod.yaml"
printf 'env:\n  CHAOS_ENABLED: "true"\n' > "$app/deploy/values-be.test.yaml"
bash "$check" "$app" >"$tmp/check8.log" 2>&1 || { echo "test 덧붙임 파일은 허용돼야 한다" >&2; cat "$tmp/check8.log" >&2; exit 1; }
rm -f "$app/deploy/values-be.test.yaml"

echo "== 계층별 배포 위치 (T32): 지원 조합만 통과, 그 밖은 인프라 변경 전에 실패"
examples="$(dirname "$skill")/deploy-analyze/references/examples/plan"
for ok in single-target layers-all layers-test-only; do
  cp "$examples/$ok.yaml" "$app/.deploy/plan.yaml"
  bash "$check" "$app" >"$tmp/layers.log" 2>&1 || { echo "$ok 예시가 실패했다" >&2; cat "$tmp/layers.log" >&2; exit 1; }
done
expect_layer_failure() {  # <설명> <기대 문구> <plan 내용>
  printf '%s\n' "$3" > "$app/.deploy/plan.yaml"
  if bash "$check" "$app" >"$tmp/layers.log" 2>&1; then echo "$1 을(를) 놓쳤다" >&2; exit 1; fi
  grep -qF "$2" "$tmp/layers.log" || { echo "$1: 기대한 문구가 없다: $2" >&2; cat "$tmp/layers.log" >&2; exit 1; }
}
cp "$examples/layers-unsupported.yaml" "$app/.deploy/plan.yaml"
if bash "$check" "$app" >"$tmp/layers.log" 2>&1; then echo "지원하지 않는 조합(db gcp)을 놓쳤다" >&2; exit 1; fi
grep -qF '지원하지 않는 계층 조합: fe aws · be aws · db gcp' "$tmp/layers.log"
services_yaml='services:
  - {name: demo-app-be, path: be, database: true}
  - {name: demo-app-fe, path: fe, database: false}'
expect_layer_failure "fe가 target과 다름" "layers.fe · layers.be는 target(aws)과 같아야 한다" \
  "target: aws
layers: {fe: gcp, be: aws, db: onprem}
$services_yaml"
expect_layer_failure "앱 대상이 aws가 아닌 하이브리드" "지원하지 않는 계층 조합: fe gcp · be gcp · db onprem" \
  "target: gcp
layers: {fe: gcp, be: gcp, db: onprem}
$services_yaml"
expect_layer_failure "layers 키 누락" "layers.db 이 없다" \
  "target: aws
layers: {fe: aws, be: aws}
$services_yaml"
expect_layer_failure "DB를 쓰는 서비스 없음" "database: true 인 서비스가 없다" \
  "target: aws
layers: {fe: aws, be: aws, db: onprem}
services:
  - {name: demo-app-be, path: be, database: false}
  - {name: demo-app-fe, path: fe, database: false}"
expect_layer_failure "database_scope 알 수 없는 환경" "database_scope에 알 수 없는 환경: staging" \
  "target: aws
layers: {fe: aws, be: aws, db: onprem}
database_scope: [staging]
$services_yaml"
expect_layer_failure "database_scope 중복" "database_scope에 중복된 환경이 있다" \
  "target: aws
layers: {fe: aws, be: aws, db: onprem}
database_scope: [test, test]
$services_yaml"
expect_layer_failure "layers 없이 database_scope" "database_scope는 layers.db가 target과 다를 때만 쓴다" \
  "target: aws
database_scope: [test]
$services_yaml"
cp "$tmp/plan-original.yaml" "$app/.deploy/plan.yaml"
bash "$check" "$app" >/dev/null || { echo "plan을 되돌린 뒤 통과해야 한다" >&2; exit 1; }

echo "== DB Secret을 받는데 PGSSL이 없으면 실패, 있으면 통과"
cp "$app/deploy/values-be.yaml" "$tmp/values-be-original.yaml"
printf 'envFromSecrets:\n  - demo-app-db\n' >> "$app/deploy/values-be.yaml"
if bash "$check" "$app" >"$tmp/check5.log" 2>&1; then echo "PGSSL 누락을 놓쳤다" >&2; cat "$tmp/check5.log" >&2; exit 1; fi
grep -q 'PGSSL' "$tmp/check5.log"
printf 'env:\n  PGSSL: disable\n' >> "$app/deploy/values-be.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "PGSSL=disable을 놓쳤다" >&2; exit 1; fi
cp "$tmp/values-be-original.yaml" "$app/deploy/values-be.yaml"
printf 'envFromSecrets:\n  - demo-app-db\nenv:\n  PGSSL: require\n' >> "$app/deploy/values-be.yaml"
bash "$check" "$app" >"$tmp/check6.log" 2>&1 || { echo "PGSSL: require 인데 실패했다" >&2; cat "$tmp/check6.log" >&2; exit 1; }
cp "$tmp/values-be-original.yaml" "$app/deploy/values-be.yaml"

echo "== smoke.json의 expect_body는 객체여야 함"
cp "$app/.deploy/smoke.json" "$tmp/smoke-original.json"
jq '.["demo-app-be"][0].expect_body = "connected"' "$tmp/smoke-original.json" > "$app/.deploy/smoke.json"
if bash "$check" "$app" >/dev/null 2>&1; then echo "expect_body 문자열을 놓쳤다" >&2; exit 1; fi
jq '.["demo-app-be"][0].expect_body = {"database": "connected"}' "$tmp/smoke-original.json" > "$app/.deploy/smoke.json"
bash "$check" "$app" >"$tmp/check7.log" 2>&1 || { echo "expect_body 객체인데 실패했다" >&2; cat "$tmp/check7.log" >&2; exit 1; }
cp "$tmp/smoke-original.json" "$app/.deploy/smoke.json"

echo "== 자리표시자가 남으면 실패"
echo "host: @@HOST_TEST@@" >> "$app/deploy/onprem/values.yaml"
if bash "$check" "$app" >/dev/null 2>&1; then echo "자리표시자 잔존을 놓쳤다" >&2; exit 1; fi

echo "== v2는 ephemeral 계약, v1은 기존 계약으로 렌더"
common[0]="TEMPLATE_VERSION=v2.0.0"
common[1]="CHART_VERSION=2.0.0"
bash "$render" "$skill/templates/infra/envs/onprem/main.tf.tmpl" "$tmp/v2-main.tf" "${common[@]}" >/dev/null
bash "$render" "$skill/templates/infra/envs/onprem/variables.tf.tmpl" "$tmp/v2-variables.tf" "${common[@]}" >/dev/null
grep -q 'var.onprem_auth' "$tmp/v2-main.tf"
grep -q 'ephemeral *= true' "$tmp/v2-variables.tf"
! grep -q 'module.cluster.client_key' "$tmp/v2-main.tf"
common[0]="TEMPLATE_VERSION=v1.16.0"
bash "$render" "$skill/templates/infra/envs/onprem/main.tf.tmpl" "$tmp/v1-main.tf" "${common[@]}" >/dev/null
grep -q 'module.cluster.client_key' "$tmp/v1-main.tf"

echo "== 렌더된 워크플로 · JSON 형식"
if command -v python3 >/dev/null; then
  for f in "$app"/.github/workflows/*.yml; do python3 -c "import sys,yaml; yaml.safe_load(open(sys.argv[1]))" "$f" 2>/dev/null || python3 -c "import sys; sys.exit(0)"; done
fi
command -v jq >/dev/null && jq -e . "$app/.deploy/smoke.json" >/dev/null

echo "통과"
