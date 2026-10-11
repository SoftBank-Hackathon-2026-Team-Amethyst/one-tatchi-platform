#!/usr/bin/env bash
# 장애 훈련 스크립트 공통 함수. 각 스크립트가 source한다.
# macOS runner의 기본 bash(3.2)에서도 돌도록 bash 4 문법은 쓰지 않는다.
#
# 환경변수
#   WORK_ROOT, NAMESPACE
#   KUBECTL                 (선택) kubectl 대신 쓸 명령 (테스트용)
#   REQUEST_TIMEOUT_SECONDS (선택) chaos API 요청 하나의 제한 시간(초), 기본 5
#   POLL_SECONDS            (선택) Rollout 상태 조회 간격(초), 기본 3

: "${WORK_ROOT:?}" "${NAMESPACE:?}"
KUBECTL="${KUBECTL:-kubectl}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-5}"
POLL_SECONDS="${POLL_SECONDS:-3}"
DRILL_ANNOTATION="one-tatchi/drill"
mkdir -p "$WORK_ROOT"

output() { [ -z "${GITHUB_OUTPUT:-}" ] || echo "$1" >> "$GITHUB_OUTPUT"; }
output_multiline() {  # <이름> <내용>
  [ -z "${GITHUB_OUTPUT:-}" ] || { echo "$1<<__${1}__"; printf '%s\n' "$2"; echo "__${1}__"; } >> "$GITHUB_OUTPUT"
}

# Rollout 상태 요약 JSON 한 줄. 읽지 못하면 1을 돌려준다.
#   {"phase","message","paused","active","preview","annotation"}
rollout_state() {  # <release>
  local json
  json="$($KUBECTL get rollout "$1" -n "$NAMESPACE" -o json 2>/dev/null)" || return 1
  jq -c --arg a "$DRILL_ANNOTATION" '{
    phase: (.status.phase // ""),
    message: (.status.message // ""),
    paused: ((.status.pauseConditions // []) | length > 0),
    active: (.status.blueGreen.activeSelector // ""),
    preview: (.status.blueGreen.previewSelector // ""),
    annotation: (.spec.template.metadata.annotations[$a] // "")
  }' <<<"$json"
}

# green 파드 목록 JSON [{name, port, ready}]. 서비스 이름 라벨과 revision 해시 라벨로 고른다 (blue는 해시가 다르다).
green_pods() {  # <release> <hash>
  $KUBECTL get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=$1,rollouts-pod-template-hash=$2" -o json 2>/dev/null \
    | jq -c '[.items[] | {name: .metadata.name,
                          port: (.spec.containers[0].ports[0].containerPort // 8000),
                          ready: any(.status.conditions[]?; .type == "Ready" and .status == "True")}]'
}

# 확인해 둔 green 해시 (check.sh · prepare.sh가 남긴 <release>/green.json). 없으면 빈 값.
green_hash() {  # <release>
  jq -r '.hash // empty' "$WORK_ROOT/$1/green.json" 2>/dev/null || true
}

# port-forward를 열고 BASE_URL을 정한다. 로컬 포트는 kubectl이 고른다 (ADR 0003: 127.0.0.1만).
PF_PID=""
start_port_forward() {  # <pod/이름 | svc/이름> <원격 포트> <로그 파일>
  local port="" log="$3"
  $KUBECTL port-forward --address 127.0.0.1 "$1" -n "$NAMESPACE" ":$2" > "$log" 2>&1 &
  PF_PID=$!
  for _ in $(seq 1 50); do
    port="$(sed -n 's/^Forwarding from 127\.0\.0\.1:\([0-9]*\) .*/\1/p' "$log" | head -1)"
    [ -n "$port" ] && break
    kill -0 "$PF_PID" 2>/dev/null || break
    sleep 0.2
  done
  if [ -z "$port" ]; then
    echo "::warning::port-forward를 열지 못했다 ($1)"; cat "$log"
    stop_port_forward
    return 1
  fi
  BASE_URL="http://127.0.0.1:$port"
}
stop_port_forward() {
  [ -z "$PF_PID" ] || { kill "$PF_PID" 2>/dev/null; wait "$PF_PID" 2>/dev/null; }
  PF_PID=""
}

# chaos API 요청. 상태 코드는 CHAOS_STATUS(연결 실패 · 시간 초과는 000), 본문은 CHAOS_BODY(JSON이 아니면 null)에 둔다.
# 명령 치환($(...)) 안에서 부르면 변수가 남지 않으니 그냥 호출한다.
CHAOS_STATUS=000 CHAOS_BODY=null
chaos_request() {  # <METHOD> <path> [JSON 본문]
  local out rc=0
  out="$(mktemp)"
  local args=(-sS -A one-tatchi-drill -o "$out" -w '%{http_code}' --max-time "$REQUEST_TIMEOUT_SECONDS" -X "$1")
  [ -z "${3:-}" ] || args+=(-H 'Content-Type: application/json' --data "$3")
  CHAOS_STATUS="$(curl "${args[@]}" "$BASE_URL$2" 2>/dev/null)" || rc=$?
  [ "$rc" -eq 0 ] && [ -n "$CHAOS_STATUS" ] || CHAOS_STATUS=000
  CHAOS_BODY="$(jq -c . "$out" 2>/dev/null)" || CHAOS_BODY=null
  [ -n "$CHAOS_BODY" ] || CHAOS_BODY=null
  rm -f "$out"
}

# 장애가 모두 풀린 상태인지 (GET /api/chaos 본문)
chaos_cleared() {  # <JSON>
  jq -e '(.latencyMs // 0) == 0 and (.errorRate // 0) == 0 and (.dbError // false) == false' <<<"$1" >/dev/null 2>&1
}
