#!/usr/bin/env bash
# Called after cluster authentication and before the app rollout. Never installs Metrics Server.
set -euo pipefail
values="${RUNTIME_STATUS_VALUES:-}"
if [ -z "$values" ] && [ -f .deploy/config.yaml ]; then
  values="$(yq -r '.runtime_status_values // ""' .deploy/config.yaml)"
fi
[ -n "$values" ] || exit 0
export RUNTIME_STATUS_VALUES="$values"
python3 - <<'PY'
import os
from pathlib import Path
root = Path.cwd().resolve()
path = (root / os.environ['RUNTIME_STATUS_VALUES']).resolve()
if not path.is_relative_to(root) or not path.is_file() or path.suffix not in ('.yaml', '.yml'):
    raise SystemExit('runtime-status values must be an existing YAML file inside the app repository')
PY
helm upgrade --install runtime-status "$CHART_REPO/runtime-status" \
  --version "$CHART_VERSION" --namespace "$NAMESPACE" --create-namespace \
  --values "$values" --wait --timeout 120s
# Missing Metrics API degrades only the resource cards. Inventory remains useful.
if ! python3 .platform/scripts/onprem/resource_metrics.py --namespace "$NAMESPACE" --wait-seconds 90; then
  echo '::warning::Resource Metrics API unavailable; Pod inventory remains enabled, CPU/memory will show unavailable'
fi
