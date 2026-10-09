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

echo "통과"
