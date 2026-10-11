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

# Extra routes go to other green Services in the same namespace, keeping the path prefix.
out="$(render "${auth[@]}" --set 'previewAuth.routes[0].path=/api/' \
  --set 'previewAuth.routes[0].service=be-preview' --set 'previewAuth.routes[0].port=8000' \
  --show-only templates/preview-auth.yaml)"
printf '%s\n' "$out" | grep -q -- '--upstream=http://be-preview.default.svc.cluster.local:8000/api/'
printf '%s\n' "$out" | grep -q -- '--upstream=http://auth-preview.default.svc.cluster.local:80/'
fails "${auth[@]}" --set 'previewAuth.routes[0].path=api' --set 'previewAuth.routes[0].service=be-preview' --set 'previewAuth.routes[0].port=8000'
fails "${auth[@]}" --set 'previewAuth.routes[0].path=/api/' --set 'previewAuth.routes[0].service=http://evil' --set 'previewAuth.routes[0].port=8000'
fails "${auth[@]}" --set 'previewAuth.routes[0].path=/api/' --set 'previewAuth.routes[0].service=be-preview'

# The active Ingress still never routes to preview.
if render "${auth[@]}" --set ingress.enabled=true --set ingress.group=g --show-only templates/ingress.yaml \
  | grep -q 'auth-preview'; then
  echo 'Active Ingress targets preview' >&2; exit 1
fi

# GKE: preview-only TLS and static IP; the active Ingress keeps its own address and no certificate.
gke=("${auth[@]}" --set ingress.enabled=true --set ingress.className=
  --set-string 'ingress.annotations.kubernetes\.io/ingress\.class=gce'
  --set-string 'ingress.annotations.kubernetes\.io/ingress\.global-static-ip-name=active-ip')
out="$(render "${gke[@]}" --set previewAuth.ingress.managedCertificate=true \
  --set-string 'previewAuth.ingress.annotations.kubernetes\.io/ingress\.global-static-ip-name=green-ip' \
  --set-string 'previewAuth.ingress.annotations.kubernetes\.io/ingress\.allow-http=false' \
  --show-only templates/preview-auth.yaml)"
# Annotation values are templates, so one target file can name a per-namespace address.
out2="$(render "${gke[@]}" --namespace test \
  --set-string 'previewAuth.ingress.annotations.kubernetes\.io/ingress\.global-static-ip-name=green-{{ .Release.Namespace }}' \
  --show-only templates/preview-auth.yaml)"
printf '%s\n' "$out2" | grep -q 'kubernetes.io/ingress.global-static-ip-name: green-test'
printf '%s\n' "$out" | grep -q '^kind: ManagedCertificate$'
printf '%s\n' "$out" | grep -A2 'domains:' | grep -q '"green.example.test"'
printf '%s\n' "$out" | grep -q 'networking.gke.io/managed-certificates: auth-preview-auth'
printf '%s\n' "$out" | grep -q 'kubernetes.io/ingress.global-static-ip-name: green-ip'
printf '%s\n' "$out" | grep -q 'kubernetes.io/ingress.class: gce'
printf '%s\n' "$out" | grep -q 'kubernetes.io/ingress.allow-http: "false"'
active="$(render "${gke[@]}" --set previewAuth.ingress.managedCertificate=true \
  --set-string 'previewAuth.ingress.annotations.kubernetes\.io/ingress\.global-static-ip-name=green-ip' \
  --show-only templates/ingress.yaml)"
printf '%s\n' "$active" | grep -q 'kubernetes.io/ingress.global-static-ip-name: active-ip'
if printf '%s\n' "$active" | grep -Eq 'managed-certificates|green-ip|allow-http|tls:'; then
  echo 'preview Ingress settings leaked into the active Ingress' >&2; exit 1
fi
# Sharing the active static IP, or a ManagedCertificate on a non-GKE Ingress, fails.
fails "${gke[@]}"
fails "${auth[@]}" --set ingress.enabled=true --set ingress.group=g --set previewAuth.ingress.managedCertificate=true
# A pre-made TLS Secret goes to spec.tls on the green host only.
out="$(render "${auth[@]}" --set ingress.enabled=true --set ingress.className=nginx \
  --set previewAuth.ingress.tlsSecretName=green-tls --show-only templates/preview-auth.yaml)"
printf '%s\n' "$out" | grep -A4 '^  tls:' | grep -q 'secretName: green-tls'
printf '%s\n' "$out" | grep -A4 '^  tls:' | grep -q '"green.example.test"'
test "$(printf '%s\n' "$out" | grep -c '^kind: ManagedCertificate$')" = 0

# onprem (no Ingress): proxy and Service only, the tunnel targets <release>-preview-auth.
out="$(render "${auth[@]}" --show-only templates/preview-auth.yaml)"
test "$(printf '%s\n' "$out" | grep -c '^kind: Ingress$')" = 0
printf '%s\n' "$out" | grep -q '^kind: Service$'
echo 'Preview auth chart regression passed'
