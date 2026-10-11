#!/usr/bin/env bash
# 1단계 (new-green일 때만): 훈련용 green을 띄운다 (docs/chaos-drill.md "1. green 준비").
# 파드 템플릿 annotation(one-tatchi/drill)에 실행 ID를 넣어 revision만 바꾼다. 이미지는 그대로다.
# autoPromotionEnabled: false(차트 기본값)라 green이 뜨면 Paused에서 멈춘다. 서비스 모두 패치한 뒤 함께 기다린다.
# 결과: 서비스마다 $WORK_ROOT/<release>/green.json에 hash를 채운다. 못 띄우면 실패 (cleanup.sh가 annotation을 되돌린다)
#
# 환경변수: WORK_ROOT, NAMESPACE, RELEASES, DRILL_ID, WAIT_SECONDS(기본 300) + lib.sh
set -uo pipefail
. "$(cd "$(dirname "$0")" && pwd)/lib.sh"
: "${RELEASES:?}" "${DRILL_ID:?}"
WAIT_SECONDS="${WAIT_SECONDS:-300}"

for r in $RELEASES; do
  patch="$(jq -nc --arg a "$DRILL_ANNOTATION" --arg v "$DRILL_ID" '{spec: {template: {metadata: {annotations: {($a): $v}}}}}')"
  if ! $KUBECTL patch rollout "$r" -n "$NAMESPACE" --type merge -p "$patch"; then
    echo "::error::$r: 훈련용 green을 띄우지 못했다 (annotation 패치 실패)"
    exit 1
  fi
  echo "$r: $DRILL_ANNOTATION=$DRILL_ID 패치"
done

status=0
for r in $RELEASES; do
  end=$((SECONDS + WAIT_SECONDS)) hash=""
  while :; do
    if state="$(rollout_state "$r")"; then
      phase="$(jq -r .phase <<<"$state")"
      preview="$(jq -r .preview <<<"$state")"
      active="$(jq -r .active <<<"$state")"
      if [ "$phase" = Paused ] && [ "$(jq -r .paused <<<"$state")" = true ] && [ -n "$preview" ] && [ "$preview" != "$active" ]; then
        hash="$preview"; break
      fi
      if [ "$phase" = Degraded ]; then
        echo "::error::$r: 훈련용 green이 Degraded가 됐다: $(jq -r .message <<<"$state")"; break
      fi
      echo "$r: phase=$phase preview=${preview:-없음} active=${active:-없음}"
    fi
    [ "$SECONDS" -lt "$end" ] || { echo "::error::$r: ${WAIT_SECONDS}초 안에 훈련용 green이 Paused가 되지 않았다"; break; }
    sleep "$POLL_SECONDS"
  done
  if [ -n "$hash" ]; then
    jq --arg hash "$hash" '.hash = $hash' "$WORK_ROOT/$r/green.json" > "$WORK_ROOT/$r/green.json.tmp" \
      && mv "$WORK_ROOT/$r/green.json.tmp" "$WORK_ROOT/$r/green.json"
    echo "$r: 훈련용 green $hash 대기 중 (Paused)"
  else
    status=1
  fi
done
exit "$status"
