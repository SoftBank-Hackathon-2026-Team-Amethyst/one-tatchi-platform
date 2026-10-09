#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/runner"
export RUNNER_TEMP="$tmp/runner" CALLS="$tmp/calls"
export GCP_PROJECT=test-project GCP_REGION=asia-northeast3
export ECR_REGISTRY=test.ecr OWNER=test-owner GITHUB_ACTOR=actor GH_TOKEN=test SOURCE=test-source
cat > "$tmp/bin/gcloud" <<'EOF'
#!/usr/bin/env bash
echo "gcloud $*" >> "$CALLS"
if [ "$1 $2 $3" = 'artifacts docker images' ]; then exit "${MISSING:-0}"; fi
EOF
cat > "$tmp/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >> "$CALLS"
EOF
cat > "$tmp/bin/aws" <<'EOF'
#!/usr/bin/env bash
echo "aws $*" >> "$CALLS"
EOF
cat > "$tmp/bin/trivy" <<'EOF'
#!/usr/bin/env bash
echo "trivy $*" >> "$CALLS"
EOF
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"
for target in aws gcp onprem; do
  : > "$CALLS"
  actual="$(bash "$here/../push.sh" "$target" demo-app-be be abc)"
  case "$target" in
    aws) expected=test.ecr/demo-app-be ;;
    gcp) expected=asia-northeast3-docker.pkg.dev/test-project/demo-app-be/demo-app-be ;;
    onprem) expected=ghcr.io/test-owner/demo-app-be ;;
  esac
  [ "$actual" = "$expected" ]
  ! grep -q 'docker build' "$CALLS"
done
: > "$CALLS"
MISSING=1 bash "$here/../push.sh" gcp demo-app-be be abc >/dev/null
grep -q 'docker build .*test-project/demo-app-be/demo-app-be:abc' "$CALLS"
grep -q 'trivy image' "$CALLS"
grep -q 'docker push .*test-project/demo-app-be/demo-app-be:abc' "$CALLS"
