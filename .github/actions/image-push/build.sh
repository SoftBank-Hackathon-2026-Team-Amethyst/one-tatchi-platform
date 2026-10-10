#!/usr/bin/env bash
# One build per service; both architecture manifests are scanned before publishing a bundle.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
: "${CONTEXT:?}" "${GITHUB_SHA:?}" "${RUNNER_TEMP:?}"
key="$(python3 "$here/bundle.py" key "$CONTEXT")"
bundle="$RUNNER_TEMP/image-bundles/$key"

# PR 검사 시 해당 서비스 디렉토리에 변경사항이 없으면 빌드와 스캔을 건너뛴다.
if [ "${GITHUB_EVENT_NAME:-}" = "pull_request" ] && [ -n "${BASE_SHA:-}" ]; then
  if ! git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null; then
    git fetch origin "$BASE_SHA" --depth=1 2>/dev/null || true
  fi
  if git cat-file -e "$BASE_SHA^{commit}" 2>/dev/null; then
    if git diff --quiet "$BASE_SHA" HEAD -- "$CONTEXT"; then
      echo "::notice::$CONTEXT 디렉토리에 변경사항이 없으므로 PR 이미지 빌드 및 취약점 검사를 건너뜁니다."
      echo "key=$key" >> "$GITHUB_OUTPUT"
      echo "skipped=true" >> "$GITHUB_OUTPUT"
      exit 0
    fi
  fi
fi

mkdir -p "$bundle"
rm -f "$bundle/verified.json"
cache_scope="buildx-${CONTEXT//\//-}"
docker buildx build --platform linux/amd64,linux/arm64 \
  --provenance=false --sbom=false \
  --label "org.opencontainers.image.source=https://github.com/$GITHUB_REPOSITORY" \
  --cache-from "type=gha,scope=$cache_scope" \
  --cache-to "type=gha,mode=max,scope=$cache_scope" \
  --tag "checked:$GITHUB_SHA" --output "type=oci,dest=$bundle/image.tar" "$CONTEXT"
python3 "$here/bundle.py" inspect "$bundle/image.tar" --extract "$bundle/oci" > "$bundle/layout.json"
ignore=(); [ ! -f .trivyignore ] || ignore=(--ignorefile .trivyignore)
for platform in linux/amd64 linux/arm64; do
  manifest="$(jq -r --arg p "$platform" '.platforms[$p]' "$bundle/layout.json")"
  trivy image --input "$bundle/oci@$manifest" --platform "$platform" --scanners vuln \
    --format json --output "$bundle/${platform#linux/}-scan.json" \
    --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 "${ignore[@]}"
done
python3 "$here/bundle.py" record "$bundle"
rm -rf "$bundle/oci" # only the extracted copy of this job's bundle; archive remains immutable
echo "key=$key" >> "$GITHUB_OUTPUT"
echo "bundle=$bundle" >> "$GITHUB_OUTPUT"
