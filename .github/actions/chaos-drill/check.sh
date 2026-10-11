#!/usr/bin/env bash
# 0단계: green 확인. 서비스(Rollout)마다 상태를 읽어 훈련을 진행할지 거절할지 정한다 (docs/chaos-drill.md "0. green 확인").
#   Paused + preview ≠ active      → 대기 중인 green으로 진행 (mode existing)
#   Healthy + green 없음            → 거절. NEW_GREEN=true면 훈련용 green을 띄워 진행 (mode new)
#   Progressing · Degraded · 읽기 실패 → 거절
# 서비스가 여럿이면 모두 같은 mode여야 진행한다 (묶음 승격, ADR 0005).
# 결과: $WORK_ROOT/check.json, 진행이면 서비스마다 $WORK_ROOT/<release>/green.json (existing은 확인한 해시)
# step 출력: proceed (true | false), mode (existing | new | ""), reason
#
# 환경변수: WORK_ROOT, NAMESPACE, RELEASES(공백 구분), NEW_GREEN (true | false) + lib.sh
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/lib.sh"
: "${RELEASES:?}"
NEW_GREEN="${NEW_GREEN:-false}"

services="$WORK_ROOT/check.services.jsonl"
: > "$services"
for r in $RELEASES; do
  mode=reject reason=""
  if ! state="$(rollout_state "$r")"; then
    state='{}'
    reason="Rollout을 읽지 못했다"
  else
    phase="$(jq -r .phase <<<"$state")"
    paused="$(jq -r .paused <<<"$state")"
    active="$(jq -r .active <<<"$state")"
    preview="$(jq -r .preview <<<"$state")"
    case "$phase" in
      Paused)
        if [ "$paused" = true ] && [ -n "$preview" ] && [ "$preview" != "$active" ]; then
          mode=existing; reason="대기 중인 green($preview)에 주입한다"
        else
          reason="Paused이지만 대기 중인 green을 찾지 못했다 (preview: ${preview:-없음}, active: ${active:-없음})"
        fi ;;
      Healthy)
        if [ -z "$preview" ] || [ "$preview" = "$active" ]; then
          if [ "$NEW_GREEN" = true ]; then
            mode=new; reason="대기 중인 green이 없어 훈련용 green을 띄운다"
          else
            reason="대기 중인 green이 없어요. new-green을 붙이면 훈련용 green을 띄워요"
          fi
        else
          reason="Healthy인데 preview($preview)와 active($active)가 다르다. 상태를 확인해 주세요"
        fi ;;
      Progressing) reason="배포 진행 중이에요. 끝난 뒤 다시 시도해 주세요" ;;
      Degraded) reason="이미 Degraded 상태예요: $(jq -r '.message // "메시지 없음"' <<<"$state")" ;;
      "") reason="Rollout 상태가 비어 있다" ;;
      *) reason="알 수 없는 상태($phase)예요" ;;
    esac
  fi
  jq -nc --arg release "$r" --arg mode "$mode" --arg reason "$reason" --argjson state "$state" \
    '{release: $release, mode: $mode, reason: $reason} + $state' >> "$services"
  echo "$r: $mode — $reason"
done

# 묶음 결정: 하나라도 reject면 거절, existing과 new가 섞여도 거절 (BE · FE는 함께 움직여야 한다)
modes="$(jq -r .mode "$services" | sort -u | tr '\n' ' ')"
case "$modes" in
  "existing ") proceed=true mode=existing ;;
  "new ")      proceed=true mode=new ;;
  *reject*)    proceed=false mode="" ;;
  *)           proceed=false mode=""; echo "mixed" > "$WORK_ROOT/check.mixed" ;;
esac
if [ "$proceed" = false ]; then
  if [ -f "$WORK_ROOT/check.mixed" ]; then
    reason="서비스 상태가 서로 달라요 (한쪽만 green이 있음). 함께 승격하는 묶음이라 같이 있어야 해요: $(jq -r '"\(.release)=\(.mode)"' "$services" | tr '\n' ' ')"
    rm -f "$WORK_ROOT/check.mixed"
  else
    reason="$(jq -rs 'map(select(.mode == "reject") | "\(.release): \(.reason)") | join(" / ")' "$services")"
  fi
else
  reason="$(jq -rs 'map("\(.release): \(.reason)") | join(" / ")' "$services")"
  for r in $RELEASES; do
    mkdir -p "$WORK_ROOT/$r"
    hash=""
    [ "$mode" = existing ] && hash="$(jq -r --arg r "$r" 'select(.release == $r) | .preview' "$services")"
    jq -nc --arg release "$r" --arg mode "$mode" --arg hash "$hash" \
      --arg annotation "$(jq -r --arg r "$r" 'select(.release == $r) | .annotation' "$services")" \
      '{release: $release, mode: $mode, hash: (if $hash == "" then null else $hash end), original_annotation: $annotation}' \
      > "$WORK_ROOT/$r/green.json"
  done
fi

jq -s --argjson proceed "$proceed" --arg mode "$mode" --arg reason "$reason" --arg new_green "$NEW_GREEN" \
  '{proceed: $proceed, mode: $mode, reason: $reason, new_green: ($new_green == "true"), services: .}' "$services" > "$WORK_ROOT/check.json"
rm -f "$services"

if [ "$proceed" = true ]; then echo "진행 ($mode): $reason"; else echo "거절: $reason"; fi
output "proceed=$proceed"
output "mode=$mode"
output_multiline reason "$reason"
