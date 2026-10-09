#!/usr/bin/env bash
# promote-judge 테스트:  bash .github/actions/promote-judge/tests/run.sh
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
action="$(dirname "$here")"
tmp="$(mktemp -d)"
server_pid=""
trap '[ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null; rm -rf "$tmp"' EXIT

fail() { echo "실패: $*" >&2; exit 1; }

# 가짜 green을 띄우고 BASE_URL을 돌려준다
start_server() {
  [ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null
  python3 "$here/fake_server.py" "$1" > "$tmp/server.log" &
  server_pid=$!
  for _ in $(seq 1 50); do
    port="$(sed -n 's/.*127\.0\.0\.1:\([0-9]*\) .*/\1/p' "$tmp/server.log")"
    [ -n "$port" ] && { BASE_URL="http://127.0.0.1:$port"; return; }
    sleep 0.1
  done
  fail "가짜 서버가 뜨지 않았다"
}

# smoke.sh 실행. 결과는 $tmp/<이름>/smoke-results.jsonl
smoke() {
  local name="$1"; shift
  env WORK_DIR="$tmp/$name" RELEASE=demo-app-be NAMESPACE=test WINDOW_SECONDS=1 \
    REQUEST_TIMEOUT_SECONDS=1 SMOKE_FILE="$tmp/smoke.json" "$@" \
    bash "$action/smoke.sh" > "$tmp/$name.log" 2>&1 || { cat "$tmp/$name.log" >&2; return 1; }
}
count() { jq -s "[.[] | select($2)] | length" "$tmp/$1/smoke-results.jsonl"; }

cat > "$tmp/smoke.json" <<'JSON'
{
  "demo-app-be": [
    {"method": "GET", "path": "/health", "expect": 200},
    {"method": "GET", "path": "/api/info", "expect": 200},
    {"method": "post", "path": "/api/guestbook", "expect": 201, "body": {"name": "smoke", "message": "hi"}}
  ]
}
JSON

echo "== 정상 green: 실패 0건, POST는 첫 바퀴에 한 번만"
start_server ok
smoke ok BASE_URL="$BASE_URL" WINDOW_SECONDS=2   # SECONDS가 1초 단위라 반복 확인은 2초 이상
[ "$(count ok '.ok | not')" = 0 ] || fail "정상 서버인데 실패가 있다"
[ "$(count ok '.method == "POST"')" = 1 ] || fail "POST가 한 번이 아니다"
[ "$(count ok '.path == "/health"')" -ge 2 ] || fail "관찰 창 동안 반복하지 않았다"

echo "== 500 green: /api/info 실패가 기록됨"
start_server fail
smoke fail BASE_URL="$BASE_URL"
[ "$(count fail '.path == "/api/info" and .status == 500 and (.ok | not)')" -ge 1 ] || fail "500이 기록되지 않았다"
[ "$(count fail '.path == "/health" and (.ok | not)')" = 0 ] || fail "/health는 정상이어야 한다"

echo "== 느린 green: 제한 시간을 넘으면 상태 000, 실패"
start_server slow
smoke slow BASE_URL="$BASE_URL"
[ "$(count slow '.status == 0 and (.ok | not)')" -ge 1 ] || fail "시간 초과가 실패로 기록되지 않았다"

echo "== smoke 파일이 없으면 GET /health만"
start_server ok
smoke nofile BASE_URL="$BASE_URL" SMOKE_FILE="$tmp/없음.json"
[ "$(count nofile '.path != "/health"')" = 0 ] || fail "기본 요청 말고 다른 요청이 있다"
[ "$(count nofile 'true')" -ge 1 ] || fail "요청이 없다"

echo "== 서비스 항목이 없으면 GET /health만"
smoke noentry BASE_URL="$BASE_URL" RELEASE=demo-app-fe
[ "$(count noentry '.path != "/health"')" = 0 ] || fail "기본 요청 말고 다른 요청이 있다"

echo "== 잘못된 JSON이면 실패로 끝남"
echo '{ 깨짐' > "$tmp/broken.json"
if smoke broken BASE_URL="$BASE_URL" SMOKE_FILE="$tmp/broken.json" 2>/dev/null; then
  fail "잘못된 JSON을 받아들였다"
fi

echo "== port-forward 경로: 가짜 kubectl로 포트를 읽어 접속"
kill "$server_pid" 2>/dev/null; server_pid=""
smoke pf KUBECTL="$here/fake-kubectl" FAKE_MODE=ok
[ "$(count pf 'true')" -ge 3 ] || fail "port-forward로 요청하지 못했다"
[ "$(count pf '.ok | not')" = 0 ] || fail "port-forward 경로에서 실패가 있다"

# ---------- metrics.sh ----------
# metrics <이름> [환경변수...]: $tmp/m-<이름>/smoke-results.jsonl을 미리 두고 실행한다
metrics() {
  local name="$1"; shift
  env WORK_DIR="$tmp/m-$name" RELEASE=demo-app-be NAMESPACE=test MAX_ERROR_RATE=0 MAX_P95_MS=2000 MAX_RESTARTS=0 \
    KUBECTL="$here/fake-kubectl" "$@" bash "$action/metrics.sh" > "$tmp/m-$name.log" 2>&1 \
    || { cat "$tmp/m-$name.log" >&2; return 1; }
}
m() { jq -r "$2" "$tmp/m-$1/metrics.json"; }
# results <이름> <ok 개수> <500 개수>: 응답 시간 1..n ms인 smoke 결과를 만든다
results() {
  mkdir -p "$tmp/m-$1"
  jq -nc --argjson ok "$2" --argjson bad "$3" '
    range(1; $ok + $bad + 1) as $i
    | if $i <= $ok then {pass: 1, method: "GET", path: "/health", expect: 200, status: 200, ms: $i, ok: true}
      else {pass: 1, method: "GET", path: "/api/info", expect: 200, status: 500, ms: $i, ok: false} end
  ' > "$tmp/m-$1/smoke-results.jsonl"
}
pods_json() {  # pods_json <파일> <restartCount> <Ready: True|False>
  jq -n --argjson r "$2" --arg ready "$3" '{items: [
    {status: {conditions: [{type: "Ready", status: "True"}], containerStatuses: [{restartCount: 0}]}},
    {status: {conditions: [{type: "Ready", status: $ready}], containerStatuses: [{restartCount: $r}]}}]}' > "$1"
}

echo "== metrics 정상: pass, p95는 nearest-rank (1..20ms → 19ms)"
results ok 20 0
metrics ok
[ "$(m ok .rule.verdict)" = pass ] || fail "정상인데 pass가 아니다: $(m ok .rule.reasons)"
[ "$(m ok .p95_ms)" = 19 ] || fail "p95 계산이 틀렸다: $(m ok .p95_ms)"
[ "$(m ok .error_rate)" = 0 ] || fail "에러율이 0이 아니다"
[ "$(m ok .pods.count)" = 2 ] || fail "green 파드 수가 틀렸다"

echo "== metrics 500 섞임: 에러율 fail, 실패 묶음"
results bad 18 2
metrics bad
[ "$(m bad .rule.verdict)" = fail ] || fail "500이 있는데 fail이 아니다"
[ "$(m bad .error_rate)" = 10 ] || fail "에러율이 10%가 아니다: $(m bad .error_rate)"
[ "$(m bad '.failures[0] | "\(.path) \(.status) \(.count)"')" = "/api/info 500 2" ] || fail "실패 묶음이 틀렸다"
m bad '.rule.reasons[]' | grep -q '에러율 10%' || fail "이유에 에러율이 없다"

echo "== metrics 재시작 · Ready 아님: fail"
results restart 20 0
pods_json "$tmp/pods-restart.json" 2 True
metrics restart FAKE_PODS_FILE="$tmp/pods-restart.json"
m restart '.rule.reasons[]' | grep -q '재시작 2회' || fail "재시작이 이유에 없다"
pods_json "$tmp/pods-notready.json" 0 False
results notready 20 0
metrics notready FAKE_PODS_FILE="$tmp/pods-notready.json"
m notready '.rule.reasons[]' | grep -q 'Ready가 아닌 green 파드 1개' || fail "Ready 아님이 이유에 없다"

echo "== metrics p95 초과: fail, 기준을 비우면 검사 안 함"
results slow 20 0
metrics slow MAX_P95_MS=10
m slow '.rule.reasons[]' | grep -q 'p95 19ms > 기준 10ms' || fail "p95 초과가 이유에 없다"
metrics slow MAX_P95_MS=
[ "$(m slow .rule.verdict)" = pass ] || fail "p95 기준을 비웠는데 fail이다"

echo "== metrics 근거 부족: smoke 결과 없음 · Rollout 조회 실패 → fail"
mkdir -p "$tmp/m-empty"
metrics empty
m empty '.rule.reasons[]' | grep -q 'smoke 결과가 없다' || fail "결과 없음이 이유에 없다"
results norollout 20 0
metrics norollout FAKE_NO_ROLLOUT=1
m norollout '.rule.reasons[]' | grep -q 'green 파드 정보를 읽지 못했다' || fail "파드 조회 실패가 이유에 없다"

echo "== metrics 잘못된 기준값: 파일은 남고 fail"
results badinput 20 0
metrics badinput MAX_ERROR_RATE=abc
[ "$(m badinput .rule.verdict)" = fail ] || fail "잘못된 기준값인데 fail이 아니다"

# ---------- judge.sh ----------
claude_pid=""
start_claude() {  # start_claude <모드> → CLAUDE_URL
  [ -n "$claude_pid" ] && kill "$claude_pid" 2>/dev/null
  python3 "$here/fake_claude.py" "$1" "$tmp/claude-capture.json" > "$tmp/claude.log" &
  claude_pid=$!
  for _ in $(seq 1 50); do
    port="$(sed -n 's/^listening 127\.0\.0\.1:\([0-9]*\)$/\1/p' "$tmp/claude.log")"
    [ -n "$port" ] && { CLAUDE_URL="http://127.0.0.1:$port"; return; }
    sleep 0.1
  done
  fail "가짜 Claude가 뜨지 않았다"
}
trap '[ -n "$server_pid" ] && kill "$server_pid" 2>/dev/null; [ -n "$claude_pid" ] && kill "$claude_pid" 2>/dev/null; rm -rf "$tmp"' EXIT

# judge <이름> <metrics 이름(m-*)> [환경변수...]
judge() {
  local name="$1" from="$2"; shift 2
  mkdir -p "$tmp/j-$name"
  cp "$tmp/m-$from/metrics.json" "$tmp/j-$name/metrics.json"
  : > "$tmp/j-$name/github_output"
  env WORK_DIR="$tmp/j-$name" RELEASE=demo-app-be MODEL=claude-sonnet-5-5 ANTHROPIC_API_KEY=test-key \
    ANTHROPIC_BASE_URL="$CLAUDE_URL" API_TIMEOUT_SECONDS=2 GITHUB_OUTPUT="$tmp/j-$name/github_output" "$@" \
    bash "$action/judge.sh" > "$tmp/j-$name.log" 2>&1 || { cat "$tmp/j-$name.log" >&2; return 1; }
}
j() { jq -r "$2" "$tmp/j-$1/judgment.json"; }

echo "== judge 규칙 pass + AI promote → promote (source ai), 요청 형식 확인"
start_claude promote
judge promote ok
[ "$(j promote '.decision + " " + .source')" = "promote ai" ] || fail "promote가 아니다: $(j promote .)"
cap="$tmp/claude-capture.json"
[ "$(jq -r '.path + " " + .api_key + " " + .version' "$cap")" = "/v1/messages test-key 2023-06-01" ] || fail "요청 헤더가 틀렸다"
[ "$(jq -r '.body.model' "$cap")" = claude-sonnet-5-5 ] || fail "모델이 전달되지 않았다"
[ "$(jq -r '.body.output_config.format.schema.properties.decision.enum | join(",")' "$cap")" = "promote,abort" ] || fail "구조화 출력 스키마가 없다"
jq -e '.body.messages[0].content | fromjson | .rule.verdict == "pass"' "$cap" >/dev/null || fail "metrics.json이 전달되지 않았다"
grep -q '^decision=promote$' "$tmp/j-promote/github_output" || fail "step 출력 decision이 없다"
grep -q '^report=' "$tmp/j-promote/github_output" || fail "step 출력 report가 없다"

echo "== judge 규칙 pass + AI abort → abort (source ai)"
start_claude abort
judge aiabort ok
[ "$(j aiabort '.decision + " " + .source')" = "abort ai" ] || fail "AI abort를 따르지 않았다"

echo "== judge 규칙 fail + AI promote → abort (규칙 거부권), 근거는 AI 문장"
start_claude promote
judge veto bad
[ "$(j veto '.decision + " " + .source')" = "abort rule" ] || fail "규칙 거부권이 동작하지 않았다: $(j veto .)"
[ "$(j veto .reason)" = "가짜 판단: promote" ] || fail "AI 근거가 남지 않았다"

for mode in err500 slow badjson refusal; do
  echo "== judge AI 실패($mode) → abort (source fallback)"
  start_claude "$mode"
  judge "$mode" ok
  [ "$(j "$mode" '.decision + " " + .source')" = "abort fallback" ] || fail "$mode인데 abort fallback이 아니다: $(j "$mode" .)"
  [ "$(j "$mode" '.ai.error')" != null ] || fail "$mode 원인이 남지 않았다"
done

echo "== judge API 키 없음 → 호출하지 않고 abort"
rm -f "$tmp/claude-capture.json"
judge nokey ok ANTHROPIC_API_KEY=
[ "$(j nokey '.decision + " " + .ai.error')" = "abort API 키 없음" ] || fail "키 없음 처리가 틀렸다"
[ ! -f "$tmp/claude-capture.json" ] || fail "키가 없는데 API를 호출했다"

echo "== judge 규칙 fail + API 키 없음 → abort, 근거는 규칙 문장"
judge nokeyfail bad ANTHROPIC_API_KEY=
[ "$(j nokeyfail .source)" = rule ] || fail "source가 rule이 아니다"
j nokeyfail .reason | grep -q '^규칙 판정 fail: 에러율' || fail "규칙 문장이 근거로 남지 않았다"

echo "== judge metrics.json이 없으면 abort"
mkdir -p "$tmp/m-missing"
echo '깨진 파일' > "$tmp/m-missing/metrics.json"
judge missing missing ANTHROPIC_API_KEY=
[ "$(j missing .decision)" = abort ] || fail "지표가 없는데 abort가 아니다"

# ---------- act.sh ----------
# act <이름> <judgment 이름(j-*)> <모드> [환경변수...] → $tmp/a-<이름>/{calls,summary,github_output}, 종료 코드는 $act_status
act() {
  local name="$1" from="$2" mode="$3"; shift 3
  mkdir -p "$tmp/a-$name"
  [ "$from" = none ] || cp "$tmp/j-$from/judgment.json" "$tmp/a-$name/judgment.json"
  : > "$tmp/a-$name/calls"; : > "$tmp/a-$name/summary"; : > "$tmp/a-$name/github_output"
  act_status=0
  env WORK_DIR="$tmp/a-$name" RELEASE=demo-app-be NAMESPACE=test TARGET=onprem ENVIRONMENT=test MODE="$mode" \
    PROMOTE_WAIT_SECONDS=5 KUBECTL="$here/fake-kubectl" FAKE_CALLS_FILE="$tmp/a-$name/calls" \
    GITHUB_STEP_SUMMARY="$tmp/a-$name/summary" GITHUB_OUTPUT="$tmp/a-$name/github_output" "$@" \
    bash "$action/act.sh" > "$tmp/a-$name.log" 2>&1 || act_status=$?
}
calls() { cat "$tmp/a-$1/calls"; }

echo "== act auto + promote → promote, Healthy 확인, 성공"
act autopromote promote auto
[ "$act_status" = 0 ] || fail "auto promote가 실패로 끝났다: $(cat "$tmp/a-autopromote.log")"
[ "$(calls autopromote)" = "$(printf 'promote demo-app-be -n test\nstatus demo-app-be -n test --timeout 5s')" ] || fail "promote 호출이 틀렸다: $(calls autopromote)"
grep -q '^executed=promote$' "$tmp/a-autopromote/github_output" || fail "executed 출력이 없다"
grep -q 'AI 승격 판단: promote' "$tmp/a-autopromote/summary" || fail "Job Summary가 없다"

echo "== act auto + promote, Healthy가 안 됨 → 실패"
act autopromotefail promote auto FAKE_STATUS=fail
[ "$act_status" = 1 ] || fail "Healthy가 안 됐는데 성공으로 끝났다"

echo "== act auto + abort → abort 실행, step 실패"
act autoabort veto auto
[ "$act_status" = 1 ] || fail "auto abort인데 성공으로 끝났다"
[ "$(calls autoabort)" = "abort demo-app-be -n test" ] || fail "abort 호출이 틀렸다: $(calls autoabort)"
grep -q '실패한 요청' "$tmp/a-autoabort/summary" || fail "실패한 요청 표가 없다"

echo "== act manual → 실행하지 않고 성공 (promote · abort 모두)"
act manualpromote promote manual
act_promote=$act_status
act manualabort veto manual
[ "$act_promote $act_status" = "0 0" ] || fail "manual인데 실패로 끝났다"
[ -z "$(calls manualpromote)$(calls manualabort)" ] || fail "manual인데 kubectl을 실행했다"
grep -q '^executed=$' "$tmp/a-manualabort/github_output" || fail "manual의 executed가 비어 있지 않다"

echo "== act 명령 실패 → executed 비움, 실패 (감사 로그에 남기지 않음)"
act actfail promote auto FAKE_ACT_FAIL=1
[ "$act_status" = 1 ] && grep -q '^executed=$' "$tmp/a-actfail/github_output" || fail "promote 명령이 실패했는데 executed가 남았다"
act abortfail veto auto FAKE_ACT_FAIL=1
[ "$act_status" = 1 ] && grep -q '^executed=$' "$tmp/a-abortfail/github_output" || fail "abort 명령이 실패했는데 executed가 남았다"
grep -q '^executed=abort$' "$tmp/a-autoabort/github_output" || fail "abort 성공인데 executed가 abort가 아니다"

echo "== act 판단 파일 없음 + auto → abort 실행, 실패"
act nojudgment none auto
[ "$act_status" = 1 ] && [ "$(calls nojudgment)" = "abort demo-app-be -n test" ] || fail "판단 파일이 없을 때 abort하지 않았다"

echo "== act 잘못된 mode → 실행하지 않고 실패"
act badmode promote yolo
[ "$act_status" = 1 ] && [ -z "$(calls badmode)" ] || fail "잘못된 mode를 받아들였다"

# ---------- 전체 흐름 (action.yml 순서) ----------
# flow <이름> <가짜 green 모드> <가짜 Claude 모드> → $tmp/f-<이름>, 마지막 단계 종료 코드는 $flow_status
flow() {
  local name="$1" green="$2" claude="$3" w="$tmp/f-$1"
  start_claude "$claude"
  mkdir -p "$w"; : > "$w/calls"
  local common=(WORK_DIR="$w" RELEASE=demo-app-be NAMESPACE=test KUBECTL="$here/fake-kubectl" FAKE_MODE="$green"
    FAKE_CALLS_FILE="$w/calls" GITHUB_OUTPUT="$w/github_output" GITHUB_STEP_SUMMARY="$w/summary")
  env "${common[@]}" SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=1 REQUEST_TIMEOUT_SECONDS=1 bash "$action/smoke.sh" > "$w/log" 2>&1
  env "${common[@]}" MAX_ERROR_RATE=0 MAX_P95_MS=2000 MAX_RESTARTS=0 bash "$action/metrics.sh" >> "$w/log" 2>&1
  env "${common[@]}" MODEL=claude-sonnet-5-5 ANTHROPIC_API_KEY=test-key ANTHROPIC_BASE_URL="$CLAUDE_URL" \
    API_TIMEOUT_SECONDS=2 bash "$action/judge.sh" >> "$w/log" 2>&1
  flow_status=0
  env "${common[@]}" TARGET=onprem ENVIRONMENT=test MODE=auto PROMOTE_WAIT_SECONDS=5 \
    bash "$action/act.sh" >> "$w/log" 2>&1 || flow_status=$?
}

echo "== 전체 흐름: 정상 green + AI promote → promote 실행"
flow normal ok promote
[ "$flow_status" = 0 ] && head -1 "$tmp/f-normal/calls" | grep -q '^promote ' || fail "정상 흐름이 promote되지 않았다: $(cat "$tmp/f-normal/log")"

echo "== 전체 흐름: 500 green + AI promote → 규칙 거부권으로 abort 실행 (완료 기준)"
flow fault fail promote
[ "$flow_status" = 1 ] && [ "$(cat "$tmp/f-fault/calls")" = "abort demo-app-be -n test" ] || fail "500 흐름이 abort되지 않았다: $(cat "$tmp/f-fault/log")"

# ---------- group.sh (서비스 묶음, ADR 0005) ----------
# grp <이름> <가짜 Claude 모드> [환경변수...] → $tmp/g-<이름>, 종료 코드는 $grp_status
grp() {
  local name="$1" claude="$2"; shift 2
  local w="$tmp/g-$name"
  start_claude "$claude"
  mkdir -p "$w"; : > "$w/calls"; : > "$w/judge_output"; : > "$w/act_output"
  local common=(WORK_ROOT="$w" RELEASES="demo-app-be demo-app-fe" NAMESPACE=test KUBECTL="$here/fake-kubectl"
    FAKE_CALLS_FILE="$w/calls" GITHUB_STEP_SUMMARY="$w/summary" "$@")
  local started=$SECONDS
  env "${common[@]}" SMOKE_FILE="$tmp/smoke.json" WINDOW_SECONDS=2 REQUEST_TIMEOUT_SECONDS=1 bash "$action/group.sh" smoke > "$w/log" 2>&1
  grp_smoke_seconds=$((SECONDS - started))
  env "${common[@]}" MAX_ERROR_RATE=0 MAX_P95_MS=2000 MAX_RESTARTS=0 bash "$action/group.sh" metrics >> "$w/log" 2>&1
  env "${common[@]}" MODEL=claude-sonnet-5-5 ANTHROPIC_API_KEY=test-key ANTHROPIC_BASE_URL="$CLAUDE_URL" \
    API_TIMEOUT_SECONDS=2 GITHUB_OUTPUT="$w/judge_output" bash "$action/group.sh" judge >> "$w/log" 2>&1
  grp_status=0
  env "${common[@]}" TARGET=onprem ENVIRONMENT=test MODE=auto PROMOTE_WAIT_SECONDS=5 GITHUB_OUTPUT="$w/act_output" \
    bash "$action/group.sh" act >> "$w/log" 2>&1 || grp_status=$?
}
g() { jq -r "$2" "$tmp/g-$1/$3"; }

echo "== group 모두 정상 → 묶음 promote, BE · FE 순서대로 promote, smoke는 동시에"
grp allok promote
[ "$(g allok .decision judgment.json)" = promote ] || fail "묶음 promote가 아니다: $(cat "$tmp/g-allok/log")"
[ "$grp_status" = 0 ] || fail "모두 정상인데 실패로 끝났다"
[ "$(grep -E '^(promote|abort) ' "$tmp/g-allok/calls")" = "$(printf 'promote demo-app-be -n test\npromote demo-app-fe -n test')" ] || fail "promote 순서 · 대상이 틀렸다: $(cat "$tmp/g-allok/calls")"
grep -q '^decision=promote$' "$tmp/g-allok/judge_output" && grep -q '^executed=promote$' "$tmp/g-allok/act_output" || fail "묶음 출력이 틀렸다"
[ "$grp_smoke_seconds" -lt 4 ] || fail "smoke가 동시에 돌지 않았다 (${grp_smoke_seconds}초, 창 2초 × 2)"
grep -q '서비스 2개 묶음' "$tmp/g-allok/summary" || fail "묶음 Job Summary가 없다"

echo "== group BE만 500 + AI promote → 묶음 abort, FE도 함께 abort (source group)"
grp onefail promote FAKE_FAIL_RELEASE=demo-app-be
[ "$(g onefail .decision judgment.json)" = abort ] || fail "묶음 abort가 아니다"
[ "$(g onefail '.decision + " " + .source' demo-app-be/judgment.json)" = "abort rule" ] || fail "BE가 규칙으로 abort되지 않았다"
[ "$(g onefail '.decision + " " + .source + " " + .ai_decision_alone' demo-app-fe/judgment.json)" = "abort group promote" ] || fail "FE가 묶음으로 abort되지 않았다: $(cat "$tmp/g-onefail/demo-app-fe/judgment.json")"
g onefail .reason judgment.json | grep -q '^demo-app-be: ' || fail "묶음 근거에 BE 원인이 없다"
[ "$(grep -E '^(promote|abort) ' "$tmp/g-onefail/calls")" = "$(printf 'abort demo-app-be -n test\nabort demo-app-fe -n test')" ] || fail "abort 대상이 틀렸다"
[ "$grp_status" = 1 ] && grep -q '^executed=abort$' "$tmp/g-onefail/act_output" || fail "묶음 abort 결과가 틀렸다"

echo "통과"
