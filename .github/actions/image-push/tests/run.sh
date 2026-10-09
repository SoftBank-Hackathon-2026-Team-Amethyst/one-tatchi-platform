#!/usr/bin/env bash
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
if bash "$here/../push.sh" onprem app . sha 2>/dev/null; then
  echo "legacy build-on-deploy unexpectedly succeeded" >&2
  exit 1
fi
python3 -B -m unittest discover -s "$here"
