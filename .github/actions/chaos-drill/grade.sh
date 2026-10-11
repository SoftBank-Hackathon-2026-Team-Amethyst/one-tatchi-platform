#!/usr/bin/env bash
# 6단계: 채점. 시나리오의 기대 결과와 실제를 비교해 통과 · 실패를 정한다 (docs/chaos-drill.md "6. 채점").
#   통과 = 주입 성공 ∧ promote-judge 묶음 결정 == 기대 ∧ blue 에러율 0% ∧ 정리 완료
# 결과: $WORK_ROOT/result.json, Job Summary, step 출력 result (pass | fail) · details (Slack mrkdwn)
# 실패면 종료 코드 1 (job을 실패로 만든다)
#
# 환경변수: WORK_ROOT, NAMESPACE, SCENARIO, SCENARIOS_FILE, INJECT_RELEASES, JUDGMENT_DIR(promote-judge 결과 폴더), LABEL, MODE
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
. "$here/lib.sh"
: "${SCENARIO:?}"
SCENARIOS_FILE="${SCENARIOS_FILE:-$here/scenarios.json}"
INJECT_RELEASES="${INJECT_RELEASES:-}"
JUDGMENT_DIR="${JUDGMENT_DIR:-${RUNNER_TEMP:-/tmp}/promote-judge}"
LABEL="${LABEL:-$SCENARIO@$NAMESPACE}"
MODE="${MODE:-}"

scenario="$(jq -c --arg s "$SCENARIO" '.scenarios[$s] // null' "$SCENARIOS_FILE" 2>/dev/null || echo null)"
[ "$scenario" != null ] || { echo "::error::알 수 없는 시나리오: $SCENARIO"; scenario='{"expect":{"decision":"abort"},"guardrail":"?","title":"?"}'; }
expected="$(jq -r .expect.decision <<<"$scenario")"
guardrail="$(jq -r .guardrail <<<"$scenario")"

read_json() { [ -s "$1" ] && jq -c . "$1" 2>/dev/null || echo null; }
judgment="$(read_json "$JUDGMENT_DIR/judgment.json")"
blue="$(read_json "$WORK_ROOT/blue.json")"
cleanup="$(read_json "$WORK_ROOT/cleanup.json")"
injects='[]'
for r in $INJECT_RELEASES; do
  injects="$(jq -c --argjson i "$(read_json "$WORK_ROOT/$r/inject.json")" --arg r "$r" '. + [($i // {release: $r, injected: false, error: "주입 단계가 돌지 않았다"})]' <<<"$injects")"
done
# 주입 대상 서비스의 green 지표(promote-judge metrics.json)
greens='{}'
for r in $INJECT_RELEASES; do
  greens="$(jq -c --arg r "$r" --argjson m "$(read_json "$JUDGMENT_DIR/$r/metrics.json")" '.[$r] = ($m | if . == null then null else {error_rate, p95_ms, requests, failed} end)' <<<"$greens")"
done

result="$(jq -n \
  --arg scenario "$SCENARIO" --argjson def "$scenario" --arg expected "$expected" --arg guardrail "$guardrail" \
  --argjson judgment "$judgment" --argjson blue "$blue" --argjson cleanup "$cleanup" --argjson injects "$injects" --argjson greens "$greens" \
  --arg label "$LABEL" --arg mode "$MODE" '
  ($judgment.decision // "none") as $actual
  # 묶음 결정에는 source가 없다. 묶음 결정과 같은 결정을 낸 서비스들의 source(rule · ai · fallback)를 모은다
  | ($judgment.source // ([($judgment.services // {}) | to_entries[] | select(.value.decision == $actual) | .value.source // empty] | unique | join("+") | if . == "" then null else . end)) as $source
  | {
      scenario: $scenario, title: $def.title, label: $label, mode: $mode,
      expected: {decision: $expected, blue_error_rate: 0},
      actual: {decision: $actual, source: $source, reason: ($judgment.reason // null), services: ($judgment.services // null)},
      green: $greens, blue: $blue, cleanup: $cleanup, inject: $injects,
      checks: [
        {name: "장애 주입", ok: (($injects | length) > 0 and all($injects[]; .injected == true)),
         detail: (if ($injects | length) == 0 then "주입 대상이 없다"
                  else ($injects | map(if .injected then "\(.release) 파드 \(.pods | length)개" else "\(.release): \(.error // "실패")" end) | join(", ")) end)},
        {name: "판단", ok: ($actual == $expected),
         detail: (if $actual == $expected then "기대 \($expected) → 실제 \($actual)" + (if $source then " (\($source))" else "" end)
                  elif $actual == "none" then "판단 결과가 없다 (기대 \($expected))"
                  else "가드레일 `\($guardrail)`이 막지 못했다: 기대 \($expected), 실제 \($actual)" end)},
        {name: "blue", ok: ($blue.ok == true),
         detail: (if $blue == null then "blue 확인 결과가 없다"
                  else ($blue.services | to_entries | map("\(.key) 에러율 \(.value.error_rate // "?")% · p95 \(.value.p95_ms // "?")ms") | join(", "))
                       + (if $blue.manual_injection == true then " · 주의: blue에 수동 주입 상태가 있다 (test 화면의 장애 버튼?)" else "" end) end)},
        {name: "정리", ok: ($cleanup.ok == true),
         detail: (if $cleanup == null then "정리 결과가 없다"
                  elif $cleanup.ok then "장애 해제 · Rollout " + ([$cleanup.rollouts | to_entries[] | "\(.key) \(.value.phase)"] | join(", "))
                  else ($cleanup.errors | join(" / ")) end)}
      ]
    }
  | .result = (if all(.checks[]; .ok) then "pass" else "fail" end)
  | .promotion_unsafe = ($cleanup != null and $cleanup.released == false and $mode == "existing")
')"
echo "$result" > "$WORK_ROOT/result.json"
verdict="$(jq -r .result <<<"$result")"

# ---------- 요약 (Job Summary · Slack) ----------
green_line="$(jq -r '.green | to_entries | map("\(.key) 에러율 \(.value.error_rate // "?")% · p95 \(.value.p95_ms // "?")ms") | join(", ")' <<<"$result")"
md="$(jq -r --arg green "$green_line" '
  "### 장애 훈련 \(if .result == "pass" then "통과 ✅" else "실패 🚨" end) — `\(.scenario)` @ `\(.label)`",
  "",
  "\(.title) · 기대 \(.expected.decision) → 실제 \(.actual.decision)\(if .actual.source then " (\(.actual.source))" else "" end)",
  "",
  (if .actual.reason then "> AI 근거: \(.actual.reason)", "" else empty end),
  "| 확인 | 결과 | 내용 |", "|---|---|---|",
  (.checks[] | "| \(.name) | \(if .ok then "✅" else "❌" end) | \(.detail) |"),
  (if $green != "" then "| green 지표 | | \($green) |" else empty end),
  (if .promotion_unsafe then "", "**⚠️ 장애가 남아 있을 수 있어요. 이 green을 승격하지 마세요.** abort로 green을 버리는 것을 권해요." else empty end)
' <<<"$result")"
echo "$md"
[ -z "${GITHUB_STEP_SUMMARY:-}" ] || echo "$md" >> "$GITHUB_STEP_SUMMARY"

details="$(jq -r --arg green "$green_line" '
  "*\(.title)* · 기대 `\(.expected.decision)` → 실제 `\(.actual.decision)`\(if .actual.source then " (\(.actual.source))" else "" end)",
  (if .actual.reason then "AI 근거: _\(.actual.reason)_" else empty end),
  (.checks[] | "\(if .ok then ":white_check_mark:" else ":x:" end) \(.name): \(.detail)"),
  (if $green != "" then "green(주입 쪽): \($green)" else empty end),
  (if .promotion_unsafe then "*:warning: 장애가 남아 있을 수 있어요. 이 green을 승격하지 마세요.* 아래 버튼으로 green을 버릴 수 있어요." else empty end)
' <<<"$result")"
output "result=$verdict"
output "promotion-unsafe=$(jq -r .promotion_unsafe <<<"$result")"
output_multiline details "$details"
[ "$verdict" = pass ]
