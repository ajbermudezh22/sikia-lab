#!/usr/bin/env bash
# Clone a codebase into workspace/ for reading. workspace/ is gitignored, so nothing
# from someone else's repo ends up in this one.
#
#   ./scripts/clone_target.sh git@github.com:org/repo.git
set -euo pipefail

REPO="${1:?usage: clone_target.sh <git-url>}"
NAME="$(basename "${REPO}" .git)"
DEST="$(dirname "$0")/../workspace/${NAME}"

mkdir -p "$(dirname "${DEST}")"

if [[ -d "${DEST}" ]]; then
  echo "${DEST} already exists — pulling instead"
  git -C "${DEST}" pull --ff-only
else
  git clone "${REPO}" "${DEST}"
fi

echo
echo "==> cloned to workspace/${NAME}"
echo "==> shape:"
git -C "${DEST}" ls-files | sed 's/.*\.//' | sort | uniq -c | sort -rn | head -10
echo
echo "==> recent activity:"
git -C "${DEST}" log --oneline -10
echo
echo "Next:  /case-study ${NAME}"
