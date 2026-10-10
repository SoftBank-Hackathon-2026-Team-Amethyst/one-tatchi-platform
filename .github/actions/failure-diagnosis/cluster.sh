#!/usr/bin/env bash
# 배포가 실패한 시점의 클러스터 상태를 모은다 (T12). 실패한 deploy job 안의 if: failure() 단계에서 돈다.
# onprem은 맥북 self-hosted 러너라 bash · kubectl · jq · sed만 쓴다. 결과는 비밀값을 가린 뒤 artifact로 올린다
# (공개 레포의 artifact는 다른 사람도 받을 수 있다).
#   NAMESPACE  배포 네임스페이스 (test | prod)
#   RELEASES   서비스(Rollout) 이름들, 공백 구분
#   OUT        결과 JSON 경로: {"cluster": {...}, "collection": {"status", "detail"}}
#   KUBECTL    (테스트용) kubectl 대신 쓸 명령
# 하나가 실패해도 멈추지 않고 collection.status를 failed로, 이유를 detail에 남긴다. 종료 코드는 항상 0이다.
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
KUBECTL="${KUBECTL:-kubectl}"
NS="${NAMESPACE:?NAMESPACE가 필요하다}"
OUT="${OUT:?OUT이 필요하다}"
read -r -a releases <<<"${RELEASES:-}" || true   # macOS bash 3.2: 빈 배열은 ${releases[@]+…}로 쓴다
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

status=ok detail=""
problem() { status=failed; detail="${detail:+$detail; }$1"; }
first_line() { head -n 1 "$1" | cut -c1-160; }
k() { $KUBECTL "$@" 2>"$tmp/err"; }

# 1. 서비스별 Rollout 상태
rollouts='[]'
for r in ${releases[@]+"${releases[@]}"}; do
  if out="$(k get rollout "$r" -n "$NS" -o json)"; then
    rollouts="$(jq -c --argjson acc "$rollouts" --arg n "$r" \
      '$acc + [{name: $n, phase: (.status.phase // "Unknown"), message: ((.status.message // "") | .[:1000])}]' <<<"$out")"
  else
    problem "rollout $r: $(first_line "$tmp/err")"
  fi
done

# 2. 네임스페이스의 Warning 이벤트 (최근 40개)
events='[]'
if out="$(k get events -n "$NS" --field-selector type=Warning -o json)"; then
  events="$(jq -c '[.items // [] | sort_by(.lastTimestamp // .eventTime // .metadata.creationTimestamp // "") | reverse
    | .[:40][] | {reason: (.reason // ""), object: "\(.involvedObject.kind // "")/\(.involvedObject.name // "")",
      message: ((.message // "") | .[:500]), count: (.count // 1)}]' <<<"$out")" || { events='[]'; problem "events: 형식을 읽지 못했다"; }
else
  problem "events: $(first_line "$tmp/err")"
fi

# 3. Ready가 아니거나 재시작한 서비스 파드 (최대 10개)와 로그 끝
pods='[]'
if [ "${#releases[@]}" -gt 0 ]; then
  selector="app.kubernetes.io/name in ($(IFS=,; echo "${releases[*]}"))"
  if out="$(k get pods -n "$NS" -l "$selector" -o json)"; then
    bad="$(jq -c '[.items // [] | .[] | {
        name: .metadata.name, phase: (.status.phase // "Unknown"),
        ready: ([.status.conditions // [] | .[] | select(.type == "Ready") | .status] == ["True"]),
        restarts: ([.status.containerStatuses // [] | .[].restartCount] | add // 0),
        reason: ([.status.containerStatuses // [] | .[] | (.state.waiting.reason // .state.terminated.reason // .lastState.terminated.reason // empty)] | first // "")}
      | select((.ready | not) or .restarts > 0)] | .[:10]' <<<"$out")" || { bad='[]'; problem "pods: 형식을 읽지 못했다"; }
    while IFS=$'\t' read -r name restarts; do
      [ -n "$name" ] || continue
      # 재시작한 파드는 직전 컨테이너의 로그에 죽은 이유가 있다.
      if [ "$restarts" -gt 0 ] && k logs "$name" -n "$NS" --all-containers --previous --tail=60 >"$tmp/log"; then :;
      elif k logs "$name" -n "$NS" --all-containers --tail=60 >"$tmp/log"; then :;
      else printf '(로그를 읽지 못했다: %s)\n' "$(first_line "$tmp/err")" >"$tmp/log"; fi
      pods="$(jq -c --argjson acc "$pods" --arg n "$name" --rawfile log "$tmp/log" --argjson bad "$bad" \
        '$acc + [$bad[] | select(.name == $n) | {name, phase, reason, restarts, log_tail: ($log | .[-4000:])}]' <<<'null')"
    done < <(jq -r '.[] | [.name, (.restarts | tostring)] | @tsv' <<<"$bad")
  else
    problem "pods: $(first_line "$tmp/err")"
  fi
fi

# 4. 마이그레이션 Job (<서비스>-migration). 실패한 hook Job은 남아 있다(hook-delete-policy: hook-succeeded).
jobs='[]'
for r in ${releases[@]+"${releases[@]}"}; do
  if out="$(k get job "$r-migration" -n "$NS" -o json)"; then
    state="$(jq -r 'if (.status.succeeded // 0) > 0 then "Complete" elif (.status.failed // 0) > 0 then "Failed" else "Active" end' <<<"$out")"
    k logs "job/$r-migration" -n "$NS" --tail=80 >"$tmp/log" || printf '(로그를 읽지 못했다: %s)\n' "$(first_line "$tmp/err")" >"$tmp/log"
    jobs="$(jq -c --argjson acc "$jobs" --arg n "$r-migration" --arg s "$state" --rawfile log "$tmp/log" \
      '$acc + [{name: $n, status: $s, log_tail: ($log | .[-4000:])}]' <<<'null')"
  elif ! grep -Eqi 'not ?found' "$tmp/err"; then
    problem "job $r-migration: $(first_line "$tmp/err")"
  fi
done

result="$(jq -n --argjson r "$rollouts" --argjson e "$events" --argjson p "$pods" --argjson j "$jobs" \
  --arg status "$status" --arg detail "$detail" \
  '{cluster: {rollouts: $r, events: $e, pods: $p, migration_jobs: $j},
    collection: {status: $status, detail: (if $detail == "" then null else ($detail | .[:300]) end)}}')"
# 가린 뒤에도 JSON이 맞는지 확인한다. 깨지면 내용 대신 실패만 남긴다(가리지 않은 원문을 올리지 않는다).
if printf '%s' "$result" | sed -E -f "$here/redact.sed" >"$tmp/redacted.json" && jq -e . "$tmp/redacted.json" >/dev/null 2>&1; then
  mkdir -p "$(dirname "$OUT")"; cp "$tmp/redacted.json" "$OUT"
else
  jq -n '{cluster: {rollouts: [], events: [], pods: [], migration_jobs: []},
          collection: {status: "failed", detail: "비밀값 가리기 뒤 JSON이 깨져 내용을 버렸다"}}' >"$OUT"
fi
echo "클러스터 상태: $(jq -r '.collection.status' "$OUT") ($OUT)"
exit 0
