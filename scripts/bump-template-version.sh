#!/usr/bin/env bash
# 대상 레포(demo-app)의 템플릿 버전 표기를 한 번에 올린다.
#
#   bump-template-version.sh <vX.Y.Z> [대상 레포 경로]
#
# 바꾸는 곳 (vX.Y.Z로 고정된 것만. @v1 같은 메이저 태그는 그대로 둔다)
#   .deploy/config.yaml        template_version: vX.Y.Z
#   .github/workflows/*.yml    one-tatchi-platform/...@vX.Y.Z, template-ref: vX.Y.Z, chart-version: X.Y.Z
#   *.tf                       one-tatchi-platform.git//...?ref=vX.Y.Z
set -euo pipefail

new="${1:?새 버전(vX.Y.Z)이 필요하다}"
root="${2:-.}"
semver='v[0-9]+\.[0-9]+\.[0-9]+'

[[ "$new" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "버전 형식은 vX.Y.Z: $new" >&2; exit 1; }
ver="${new#v}"
cd "$root"

config=.deploy/config.yaml
[[ -f "$config" ]] || { echo "$config 가 없다" >&2; exit 1; }
pins='{}'
if grep -q '^infra_versions:' "$config"; then
  pins="$(yq -o=json '.infra_versions' "$config")"
  jq -e 'type == "object" and all(to_entries[]; (.key == "aws" or .key == "gcp" or .key == "onprem") and (.value | test("^v[0-9]+\\.[0-9]+\\.[0-9]+$")))' <<<"$pins" >/dev/null
fi
sed -E -i "s/^(template_version:[[:space:]]*[\"']?)${semver}/\1${new}/" "$config"

if [[ -d .github/workflows ]]; then
  find .github/workflows -type f \( -name '*.yml' -o -name '*.yaml' \) -print0 |
    xargs -0 -r sed -E -i \
      -e "s#(one-tatchi-platform/[^@[:space:]]+@)${semver}#\1${new}#g" \
      -e "s/^([[:space:]]*template-ref:[[:space:]]*[\"']?)${semver}/\1${new}/" \
      -e "s/^([[:space:]]*chart-version:[[:space:]]*[\"']?)[0-9]+\.[0-9]+\.[0-9]+/\1${ver}/"
fi

find . -type f -name '*.tf' -not -path '*/.terraform/*' -print0 |
  xargs -0 -r sed -E -i "s#(one-tatchi-platform(\.git)?//[^\"?]*\?ref=)${semver}#\1${new}#g"

# Explicit migration pins survive automated template updates. Removing one is a reviewed change.
for scope in aws gcp onprem; do
  pin="$(jq -r --arg s "$scope" '.[$s] // empty' <<<"$pins")"
  if [[ -n "$pin" && -d "infra/envs/$scope" ]]; then
    find "infra/envs/$scope" -type f -name '*.tf' -not -path '*/.terraform/*' -print0 |
      xargs -0 -r sed -E -i "s#(one-tatchi-platform(\.git)?//[^\"?]*\?ref=)${semver}#\1${pin}#g"
  fi
done

# v2 app extensions follow the app contract, even in a pinned v1 cloud root.
find . -type f -name '*.tf' -not -path '*/.terraform/*' -print0 |
  xargs -0 -r sed -E -i "s#(one-tatchi-platform(\.git)?//modules/(preview_auth/aws|db_link/tailscale)\?ref=)${semver}#\1${new}#g"

echo "템플릿 버전 → ${new}"
