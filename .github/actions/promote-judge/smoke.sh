#!/usr/bin/env bash
# green(<release>-preview)에 관찰 창 동안 smoke 요청을 보내고 요청마다 결과를 한 줄씩 남긴다.
# 결과: $WORK_DIR/smoke-results.jsonl
#   {"pass":1,"method":"GET","path":"/health","expect":200,"status":200,"ms":12,"ok":true}
# macOS runner의 기본 bash(3.2)에서도 돌도록 bash 4 문법은 쓰지 않는다.
#
# 환경변수
#   WORK_DIR, RELEASE, NAMESPACE, SMOKE_FILE, WINDOW_SECONDS, REQUEST_TIMEOUT_SECONDS
#   BASE_URL  (선택) 주면 port-forward 없이 이 주소로 요청한다 (테스트용)
#   KUBECTL   (선택) kubectl 대신 쓸 명령 (테스트용)
set -euo pipefail

: "${WORK_DIR:?}" "${RELEASE:?}"
NAMESPACE="${NAMESPACE:-}"
SMOKE_FILE="${SMOKE_FILE:-.deploy/smoke.json}"
WINDOW_SECONDS="${WINDOW_SECONDS:-30}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-5}"
KUBECTL="${KUBECTL:-kubectl}"

mkdir -p "$WORK_DIR"
out="$WORK_DIR/smoke-results.jsonl"
requests="$WORK_DIR/smoke-requests.jsonl"
: > "$out"

# ---------- 요청 목록 ----------
# .deploy/smoke.json: { "<release>": [ {"method":"GET","path":"/health","expect":200,"body":{...}} ] }
# 파일이나 이 서비스 항목이 없으면 GET /health → 200 하나로 확인한다.
default='[{"method":"GET","path":"/health","expect":200}]'
if [ -f "$SMOKE_FILE" ]; then
  if ! list="$(jq -ce --arg r "$RELEASE" '.[$r] // empty' "$SMOKE_FILE" 2>/dev/null)"; then
    if jq -e . "$SMOKE_FILE" >/dev/null 2>&1; then
      echo "$SMOKE_FILE에 $RELEASE 항목이 없어 기본 요청(GET /health)을 쓴다"
      list="$default"
    else
      echo "::error::$SMOKE_FILE이 올바른 JSON이 아니다"
      exit 1
    fi
  fi
else
  echo "$SMOKE_FILE이 없어 기본 요청(GET /health)을 쓴다"
  list="$default"
fi
jq -c '.[] | {method: ((.method // "GET") | ascii_upcase), path, expect: (.expect // 200), body}' <<<"$list" > "$requests"
if [ ! -s "$requests" ]; then
  echo "::error::smoke 요청 목록이 비어 있다"
  exit 1
fi

# ---------- green 접속 (ADR 0003) ----------
pf_pid=""
cleanup() { [ -n "$pf_pid" ] && kill "$pf_pid" 2>/dev/null || true; }
trap cleanup EXIT

if [ -z "${BASE_URL:-}" ]; then
  : "${NAMESPACE:?}"
  svc="$RELEASE-preview"
  svc_port="$($KUBECTL get svc "$svc" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}')"
  pf_log="$WORK_DIR/port-forward.log"
  # 로컬 포트는 비어 있는 것을 kubectl이 고른다. 고른 포트는 로그의 "Forwarding from 127.0.0.1:<포트>"에서 읽는다.
  $KUBECTL port-forward --address 127.0.0.1 "svc/$svc" -n "$NAMESPACE" ":$svc_port" > "$pf_log" 2>&1 &
  pf_pid=$!
  local_port=""
  for _ in $(seq 1 50); do
    local_port="$(sed -n 's/^Forwarding from 127\.0\.0\.1:\([0-9]*\) .*/\1/p' "$pf_log" | head -1)"
    [ -n "$local_port" ] && break
    kill -0 "$pf_pid" 2>/dev/null || break
    sleep 0.2
  done
  if [ -z "$local_port" ]; then
    echo "::error::port-forward를 열지 못했다 (svc/$svc)"
    cat "$pf_log"
    exit 1
  fi
  BASE_URL="http://127.0.0.1:$local_port"
  echo "green: svc/$svc:$svc_port → $BASE_URL"
fi

# ---------- 관찰 창 ----------
# 첫 바퀴는 목록 전체, 이후에는 GET만 반복한다 (POST 같은 쓰기 요청을 반복하지 않는다).
request() {
  local method="$1" path="$2" body="$3" result rc=0
  local args=(-sS -A one-tatchi-smoke -o /dev/null -w '%{http_code} %{time_total}' --max-time "$REQUEST_TIMEOUT_SECONDS" -X "$method")
  if [ "$body" != null ]; then args+=(-H 'Content-Type: application/json' --data "$body"); fi
  result="$(curl "${args[@]}" "$BASE_URL$path" 2>/dev/null)" || rc=$?
  # 연결 실패 · 시간 초과면 상태 코드는 000
  [ -n "$result" ] || result="000 $REQUEST_TIMEOUT_SECONDS"
  [ "$rc" -eq 0 ] || result="000 ${result#* }"
  echo "$result"
}

end=$((SECONDS + WINDOW_SECONDS))
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
jq -n --arg started_at "$started_at" --argjson configured_seconds "$WINDOW_SECONDS" \
  '{started_at:$started_at,ended_at:null,configured_seconds:$configured_seconds}' > "$WORK_DIR/observation.json"
pass=0
while :; do
  pass=$((pass + 1))
  while IFS= read -r item; do
    method="$(jq -r .method <<<"$item")"
    [ "$pass" -gt 1 ] && [ "$method" != GET ] && continue
    path="$(jq -r .path <<<"$item")"
    expect="$(jq -r .expect <<<"$item")"
    body="$(jq -c .body <<<"$item")"
    read -r status secs <<<"$(request "$method" "$path" "$body")"
    jq -nc --argjson pass "$pass" --arg method "$method" --arg path "$path" \
      --argjson expect "$expect" --argjson status "$((10#$status))" --arg secs "$secs" '
      {pass: $pass, method: $method, path: $path, expect: $expect, status: $status,
       ms: (($secs | tonumber) * 1000 | round), ok: ($status == $expect)}' >> "$out"
  done < "$requests"
  [ "$SECONDS" -lt "$end" ] || break
  sleep 0.2
done

jq -n --arg started_at "$started_at" --arg ended_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --argjson configured_seconds "$WINDOW_SECONDS" \
  '{started_at:$started_at,ended_at:$ended_at,configured_seconds:$configured_seconds}' > "$WORK_DIR/observation.json"
total="$(wc -l < "$out" | tr -d ' ')"
failed="$(jq -s '[.[] | select(.ok | not)] | length' "$out")"
echo "smoke: $pass바퀴, 요청 $total건, 실패 $failed건 ($WINDOW_SECONDS초)"
