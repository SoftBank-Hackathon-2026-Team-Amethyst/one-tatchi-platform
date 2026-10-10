#!/usr/bin/env bash
# Regression: green is public only through the OIDC proxy, never directly (ADR 0015).
set -euo pipefail
chart="$(cd "$(dirname "$0")/.." && pwd)"
base=(--set image.repository=r --set image.tag=t)
auth=(--set previewAuth.enabled=true --set previewAuth.host=green.example.test
  --set previewAuth.issuerUrl=https://issuer.example.test --set previewAuth.remoteKey=preview-auth)
render() { helm template auth "$chart" "${base[@]}" "$@"; }
fails() { if render "$@" >/dev/null 2>&1; then echo "expected failure: $*" >&2; exit 1; fi; }

# Off by default: no proxy, no extra Ingress.
test -z "$(render --show-only templates/preview-auth.yaml 2>/dev/null || true)"

# Missing settings or unsupported strategy fail instead of opening green.
fails --set previewAuth.enabled=true
fails "${auth[@]}" --set previewAuth.issuerUrl=
fails "${auth[@]}" --set previewAuth.remoteKey=
fails "${auth[@]}" --set deployStrategy=rolling
fails "${auth[@]}" --set ingress.enabled=true --set ingress.group=g --set ingress.host=green.example.test

for class in alb gce nginx; do
  out="$(render "${auth[@]}" --set ingress.enabled=true --set ingress.className="$class" \
    --set ingress.group=g --set ingress.host=example.test --show-only templates/preview-auth.yaml)"
  # The only Ingress for green targets the proxy, on the green host.
  test "$(printf '%s\n' "$out" | grep -c '^kind: Ingress$')" = 1
  printf '%s\n' "$out" | grep -q 'host: "green.example.test"'
  test "$(printf '%s\n' "$out" | grep -A3 'service:$' | grep -c 'name: auth-preview-auth')" = 1
  if printf '%s\n' "$out" | grep -A3 'service:$' | grep -q 'name: auth-preview$'; then
    echo 'Ingress targets preview directly' >&2; exit 1
  fi
  printf '%s\n' "$out" | grep -q -- '--upstream=http://auth-preview.default.svc.cluster.local:80/'
  printf '%s\n' "$out" | grep -q -- '--redirect-url=https://green.example.test/oauth2/callback'
done

# The active Ingress still never routes to preview.
if render "${auth[@]}" --set ingress.enabled=true --set ingress.group=g --show-only templates/ingress.yaml \
  | grep -q 'auth-preview'; then
  echo 'Active Ingress targets preview' >&2; exit 1
fi

# onprem (no Ingress): proxy and Service only, the tunnel targets <release>-preview-auth.
out="$(render "${auth[@]}" --show-only templates/preview-auth.yaml)"
test "$(printf '%s\n' "$out" | grep -c '^kind: Ingress$')" = 0
printf '%s\n' "$out" | grep -q '^kind: Service$'
echo 'Preview auth chart regression passed'
