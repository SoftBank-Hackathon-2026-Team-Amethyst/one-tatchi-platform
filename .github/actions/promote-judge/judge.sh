#!/usr/bin/env bash
# metrics.json을 Claude에 보내 promote / abort와 근거를 받는다 (ADR 0004: 규칙에 거부권).
# 결과: $WORK_DIR/judgment.json, step 출력 decision · reason · report
# AI 판단을 쓸 수 없으면(키 없음 · 호출 실패 · 시간 초과 · 거절 · 형식 오류) 재시도 없이 abort다.
#
# 환경변수
#   WORK_DIR, RELEASE, MODEL, ANTHROPIC_API_KEY, API_TIMEOUT_SECONDS
#   ANTHROPIC_BASE_URL  (선택) API 주소 (테스트용)
set -uo pipefail

: "${WORK_DIR:?}" "${RELEASE:?}"
MODEL="${MODEL:-claude-sonnet-5-5}"
API_TIMEOUT_SECONDS="${API_TIMEOUT_SECONDS:-60}"
ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.anthropic.com}"

mkdir -p "$WORK_DIR"
metrics="$WORK_DIR/metrics.json"
out="$WORK_DIR/judgment.json"
[ -s "$metrics" ] && jq -e . "$metrics" >/dev/null 2>&1 \
  || echo '{"rule":{"verdict":"fail","reasons":["지표 파일이 없다"]}}' > "$metrics"

read -r -d '' SYSTEM <<'EOF'
너는 Blue-Green 배포의 승격 판단자다. green(새 버전)은 아직 사용자 트래픽이 없고, 파이프라인이 관찰 창 동안 보낸 smoke 요청과 green 파드 상태로 지표를 만들었다.
입력 JSON의 지표, 기준값(thresholds), 규칙 판정(rule)을 보고 promote 또는 abort를 정하라.
- rule.verdict가 fail이면 decision은 반드시 abort이고, reason에는 실패 원인(어떤 경로 · 상태 코드 · 수치)을 설명한다.
- rule.verdict가 pass여도 지표에 이상이 있으면(특정 경로만 실패에 가깝게 느림, 요청 수가 지나치게 적음 등) abort할 수 있다.
- reason은 한국어 한두 문장으로, 판단에 쓴 수치를 포함한다. 예: "에러율 0%, p95 38ms로 기준 안이고 green 파드 2개 모두 Ready라 승격한다."
EOF

ai_decision="" ai_reason="" ai_error="" started=$SECONDS
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  ai_error="API 키 없음"
else
  request="$WORK_DIR/claude-request.json"
  jq -n --arg model "$MODEL" --arg system "$SYSTEM" --rawfile metrics "$metrics" '{
    model: $model,
    max_tokens: 16000,
    fallbacks: "default",
    system: $system,
    messages: [{role: "user", content: $metrics}],
    output_config: {format: {type: "json_schema", schema: {
      type: "object",
      properties: {
        decision: {type: "string", enum: ["promote", "abort"]},
        reason: {type: "string"}
      },
      required: ["decision", "reason"],
      additionalProperties: false
    }}}
  }' > "$request"

  response="$WORK_DIR/claude-response.json"
  http="$(curl -sS -o "$response" -w '%{http_code}' --max-time "$API_TIMEOUT_SECONDS" \
    "$ANTHROPIC_BASE_URL/v1/messages" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "anthropic-beta: server-side-fallback-2026-07-01" \
    -H "content-type: application/json" \
    --data-binary @"$request" 2>"$WORK_DIR/claude-curl.err")" || http="000"

  if [ "$http" = 000 ]; then
    ai_error="호출 실패: $(tr '\n' ' ' < "$WORK_DIR/claude-curl.err" | cut -c1-200)"
  elif [ "$http" != 200 ]; then
    ai_error="HTTP $http: $(jq -r '.error.message // empty' "$response" 2>/dev/null | cut -c1-200)"
  else
    stop="$(jq -r '.stop_reason // empty' "$response" 2>/dev/null)"
    if [ "$stop" = refusal ]; then
      ai_error="모델이 판단을 거절함"
    elif [ "$stop" != end_turn ]; then
      ai_error="응답이 끝나지 않음 (stop_reason: ${stop:-없음})"
    else
      # thinking 블록이 앞에 올 수 있어 text 블록만 본다
      answer="$(jq -c '[.content[] | select(.type == "text") | .text] | last | fromjson
        | select((.decision == "promote" or .decision == "abort") and (.reason | type == "string" and length > 0))' \
        "$response" 2>/dev/null)"
      if [ -n "$answer" ]; then
        ai_decision="$(jq -r .decision <<<"$answer")"
        ai_reason="$(jq -r .reason <<<"$answer")"
      else
        ai_error="응답 형식 오류"
      fi
    fi
  fi
fi
elapsed=$((SECONDS - started))

# ---------- 최종 결정 (ADR 0004) ----------
jq -n --rawfile metrics_raw "$metrics" \
  --arg release "$RELEASE" --arg model "$MODEL" --argjson elapsed "$elapsed" \
  --arg ai_decision "$ai_decision" --arg ai_reason "$ai_reason" --arg ai_error "$ai_error" '
  ($metrics_raw | fromjson) as $m
  | ($m.rule.verdict // "fail") as $verdict
  | ($m.rule.reasons // [] | join(", ")) as $rule_text
  | {release: $release, model: $model, ai_seconds: $elapsed,
     ai: {decision: (if $ai_decision == "" then null else $ai_decision end),
          reason: (if $ai_reason == "" then null else $ai_reason end),
          error: (if $ai_error == "" then null else $ai_error end)},
     rule: $m.rule, metrics: ($m | del(.rule))}
  | if $verdict != "pass" then
      .decision = "abort" | .source = "rule"
      | .reason = (if $ai_reason != "" then $ai_reason else "규칙 판정 fail: \($rule_text)" end)
    elif $ai_decision != "" then
      .decision = $ai_decision | .source = "ai" | .reason = $ai_reason
    else
      .decision = "abort" | .source = "fallback"
      | .reason = "AI 판단을 받지 못해 abort한다 (\($ai_error)). 규칙 판정은 pass였다."
    end
' > "$out"

decision="$(jq -r .decision "$out")"
reason="$(jq -r .reason "$out")"
echo "판단: $decision ($(jq -r .source "$out"), AI ${elapsed}초) — $reason"
[ -z "$ai_error" ] || echo "::warning::AI 판단 실패: $ai_error"

if [ -n "${GITHUB_OUTPUT:-}" ]; then
  {
    echo "decision=$decision"
    echo "reason<<__REASON__"
    echo "$reason"
    echo "__REASON__"
    echo "report=$out"
  } >> "$GITHUB_OUTPUT"
fi
