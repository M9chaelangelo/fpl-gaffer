#!/usr/bin/env bash
# One-shot deploy. Needs the GitHub CLI (`brew install gh` or see cli.github.com)
# and a one-time `gh auth login`. Everything after that is automatic.
set -euo pipefail

REPO="${1:-fpl-gaffer}"
USER="$(gh api user --jq .login)"

echo "==> creating $USER/$REPO"
git init -q -b main
git add -A
git -c user.email=gaffer@local -c user.name=gaffer commit -qm "gaffer: initial" || true
gh repo create "$REPO" --public --source=. --push

echo "==> allowing Actions to commit results"
gh api -X PUT "repos/$USER/$REPO/actions/permissions/workflow" \
  -f default_workflow_permissions=write -F can_approve_pull_request_reviews=false

echo "==> turning on Pages from /docs"
gh api -X POST "repos/$USER/$REPO/pages" \
  -f "source[branch]=main" -f "source[path]=/docs" 2>/dev/null \
  || gh api -X PUT "repos/$USER/$REPO/pages" \
       -f "source[branch]=main" -f "source[path]=/docs"

echo "==> first run"
gh workflow run gaffer.yml -f free_transfers=0 || \
  echo "   (start it by hand from the Actions tab if that failed)"

echo
echo "Done. Your page: https://${USER,,}.github.io/$REPO/"
echo "Give Pages a couple of minutes on the first build."
