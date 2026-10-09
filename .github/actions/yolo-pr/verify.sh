#!/usr/bin/env bash
# An AI recommendation or a successful deploy job alone does not prove promotion.
set -euo pipefail
: "${SERVICES:?}" "${NAMESPACE:?}" "${TAG:?}"
jq -e 'type == "array" and length > 0' <<<"$SERVICES" >/dev/null
deadline=$((SECONDS + ${WAIT_SECONDS:-60}))
while :; do
  pending=0
  for name in $(jq -r '.[].name' <<<"$SERVICES"); do
    rollout="$(kubectl get rollout "$name" -n "$NAMESPACE" -o json)"
    hash="$(jq -r '.status.stableRS // ""' <<<"$rollout")"
    if ! jq -e '.status.phase == "Healthy" and .status.stableRS != null and
      .status.stableRS == .status.currentPodHash' <<<"$rollout" >/dev/null; then
      pending=1; continue
    fi
    replicas="$(kubectl get rs -n "$NAMESPACE" -l "rollouts-pod-template-hash=$hash" -o json)"
    expected=""
    if [ -n "${IMAGES:-}" ]; then
      expected="$(jq -er --arg name "$name" '.[$name] | .repository + "@" + .digest' <<<"$IMAGES")"
    fi
    if ! jq -e --arg name "$name" --arg tag "$TAG" --arg expected "$expected" '
      any(.items[]; any(.metadata.ownerReferences[]?; .kind == "Rollout" and .name == $name) and
        (.spec.template.spec.containers[0].image | if $expected != "" then . == $expected else endswith(":" + $tag) end))
    ' <<<"$replicas" >/dev/null; then pending=1; fi
  done
  [ "$pending" = 0 ] && break
  [ "$SECONDS" -lt "$deadline" ] || { echo "::error::모든 서비스가 이 커밋으로 승격되지 않았다"; exit 1; }
  sleep 5
done
echo "promoted=true" >> "$GITHUB_OUTPUT"
