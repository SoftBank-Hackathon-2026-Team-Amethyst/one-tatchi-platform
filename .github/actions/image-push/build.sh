#!/usr/bin/env bash
# One build per service; both architecture manifests are scanned before publishing a bundle.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
: "${CONTEXT:?}" "${GITHUB_SHA:?}" "${RUNNER_TEMP:?}"
key="$(python3 "$here/bundle.py" key "$CONTEXT")"
bundle="$RUNNER_TEMP/image-bundles/$key"
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
