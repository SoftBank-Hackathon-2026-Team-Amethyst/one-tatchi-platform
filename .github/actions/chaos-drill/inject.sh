#!/usr/bin/env bash
# 2단계: 장애 주입. 주입 대상 서비스의 green 파드마다 port-forward로 붙어 POST /api/chaos를 보낸다 (docs/chaos-drill.md "2. 장애 주입").
#   - chaosState는 파드 메모리에 있어 Service로 한 번 보내면 파드 하나에만 들어간다. 그래서 파드마다 직접 보낸다.
#   - 확인해 둔 green 해시(green.json)와 지금 Rollout의 preview가 다르면 아무것도 하지 않고 실패한다.
#   - GET /api/chaos의 enabled가 true가 아니면(CHAOS_ENABLED 꺼짐) 실패한다. blue · prod에는 보내는 경로가 없다.
# 결과: $WORK_ROOT/<release>/inject.json
#
# 환경변수: WORK_ROOT, NAMESPACE, RELEASES(주입 대상), SCENARIO, SCENARIOS_FILE(기본 scenarios.json) + lib.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"
: "${RELEASES:?}" "${SCENARIO:?}"
SCENARIOS_FILE="${SCENARIOS_FILE:-$here/scenarios.json}"
trap stop_port_forward EXIT

body="$(jq -ce --arg s "$SCENARIO" '.scenarios[$s].inject' "$SCENARIOS_FILE" 2>/dev/null)" \
  || { echo "::error::알 수 없는 시나리오: $SCENARIO"; exit 1; }
echo "시나리오 $SCENARIO: POST /api/chaos $body"

status=0
for r in $RELEASES; do
  mkdir -p "$WORK_ROOT/$r"
  out="$WORK_ROOT/$r/inject.json"
  expected="$(green_hash "$r")"
  pods='[]' error=""
  if [ -z "$expected" ]; then
    error="확인한 green 해시가 없다"
  elif ! state="$(rollout_state "$r")"; then
    error="Rollout을 읽지 못했다"
  elif [ "$(jq -r .preview <<<"$state")" != "$expected" ]; then
    error="green이 바뀌었다 (확인 $expected → 지금 $(jq -r '.preview // "없음"' <<<"$state")). 주입하지 않는다"
  else
    pods="$(green_pods "$r" "$expected")" || pods='[]'
    [ "$(jq length <<<"$pods")" -gt 0 ] || error="green 파드가 없다 (해시 $expected)"
  fi

  results='[]'
  if [ -z "$error" ]; then
    for i in $(seq 0 $(( $(jq length <<<"$pods") - 1 ))); do
      name="$(jq -r ".[$i].name" <<<"$pods")"
      port="$(jq -r ".[$i].port" <<<"$pods")"
      pod_error="" after="null"
      if start_port_forward "pod/$name" "$port" "$WORK_ROOT/$r/port-forward.$name.log"; then
        chaos_request GET /api/chaos
        if [ "$CHAOS_STATUS" != 200 ] || ! jq -e '.enabled == true' <<<"$CHAOS_BODY" >/dev/null 2>&1; then
          pod_error="장애 주입 API가 닫혀 있다 (GET /api/chaos → $CHAOS_STATUS, enabled: $(jq -r '.enabled // "?"' <<<"$CHAOS_BODY")). test 덧붙임 값 파일의 CHAOS_ENABLED를 확인"
        else
          chaos_request POST /api/chaos "$body"
          after="$CHAOS_BODY"
          if [ "$CHAOS_STATUS" != 200 ]; then
            pod_error="POST /api/chaos → $CHAOS_STATUS"
          elif ! jq -e --argjson want "$body" '. as $got | all($want | to_entries[]; $got[.key] == .value)' <<<"$after" >/dev/null 2>&1; then
            pod_error="응답이 주입 값과 다르다: $after"
          fi
        fi
        stop_port_forward
      else
        pod_error="port-forward 실패"
      fi
      results="$(jq -c --arg name "$name" --arg err "$pod_error" --argjson state "$after" \
        '. + [{name: $name, injected: ($err == ""), error: (if $err == "" then null else $err end), state: $state}]' <<<"$results")"
      if [ -z "$pod_error" ]; then echo "$r/$name: 주입 완료 $after"; else echo "::error::$r/$name: $pod_error"; fi
    done
    [ "$(jq 'all(.[]; .injected)' <<<"$results")" = true ] || error="파드 일부에 주입하지 못했다"
  else
    echo "::error::$r: $error"
  fi

  jq -nc --arg release "$r" --arg scenario "$SCENARIO" --arg hash "${expected:-}" --argjson inject "$body" \
    --argjson pods "$results" --arg err "$error" \
    '{release: $release, scenario: $scenario, hash: (if $hash == "" then null else $hash end), inject: $inject,
      pods: $pods, injected: ($err == ""), error: (if $err == "" then null else $err end)}' > "$out"
  [ -z "$error" ] || status=1
done
exit "$status"
