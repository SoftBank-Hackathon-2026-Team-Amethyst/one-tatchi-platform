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

echo "통과"
