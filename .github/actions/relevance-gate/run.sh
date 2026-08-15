#!/usr/bin/env bash
# Marketplace auto-publish relevance gate — composite action body.
#
# Wraps `marketplace_kit.cli relevance-score`, invoked as a module (not a
# direct script path) so its package-relative imports resolve correctly —
# see `config.py`'s own docstring for why `cli.py` needs `-m` where
# `config.py`/`summary.py` can be run as bare scripts.

set -euo pipefail

: "${CONFIG_PATH:=}"
: "${GLOBAL_CONFIG_PATH:=}"
: "${BASE_REF:=HEAD~1}"
: "${HEAD_REF:=HEAD}"
: "${RESET:=false}"

command -v python3 >/dev/null 2>&1 || {
  echo "::error title=Marketplace relevance gate::python3 is required but not on PATH." >&2
  exit 1
}

KIT_SRC="${GITHUB_ACTION_PATH}/../../../src"
[ -d "${KIT_SRC}/marketplace_kit" ] || {
  echo "::error title=Marketplace relevance gate::internal: marketplace_kit package not found at ${KIT_SRC}" >&2
  exit 1
}

ARGS=(relevance-score --json)
if [ "${RESET}" = "true" ]; then
  ARGS=(relevance-score --reset --head "${HEAD_REF}")
else
  ARGS+=(--base "${BASE_REF}" --head "${HEAD_REF}")
fi

OUT_JSON="${RUNNER_TEMP:-/tmp}/relevance-gate.json"
if ! PYTHONPATH="${KIT_SRC}:${PYTHONPATH:-}" python3 -m marketplace_kit.cli "${ARGS[@]}" \
    >"${OUT_JSON}" 2>"${RUNNER_TEMP:-/tmp}/relevance-gate.err"; then
  echo "::error title=Marketplace relevance gate::scoring failed" >&2
  cat "${RUNNER_TEMP:-/tmp}/relevance-gate.err" >&2
  exit 1
fi

if [ "${RESET}" = "true" ]; then
  echo "::notice title=Marketplace relevance gate::running score reset to 0"
  {
    echo "running_total=0"
    echo "deterministic_score=0"
    echo "final_score=0"
    echo "ai_used=false"
    echo "threshold=0"
    echo "should_publish=false"
    echo "requires_manual_approval=false"
    echo "approval_environment="
  } >> "${GITHUB_OUTPUT}"
  exit 0
fi

DETERMINISTIC_SCORE=$(jq -r '.deterministic_score' "${OUT_JSON}")
FINAL_SCORE=$(jq -r '.final_score' "${OUT_JSON}")
AI_SCORE=$(jq -r '.ai_score' "${OUT_JSON}")
AI_SOURCE=$(jq -r '.ai_source' "${OUT_JSON}")
AI_REASONING=$(jq -r '.ai_reasoning' "${OUT_JSON}")
AI_FALLBACK_REASON=$(jq -r '.ai_fallback_reason' "${OUT_JSON}")
RUNNING_TOTAL=$(jq -r '.running_total' "${OUT_JSON}")
THRESHOLD=$(jq -r '.threshold' "${OUT_JSON}")
SHOULD_PUBLISH=$(jq -r '.should_publish' "${OUT_JSON}")
REQUIRES_MANUAL_APPROVAL=$(jq -r '.requires_manual_approval' "${OUT_JSON}")
APPROVAL_ENVIRONMENT=$(jq -r '.approval_environment' "${OUT_JSON}")
REPO_TYPE=$(jq -r '.repo_type' "${OUT_JSON}")

AI_USED='false'
[ "${AI_SCORE}" != "-1" ] && AI_USED='true'

{
  echo "deterministic_score=${DETERMINISTIC_SCORE}"
  echo "final_score=${FINAL_SCORE}"
  echo "ai_used=${AI_USED}"
  echo "running_total=${RUNNING_TOTAL}"
  echo "threshold=${THRESHOLD}"
  echo "should_publish=${SHOULD_PUBLISH}"
  echo "requires_manual_approval=${REQUIRES_MANUAL_APPROVAL}"
  echo "approval_environment=${APPROVAL_ENVIRONMENT}"
} >> "${GITHUB_OUTPUT}"

echo "::notice title=Marketplace relevance gate::score=${FINAL_SCORE} running_total=${RUNNING_TOTAL}/${THRESHOLD} should_publish=${SHOULD_PUBLISH} manual_approval=${REQUIRES_MANUAL_APPROVAL}"

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "### Marketplace auto-publish relevance gate"
    echo ""
    echo "| Field | Value |"
    echo "|---|---|"
    echo "| Repo type | \`${REPO_TYPE}\` |"
    echo "| Deterministic score | ${DETERMINISTIC_SCORE}/100 |"
    if [ "${AI_USED}" = "true" ]; then
      echo "| AI score | ${AI_SCORE}/100 (\`${AI_SOURCE}\`) |"
      [ -n "${AI_REASONING}" ] && echo "| AI reasoning | ${AI_REASONING} |"
    else
      echo "| AI score | not used (${AI_FALLBACK_REASON}) |"
    fi
    echo "| **Final score (this diff)** | **${FINAL_SCORE}/100** |"
    echo "| **Running total** | **${RUNNING_TOTAL}/${THRESHOLD}** (threshold) |"
    echo "| Decision | $( [ "${SHOULD_PUBLISH}" = "true" ] && echo "publish" || echo "hold — waiting for more changes" ) |"
    if [ "${SHOULD_PUBLISH}" = "true" ] && [ "${REQUIRES_MANUAL_APPROVAL}" = "true" ]; then
      echo "| Approval | Required — gated behind the \`${APPROVAL_ENVIRONMENT}\` environment |"
    fi
    echo ""
    echo "#### File breakdown"
    echo ""
    echo "| Path | Weight | Matched pattern |"
    echo "|---|---:|---|"
    jq -r '.breakdown[] | "| `\(.path)` | \(.weight) | \(.pattern // "_(default)_") |"' "${OUT_JSON}"
  } >> "${GITHUB_STEP_SUMMARY}"
fi
