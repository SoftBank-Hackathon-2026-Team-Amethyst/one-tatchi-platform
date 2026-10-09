#!/usr/bin/env bash
# 여러 서비스를 묶어 판단한다 (ADR 0005). deploy.yml은 한 job에서 서비스를 함께 배포하고 함께 승격 · 취소한다.
#   smoke    서비스마다 smoke.sh를 동시에 실행한다 (관찰 창은 한 번)
#   metrics  서비스마다 metrics.sh
#   judge    서비스마다 judge.sh → 묶음 결정: 모두 promote면 promote, 하나라도 abort면 전체 abort
#   act      서비스마다 act.sh로 묶음 결정을 실행(auto)하거나 기록(manual)한다
# 서비스별 결과는 $WORK_ROOT/<release>/, 묶음 결정은 $WORK_ROOT/judgment.json
# step 출력: judge → decision · reason · report, act → executed
#
# 환경변수: WORK_ROOT, RELEASES(공백 구분) + 각 스크립트의 환경변수
set -uo pipefail

cmd="${1:?사용: group.sh smoke | metrics | judge | act}"
: "${WORK_ROOT:?}" "${RELEASES:?}"
here="$(cd "$(dirname "$0")" && pwd)"
read -r -a releases <<<"$RELEASES"
mkdir -p "$WORK_ROOT"

output() { [ -z "${GITHUB_OUTPUT:-}" ] || echo "$1" >> "$GITHUB_OUTPUT"; }

case "$cmd" in
  smoke)
    pids=()
    for r in "${releases[@]}"; do
      WORK_DIR="$WORK_ROOT/$r" RELEASE="$r" bash "$here/smoke.sh" > "$WORK_ROOT/$r.smoke.log" 2>&1 &
      pids+=($!)
    done
    status=0
    for i in "${!releases[@]}"; do
      wait "${pids[$i]}" || status=1
      echo "::group::smoke ${releases[$i]}"; cat "$WORK_ROOT/${releases[$i]}.smoke.log"; echo "::endgroup::"
    done
    exit "$status" ;;

  metrics)
    status=0
    for r in "${releases[@]}"; do
      WORK_DIR="$WORK_ROOT/$r" RELEASE="$r" bash "$here/metrics.sh" || status=1
    done
    exit "$status" ;;

  judge)
    files=()
    for r in "${releases[@]}"; do
      WORK_DIR="$WORK_ROOT/$r" RELEASE="$r" GITHUB_OUTPUT="" bash "$here/judge.sh"
      files+=("$WORK_ROOT/$r/judgment.json")
    done
    group="$WORK_ROOT/judgment.json"
    jq -s '
      (if all(.[]; .decision == "promote") then "promote" else "abort" end) as $d
      | {decision: $d,
         reason: ((if $d == "promote" then . else map(select(.decision == "abort")) end)
                  | map("\(.release): \(.reason)") | join(" / ")),
         services: (map({key: .release, value: {decision, source, reason}}) | from_entries)}
    ' "${files[@]}" > "$group" 2>/dev/null \
      || jq -n '{decision: "abort", reason: "서비스 판단 결과를 읽지 못해 abort한다.", services: {}}' > "$group"
    decision="$(jq -r .decision "$group")"

    # 묶음이 abort면 promote로 판단한 서비스도 함께 abort한다 (BE · FE 버전이 섞이지 않게)
    if [ "$decision" = abort ]; then
      aborted="$(jq -r '[.services | to_entries[] | select(.value.decision == "abort") | .key] | join(", ")' "$group")"
      for f in "${files[@]}"; do
        [ -f "$f" ] || continue
        jq --arg who "${aborted:-다른 서비스}" '
          if .decision == "promote" then
            .ai_decision_alone = "promote" | .decision = "abort" | .source = "group"
            | .reason = "\($who)이(가) abort라 함께 abort한다. 이 서비스만 보면: \(.reason)"
          else . end' "$f" > "$f.tmp" && mv "$f.tmp" "$f"
      done
    fi

    reason="$(jq -r .reason "$group")"
    echo "묶음 판단: $decision — $reason"
    output "decision=$decision"
    output "reason<<__REASON__"; output "$reason"; output "__REASON__"
    output "report=$group" ;;

  act)
    decision="$(jq -r '.decision // "abort"' "$WORK_ROOT/judgment.json" 2>/dev/null || echo abort)"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
      echo "## AI 승격 판단 (서비스 ${#releases[@]}개 묶음): $decision" >> "$GITHUB_STEP_SUMMARY"
    fi
    status=0 executed=""
    for r in "${releases[@]}"; do
      out="$WORK_ROOT/$r/act-output"
      mkdir -p "$WORK_ROOT/$r"; : > "$out"
      WORK_DIR="$WORK_ROOT/$r" RELEASE="$r" GITHUB_OUTPUT="$out" bash "$here/act.sh" || status=1
      e="$(sed -n 's/^executed=//p' "$out")"
      [ -z "$e" ] || executed="$e"
    done
    # 한 서비스라도 실제로 실행했으면 그 조작을 남긴다. 실행 실패는 step 실패(status)로 드러난다.
    output "executed=$executed"
    exit "$status" ;;

  *)
    echo "::error::group.sh: 알 수 없는 명령 $cmd"
    exit 1 ;;
esac
