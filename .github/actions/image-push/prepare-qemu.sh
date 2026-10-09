#!/usr/bin/env bash
# Authenticate before pulling QEMU. Never print credentials.
set -euo pipefail
retry() {
  local attempt
  for attempt in 1 2 3; do
    if "$@"; then return 0; fi
    if [ "$attempt" -eq 3 ]; then return 1; fi
    echo "Registry request failed; retrying ($attempt/3)" >&2
    sleep "$((attempt * 10))"
  done
}
login() {
  printf '%s' "$DOCKERHUB_TOKEN" | docker login docker.io --username "$DOCKERHUB_USERNAME" --password-stdin
}
if [ -n "${DOCKERHUB_USERNAME:-}" ] && [ -n "${DOCKERHUB_TOKEN:-}" ]; then
  retry login
elif [ -n "${DOCKERHUB_USERNAME:-}" ] || [ -n "${DOCKERHUB_TOKEN:-}" ]; then
  echo "::error::Both Docker Hub username and token are required when configured" >&2
  exit 1
else
  echo "Docker Hub credentials unavailable; using public pulls"
fi
image=docker.io/tonistiigi/binfmt:latest
retry docker pull "$image"
docker run --privileged --rm "$image" --install amd64,arm64
