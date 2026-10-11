#!/usr/bin/env bash
# Regression: GKE active Ingress gets its own ManagedCertificate and static IP (T38), without touching ALB or green.
set -euo pipefail
chart="$(cd "$(dirname "$0")/.." && pwd)"
base=(--set image.repository=r --set image.tag=t --set ingress.enabled=true)
gke=("${base[@]}" --set ingress.className= --set ingress.host=gcp.example.test
  --set-string 'ingress.annotations.kubernetes\.io/ingress\.global-static-ip-name=app-{{ .Release.Namespace }}')
render() { helm template app "$chart" "$@" --show-only templates/ingress.yaml; }
fails() { if helm template app "$chart" "$@" >/dev/null 2>&1; then echo "expected failure: $*" >&2; exit 1; fi; }

# Off by default: one Ingress, no certificate.
out="$(render "${gke[@]}" --namespace prod)"
test "$(printf '%s\n' "$out" | grep -c '^kind: ManagedCertificate$')" = 0
# Annotation values are templates: one target file names a per-namespace address.
printf '%s\n' "$out" | grep -Eq 'kubernetes.io/ingress.global-static-ip-name: "?app-prod"?$'

out="$(render "${gke[@]}" --namespace prod --set ingress.managedCertificate=true)"
test "$(printf '%s\n' "$out" | grep -c '^kind: ManagedCertificate$')" = 1
test "$(printf '%s\n' "$out" | grep -c '^kind: Ingress$')" = 1
printf '%s\n' "$out" | grep -A2 'domains:' | grep -q '"gcp.example.test"'
printf '%s\n' "$out" | grep -Eq 'networking.gke.io/managed-certificates: "?app"?$'
printf '%s\n' "$out" | grep -q 'host: "gcp.example.test"'
if printf '%s\n' "$out" | grep -q -- '[^-]---$'; then echo 'document separator glued to the previous line' >&2; exit 1; fi

# Needs a host and a GKE Ingress.
fails "${base[@]}" --set ingress.className= --set ingress.managedCertificate=true
fails "${base[@]}" --set ingress.className=alb --set ingress.group=g --set ingress.host=x.test --set ingress.managedCertificate=true

# ALB output keeps its annotations.
alb="$(render "${base[@]}" --set ingress.group=g --set ingress.host=aws.example.test)"
printf '%s\n' "$alb" | grep -q 'alb.ingress.kubernetes.io/group.name: g'
printf '%s\n' "$alb" | grep -q 'alb.ingress.kubernetes.io/ssl-redirect: "443"'
echo 'Ingress managed certificate regression passed'
