#!/usr/bin/env bash
set -euo pipefail
echo "::error::build-on-deploy was removed in v2.0; use checks artifacts and publish.py (same workflow run)" >&2
exit 1
