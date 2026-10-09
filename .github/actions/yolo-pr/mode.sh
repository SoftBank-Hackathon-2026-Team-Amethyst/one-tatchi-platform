#!/usr/bin/env bash
set -euo pipefail
mode="${MODE:-manual}"
if [ "$mode" = branch ]; then
  mode=manual
  if [ "$GITHUB_EVENT_NAME" = push ]; then
    case "$GITHUB_REF" in
      refs/heads/yolo/*) mode=auto ;;
      refs/heads/main)
        prs="$(gh api "repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/pulls")"
        if jq -e --arg sha "$GITHUB_SHA" --arg repo "$GITHUB_REPOSITORY" '
          any(.[]; .merged_at != null and .merge_commit_sha == $sha and
            .base.ref == "main" and .head.repo.full_name == $repo and
            (.head.ref | startswith("yolo/")) and any(.labels[]; .name == "yolo"))
        ' <<<"$prs" >/dev/null; then mode=auto; fi ;;
    esac
  fi
fi
case "$mode" in auto|manual) ;; *) echo "::error::알 수 없는 promote-mode: $mode"; exit 1 ;; esac
echo "mode=$mode" >> "$GITHUB_OUTPUT"
