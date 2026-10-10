#!/usr/bin/env bash
# Regression: no public route may target preview, including legacy values.
set -euo pipefail
chart="$(cd "$(dirname "$0")/.." && pwd)"
for class in alb gce nginx; do
  for host in '' example.test; do
    for strategy in blueGreen rolling; do
      rendered="$(helm template private "$chart" --set image.repository=r --set image.tag=t \
        --set ingress.enabled=true --set ingress.className="$class" --set ingress.group=test \
        --set ingress.host="$host" --set ingress.previewPort=9999 --set deployStrategy="$strategy")"
      ingress="$(helm template private "$chart" --show-only templates/ingress.yaml \
        --set image.repository=r --set image.tag=t --set ingress.enabled=true \
        --set ingress.className="$class" --set ingress.group=test --set ingress.host="$host" \
        --set ingress.previewPort=9999 --set deployStrategy="$strategy")"
      test "$(printf '%s\n' "$ingress" | grep -c '^kind: Ingress$')" = 1
      if printf '%s\n' "$ingress" | grep -Eq 'preview|9999'; then
        echo 'Public preview route rendered' >&2; exit 1
      fi
      if [ "$strategy" = blueGreen ]; then
        printf '%s\n' "$rendered" | grep -q 'previewService: private-preview'
        test "$(printf '%s\n' "$rendered" | grep -c 'type: ClusterIP')" = 2
      fi
    done
  done
done
echo 'Private preview chart regression: 12 cases passed'
