#!/usr/bin/env bash
# bootstrap-branch-protection.sh — apply Marketplace-friendly branch
# protection to the default branch of a single repo.
#
# Part of the bos-marketplace-kit toolkit. This is the fallback for
# when org-level rulesets aren't available (e.g. you only have repo-
# admin rights, or the repo is in a personal account). Branch
# protection cannot do `file_path_restriction` — that is a ruleset-only
# feature — so this script configures the surrounding policies and
# relies on the kit's `guard` workflow + `promote` composite to do the
# path-block enforcement.
#
# Usage:
#   ./bootstrap-branch-protection.sh <owner/repo> [<branch>]
#
# Default branch is `main`.
#
# Requires: `gh` CLI authenticated with repo-admin scope.

set -euo pipefail

die() {
  printf 'bootstrap-branch-protection: %s\n' "$*" >&2
  exit 1
}

REPO="${1:-}"
BRANCH="${2:-main}"

[ -n "${REPO}" ] || die "usage: $0 <owner/repo> [<branch>]"
case "${REPO}" in
  */*) ;;
  *) die "first arg must be in 'owner/repo' form, got: '${REPO}'" ;;
esac

command -v gh >/dev/null 2>&1 || die "'gh' CLI not on PATH"
gh auth status >/dev/null 2>&1 || die "gh CLI not authenticated. Run: gh auth login"

# Confirm the branch exists.
gh api "/repos/${REPO}/branches/${BRANCH}" >/dev/null 2>&1 || \
  die "branch '${BRANCH}' not found on ${REPO}. Set the default branch first."

echo "==> Applying branch protection to ${REPO}:${BRANCH}..."

PAYLOAD=$(cat <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "required_approving_review_count": 0,
    "dismiss_stale_reviews": false,
    "require_code_owner_reviews": false,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": false,
  "lock_branch": false,
  "allow_fork_syncing": false
}
JSON
)

printf '%s' "${PAYLOAD}" | gh api \
  -X PUT \
  -H 'Accept: application/vnd.github+json' \
  --input - \
  "/repos/${REPO}/branches/${BRANCH}/protection" >/dev/null

echo "==> Protection applied to ${REPO}:${BRANCH}."
echo ""
echo "REMINDER: branch protection does NOT support 'file_path_restriction'."
echo "The .github/workflows/** block on default is enforced in two ways:"
echo "  1. The kit's 'guard' workflow on every PR (fast feedback)"
echo "  2. The kit's 'promote' composite refuses to publish those paths"
echo ""
echo "For platform-level enforcement that ALSO catches direct pushes,"
echo "use the org ruleset path (bootstrap-ruleset.sh) instead."
