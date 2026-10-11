#!/usr/bin/env bash
# 4단계: blue 확인. active Service(<release>)에 promote-judge의 smoke를 그대로 보내 blue 에러율을 남긴다 (docs/chaos-drill.md "4. blue 확인").
# "장애가 사용자 쪽으로 새지 않았다"의 증거다. 주입 대상 서비스는 blue의 GET /api/chaos도 읽어 두어,
# 누가 test 화면의 장애 버튼으로 blue에 직접 주입했는지(훈련과 무관한 간섭) 구분할 수 있게 한다.
# 결과: $WORK_ROOT/blue.json, 서비스별 smoke 결과는 $WORK_ROOT/blue/<release>/
#
# 환경변수: WORK_ROOT, NAMESPACE, RELEASES(묶음 전체), INJECT_RELEASES, SMOKE_FILE, WINDOW_SECONDS(기본 10), REQUEST_TIMEOUT_SECONDS + lib.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"
: "${RELEASES:?}"
INJECT_RELEASES="${INJECT_RELEASES:-}"
WINDOW_SECONDS="${WINDOW_SECONDS:-10}"
SMOKE_FILE="${SMOKE_FILE:-.deploy/smoke.json}"
smoke="$here/../promote-judge/smoke.sh"
trap stop_port_forward EXIT

# smoke는 서비스마다 동시에 (관찰 창은 한 번). SERVICE로 preview 대신 active Service를 가리킨다.
pids="" names=""
for r in $RELEASES; do
  mkdir -p "$WORK_ROOT/blue/$r"
  env WORK_DIR="$WORK_ROOT/blue/$r" RELEASE="$r" SERVICE="$r" NAMESPACE="$NAMESPACE" SMOKE_FILE="$SMOKE_FILE" \
    WINDOW_SECONDS="$WINDOW_SECONDS" REQUEST_TIMEOUT_SECONDS="$REQUEST_TIMEOUT_SECONDS" KUBECTL="$KUBECTL" \
    bash "$smoke" > "$WORK_ROOT/blue/$r.smoke.log" 2>&1 &
  pids="$pids $!"; names="$names $r"
done
set -- $pids
for r in $names; do
  wait "$1" || echo "::warning::$r: blue smoke 실행 실패"; shift
  echo "::group::blue smoke $r"; cat "$WORK_ROOT/blue/$r.smoke.log"; echo "::endgroup::"
done

services='{}'
for r in $RELEASES; do
  results="$WORK_ROOT/blue/$r/smoke-results.jsonl"
  [ -f "$results" ] || : > "$results"
  metrics="$(jq -s '(map(.ms) | sort) as $ms
    | {requests: length, failed: (map(select(.ok | not)) | length),
       p95_ms: (if length > 0 then $ms[((length * 0.95) | ceil) - 1] else null end)}
    | .error_rate = (if .requests > 0 then (.failed * 10000 / .requests | round) / 100 else null end)' "$results")"
  chaos=null
  case " $INJECT_RELEASES " in *" $r "*)
    port="$($KUBECTL get svc "$r" -n "$NAMESPACE" -o jsonpath='{.spec.ports[0].port}' 2>/dev/null)"
    if [ -n "$port" ] && start_port_forward "svc/$r" "$port" "$WORK_ROOT/blue/$r/port-forward.chaos.log"; then
      chaos_request GET /api/chaos
      chaos="$CHAOS_BODY"; [ "$CHAOS_STATUS" = 200 ] || chaos=null
      stop_port_forward
    fi ;;
  esac
  services="$(jq -c --arg r "$r" --argjson m "$metrics" --argjson c "$chaos" '
    .[$r] = ($m + {chaos: $c, manual_injection: (if $c == null then null else (($c.latencyMs // 0) != 0 or ($c.errorRate // 0) != 0 or ($c.dbError // false)) end)})' <<<"$services")"
done

jq -n --argjson s "$services" --argjson window "$WINDOW_SECONDS" '
  {services: $s, window_seconds: $window,
   ok: ($s | to_entries | all(.[]; .value.requests > 0 and .value.error_rate == 0)),
   manual_injection: ($s | to_entries | any(.[]; .value.manual_injection == true))}' > "$WORK_ROOT/blue.json"
jq -r '"blue: " + (if .ok then "정상" else "이상" end) + " — " + (.services | to_entries | map("\(.key) 요청 \(.value.requests)건 · 에러율 \(.value.error_rate // "?")% · p95 \(.value.p95_ms // "?")ms" + (if .value.manual_injection == true then " (수동 주입 있음: \(.value.chaos | tojson))" else "" end)) | join(", "))' "$WORK_ROOT/blue.json"
[ "$(jq -r .ok "$WORK_ROOT/blue.json")" = true ]
