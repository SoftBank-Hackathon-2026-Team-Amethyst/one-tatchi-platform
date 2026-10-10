#!/usr/bin/env bash
# 대상 레포의 배포 산출물을 정적으로 검사한다. 문제를 모두 출력하고, 하나라도 있으면 1로 끝난다.
#   check-artifacts.sh [대상 레포 경로]
# 검사: 자리표시자 잔존 · .deploy/config.yaml 형식 · plan.yaml(계층별 배포 위치 조합 포함) · 버전 표기 일치 · 필수 파일 · smoke.json 형식 · Dockerfile · terraform fmt
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

# 계획과 보호 설정을 분리한다. 읽기만 하며 config.yaml을 다시 쓰지 않는다.
plan=.deploy/plan.yaml
[ -f "$plan" ] || fail "$plan 가 없다 (target · services는 config.yaml에서 분리)"
if command -v yq >/dev/null && [ -f "$plan" ]; then
  target="$(yq -r '.target' "$plan" 2>/dev/null)"
  case "$target" in aws|onprem|gcp) ;; *) fail "$plan: target은 aws | onprem | gcp 이어야 한다" ;; esac
  yq -o=json '.' "$plan" | jq -e '.services | type == "array" and length > 0 and all(.[];
    (.name | type == "string" and length > 0) and (.path | type == "string" and length > 0))' >/dev/null 2>&1 \
    || fail "$plan: services는 name · path가 있는 비어 있지 않은 배열이어야 한다"
  yq -o=json '.' "$plan" | jq -e 'has("compliance") or has("template_version")' >/dev/null 2>&1 \
    && fail "$plan: compliance · template_version은 config.yaml에만 둔다"
  if [ -f "$cfg" ]; then
    yq -o=json '.' "$cfg" | jq -e 'has("target") or has("services")' >/dev/null 2>&1 \
      && fail "$cfg: target · services는 plan.yaml로 옮긴다"
  fi
  # 계층별 배포 위치 (T32, ADR 0018). layers가 없으면 모든 계층이 target에 있다(기존 동작).
  # 지원 조합은 target aws + fe aws · be aws · db onprem 하나다. 인프라를 바꾸기 전에 여기서 멈춘다.
  while IFS= read -r msg; do
    [ -n "$msg" ] && fail "$plan: $msg"
  done < <(yq -o=json '.' "$plan" 2>/dev/null | jq -r '
    . as $p | ($p.target) as $t |
    if ($p | has("layers")) | not then
      if $p | has("database_scope") then "database_scope는 layers.db가 target과 다를 때만 쓴다" else empty end
    elif ($p.layers | type) != "object" then
      "layers는 fe · be · db 세 키를 가진 객체여야 한다"
    else
      ($p.layers) as $l |
      ( ["fe", "be", "db"][] as $k | select(($l[$k] | type) != "string") | "layers.\($k) 이 없다 (fe · be · db를 모두 적는다)" ),
      ( ($l | keys - ["fe", "be", "db"])[] | "layers에 알 수 없는 키: \(.)" ),
      ( if ($l.fe | type) == "string" and ($l.be | type) == "string" and ($l.db | type) == "string" then
          if $l.fe != $t or $l.be != $t then
            "layers.fe · layers.be는 target(\($t))과 같아야 한다 (지금: fe \($l.fe) · be \($l.be))"
          elif $l.db != $t and ([$t, $l.db] != ["aws", "onprem"]) then
            "지원하지 않는 계층 조합: fe \($l.fe) · be \($l.be) · db \($l.db) (지원: fe aws · be aws · db onprem)"
          elif $l.db == $t then
            (if $p | has("database_scope") then "database_scope는 layers.db가 target과 다를 때만 쓴다" else empty end)
          else
            ( if ([$p.services[]? | select(.database == true)] | length) == 0 then
                "layers.db가 \($l.db) 인데 database: true 인 서비스가 없다" else empty end ),
            ( if $p | has("database_scope") then
                ($p.database_scope) as $s |
                if ($s | type) != "array" or ($s | length) == 0 then
                  "database_scope는 test · prod 중 하나 이상을 담은 목록이어야 한다 (생략하면 모든 환경)"
                elif ($s | map(select(. != "test" and . != "prod")) | length) > 0 then
                  "database_scope에 알 수 없는 환경: \($s | map(select(. != "test" and . != "prod")) | join(", ")) (test · prod)"
                elif ($s | unique | length) != ($s | length) then
                  "database_scope에 중복된 환경이 있다"
                else empty end
              else empty end )
          end
        else empty end )
    end' 2>/dev/null || echo "layers · database_scope를 읽지 못했다")
  # DB를 온프레미스에 둔다면 AWS 루트가 그 계획대로 렌더됐는지 본다 (T32 C3). 운영 DB(RDS)를 실수로 빼는 것을 막는다.
  if [ "$(yq -r '.layers.db // ""' "$plan" 2>/dev/null)" = onprem ] && [ -d infra/envs/aws ]; then
    aws_main=infra/envs/aws/main.tf; aws_vars=infra/envs/aws/terraform.tfvars
    scope="$(yq -r '(.database_scope // ["test", "prod"]) | sort | join(" ")' "$plan" 2>/dev/null)"
    /usr/bin/grep -q '^module "db_link"' "$aws_main" 2>/dev/null \
      || fail "$aws_main: layers.db가 onprem인데 module \"db_link\"가 없다 (DB_LINK=true로 렌더)"
    if yq -e 'has("database_scope")' "$plan" >/dev/null 2>&1; then
      /usr/bin/grep -q '^module "database"' "$aws_main" 2>/dev/null \
        || fail "$aws_main: database_scope($scope) 밖의 환경이 쓸 RDS(module \"database\")가 없다. 운영 DB를 빼지 않는다"
    else
      /usr/bin/grep -q '^module "database"' "$aws_main" 2>/dev/null \
        && fail "$aws_main: database_scope를 생략해 모든 환경이 온프레미스 DB인데 RDS(module \"database\")가 남아 있다 (NO_RDS=true로 렌더하거나, 운영 데이터가 있으면 database_scope를 좁힌다)"
    fi
    linked="$(awk '/^db_link[[:space:]]*=/ { on = 1; next } on && /^}/ { exit }
      on && match($0, /^[[:space:]]*[a-z][a-z0-9-]*[[:space:]]*=[[:space:]]*\{/) { k = $0; sub(/^[[:space:]]*/, "", k); sub(/[[:space:]]*=.*/, "", k); print k }' \
      "$aws_vars" 2>/dev/null | sort | tr '\n' ' ')"
    [ "${linked% }" = "$scope" ] \
      || fail "$aws_vars: db_link 환경(${linked% })이 plan.yaml database_scope($scope)와 다르다"
  fi
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
  # Major migrations may pin existing cloud roots while upgrading the onprem contract.
  # Pins are explicit in the protected config, never inferred from whichever code happens to exist.
  for scope in aws gcp onprem; do
    expected="$version"
    if /usr/bin/grep -q '^infra_versions:' "$cfg"; then
      if ! command -v yq >/dev/null; then fail "infra_versions 검사에는 yq가 필요하다"; break; fi
      expected="$(yq -r ".infra_versions.$scope // .template_version" "$cfg")"
      [[ "$expected" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "infra_versions.$scope: vX.Y.Z 형식이 아니다"
    fi
    # v2 app extensions follow template_version; cloud migration pins only apply to
    # the existing infrastructure. They do not exist in the pinned v1 release.
    refs="$(/usr/bin/grep -rn --include='*.tf' --exclude-dir=.terraform "one-tatchi-platform.git//[^?]*?ref=$semver" "infra/envs/$scope" 2>/dev/null || true)"
    bad="$(printf '%s\n' "$refs" | /usr/bin/grep -Ev '//modules/(preview_auth/aws|db_link/tailscale)\?ref=' | /usr/bin/grep -v "?ref=$expected\"" || true)"
    [ -z "$bad" ] || fail "$scope 모듈 ?ref= 버전이 $expected 과 다르다:"$'\n'"$bad"
    bad="$(printf '%s\n' "$refs" | /usr/bin/grep -E '//modules/(preview_auth/aws|db_link/tailscale)\?ref=' | /usr/bin/grep -v "?ref=$version\"" || true)"
    [ -z "$bad" ] || fail "$scope 앱 확장 모듈 버전이 $version 과 다르다:"$'\n'"$bad"
  done
fi

# 3b. 템플릿 버전보다 새 입력을 쓰지 않는지 (호출부 입력이 없으면 워크플로가 startup_failure로 시작도 못 한다)
if [ -n "$version" ] && [ -f .github/workflows/deploy.yml ]; then
  minor="$(echo "$version" | cut -d. -f2)"; major="$(echo "${version#v}" | cut -d. -f1)"
  if /usr/bin/grep -Eq '^[[:space:]]*(yolo-auto-merge:|promote-mode: branch)' .github/workflows/deploy.yml && [ "$major" -eq 1 ] && [ "$minor" -lt 14 ]; then
    fail "deploy.yml: yolo-auto-merge · branch 모드는 템플릿 v1.14.0부터다 (지금 $version)"
  fi
  if /usr/bin/grep -q '^\s*promote-mode:' .github/workflows/deploy.yml && [ "$major" -eq 1 ] && [ "$minor" -lt 9 ]; then
    fail "deploy.yml: promote-mode 입력은 템플릿 v1.9.0부터다 (지금 $version). 줄을 지우거나 버전을 올린다"
  fi
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
    jq -e 'all(.[][]; (.expect_body // {}) | type == "object")' .deploy/smoke.json >/dev/null 2>&1 \
      || fail ".deploy/smoke.json: expect_body 는 JSON 객체여야 한다 (예: {\"database\": \"connected\"})"
  else skip "jq가 없어 smoke.json 형식"; fi
fi

# 6. 서비스별 Dockerfile · 값 파일 (plan.yaml의 services)
if [ -f "$plan" ] && command -v yq >/dev/null; then
  while IFS=$'\t' read -r name path; do
    [ -n "$name" ] || continue
    [ -f "$path/Dockerfile" ] || fail "$name: $path/Dockerfile 이 없다"
    [ -s "$path/.dockerignore" ] || fail "$name: $path/.dockerignore 가 없거나 비어 있다"
    short="${name##*-}"   # demo-app-be → be
    [ -f "deploy/values-$short.yaml" ] || [ -f "deploy/values-$name.yaml" ] || fail "$name: deploy/values-$short.yaml 이 없다"
    if [ -f "$path/Dockerfile" ]; then
      /usr/bin/grep -Eq '^USER[[:space:]]+[0-9]+' "$path/Dockerfile" || fail "$name: Dockerfile에 숫자 UID의 USER 가 없다 (App Chart runAsNonRoot)"
    fi
    # DB Secret을 받는 서비스는 TLS 설정이 있어야 한다. 클라우드 DB는 TLS 없는 접속을 거부해 앱이 메모리 폴백 등으로 조용히 넘어간다 (T28).
    values="deploy/values-$short.yaml"; [ -f "$values" ] || values="deploy/values-$name.yaml"
    if [ -f "$values" ] && yq -r '(.envFromSecrets // [])[]' "$values" 2>/dev/null | /usr/bin/grep -q -- '-db$'; then
      sslmode="$(yq -r '.env.PGSSL // .env.PGSSLMODE // ""' "$values" 2>/dev/null)"
      case "$sslmode" in
        ""|null) fail "$name: $values 가 DB Secret을 받는데 env.PGSSL 이 없다 (클라우드 DB는 TLS 필수, 예: PGSSL: require)" ;;
        disable|false|0) fail "$name: $values 의 env.PGSSL=$sslmode 는 TLS를 끈다 (클라우드 DB는 접속을 거부한다)" ;;
      esac
    fi
    # 장애 주입 · 디버그 플래그(CHAOS_* · DEBUG · *_DEBUG · FAULT_*)는 test 덧붙임 파일(values-<svc>.test.yaml)에만 둔다 (T35).
    # 기본 파일 · 대상별 파일 · prod 덧붙임 파일에 있으면 prod에도 열린다.
    for vf in "$values" deploy/*/values.yaml "${values%.yaml}.prod.yaml"; do
      [ -f "$vf" ] || continue
      bad="$(yq -r '(.env // {}) | keys[]' "$vf" 2>/dev/null | /usr/bin/grep -E '^(CHAOS_|FAULT_|DEBUG$|.*_DEBUG$)' || true)"
      [ -z "$bad" ] || fail "$name: $vf 에 장애 주입 · 디버그 플래그가 있다 ($(echo "$bad" | tr '\n' ' ')). ${values%.yaml}.test.yaml 에만 둔다"
    done
  done < <(yq -r '.services[]? | [.name, .path] | @tsv' "$plan" 2>/dev/null)
else
  skip "yq가 없거나 plan.yaml이 없어 서비스별 Dockerfile 검사"
fi

# 7. terraform fmt
if [ -d infra ]; then
  if command -v terraform >/dev/null; then
    out="$(terraform fmt -check -recursive infra 2>&1)" || fail "terraform fmt:"$'\n'"$out"
  else skip "terraform이 없어 fmt 검사"; fi
fi

if [ "$problems" -eq 0 ]; then echo "✓ 산출물 검사 통과"; exit 0; fi
echo "문제 $problems 건"; exit 1
