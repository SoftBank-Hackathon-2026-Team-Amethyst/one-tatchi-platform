#!/usr/bin/env bash
# Display-only context. Never changes button payloads or deployment policy.
set -euo pipefail
escape() { printf '%s' "$1" | sed 's/\&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }
[ -z "${FLOW:-}${DEPLOY_ENVIRONMENT:-}${STAGE:-}${NEXT_ACTION:-}" ] && exit 0
[ -z "${FLOW:-}" ] || printf '*배포 경로:* %s\n' "$(escape "$FLOW")"
[ -z "${BRANCH:-}" ] || printf '*소스 브랜치:* %s\n' "$(escape "$BRANCH")"
[ -z "${DEPLOY_ENVIRONMENT:-}" ] || printf '*배포 환경:* %s\n' "$(escape "$DEPLOY_ENVIRONMENT")"
[ -z "${STAGE:-}" ] || printf '*현재 단계:* %s\n' "$(escape "$STAGE")"
[ -z "${NEXT_ACTION:-}" ] || printf '*할 일:* %s\n' "$(escape "$NEXT_ACTION")"
