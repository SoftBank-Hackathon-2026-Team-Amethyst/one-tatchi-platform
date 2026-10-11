#!/usr/bin/env bash
# 5단계: 정리. 앞 단계가 실패해도 항상 실행한다 (docs/chaos-drill.md "5. 정리").
#   1. 주입 대상 서비스의 green 파드마다 POST /api/chaos/reset → GET /api/chaos로 해제됐는지 확인
#   2. 대기 중이던 green(mode existing)이면 Rollout이 아직 Paused인지만 확인한다. 승격 여부는 사람이 정한다
#   3. 훈련용 green(mode new)이면 abort → annotation을 원래 값으로 되돌려 spec을 stable과 같게 → Healthy 확인
#   4. 해제나 기대 상태를 확인하지 못하면 실패로 남긴다 (grade.sh가 훈련 실패로 채점하고 Slack에 경고한다)
# 결과: $WORK_ROOT/cleanup.json, step 출력 released (true | false)
#
# 환경변수: WORK_ROOT, NAMESPACE, RELEASES(묶음 전체), INJECT_RELEASES, MODE(existing | new), WAIT_SECONDS(기본 180) + lib.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"
: "${RELEASES:?}" "${MODE:?}"
INJECT_RELEASES="${INJECT_RELEASES:-}"
WAIT_SECONDS="${WAIT_SECONDS:-180}"
trap stop_port_forward EXIT

errors='[]'
add_error() { errors="$(jq -c --arg e "$1" '. + [$e]' <<<"$errors")"; echo "::error::$1"; }

# ---------- 1. 장애 해제 ----------
released=true
release_results='{}'
for r in $INJECT_RELEASES; do
  hash="$(green_hash "$r")"
  pods='[]' note=""
  if [ -z "$hash" ]; then
    note="green을 띄우지 못해 해제할 파드가 없다"
  elif ! state="$(rollout_state "$r")"; then
    note="Rollout을 읽지 못했다"; released=false
  elif [ "$(jq -r .preview <<<"$state")" != "$hash" ]; then
    note="green이 바뀌어 해제를 확인하지 못했다 (확인 $hash → 지금 $(jq -r '.preview // "없음"' <<<"$state"))"; released=false
  else
    pods="$(green_pods "$r" "$hash")" || pods='[]'
  fi
  results='[]'
  for i in $(seq 0 $(( $(jq length <<<"$pods") - 1 ))); do
    [ "$(jq length <<<"$pods")" -gt 0 ] || break
    name="$(jq -r ".[$i].name" <<<"$pods")"
    port="$(jq -r ".[$i].port" <<<"$pods")"
    ok=false after=null
    if start_port_forward "pod/$name" "$port" "$WORK_ROOT/$r/port-forward.reset.$name.log"; then
      chaos_request POST /api/chaos/reset
      chaos_request GET /api/chaos
      after="$CHAOS_BODY"
      if [ "$CHAOS_STATUS" = 200 ] && chaos_cleared "$after"; then ok=true; fi
      stop_port_forward
    fi
    results="$(jq -c --arg name "$name" --argjson ok "$ok" --argjson state "$after" '. + [{name: $name, released: $ok, state: $state}]' <<<"$results")"
    if [ "$ok" = true ]; then echo "$r/$name: 장애 해제 확인"; else released=false; add_error "$r/$name: 장애 해제를 확인하지 못했다 (GET /api/chaos → $CHAOS_STATUS $after)"; fi
  done
  [ -z "$note" ] || { echo "$r: $note"; [ "$released" = true ] || add_error "$r: $note"; }
  release_results="$(jq -c --arg r "$r" --arg note "$note" --argjson pods "$results" \
    '.[$r] = {note: (if $note == "" then null else $note end), pods: $pods}' <<<"$release_results")"
done

# ---------- 2 · 3. Rollout 원상 복구 ----------
rollouts='{}'
for r in $RELEASES; do
  want=Paused ok=false phase="" hash="$(green_hash "$r")"
  if [ "$MODE" = new ]; then
    want=Healthy
    if state="$(rollout_state "$r")"; then
      preview="$(jq -r .preview <<<"$state")"
      if [ -n "$preview" ] && [ "$preview" != "$(jq -r .active <<<"$state")" ]; then
        $KUBECTL argo rollouts abort "$r" -n "$NAMESPACE" || add_error "$r: abort 명령 실패"
      fi
    fi
    original="$(jq -r '.original_annotation // ""' "$WORK_ROOT/$r/green.json" 2>/dev/null)"
    if [ -n "$original" ]; then value="\"$original\""; else value=null; fi
    patch="$(jq -nc --arg a "$DRILL_ANNOTATION" --argjson v "$value" '{spec: {template: {metadata: {annotations: {($a): $v}}}}}')"
    $KUBECTL patch rollout "$r" -n "$NAMESPACE" --type merge -p "$patch" || add_error "$r: annotation 복구 실패"
  fi
  end=$((SECONDS + WAIT_SECONDS))
  while :; do
    if state="$(rollout_state "$r")"; then
      phase="$(jq -r .phase <<<"$state")"
      preview="$(jq -r .preview <<<"$state")"
      active="$(jq -r .active <<<"$state")"
      if [ "$MODE" = new ]; then
        [ "$phase" = Healthy ] && { [ -z "$preview" ] || [ "$preview" = "$active" ]; } && { ok=true; break; }
      else
        # 대기 중이던 green: 같은 green이 그대로 Paused여야 한다. 다른 상태면 더 기다리지 않는다
        [ "$phase" = Paused ] && [ "$preview" = "$hash" ] && ok=true
        break
      fi
    fi
    [ "$SECONDS" -lt "$end" ] || break
    sleep "$POLL_SECONDS"
  done
  if [ "$ok" = true ]; then echo "$r: Rollout $phase (기대 $want)"; else add_error "$r: Rollout이 기대한 상태($want)가 아니다: ${phase:-읽기 실패}"; fi
  rollouts="$(jq -c --arg r "$r" --arg phase "$phase" --arg want "$want" --argjson ok "$ok" '.[$r] = {phase: $phase, expected: $want, ok: $ok}' <<<"$rollouts")"
done

jq -n --arg mode "$MODE" --argjson released "$released" --argjson services "$release_results" --argjson rollouts "$rollouts" --argjson errors "$errors" '
  {mode: $mode, released: $released, services: $services, rollouts: $rollouts, errors: $errors,
   ok: ($released and ($rollouts | to_entries | all(.[]; .value.ok)) and ($errors | length == 0))}' > "$WORK_ROOT/cleanup.json"
output "released=$released"
if [ "$(jq -r .ok "$WORK_ROOT/cleanup.json")" = true ]; then echo "정리 완료"; else echo "::error::정리 실패: $(jq -r '.errors | join(" / ")' "$WORK_ROOT/cleanup.json")"; exit 1; fi
