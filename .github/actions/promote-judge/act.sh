#!/usr/bin/env bash
# judgment.json의 결정을 실행(auto)하거나 기록만(manual) 하고, Job Summary에 근거를 남긴다.
#   auto   promote → kubectl argo rollouts promote 후 Healthy까지 확인 (못 되면 실패)
#          abort   → kubectl argo rollouts abort 후 step 실패 (yolo 파이프라인을 멈춘다)
#   manual 실행하지 않는다. 사람이 Slack 버튼(rollout.yml)으로 결정한다. step은 성공
# step 출력: executed (실제로 성공한 명령 promote | abort, 없으면 빈 값)
#
# 환경변수
#   WORK_DIR, RELEASE, NAMESPACE, TARGET, ENVIRONMENT, MODE, PROMOTE_WAIT_SECONDS
#   KUBECTL  (선택) kubectl 대신 쓸 명령 (테스트용)
set -uo pipefail

: "${WORK_DIR:?}" "${RELEASE:?}" "${NAMESPACE:?}"
TARGET="${TARGET:-}"
ENVIRONMENT="${ENVIRONMENT:-$NAMESPACE}"
MODE="${MODE:-manual}"
PROMOTE_WAIT_SECONDS="${PROMOTE_WAIT_SECONDS:-60}"
KUBECTL="${KUBECTL:-kubectl}"

judgment="$WORK_DIR/judgment.json"
if [ -s "$judgment" ] && jq -e .decision "$judgment" >/dev/null 2>&1; then
  decision="$(jq -r .decision "$judgment")"
else
  decision=abort
  jq -n --arg release "$RELEASE" \
    '{release: $release, decision: "abort", source: "fallback", reason: "판단 결과 파일이 없어 abort한다."}' > "$judgment"
fi
[ "$decision" = promote ] || decision=abort

executed="" result="" status=0
case "$MODE" in
  auto)
    # executed는 promote · abort 명령이 성공했을 때만 남긴다 (감사 로그 기준)
    if [ "$decision" = promote ]; then
      if ! $KUBECTL argo rollouts promote "$RELEASE" -n "$NAMESPACE"; then
        result="promote 명령 실패"
        status=1
      else
        executed=promote
        if $KUBECTL argo rollouts status "$RELEASE" -n "$NAMESPACE" --timeout "${PROMOTE_WAIT_SECONDS}s"; then
          result="promote 완료: green이 active가 됐다"
        else
          result="promote 후 ${PROMOTE_WAIT_SECONDS}초 안에 Healthy가 되지 않았다"
          status=1
        fi
      fi
    else
      if $KUBECTL argo rollouts abort "$RELEASE" -n "$NAMESPACE"; then
        executed=abort
        result="abort 완료: green을 버리고 blue를 유지한다"
      else
        result="abort 명령 실패"
      fi
      status=1
    fi ;;
  manual)
    result="실행하지 않음: 사람이 Slack 버튼으로 승격 · 취소한다" ;;
  *)
    echo "::error::mode는 auto | manual: $MODE"
    result="잘못된 mode: $MODE"
    status=1 ;;
esac

[ -z "${GITHUB_OUTPUT:-}" ] || echo "executed=$executed" >> "$GITHUB_OUTPUT"

# ---------- Job Summary ----------
summary="$(jq -r --arg label "$RELEASE@${TARGET:+$TARGET.}$ENVIRONMENT" --arg mode "$MODE" --arg result "$result" '
  def n: if . == null then "-" else tostring end;
  "### AI 승격 판단: \(.decision) — `\($label)`",
  "",
  "> \(.reason)",
  "",
  "| 항목 | 값 |",
  "|---|---|",
  "| 결정 출처 | \(.source) (ai: AI 결정 · rule: 규칙 거부권 · fallback: AI 판단 없음 · group: 다른 서비스 abort) |",
  "| 모드 · 실행 | \($mode) · \($result) |",
  "| 요청 · 실패 | \(.metrics.requests | n)건 · \(.metrics.failed | n)건 |",
  "| 에러율 · p95 | \(.metrics.error_rate | n)% · \(.metrics.p95_ms | n)ms |",
  "| green 파드 (Ready · 재시작) | \(.metrics.pods.count | n)개 (\(.metrics.pods.ready | n) · \(.metrics.pods.restarts | n)회) |",
  "| 규칙 판정 | \(.rule.verdict | n)\(if (.rule.reasons // []) | length > 0 then ": " + (.rule.reasons | join(", ")) else "" end) |",
  "| 모델 · AI 응답 | \(.model | n) · \(.ai_seconds | n)초\(if .ai.error then " (실패: " + .ai.error + ")" else "" end) |",
  (if (.metrics.failures // []) | length > 0 then
    "", "실패한 요청", "", "| 요청 | 기대 | 실제 | 횟수 |", "|---|---|---|---|",
    (.metrics.failures[] | "| \(.method) \(.path) | \(.expect) | \(.status) | \(.count) |")
   else empty end)
' "$judgment")"
echo "$summary"
[ -z "${GITHUB_STEP_SUMMARY:-}" ] || echo "$summary" >> "$GITHUB_STEP_SUMMARY"

if [ "$status" -ne 0 ]; then
  echo "::error::$RELEASE: $result"
fi
exit "$status"
