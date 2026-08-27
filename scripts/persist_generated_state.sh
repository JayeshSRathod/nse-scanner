#!/usr/bin/env bash
set -euo pipefail

commit_message="${1:?commit message is required}"
remote_name="${2:-origin}"
remote_branch="${3:-main}"

if git diff --cached --quiet; then
  echo "No generated state changes to commit."
  exit 0
fi

git commit -m "$commit_message"

# Daily scanners finish close together and write different generated files.
# Rebase each generated-state commit on the latest main before pushing so a
# harmless race does not make an otherwise successful Telegram run appear red.
for attempt in 1 2 3; do
  echo "Generated-state push attempt ${attempt}/3"
  git fetch "$remote_name" "$remote_branch"
  if ! git rebase "$remote_name/$remote_branch"; then
    git rebase --abort || true
    echo "Generated-state rebase conflicted; manual review is required."
    exit 1
  fi
  if git push "$remote_name" "HEAD:$remote_branch"; then
    exit 0
  fi
  sleep $((attempt * 2))
done

echo "Generated-state push failed after three attempts."
exit 1
