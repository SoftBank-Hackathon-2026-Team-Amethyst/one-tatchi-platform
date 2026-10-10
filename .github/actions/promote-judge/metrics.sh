#!/usr/bin/env bash
# smoke 결과와 green 파드 상태로 지표를 계산하고 기준값과 비교한다 (규칙 판정).
# 입력: $WORK_DIR/smoke-results.jsonl (smoke.sh)
# 결과: $WORK_DIR/metrics.json — 무엇이 실패해도 파일은 남기고, 판단 근거가 모자라면 verdict는 fail이다.
#
# 환경변수
#   WORK_DIR, RELEASE, NAMESPACE, MAX_ERROR_RATE(%), MAX_P95_MS(비우면 검사 안 함), MAX_RESTARTS
#   KUBECTL  (선택) kubectl 대신 쓸 명령 (테스트용)
set -uo pipefail

: "${WORK_DIR:?}" "${RELEASE:?}" "${NAMESPACE:?}"
MAX_ERROR_RATE="${MAX_ERROR_RATE:-0}"
MAX_P95_MS="${MAX_P95_MS:-}"
MAX_RESTARTS="${MAX_RESTARTS:-0}"
KUBECTL="${KUBECTL:-kubectl}"

mkdir -p "$WORK_DIR"
results="$WORK_DIR/smoke-results.jsonl"
out="$WORK_DIR/metrics.json"
[ -f "$results" ] || : > "$results"

# ---------- smoke 지표 ----------
# p95는 nearest-rank: 응답 시간을 오름차순으로 세웠을 때 ceil(0.95 × n)번째 값
smoke="$(jq -s '
  (map(.ms) | sort) as $ms
  | {
      requests: length,
      failed: (map(select(.ok | not)) | length),
      passes: (map(.pass) | max // 0),
      p95_ms: (if length > 0 then $ms[((length * 0.95) | ceil) - 1] else null end),
      max_ms: ($ms | max),
      failures: (map(select(.ok | not))
        | group_by([.method, .path, .status, .body_mismatch])
        | map(.[0] + {count: length} | {method, path, expect, status, body_mismatch, count}))
    }
  | .error_rate = (if .requests > 0 then (.failed * 10000 / .requests | round) / 100 else null end)
' "$results")" || smoke='{"requests":0,"failed":0,"passes":0,"p95_ms":null,"max_ms":null,"failures":[],"error_rate":null}'

# ---------- green 파드 ----------
# Paused 상태 Blue-Green에서 green 파드는 previewSelector(= 새 버전 해시) 라벨을 가진다.
pods=null
hash="$($KUBECTL get rollout "$RELEASE" -n "$NAMESPACE" -o json 2>/dev/null \
  | jq -r '.status.blueGreen.previewSelector // .status.currentPodHash // empty' 2>/dev/null)"
if [ -n "$hash" ]; then
  pods="$($KUBECTL get pods -n "$NAMESPACE" -l "rollouts-pod-template-hash=$hash" -o json 2>/dev/null | jq -c '
    .items | {
      count: length,
      ready: (map(select(any(.status.conditions[]?; .type == "Ready" and .status == "True"))) | length),
      restarts: (map([.status.containerStatuses[]?.restartCount] | add // 0) | add // 0)
    }' 2>/dev/null)" || pods=null
  [ -n "$pods" ] || pods=null
fi

# ---------- 규칙 판정 ----------
jq -n \
  --arg release "$RELEASE" --arg hash "$hash" \
  --argjson smoke "$smoke" --argjson pods "$pods" \
  --argjson max_error_rate "$MAX_ERROR_RATE" \
  --argjson max_p95_ms "${MAX_P95_MS:-null}" \
  --argjson max_restarts "$MAX_RESTARTS" '
  ($smoke + {release: $release, green_hash: (if $hash == "" then null else $hash end), pods: $pods,
             thresholds: {max_error_rate: $max_error_rate, max_p95_ms: $max_p95_ms, max_restarts: $max_restarts}})
  | .rule.reasons = [
      (if .requests == 0 then "smoke 결과가 없다" else empty end),
      (if .requests > 0 and .error_rate > $max_error_rate
        then "에러율 \(.error_rate)% > 기준 \($max_error_rate)%" else empty end),
      (if .requests > 0 and $max_p95_ms != null and .p95_ms > $max_p95_ms
        then "p95 \(.p95_ms)ms > 기준 \($max_p95_ms)ms" else empty end),
      (if .pods == null then "green 파드 정보를 읽지 못했다"
       elif .pods.count == 0 then "green 파드가 없다"
       else
         (if .pods.ready < .pods.count then "Ready가 아닌 green 파드 \(.pods.count - .pods.ready)개" else empty end),
         (if .pods.restarts > $max_restarts then "green 파드 재시작 \(.pods.restarts)회 > 기준 \($max_restarts)회" else empty end)
       end)
    ]
  | .rule.verdict = (if (.rule.reasons | length) == 0 then "pass" else "fail" end)
' > "$out" || {
  echo "::warning::지표 계산 실패 (기준값 입력을 확인)"
  jq -n --arg release "$RELEASE" '{release: $release, rule: {verdict: "fail", reasons: ["지표 계산 실패"]}}' > "$out"
}

jq -r '"규칙 판정: \(.rule.verdict) — 요청 \(.requests)건, 에러율 \(.error_rate)%, p95 \(.p95_ms)ms, green 파드 \(.pods.count // "?")개 · 재시작 \(.pods.restarts // "?")회"
  + (if (.rule.reasons | length) > 0 then "\n  - " + (.rule.reasons | join("\n  - ")) else "" end)' "$out"
