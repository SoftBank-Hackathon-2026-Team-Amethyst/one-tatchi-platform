#!/usr/bin/env bash
# 장애 훈련 스크립트 테스트 (가짜 kubectl · 가짜 BE 파드):  bash .github/actions/chaos-drill/tests/run.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
action="$(dirname "$here")"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fail() { echo "실패: $*" >&2; exit 1; }

# ---------- 준비 ----------
# 상태 파일: BE는 green 파드 2개(파드마다 주입을 확인), FE는 1개
set_state() {  # <이름> <phase> [preview] [stable_annotation]
  local phase="$2" preview="${3:-blue1}" ann="${4:-}"
  jq -n --arg phase "$phase" --arg preview "$preview" --arg ann "$ann" '
    def ro(prefix): {phase: $phase, message: (if $phase == "Degraded" then "ProgressDeadlineExceeded" else "" end),
      paused: ($phase == "Paused"), active: "blue1", preview: $preview, annotation: $ann, stable_annotation: $ann,
      pods: ([{name: (prefix + "-blue"), hash: "blue1"}]
             + (if $preview != "blue1" then [{name: (prefix + "-green-a"), hash: $preview}] + (if prefix == "be" then [{name: "be-green-b", hash: $preview}] else [] end) else [] end))};
    {"demo-app-be": ro("be"), "demo-app-fe": ro("fe")}' > "$tmp/state-$1.json"
}
# run <스크립트> <이름> [환경변수...] → 종료 코드는 $rc, 결과는 $tmp/w-<이름>/
run() {
  local script="$1" name="$2"; shift 2
  mkdir -p "$tmp/w-$name" "$tmp/chaos-$name"
  rc=0
  env WORK_ROOT="$tmp/w-$name" NAMESPACE=test KUBECTL="$here/fake-kubectl" FAKE_STATE_FILE="$tmp/state-$name.json" \
    FAKE_CHAOS_DIR="$tmp/chaos-$name" FAKE_CALLS_FILE="$tmp/w-$name/calls" POLL_SECONDS=0.2 REQUEST_TIMEOUT_SECONDS=2 \
    GITHUB_OUTPUT="$tmp/w-$name/output" GITHUB_STEP_SUMMARY="$tmp/w-$name/summary" "$@" \
    bash "$action/$script.sh" > "$tmp/w-$name/$script.log" 2>&1 || rc=$?
}
out() { sed -n "s/^$2=//p" "$tmp/w-$1/output" | tail -1; }
w() { jq -r "$3" "$tmp/w-$1/$2"; }
st() { jq -r "$2" "$tmp/state-$1.json"; }
chaos() { jq -r "$3" "$tmp/chaos-$1/$2.json"; }
calls() { cat "$tmp/w-$1/calls" 2>/dev/null || true; }
log() { cat "$tmp/w-$1/$2.log"; }
RELEASES="demo-app-be demo-app-fe"

cat > "$tmp/smoke.json" <<'JSON'
{"demo-app-be": [{"method": "GET", "path": "/health", "expect": 200, "expect_body": {"database": "connected"}},
                 {"method": "GET", "path": "/api/info", "expect": 200, "expect_body": {"dbConnected": true}},
                 {"method": "GET", "path": "/api/chaos", "expect": 200}],
 "demo-app-fe": [{"method": "GET", "path": "/", "expect": 200}]}
JSON

echo "== scenarios.json: 1차 시나리오 4개, 기대는 모두 abort, 장애 값은 상한 안"
for s in error-burst slow-response db-down flaky; do
  [ "$(jq -r --arg s "$s" '.scenarios[$s].expect.decision' "$action/scenarios.json")" = abort ] || fail "$s 기대가 abort가 아니다"
done
jq -e '.limits.latencyMs as $l | .limits.errorRate as $e | all(.scenarios[]; (.inject.latencyMs // 0) <= $l and (.inject.errorRate // 0) <= $e)' "$action/scenarios.json" >/dev/null || fail "장애 값이 상한을 넘는다"

# ---------- check.sh ----------
echo "== check: Paused + green → 진행 (existing), 확인한 해시를 남김"
set_state paused Paused green1
run check paused RELEASES="$RELEASES" NEW_GREEN=false
[ "$rc" = 0 ] && [ "$(out paused proceed) $(out paused mode)" = "true existing" ] || fail "Paused인데 진행하지 않았다: $(log paused check)"
[ "$(w paused demo-app-be/green.json .hash) $(w paused demo-app-fe/green.json .hash)" = "green1 green1" ] || fail "green 해시가 남지 않았다"
[ "$(w paused check.json .proceed)" = true ] || fail "check.json이 틀렸다"

echo "== check: Healthy(green 없음) → 거절, new-green 안내"
set_state healthy Healthy
run check healthy RELEASES="$RELEASES" NEW_GREEN=false
[ "$(out healthy proceed)" = false ] || fail "green이 없는데 진행했다"
grep -q 'new-green' "$tmp/w-healthy/output" || fail "거절 이유에 new-green 안내가 없다: $(log healthy check)"
[ ! -f "$tmp/w-healthy/demo-app-be/green.json" ] || fail "거절인데 green.json을 남겼다"

echo "== check: Healthy + new-green → 진행 (new), 원래 annotation 기록"
set_state newgreen Healthy blue1 old-value
run check newgreen RELEASES="$RELEASES" NEW_GREEN=true
[ "$(out newgreen proceed) $(out newgreen mode)" = "true new" ] || fail "new-green인데 진행하지 않았다: $(log newgreen check)"
[ "$(w newgreen demo-app-be/green.json '.hash // "null"')" = null ] || fail "new인데 해시가 있다"
[ "$(w newgreen demo-app-be/green.json .original_annotation)" = old-value ] || fail "원래 annotation을 기록하지 않았다"

echo "== check: Progressing · Degraded · 읽기 실패 · 서비스 상태 불일치 → 거절"
set_state progressing Progressing green1
run check progressing RELEASES="$RELEASES" NEW_GREEN=true
[ "$(out progressing proceed)" = false ] && grep -q '배포 진행 중' "$tmp/w-progressing/output" || fail "Progressing을 거절하지 않았다"
set_state degraded Degraded green1
run check degraded RELEASES="$RELEASES" NEW_GREEN=true
[ "$(out degraded proceed)" = false ] && grep -q 'Degraded' "$tmp/w-degraded/output" || fail "Degraded를 거절하지 않았다"
set_state norollout Paused green1
run check norollout RELEASES="$RELEASES" NEW_GREEN=false FAKE_NO_ROLLOUT=demo-app-fe
[ "$(out norollout proceed)" = false ] && grep -q 'demo-app-fe: Rollout을 읽지 못했다' "$tmp/w-norollout/output" || fail "읽기 실패를 거절하지 않았다: $(log norollout check)"
set_state mixed Paused green1
jq '.["demo-app-fe"] |= (.phase = "Healthy" | .paused = false | .preview = "blue1")' "$tmp/state-mixed.json" > "$tmp/m.json" && mv "$tmp/m.json" "$tmp/state-mixed.json"
run check mixed RELEASES="$RELEASES" NEW_GREEN=true
[ "$(out mixed proceed)" = false ] && grep -q '서로 달라요' "$tmp/w-mixed/output" || fail "상태 불일치를 거절하지 않았다: $(log mixed check)"

# ---------- prepare.sh ----------
echo "== prepare: annotation 패치 → Paused 대기 → 해시 기록"
run prepare newgreen RELEASES="$RELEASES" DRILL_ID=run1 WAIT_SECONDS=5
[ "$rc" = 0 ] || fail "prepare가 실패했다: $(log newgreen prepare)"
grep -q '^patch demo-app-be .*"one-tatchi/drill":"run1"' "$tmp/w-newgreen/calls" || fail "annotation 패치가 없다: $(calls newgreen)"
[ "$(w newgreen demo-app-be/green.json .hash) $(w newgreen demo-app-fe/green.json .hash)" = "drill-run1 drill-run1" ] || fail "훈련용 green 해시가 남지 않았다"
[ "$(st newgreen '.["demo-app-be"].phase')" = Paused ] || fail "가짜 Rollout이 Paused가 아니다"

echo "== prepare: green이 뜨지 않으면 실패"
set_state stuck Healthy
run check stuck RELEASES="$RELEASES" NEW_GREEN=true
run prepare stuck RELEASES="$RELEASES" DRILL_ID=run2 WAIT_SECONDS=1 FAKE_PATCH_STUCK=1
[ "$rc" = 1 ] && grep -q 'Paused가 되지 않았다' "$tmp/w-stuck/prepare.log" || fail "green이 안 떴는데 성공했다"

# ---------- inject.sh ----------
echo "== inject: green 파드마다 POST /api/chaos, FE는 건드리지 않음"
run inject paused RELEASES=demo-app-be SCENARIO=error-burst
[ "$rc" = 0 ] || fail "inject가 실패했다: $(log paused inject)"
[ "$(w paused demo-app-be/inject.json '.injected, (.pods | length)' | tr '\n' ' ')" = "true 2 " ] || fail "inject.json이 틀렸다: $(cat "$tmp/w-paused/demo-app-be/inject.json")"
[ "$(chaos paused be-green-a .errorRate) $(chaos paused be-green-b .errorRate)" = "1 1" ] || fail "파드마다 주입되지 않았다"
[ ! -f "$tmp/chaos-paused/be-blue.json" ] && [ ! -f "$tmp/chaos-paused/fe-green-a.json" ] || fail "blue 또는 FE에 주입했다"
grep -q '주입 완료' "$tmp/w-paused/inject.log" || fail "주입 로그가 없다"

echo "== inject: 시나리오별 본문 (slow-response → latencyMs, db-down → dbError)"
set_state slow Paused green1; cp -r "$tmp/w-paused/demo-app-be" "$tmp/w-slow-src"; mkdir -p "$tmp/w-slow"; cp -r "$tmp/w-slow-src" "$tmp/w-slow/demo-app-be"
run inject slow RELEASES=demo-app-be SCENARIO=slow-response
[ "$rc" = 0 ] && [ "$(chaos slow be-green-a .latencyMs)" = 3000 ] || fail "latencyMs가 주입되지 않았다: $(log slow inject)"
set_state dbdown Paused green1; mkdir -p "$tmp/w-dbdown"; cp -r "$tmp/w-slow-src" "$tmp/w-dbdown/demo-app-be"
run inject dbdown RELEASES=demo-app-be SCENARIO=db-down
[ "$rc" = 0 ] && [ "$(chaos dbdown be-green-b .dbError)" = true ] || fail "dbError가 주입되지 않았다"

echo "== inject: green이 바뀌었으면 아무것도 하지 않고 실패"
set_state changed Paused green2; mkdir -p "$tmp/w-changed"; cp -r "$tmp/w-slow-src" "$tmp/w-changed/demo-app-be"
run inject changed RELEASES=demo-app-be SCENARIO=error-burst
[ "$rc" = 1 ] && grep -q 'green이 바뀌었다 (확인 green1 → 지금 green2)' "$tmp/w-changed/inject.log" || fail "해시 변경을 잡지 못했다: $(log changed inject)"
[ -z "$(ls "$tmp/chaos-changed")" ] || fail "해시가 바뀌었는데 주입했다"

echo "== inject: CHAOS_ENABLED가 꺼진 파드 → 실패, 알 수 없는 시나리오 → 실패"
set_state disabled Paused green1; mkdir -p "$tmp/w-disabled"; cp -r "$tmp/w-slow-src" "$tmp/w-disabled/demo-app-be"
run inject disabled RELEASES=demo-app-be SCENARIO=error-burst FAKE_CHAOS_DISABLED=all
[ "$rc" = 1 ] && grep -q 'CHAOS_ENABLED' "$tmp/w-disabled/inject.log" && [ "$(w disabled demo-app-be/inject.json .injected)" = false ] || fail "닫힌 API를 잡지 못했다: $(log disabled inject)"
run inject disabled RELEASES=demo-app-be SCENARIO=no-such
[ "$rc" = 1 ] && grep -q '알 수 없는 시나리오' "$tmp/w-disabled/inject.log" || fail "알 수 없는 시나리오를 받아들였다"

# ---------- blue.sh ----------
echo "== blue: active Service(<release>)에 smoke, 에러율 0% → ok, blue의 chaos 상태 기록"
run blue paused RELEASES="$RELEASES" INJECT_RELEASES=demo-app-be SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=1
[ "$rc" = 0 ] && [ "$(w paused blue.json .ok)" = true ] || fail "blue 확인이 실패했다: $(log paused blue)"
grep -q 'svc/demo-app-be:80' "$tmp/w-paused/blue/demo-app-be.smoke.log" || fail "preview가 아닌 active Service에 붙어야 한다: $(cat "$tmp/w-paused/blue/demo-app-be.smoke.log")"
[ "$(w paused blue.json '.services["demo-app-be"].requests > 0 and .services["demo-app-fe"].requests > 0')" = true ] || fail "blue smoke 요청이 없다"
[ "$(w paused blue.json '.services["demo-app-be"].manual_injection')" = false ] || fail "수동 주입 표시가 틀렸다"
[ "$(w paused blue.json '.services["demo-app-fe"].chaos')" = null ] || fail "주입 대상이 아닌 FE의 chaos를 읽었다"

echo "== blue: 에러가 있으면 ok false · 실패, blue에 수동 주입이 있으면 표시"
run blue bluefail RELEASES=demo-app-be INJECT_RELEASES=demo-app-be SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=1 FAKE_INFO_FAIL=svc-demo-app-be
[ "$rc" = 1 ] && [ "$(w bluefail blue.json '.ok, (.services["demo-app-be"].error_rate > 0)' | tr '\n' ' ')" = "false true " ] || fail "blue 에러를 잡지 못했다: $(log bluefail blue)"
mkdir -p "$tmp/chaos-manual"; echo '{"latencyMs":0,"errorRate":0.5,"dbError":false}' > "$tmp/chaos-manual/svc-demo-app-be.json"
run blue manual RELEASES=demo-app-be INJECT_RELEASES=demo-app-be SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=1
[ "$(w manual blue.json '.manual_injection')" = true ] || fail "blue의 수동 주입을 표시하지 않았다"

# ---------- cleanup.sh ----------
echo "== cleanup existing: 파드마다 reset · 해제 확인, abort 없음, Rollout은 Paused 그대로"
run cleanup paused RELEASES="$RELEASES" INJECT_RELEASES=demo-app-be MODE=existing WAIT_SECONDS=2
[ "$rc" = 0 ] && [ "$(out paused released)" = true ] && [ "$(w paused cleanup.json .ok)" = true ] || fail "cleanup이 실패했다: $(log paused cleanup)"
[ "$(chaos paused be-green-a .errorRate) $(chaos paused be-green-b .errorRate)" = "0 0" ] || fail "장애가 해제되지 않았다"
[ -z "$(calls paused | grep -E '^(abort|patch)' || true)" ] || fail "대기 중 green인데 abort · patch를 했다: $(calls paused)"
[ "$(w paused cleanup.json '.rollouts["demo-app-be"].phase')" = Paused ] || fail "Rollout이 Paused가 아니다"

echo "== cleanup existing: 해제를 확인하지 못하면 released=false · 실패"
run cleanup slow RELEASES=demo-app-be INJECT_RELEASES=demo-app-be MODE=existing WAIT_SECONDS=2 FAKE_CHAOS_STUCK=be-green-a
[ "$rc" = 1 ] && [ "$(out slow released)" = false ] && grep -q 'be-green-a: 장애 해제를 확인하지 못했다' "$tmp/w-slow/cleanup.log" || fail "해제 실패를 잡지 못했다: $(log slow cleanup)"
[ "$(chaos slow be-green-b .latencyMs)" = 0 ] || fail "다른 파드는 해제돼야 한다"

echo "== cleanup existing: green이 바뀌었으면 해제 확인 실패"
run cleanup changed RELEASES=demo-app-be INJECT_RELEASES=demo-app-be MODE=existing WAIT_SECONDS=1
[ "$rc" = 1 ] && [ "$(out changed released)" = false ] && grep -q 'green이 바뀌어' "$tmp/w-changed/cleanup.log" || fail "해시 변경을 잡지 못했다: $(log changed cleanup)"

echo "== cleanup new: 해제 → abort → annotation 원래 값(old-value) 복구 → Healthy"
run inject newgreen RELEASES=demo-app-be SCENARIO=flaky
[ "$rc" = 0 ] && [ "$(chaos newgreen demo-app-be-drill-run1 .errorRate)" = 0.05 ] || fail "훈련용 green에 주입하지 못했다: $(log newgreen inject)"
: > "$tmp/w-newgreen/calls"
run cleanup newgreen RELEASES="$RELEASES" INJECT_RELEASES=demo-app-be MODE=new WAIT_SECONDS=5
[ "$rc" = 0 ] && [ "$(w newgreen cleanup.json .ok)" = true ] || fail "new 정리가 실패했다: $(log newgreen cleanup)"
[ "$(chaos newgreen demo-app-be-drill-run1 .errorRate)" = 0 ] || fail "훈련용 green의 장애가 해제되지 않았다"
expected_calls="$(printf 'abort demo-app-be -n test\npatch demo-app-be {"spec":{"template":{"metadata":{"annotations":{"one-tatchi/drill":"old-value"}}}}}\nabort demo-app-fe -n test\npatch demo-app-fe {"spec":{"template":{"metadata":{"annotations":{"one-tatchi/drill":"old-value"}}}}}')"
[ "$(calls newgreen)" = "$expected_calls" ] || fail "abort · 복구 순서가 틀렸다: $(calls newgreen)"
[ "$(st newgreen '.["demo-app-be"] | "\(.phase) \(.preview) \(.annotation)"')" = "Healthy blue1 old-value" ] || fail "Rollout이 원래 상태로 돌아오지 않았다: $(st newgreen .)"

echo "== cleanup new: annotation이 없던 Rollout은 키를 지운다(null)"
set_state newnone Healthy
run check newnone RELEASES=demo-app-be NEW_GREEN=true
run prepare newnone RELEASES=demo-app-be DRILL_ID=run3 WAIT_SECONDS=5
: > "$tmp/w-newnone/calls"
run cleanup newnone RELEASES=demo-app-be INJECT_RELEASES= MODE=new WAIT_SECONDS=5
[ "$rc" = 0 ] && grep -q '"one-tatchi/drill":null' "$tmp/w-newnone/calls" || fail "annotation을 null로 지우지 않았다: $(calls newnone)"

echo "== cleanup new: Healthy가 되지 않으면 실패"
set_state newbad Healthy
run check newbad RELEASES=demo-app-be NEW_GREEN=true
run prepare newbad RELEASES=demo-app-be DRILL_ID=run4 WAIT_SECONDS=5
run cleanup newbad RELEASES=demo-app-be INJECT_RELEASES= MODE=new WAIT_SECONDS=1 FAKE_RESTORE_PHASE=Degraded
[ "$rc" = 1 ] && grep -q '기대한 상태(Healthy)가 아니다: Degraded' "$tmp/w-newbad/cleanup.log" || fail "Healthy 실패를 잡지 못했다: $(log newbad cleanup)"

echo "== cleanup new: green을 띄우지 못했어도(해시 없음) annotation을 되돌린다"
: > "$tmp/w-stuck/calls"
run cleanup stuck RELEASES=demo-app-be INJECT_RELEASES=demo-app-be MODE=new WAIT_SECONDS=5
[ "$rc" = 0 ] && grep -q '^patch demo-app-be' "$tmp/w-stuck/calls" && grep -q '해제할 파드가 없다' "$tmp/w-stuck/cleanup.log" || fail "green 없이 정리하지 못했다: $(log stuck cleanup)"

# ---------- grade.sh ----------
# judgment <폴더> <decision> <source>: promote-judge 결과 흉내
judgment() {
  mkdir -p "$1/demo-app-be"
  jq -n --arg d "$2" --arg s "$3" '{decision: $d, reason: "가짜 근거: \($d)", services: {"demo-app-be": {decision: $d, source: $s, reason: "x"}}}' > "$1/judgment.json"
  echo '{"error_rate": 100, "p95_ms": 12, "requests": 40, "failed": 40}' > "$1/demo-app-be/metrics.json"
}
echo "== grade: 주입 · 판단(abort) · blue 0% · 정리 모두 통과 → pass"
judgment "$tmp/j-abort" abort rule
run grade paused SCENARIO=error-burst INJECT_RELEASES=demo-app-be MODE=existing JUDGMENT_DIR="$tmp/j-abort" LABEL=error-burst@aws.test
[ "$rc" = 0 ] && [ "$(out paused result)" = pass ] && [ "$(w paused result.json '.checks | all(.[]; .ok)')" = true ] || fail "통과여야 한다: $(log paused grade)"
grep -q '장애 훈련 통과' "$tmp/w-paused/summary" && grep -q ':white_check_mark: 판단: 기대 abort → 실제 abort (rule)' "$tmp/w-paused/output" || fail "요약이 틀렸다: $(cat "$tmp/w-paused/output")"
grep -q 'green(주입 쪽): demo-app-be 에러율 100%' "$tmp/w-paused/output" || fail "green 지표가 없다"
[ "$(out paused promotion-unsafe)" = false ] || fail "승격 금지 표시가 잘못 켜졌다"

echo "== grade: 판단이 promote → fail, 뚫린 가드레일 이름"
judgment "$tmp/j-promote" promote ai
run grade paused SCENARIO=error-burst INJECT_RELEASES=demo-app-be MODE=existing JUDGMENT_DIR="$tmp/j-promote"
[ "$rc" = 1 ] && [ "$(out paused result)" = fail ] || fail "promote인데 통과했다"
grep -q '가드레일 `규칙 거부권 (에러율 기준 0%)`이 막지 못했다: 기대 abort, 실제 promote' "$tmp/w-paused/output" || fail "뚫린 가드레일 설명이 없다: $(cat "$tmp/w-paused/output")"

echo "== grade: 판단 결과 없음 · blue 이상 · 정리 실패 → fail"
run grade paused SCENARIO=error-burst INJECT_RELEASES=demo-app-be MODE=existing JUDGMENT_DIR="$tmp/없음"
[ "$rc" = 1 ] && grep -q '판단 결과가 없다' "$tmp/w-paused/output" || fail "판단 없음을 잡지 못했다"
cp "$tmp/w-bluefail/blue.json" "$tmp/w-paused/blue.json.bad"; cp "$tmp/w-paused/blue.json" "$tmp/w-paused/blue.json.ok"; cp "$tmp/w-paused/blue.json.bad" "$tmp/w-paused/blue.json"
run grade paused SCENARIO=error-burst INJECT_RELEASES=demo-app-be MODE=existing JUDGMENT_DIR="$tmp/j-abort"
[ "$rc" = 1 ] && grep -q ':x: blue:' "$tmp/w-paused/output" || fail "blue 이상을 잡지 못했다"
cp "$tmp/w-paused/blue.json.ok" "$tmp/w-paused/blue.json"

echo "== grade: 대기 중 green의 해제 실패 → fail, 승격 금지 경고 (promotion-unsafe)"
mkdir -p "$tmp/w-slow/blue"; cp "$tmp/w-paused/blue.json" "$tmp/w-slow/blue.json"; cp "$tmp/w-paused/demo-app-be/inject.json" "$tmp/w-slow/demo-app-be/inject.json"
run grade slow SCENARIO=error-burst INJECT_RELEASES=demo-app-be MODE=existing JUDGMENT_DIR="$tmp/j-abort"
[ "$rc" = 1 ] && [ "$(out slow promotion-unsafe)" = true ] && grep -q '승격하지 마세요' "$tmp/w-slow/output" || fail "승격 금지 경고가 없다: $(cat "$tmp/w-slow/output")"

echo "== grade: 주입 단계가 돌지 않았으면 fail"
run grade empty SCENARIO=flaky INJECT_RELEASES=demo-app-be MODE=new JUDGMENT_DIR="$tmp/j-abort"
[ "$rc" = 1 ] && grep -q '주입 단계가 돌지 않았다' "$tmp/w-empty/output" || fail "주입 없음을 잡지 못했다"

# ---------- 전체 흐름 (chaos.yml 순서) ----------
echo "== 전체 흐름 new-green: 확인 → 준비 → 주입 → (판단 abort) → blue → 정리 → 채점 pass"
set_state flow Healthy
run check flow RELEASES="$RELEASES" NEW_GREEN=true
run prepare flow RELEASES="$RELEASES" DRILL_ID=flow1 WAIT_SECONDS=5
run inject flow RELEASES=demo-app-be SCENARIO=slow-response
[ "$rc" = 0 ] || fail "흐름 주입 실패: $(log flow inject)"
run blue flow RELEASES="$RELEASES" INJECT_RELEASES=demo-app-be SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=1
[ "$rc" = 0 ] || fail "흐름 blue 실패: $(log flow blue)"
run cleanup flow RELEASES="$RELEASES" INJECT_RELEASES=demo-app-be MODE=new WAIT_SECONDS=5
[ "$rc" = 0 ] || fail "흐름 정리 실패: $(log flow cleanup)"
run grade flow SCENARIO=slow-response INJECT_RELEASES=demo-app-be MODE=new JUDGMENT_DIR="$tmp/j-abort" LABEL=slow-response@onprem.test
[ "$rc" = 0 ] && [ "$(out flow result)" = pass ] || fail "흐름 채점 실패: $(log flow grade)"
[ "$(st flow '.["demo-app-be"] | "\(.phase) \(.preview) \(.annotation)"')" = "Healthy blue1 " ] || fail "흐름 끝에 Rollout이 원래대로가 아니다: $(st flow .)"
[ "$(st flow '.["demo-app-be"].pods | length')" = 1 ] || fail "훈련용 green 파드가 남았다"

echo "통과"
