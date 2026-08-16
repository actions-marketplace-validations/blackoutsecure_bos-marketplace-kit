#!/usr/bin/env bash
# Extracted from .github/actions/check/action.yml (was the inline `run:` body
# of the `run` step). Moved to an external script because the rendered
# template exceeded the GitHub Actions runner-side 21000-char expression
# limit ("The template is not valid ... Exceeded max expression length
# 21000"). All semantics are preserved — every variable the script
# consumes is set on the step’s `env:` block in action.yml. lib.sh is
# resolved via the GHA-provided `$GITHUB_ACTION_PATH` env var.
#
# shellcheck shell=bash
set -euo pipefail

export ERR_TITLE='Marketplace check'
# shellcheck source=/dev/null
. "${GITHUB_ACTION_PATH}/../_lib/lib.sh"

# ----- Validate inputs ---------------------------------------------
validate_bool FAIL_ON_WARN

case "${ACTION_YML_PATH}" in
  ''|/*|*..*) die "action_yml_path must be a non-empty, repo-relative path (got: '${ACTION_YML_PATH}')" ;;
esac

# Parse skip list into an awk-friendly regex.
SKIP_REGEX=''
if [ -n "${SKIP_CHECKS}" ]; then
  SKIP_REGEX="$(printf '%s' "${SKIP_CHECKS}" | tr ',' '\n' | sed -E 's/[[:space:]]//g' | grep -E '^[A-Z]{2}[0-9]{3}$' | paste -sd'|' -)"
fi

skipped() {
  local id="$1"
  [ -n "${SKIP_REGEX}" ] && printf '%s' "${id}" | grep -Eq "^(${SKIP_REGEX})$"
}

# ----- Result accumulator ------------------------------------------
# Each entry: "ID|STATUS|MESSAGE" where STATUS is pass|fail|warn|skip.
REPORT_FILE="$(mktemp -t mk-report-XXXXXX.txt)"
# shellcheck disable=SC2064
trap "rm -f '${REPORT_FILE}'" EXIT

record() {
  # Args: id, status, message
  local id="$1" status="$2" msg="$3"
  if skipped "${id}"; then
    printf '%s|skip|(skipped via skip_checks)\n' "${id}" >> "${REPORT_FILE}"
    return
  fi
  printf '%s|%s|%s\n' "${id}" "${status}" "${msg}" >> "${REPORT_FILE}"
}

# ----- Validate require_* inputs + resolve org-health repo --------
validate_req() {
  # Args: input_name, value
  case "${2}" in
    fail|warn|skip) ;;
    *) die "${1} must be one of 'fail', 'warn', 'skip' (got: '${2}')" ;;
  esac
}
validate_req require_security        "${REQ_SECURITY}"
validate_req require_code_of_conduct "${REQ_CODE_OF_CONDUCT}"
validate_req require_contributing    "${REQ_CONTRIBUTING}"
validate_req require_support         "${REQ_SUPPORT}"
validate_req require_issue_templates "${REQ_ISSUE_TEMPLATES}"
validate_req require_pr_template     "${REQ_PR_TEMPLATE}"
validate_req require_funding         "${REQ_FUNDING}"
validate_req require_dependabot           "${REQ_DEPENDABOT}"
validate_req require_codeql               "${REQ_CODEQL}"
validate_req require_editorconfig         "${REQ_EDITORCONFIG}"
validate_req require_gitattributes        "${REQ_GITATTRIBUTES}"
validate_req require_gitignore            "${REQ_GITIGNORE}"
validate_req require_markdownlint         "${REQ_MARKDOWNLINT}"
validate_req require_yamllint             "${REQ_YAMLLINT}"
validate_req require_ghas_code_scanning   "${REQ_GHAS_CODE_SCANNING}"
validate_req require_ghas_secret_scanning "${REQ_GHAS_SECRET_SCANNING}"
validate_req require_dependabot_alerts    "${REQ_DEPENDABOT_ALERTS}"
validate_req require_security_devops      "${REQ_SECURITY_DEVOPS}"
validate_req require_scorecard            "${REQ_SCORECARD}"
validate_req require_repo_description     "${REQ_REPO_DESCRIPTION}"
validate_req require_repo_homepage        "${REQ_REPO_HOMEPAGE}"
validate_req require_repo_topics          "${REQ_REPO_TOPICS}"

case "${REPO_DESC_MAX_LEN}" in
  ''|*[!0-9]*)
    die "repo_description_max_length must be a non-negative integer (got: '${REPO_DESC_MAX_LEN}')"
    ;;
esac
case "${REPO_DESC_MIN_LEN}" in
  ''|*[!0-9]*)
    die "repo_description_min_length must be a non-negative integer (got: '${REPO_DESC_MIN_LEN}')"
    ;;
esac

# ----- Validate *_source inputs + helper for per-rule resolution --
validate_source() {
  # Args: input_name, value, allow_empty (true|false)
  case "${2}" in
    local|inherit|either) ;;
    '')
      if [ "${3:-false}" != "true" ]; then
        die "${1} must be 'local', 'inherit', or 'either' (got empty)"
      fi
      ;;
    *) die "${1} must be 'local', 'inherit', or 'either' (got: '${2}')" ;;
  esac
}
validate_source community_health_source "${CH_SOURCE_DEFAULT}"  false
validate_source security_source         "${SRC_SECURITY}"        true
validate_source code_of_conduct_source  "${SRC_CODE_OF_CONDUCT}" true
validate_source contributing_source     "${SRC_CONTRIBUTING}"    true
validate_source support_source          "${SRC_SUPPORT}"         true
validate_source issue_templates_source  "${SRC_ISSUE_TEMPLATES}" true
validate_source pr_template_source      "${SRC_PR_TEMPLATE}"     true
validate_source funding_source          "${SRC_FUNDING}"         true

resolve_source() {
  # Echo the per-rule override if non-empty, else the global default.
  local override="$1"
  if [ -n "${override}" ]; then
    printf '%s' "${override}"
  else
    printf '%s' "${CH_SOURCE_DEFAULT}"
  fi
}

# ----- Forward-compatible stub for AI auto-generation -------------
validate_bool AUTO_GENERATE_MISSING
if [ "${AUTO_GENERATE_MISSING}" = "true" ]; then
  echo "::warning::auto_generate_missing=true was supplied, but AI auto-generation is not yet implemented in this release. The input is a forward-compatible stub and currently has no effect."
fi

case "${CHECK_ORG_HEALTH}" in
  true|false) ;;
  *) die "check_org_health must be 'true' or 'false' (got: '${CHECK_ORG_HEALTH}')" ;;
esac

# Resolve the org health repo. Workflow override wins; otherwise
# derive from REPO_OWNER. If both are empty we skip org-health.
ORG_HEALTH_REPO="${ORG_HEALTH_REPO_IN}"
if [ -z "${ORG_HEALTH_REPO}" ] && [ -n "${REPO_OWNER:-}" ]; then
  ORG_HEALTH_REPO="${REPO_OWNER}/.github"
fi

# ----- Org-health probe + lookup helpers --------------------------
# ORG_HEALTH_AVAILABLE values: true | false | unknown.
ORG_HEALTH_AVAILABLE="false"
if [ "${CHECK_ORG_HEALTH}" = "true" ] && [ -n "${ORG_HEALTH_REPO}" ] && [ -n "${GH_TOKEN}" ]; then
  probe_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${ORG_HEALTH_REPO}" 2>/dev/null || echo '000')"
  case "${probe_status}" in
    200)
      ORG_HEALTH_AVAILABLE="true"
      echo "org-health: ${ORG_HEALTH_REPO} present (HTTP 200)"
      ;;
    404)
      echo "org-health: ${ORG_HEALTH_REPO} not present (HTTP 404) -- lookups will fall back to local-only"
      ;;
    *)
      ORG_HEALTH_AVAILABLE="unknown"
      echo "::warning::org-health: probe to ${ORG_HEALTH_REPO} returned HTTP ${probe_status} -- lookups will fall back to local-only"
      ;;
  esac
elif [ "${CHECK_ORG_HEALTH}" = "true" ] && [ -z "${GH_TOKEN}" ]; then
  echo "org-health: no github_token provided -- checks will run against the local repo only"
fi

gh_api_file_exists() {
  # Returns 0 if the given path exists in ORG_HEALTH_REPO.
  local path="$1"
  [ "${ORG_HEALTH_AVAILABLE}" = "true" ] || return 1
  local status
  status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${ORG_HEALTH_REPO}/contents/${path}" 2>/dev/null || echo '000')"
  [ "${status}" = "200" ]
}

check_health_file() {
  # Args: rule_id, label, requirement, generate_kind, source, file1 [file2 ...]
  # source must be one of: local | inherit | either
  local id="$1" label="$2" req="$3" gen_kind="$4" src="$5"
  shift 5
  local files=("$@")

  if [ "${req}" = "skip" ]; then
    record "${id}" skip "${label} check disabled via require_* input"
    return
  fi

  # Pre-compute local + org lookups based on the source mode.
  # `local` skips org entirely; `inherit` skips local entirely;
  # `either` does both (current default behavior).
  local f
  local local_found=""
  local org_found=""

  if [ "${src}" != "inherit" ]; then
    for f in "${files[@]}"; do
      if [ -e "${f}" ]; then
        local_found="${f}"
        break
      fi
    done
  fi

  if [ "${src}" != "local" ] && [ "${ORG_HEALTH_AVAILABLE}" = "true" ]; then
    for f in "${files[@]}"; do
      if gh_api_file_exists "${f}"; then
        org_found="${f}"
        break
      fi
    done
  fi

  case "${src}" in
    local)
      if [ -n "${local_found}" ]; then
        record "${id}" pass "${label} present at \`${local_found}\` (source: local)"
        return
      fi
      local hint=""
      [ -n "${gen_kind}" ] && hint=" -- run \`marketplace-kit generate-policy ${gen_kind}\` for a starter template"
      record "${id}" "${req}" "${label} missing locally (source: local; org fallback disabled)${hint}"
      ;;
    inherit)
      if [ -n "${org_found}" ]; then
        record "${id}" pass "${label} inherited from \`${ORG_HEALTH_REPO}\` (\`${org_found}\`, source: inherit)"
        return
      fi
      if [ "${ORG_HEALTH_AVAILABLE}" != "true" ]; then
        record "${id}" "${req}" "${label} expected at \`${ORG_HEALTH_REPO}\` (source: inherit) but org-health lookup is unavailable -- set \`check_org_health: true\` and pass a \`github_token\`"
      else
        local hint=""
        [ -n "${gen_kind}" ] && hint=" -- add the file to \`${ORG_HEALTH_REPO}\` for org-wide coverage"
        record "${id}" "${req}" "${label} missing from \`${ORG_HEALTH_REPO}\` (source: inherit)${hint}"
      fi
      ;;
    either|*)
      if [ -n "${local_found}" ]; then
        record "${id}" pass "${label} present at \`${local_found}\`"
        return
      fi
      if [ -n "${org_found}" ]; then
        record "${id}" pass "${label} inherited from \`${ORG_HEALTH_REPO}\` (\`${org_found}\`)"
        return
      fi
      local hint=""
      [ -n "${gen_kind}" ] && hint=" -- run \`marketplace-kit generate-policy ${gen_kind}\` for a starter template, or add the file to \`${ORG_HEALTH_REPO}\` for org-wide coverage"
      record "${id}" "${req}" "${label} missing in this repo and in \`${ORG_HEALTH_REPO}\`${hint}"
      ;;
  esac
}


# ----- MP001: action.yml present at root ---------------------------
ROOT_YML=''
if [ -f action.yml ]; then
  ROOT_YML=action.yml
elif [ -f action.yaml ]; then
  ROOT_YML=action.yaml
fi
if [ -z "${ROOT_YML}" ]; then
  record MP001 fail "neither 'action.yml' nor 'action.yaml' exists at the repo root — Marketplace requires the manifest at root"
else
  record MP001 pass "found ${ROOT_YML} at repo root"
  # Use the actual filename for downstream checks regardless of input.
  ACTION_YML_PATH="${ROOT_YML}"
fi

# If MP001 failed we can still continue with the remaining
# checks against ACTION_YML_PATH if the caller passed a custom
# path. Otherwise short-circuit the YAML-shape checks.
HAS_YML=false
if [ -f "${ACTION_YML_PATH}" ]; then
  HAS_YML=true
fi

# ----- MP002-005: action.yml shape ---------------------------------
# Delegate parsing to a sibling helper script so the YAML stays
# clean (heredocs inside `run: |` are an indentation foot-gun).
# The helper emits `KEY='value'` with values shell-quoted via
# shlex.quote, so the eval is safe against quotes/whitespace.
if "${HAS_YML}"; then
  ACTION_META="$(python3 "${GITHUB_ACTION_PATH}/extract_meta.py" "${ACTION_YML_PATH}")"
  eval "${ACTION_META}"

  # ----- MP002: name non-empty + not org/user-shaped ----------------
  if [ -z "${NAME:-}" ]; then
    record MP002 fail "'name:' is empty or missing in ${ACTION_YML_PATH}"
  else
    # Marketplace rejects names that look like a GitHub user/org
    # slug (single-segment, [-A-Za-z0-9], 1-39 chars). The
    # heuristic here is conservative: short single-word names
    # with no spaces are a yellow flag.
    if printf '%s' "${NAME}" | grep -Eq '[[:space:]]'; then
      record MP002 pass "name '${NAME}' contains whitespace (clearly not a user/org)"
    elif [ "${#NAME}" -lt 4 ]; then
      record MP002 warn "name '${NAME}' is short and may collide with a reserved feature; consider a more descriptive name"
    else
      record MP002 pass "name '${NAME}' looks valid"
    fi
  fi

  # ----- MP003: description non-empty -------------------------------
  if [ "${DESC_LEN:-0}" -eq 0 ]; then
    record MP003 fail "'description:' is empty or missing"
  else
    record MP003 pass "description is ${DESC_LEN} chars"
  fi

  # ----- MP010: description hard upper bound (<= 125 chars) ---------
  # Marketplace truncates the card-view subtitle past 125
  # chars. Treat the limit as a hard fail so a listing never
  # ships with a truncated description; tighten the manifest
  # and put detail in README.md instead.
  if [ "${DESC_LEN:-0}" -gt 125 ]; then
    record MP010 fail "description is ${DESC_LEN} chars (>125) — Marketplace card view will truncate. Tighten to a single short sentence; use README.md for detail."
  elif [ "${DESC_LEN:-0}" -gt 0 ]; then
    record MP010 pass "description is ${DESC_LEN} chars (<=125)"
  fi

  # ----- MP004: runs block present + supported using ----------------
  case "${RUNS_USING:-}" in
    composite|node20|node22|docker)
      record MP004 pass "runs.using='${RUNS_USING}'"
      ;;
    '')
      record MP004 fail "'runs.using:' is missing"
      ;;
    *)
      record MP004 fail "'runs.using:' value '${RUNS_USING}' is not a supported runtime (composite, node20, node22, docker)"
      ;;
  esac

  # ----- MP005/MP006: branding (delegate to actionlint) -------------
  # actionlint already validates branding.icon (Feather snapshot)
  # and branding.color (allowed enum). We surface its findings
  # under the MP005/MP006 IDs.
  if [ -n "${BRANDING_ICON:-}" ] && [ -n "${BRANDING_COLOR:-}" ]; then
    AL_OUT="$(actionlint -no-color "${ACTION_YML_PATH}" 2>&1 || true)"
    if printf '%s' "${AL_OUT}" | grep -qiE "branding.*icon"; then
      record MP005 fail "branding.icon '${BRANDING_ICON}' rejected by actionlint — must be a Feather v4.28.0 icon (see https://github.com/rhysd/actionlint/blob/main/docs/checks.md)"
    else
      record MP005 pass "branding.icon='${BRANDING_ICON}'"
    fi
    if printf '%s' "${AL_OUT}" | grep -qiE "branding.*colou?r"; then
      record MP006 fail "branding.color '${BRANDING_COLOR}' rejected by actionlint — must be one of white,yellow,blue,green,orange,red,purple,gray-dark"
    else
      record MP006 pass "branding.color='${BRANDING_COLOR}'"
    fi
  else
    record MP005 warn "branding.icon not set — Marketplace listings without an icon look bare"
    record MP006 warn "branding.color not set — Marketplace listings without a colour look bare"
  fi
else
  # No YAML at the expected path — skip MP002-006 + MP010.
  for id in MP002 MP003 MP004 MP005 MP006 MP010; do
    record "${id}" skip "no action manifest found at '${ACTION_YML_PATH}'"
  done
fi

# ----- MP007: README.md present at root ----------------------------
if [ -f README.md ] || [ -f README ] || [ -f Readme.md ] || [ -f readme.md ]; then
  record MP007 pass "README found at repo root"
else
  record MP007 fail "no README.md at the repo root — appears on the Marketplace listing"
fi

# ----- MP008: LICENSE present at root ------------------------------
if [ -f LICENSE ] || [ -f LICENSE.md ] || [ -f LICENSE.txt ] || [ -f COPYING ]; then
  record MP008 pass "LICENSE found at repo root"
else
  record MP008 fail "no LICENSE file at the repo root — Marketplace policy requires one"
fi

# ----- MP009: NO workflow files (on the target branch) -------------
# This check is most meaningful on `main`. On `dev` it'll be
# noisy by design — every Action repo with CI will fail it.
# Surface as a WARN here; the `guard` action enforces it as a
# hard fail at promote time.
if [ -n "${WORKFLOW_DIR}" ] && [ -d "${WORKFLOW_DIR}" ]; then
  WF_COUNT="$(find "${WORKFLOW_DIR}" -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null | wc -l | tr -d ' ')"
  if [ "${WF_COUNT}" -gt 0 ]; then
    record MP009 warn "${WF_COUNT} workflow file(s) under ${WORKFLOW_DIR} — fine on 'dev', but Marketplace publishing requires zero on the default branch (the kit's 'promote' action strips them)"
  else
    record MP009 pass "no workflow files under ${WORKFLOW_DIR}"
  fi
else
  record MP009 pass "no ${WORKFLOW_DIR} directory"
fi

# ----- OP001: composite actions use `set -euo pipefail` ------------
# Scan every action.yml under actions/ (preferred) AND
# .github/actions/ (legacy / dev-only CI helpers) for a
# `using: composite` whose run blocks lack the standard
# hardening header.
WEAK_COMPOSITES=""
SCAN_DIRS=""
[ -d actions ] && SCAN_DIRS="${SCAN_DIRS} actions"
[ -d .github/actions ] && SCAN_DIRS="${SCAN_DIRS} .github/actions"
if [ -n "${SCAN_DIRS}" ]; then
  # shellcheck disable=SC2086
  while IFS= read -r f; do
    [ -z "${f}" ] && continue
    # Crude but effective: if the file declares using: composite
    # and contains any `run: |` block, check it for set -euo.
    if grep -qE '^[[:space:]]*using:[[:space:]]*composite' "${f}" && \
       grep -qE '^[[:space:]]*run:[[:space:]]*\|' "${f}"; then
      if ! grep -qE 'set -euo pipefail' "${f}"; then
        WEAK_COMPOSITES="${WEAK_COMPOSITES}${f}\n"
      fi
    fi
  done < <(find ${SCAN_DIRS} -maxdepth 3 -type f \( -name 'action.yml' -o -name 'action.yaml' \) 2>/dev/null)
fi
if [ -n "${WEAK_COMPOSITES}" ]; then
  record OP001 warn "$(printf 'composite action(s) missing `set -euo pipefail`:\n%b' "${WEAK_COMPOSITES}" | tr '\n' ' ')"
else
  record OP001 pass "all composite actions use 'set -euo pipefail' (or none found)"
fi

# ----- OP003: description >= 50 chars ------------------------------
if "${HAS_YML}"; then
  if [ "${DESC_LEN:-0}" -ge 50 ]; then
    record OP003 pass "description is ${DESC_LEN} chars (>= 50)"
  else
    record OP003 warn "description is ${DESC_LEN} chars; Marketplace cards truncate at ~120 but very short descriptions read as low-effort"
  fi
else
  record OP003 skip "no action manifest"
fi

# ----- OP004: README has a Usage section ---------------------------
README_FILE=''
for cand in README.md Readme.md readme.md README; do
  if [ -f "${cand}" ]; then README_FILE="${cand}"; break; fi
done
if [ -n "${README_FILE}" ]; then
  if grep -qiE '^#+[[:space:]]*(usage|quick[[:space:]]*start|example|getting[[:space:]]*started)' "${README_FILE}"; then
    record OP004 pass "${README_FILE} has a usage / quickstart / example section"
  else
    record OP004 warn "${README_FILE} has no detectable Usage / Quickstart / Example heading — Marketplace consumers expect one"
  fi

  # ----- OP005: README size sanity ---------------------------------
  # Marketplace renders the README on the listing page. Tiny
  # READMEs read as low-effort; huge ones (>128 KB) hit the
  # GitHub-side render limit and may truncate.
  README_BYTES="$(wc -c < "${README_FILE}" | tr -d '[:space:]')"
  if [ "${README_BYTES}" -lt 512 ]; then
    record OP005 warn "${README_FILE} is only ${README_BYTES} bytes — Marketplace consumers expect more"
  elif [ "${README_BYTES}" -gt 131072 ]; then
    record OP005 warn "${README_FILE} is ${README_BYTES} bytes (>128KB) — GitHub may truncate the rendered view"
  else
    record OP005 pass "${README_FILE} is ${README_BYTES} bytes (within sane range)"
  fi

  # ----- OP006: README has at least one image/badge ----------------
  # A Marketplace listing without any visual element looks
  # noticeably less polished. Any markdown image syntax
  # `![alt](url)` counts.
  if grep -qE '!\[[^]]*\]\([^)]+\)' "${README_FILE}"; then
    record OP006 pass "${README_FILE} contains at least one image/badge"
  else
    record OP006 warn "${README_FILE} has no images or badges — add a status badge or screenshot"
  fi

  # ----- OP007: README has at least 3 fenced code blocks -----------
  # Marketplace consumers scan READMEs for copy-pasteable
  # snippets. We look for triple-backtick OPEN fences (lines
  # starting with ``` followed by an optional language tag).
  FENCE_COUNT="$(grep -cE '^```[A-Za-z0-9_+-]*[[:space:]]*$' "${README_FILE}" || true)"
  # Each block has an open + close fence, so divide by 2.
  BLOCK_COUNT=$(( FENCE_COUNT / 2 ))
  if [ "${BLOCK_COUNT}" -ge 3 ]; then
    record OP007 pass "${README_FILE} contains ${BLOCK_COUNT} fenced code blocks"
  else
    record OP007 warn "${README_FILE} contains ${BLOCK_COUNT} fenced code blocks — Marketplace consumers expect at least 3 copy-pasteable examples"
  fi
else
  record OP004 skip "no README"
  record OP005 skip "no README"
  record OP006 skip "no README"
  record OP007 skip "no README"
fi

# ----- SC001: composites don't interpolate inputs into run: --------
# Expression-form input interpolation (the dollar-double-brace
# syntax around `inputs.foo` or `github.event.*`) inside a
# composite `run:` body is a shell-injection surface. Inputs
# should be plumbed via `env:` so the runner quotes them.
#
# The previous implementation used an awk one-liner that
# latched `inrun=1` on the first `run:` and never reset, so
# SAFE `${{ inputs.* }}` references inside the `env:` blocks
# of LATER steps were flagged as violations. The Python helper
# tracks the `run:` mapping-key indentation and only scans
# lines that are structurally inside a `run:` body, eliminating
# the false positives. See scan_sc001.py for full background.
UNSAFE_INTERP=""
SCAN_DIRS=""
[ -d actions ] && SCAN_DIRS="${SCAN_DIRS} actions"
[ -d .github/actions ] && SCAN_DIRS="${SCAN_DIRS} .github/actions"
if [ -n "${SCAN_DIRS}" ]; then
  # Collect every action.yml/action.yaml under the scan dirs.
  ACTION_FILES=""
  # shellcheck disable=SC2086
  while IFS= read -r f; do
    [ -z "${f}" ] && continue
    ACTION_FILES="${ACTION_FILES} ${f}"
  done < <(find ${SCAN_DIRS} -maxdepth 3 -type f \( -name 'action.yml' -o -name 'action.yaml' \) 2>/dev/null)
  if [ -n "${ACTION_FILES}" ]; then
    # shellcheck disable=SC2086
    UNSAFE_INTERP="$(python3 "${GITHUB_ACTION_PATH}/scan_sc001.py" ${ACTION_FILES} || true)"
  fi
fi
if [ -n "${UNSAFE_INTERP}" ]; then
  # Render the path list on one line (Markdown renders the join
  # cleanly in step summaries).
  # shellcheck disable=SC2001
  UNSAFE_LIST="$(printf '%s' "${UNSAFE_INTERP}" | tr '\n' ' ' | sed 's/[[:space:]]\{1,\}/ /g' | sed 's/^ //;s/ $//')"
  record SC001 fail "composite action(s) interpolate \`inputs.*\` or \`github.event.*\` directly inside \`run:\` (shell injection surface — plumb via \`env:\` instead): ${UNSAFE_LIST}"
else
  record SC001 pass "no expression-form inputs.* / github.event.* interpolation in composite run blocks"
fi

# ----- SC003: SECURITY.md (org-aware) ------------------------------
# README escape hatch: a README that points readers to a private
# reporting process satisfies SC003 without hitting the org probe.
# The escape hatch is suppressed when source=inherit -- in that
# mode the org file is the authoritative source.
SECURITY_HINT_OK=false
if [ -n "${README_FILE}" ] && grep -qiE 'security policy|SECURITY\.md|report.*vulnerability' "${README_FILE}"; then
  SECURITY_HINT_OK=true
fi
SC003_SRC="$(resolve_source "${SRC_SECURITY}")"
if [ "${SC003_SRC}" != "inherit" ] && "${SECURITY_HINT_OK}" && [ "${REQ_SECURITY}" != "fail" ]; then
  record SC003 pass "security policy is discoverable (README mentions reporting)"
else
  check_health_file SC003 "SECURITY.md (security policy)" "${REQ_SECURITY}" "security" "${SC003_SRC}" \
    "SECURITY.md" ".github/SECURITY.md" "docs/SECURITY.md"
fi

# ----- CH001: CODE_OF_CONDUCT.md (org-aware) -----------------------
check_health_file CH001 "CODE_OF_CONDUCT.md (code of conduct)" "${REQ_CODE_OF_CONDUCT}" "code-of-conduct" "$(resolve_source "${SRC_CODE_OF_CONDUCT}")" \
  "CODE_OF_CONDUCT.md" ".github/CODE_OF_CONDUCT.md" "docs/CODE_OF_CONDUCT.md"

# ----- CH002: CONTRIBUTING.md (org-aware) --------------------------
check_health_file CH002 "CONTRIBUTING.md (contributor guide)" "${REQ_CONTRIBUTING}" "contributing" "$(resolve_source "${SRC_CONTRIBUTING}")" \
  "CONTRIBUTING.md" ".github/CONTRIBUTING.md" "docs/CONTRIBUTING.md"

# ----- CH003: SUPPORT.md (org-aware) -------------------------------
check_health_file CH003 "SUPPORT.md (support guide)" "${REQ_SUPPORT}" "support" "$(resolve_source "${SRC_SUPPORT}")" \
  "SUPPORT.md" ".github/SUPPORT.md" "docs/SUPPORT.md"

# ----- CH004: issue templates (org-aware) --------------------------
check_health_file CH004 "issue template(s)" "${REQ_ISSUE_TEMPLATES}" "issue-bug" "$(resolve_source "${SRC_ISSUE_TEMPLATES}")" \
  ".github/ISSUE_TEMPLATE" ".github/ISSUE_TEMPLATE.md" "ISSUE_TEMPLATE.md"

# ----- CH005: pull-request template (org-aware) --------------------
check_health_file CH005 "pull-request template" "${REQ_PR_TEMPLATE}" "pr-template" "$(resolve_source "${SRC_PR_TEMPLATE}")" \
  ".github/PULL_REQUEST_TEMPLATE.md" "PULL_REQUEST_TEMPLATE.md" \
  ".github/pull_request_template.md" "docs/PULL_REQUEST_TEMPLATE.md"

# ----- CH006: FUNDING.yml (org-aware) ------------------------------
check_health_file CH006 "FUNDING.yml" "${REQ_FUNDING}" "funding" "$(resolve_source "${SRC_FUNDING}")" \
  ".github/FUNDING.yml" "FUNDING.yml"

# ----- DP001: Dependabot config ------------------------------------
# Dependabot is a per-repo config file; org-level dependabot doesn't
# exist (the org `.github` repo doesn't apply this one). So check
# local only.
check_local_file() {
  # Args: rule_id, label, requirement, generate_hint, file1 [file2 ...]
  local id="$1" label="$2" req="$3" hint="$4"; shift 4
  if [ "${req}" = "skip" ]; then
    record "${id}" skip "${label} check disabled via require_* input"
    return
  fi
  local f
  for f in "$@"; do
    if [ -e "${f}" ]; then
      record "${id}" pass "${label} present at \`${f}\`"
      return
    fi
  done
  if [ -n "${hint}" ]; then
    record "${id}" "${req}" "${label} not found -- ${hint}"
  else
    record "${id}" "${req}" "${label} not found (searched: $*)"
  fi
}

check_local_file DP001 "Dependabot config" "${REQ_DEPENDABOT}" \
  "scaffold via \`marketplace-kit generate-policy dependabot\` or copy from https://github.com/blackoutsecure/bos-marketplace-kit" \
  ".github/dependabot.yml" ".github/dependabot.yaml"

# ----- CQ001: CodeQL workflow --------------------------------------
# A CodeQL workflow file conventionally lives at
# `.github/workflows/codeql.yml` but the naming is not enforced
# by GitHub. We detect by content too -- any workflow file that
# references the codeql-action repo counts.
CODEQL_WF=""
if [ -d .github/workflows ]; then
  while IFS= read -r f; do
    [ -z "${f}" ] && continue
    if grep -qE 'github/codeql-action(/init|/analyze|/upload-sarif|@)' "${f}"; then
      CODEQL_WF="${f}"
      break
    fi
  done < <(find .github/workflows -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null)
fi
if [ "${REQ_CODEQL}" = "skip" ]; then
  record CQ001 skip "CodeQL workflow check disabled via require_codeql"
elif [ -n "${CODEQL_WF}" ]; then
  record CQ001 pass "CodeQL workflow found at \`${CODEQL_WF}\`"
else
  record CQ001 "${REQ_CODEQL}" "no CodeQL workflow found -- scaffold via \`marketplace-kit generate-policy codeql-workflow\` (free on public repos via GitHub Advanced Security)"
fi

# ----- LT001-LT005: lint config presence ---------------------------
check_local_file LT001 ".editorconfig" "${REQ_EDITORCONFIG}" \
  "add an .editorconfig to standardise indentation/encoding across editors" \
  ".editorconfig"
check_local_file LT002 ".gitattributes" "${REQ_GITATTRIBUTES}" \
  "add a .gitattributes to lock line-endings + tag generated files" \
  ".gitattributes"
check_local_file LT003 ".gitignore" "${REQ_GITIGNORE}" \
  "add a .gitignore" \
  ".gitignore"
check_local_file LT004 "markdownlint config" "${REQ_MARKDOWNLINT}" \
  "scaffold via \`marketplace-kit generate-policy markdownlint\`" \
  ".markdownlint.yaml" ".markdownlint.yml" ".markdownlint-cli2.yaml" \
  ".markdownlint-cli2.jsonc" ".markdownlint.json"
check_local_file LT005 "yamllint config" "${REQ_YAMLLINT}" \
  "scaffold via \`marketplace-kit generate-policy yamllint\`" \
  ".yamllint.yml" ".yamllint.yaml" ".yamllint"

# ----- GH001-GH003: GitHub Advanced Security toggles ---------------
# The repo-settings endpoint returns `security_and_analysis.*`
# which is the source of truth for GHAS toggles. Requires a
# token. Dependabot alerts have a separate endpoint that needs
# admin scope; we probe it but skip cleanly on 403/404.
SAS_JSON=""
if [ -n "${GH_TOKEN}" ] && [ -n "${REPO_FULL}" ]; then
  SAS_JSON="$(curl -sS \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO_FULL}" 2>/dev/null || echo '')"
fi

gh_feature_status() {
  # Args: jq-style path, e.g. .security_and_analysis.advanced_security.status
  local path="$1"
  [ -z "${SAS_JSON}" ] && return 1
  printf '%s' "${SAS_JSON}" | python3 -c '
import json, sys, os
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
path = sys.argv[1].lstrip(".").split(".")
for p in path:
    if not isinstance(d, dict): sys.exit(1)
    d = d.get(p)
    if d is None: sys.exit(1)
print(d)
' "${path}"
}

record_gh_feature() {
  # Args: rule_id, label, requirement, status_value (or empty)
  local id="$1" label="$2" req="$3" status="$4"
  if [ "${req}" = "skip" ]; then
    record "${id}" skip "${label} check disabled via require_* input"
    return
  fi
  if [ -z "${GH_TOKEN}" ]; then
    record "${id}" skip "${label}: no github_token -- skipped (pass \`github_token\` to enable)"
    return
  fi
  if [ -z "${SAS_JSON}" ]; then
    record "${id}" "${req}" "${label}: repo settings lookup failed -- token may lack \`metadata: read\`"
    return
  fi
  # GitHub only returns the `security_and_analysis` object in
  # `GET /repos/{}` responses when the caller has admin/write
  # access to the repo. The default GITHUB_TOKEN does NOT see
  # this field, so an absent object means "can't tell" rather
  # than "disabled". Skip with a clear remediation hint.
  if ! printf '%s' "${SAS_JSON}" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(d.get("security_and_analysis"), dict) else 1)
' >/dev/null 2>&1; then
    record "${id}" skip "${label}: \`security_and_analysis\` not visible to token -- supply a PAT/App token with admin/write to introspect (the feature itself may already be enabled)"
    return
  fi
  case "${status}" in
    enabled)
      record "${id}" pass "${label} enabled"
      ;;
    disabled|"")
      record "${id}" "${req}" "${label} is disabled or not visible -- enable at Settings > Code security and analysis"
      ;;
    *)
      record "${id}" "${req}" "${label} status=${status} (expected 'enabled')"
      ;;
  esac
}

# GH001: Code scanning (CodeQL alerts default-setup OR a workflow exists)
# The settings object doesn't expose a single 'code_scanning' bit;
# presence of the workflow (CQ001) plus successful default-setup
# is the signal. We approximate via the GET /repos/{}/code-scanning/default-setup endpoint.
if [ "${REQ_GHAS_CODE_SCANNING}" = "skip" ]; then
  record GH001 skip "GHAS code scanning check disabled via require_ghas_code_scanning"
elif [ -z "${GH_TOKEN}" ]; then
  record GH001 skip "GHAS code scanning: no github_token -- skipped"
else
  cs_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO_FULL}/code-scanning/default-setup" 2>/dev/null || echo '000')"
  case "${cs_status}" in
    200)
      cs_state="$(curl -sS \
        -H "Authorization: Bearer ${GH_TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "https://api.github.com/repos/${REPO_FULL}/code-scanning/default-setup" 2>/dev/null \
        | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state",""))')"
      if [ "${cs_state}" = "configured" ] || [ -n "${CODEQL_WF}" ]; then
        record GH001 pass "code scanning configured (default-setup state=${cs_state:-via-workflow})"
      else
        record GH001 "${REQ_GHAS_CODE_SCANNING}" "code scanning not configured -- enable at Settings > Code security or add a CodeQL workflow"
      fi
      ;;
    404)
      # Default-setup unavailable AND no workflow.
      if [ -n "${CODEQL_WF}" ]; then
        record GH001 pass "code scanning provided by workflow \`${CODEQL_WF}\`"
      else
        record GH001 "${REQ_GHAS_CODE_SCANNING}" "code scanning not configured (HTTP 404 + no CodeQL workflow)"
      fi
      ;;
    403)
      record GH001 skip "GHAS code scanning: token lacks scope -- HTTP 403"
      ;;
    *)
      record GH001 "${REQ_GHAS_CODE_SCANNING}" "code scanning probe returned HTTP ${cs_status}"
      ;;
  esac
fi

# GH002: Secret scanning
ss_status="$(gh_feature_status .security_and_analysis.secret_scanning.status || echo '')"
record_gh_feature GH002 "secret scanning" "${REQ_GHAS_SECRET_SCANNING}" "${ss_status}"

# GH003: Dependabot alerts
# The /vulnerability-alerts endpoint returns 204 if enabled,
# 404 if disabled. Requires Admin:read.
if [ "${REQ_DEPENDABOT_ALERTS}" = "skip" ]; then
  record GH003 skip "Dependabot alerts check disabled via require_dependabot_alerts"
elif [ -z "${GH_TOKEN}" ]; then
  record GH003 skip "Dependabot alerts: no github_token -- skipped"
else
  va_status="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${GH_TOKEN}" \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    "https://api.github.com/repos/${REPO_FULL}/vulnerability-alerts" 2>/dev/null || echo '000')"
  case "${va_status}" in
    204) record GH003 pass "Dependabot alerts enabled" ;;
    404) record GH003 "${REQ_DEPENDABOT_ALERTS}" "Dependabot alerts disabled -- enable at Settings > Code security" ;;
    403) record GH003 skip "Dependabot alerts: token lacks scope (need \`Administration: read\`)" ;;
    *)   record GH003 "${REQ_DEPENDABOT_ALERTS}" "Dependabot alerts probe returned HTTP ${va_status}" ;;
  esac
fi

# ----- MS001: Microsoft Security DevOps workflow -------------------
# Detect by content: any workflow referencing
# microsoft/security-devops-action counts.
MS_WF=""
if [ -d .github/workflows ]; then
  while IFS= read -r f; do
    [ -z "${f}" ] && continue
    if grep -qE 'microsoft/security-devops-action' "${f}"; then
      MS_WF="${f}"
      break
    fi
  done < <(find .github/workflows -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null)
fi
if [ "${REQ_SECURITY_DEVOPS}" = "skip" ]; then
  record MS001 skip "Microsoft Security DevOps workflow check disabled via require_security_devops"
elif [ -n "${MS_WF}" ]; then
  record MS001 pass "Microsoft Security DevOps workflow found at \`${MS_WF}\`"
else
  record MS001 "${REQ_SECURITY_DEVOPS}" "no Microsoft Security DevOps workflow found -- scaffold via \`marketplace-kit generate-policy security-devops-workflow\` (useful for repos with IaC or container images; integrates with Defender for Cloud)"
fi

# ----- SR001: OpenSSF Scorecard workflow ---------------------------
SR_WF=""
if [ -d .github/workflows ]; then
  while IFS= read -r f; do
    [ -z "${f}" ] && continue
    if grep -qE 'ossf/scorecard-action' "${f}"; then
      SR_WF="${f}"
      break
    fi
  done < <(find .github/workflows -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) 2>/dev/null)
fi
if [ "${REQ_SCORECARD}" = "skip" ]; then
  record SR001 skip "OpenSSF Scorecard workflow check disabled via require_scorecard"
elif [ -n "${SR_WF}" ]; then
  record SR001 pass "OpenSSF Scorecard workflow found at \`${SR_WF}\`"
else
  record SR001 "${REQ_SCORECARD}" "no OpenSSF Scorecard workflow found -- scaffold via \`marketplace-kit generate-policy scorecard-workflow\` (free for public repos; results at https://scorecard.dev)"
fi

# ----- RM001-RM005: live repo "About" box (description/homepage/topics) -
# Validates what the public sees in the sidebar — the same fields
# the companion `repo-metadata` composite writes on release.
# `SAS_JSON` (fetched earlier for the GHAS checks) is the result of
# `GET /repos/{owner}/{repo}` and carries all three values; reuse it.
# These fields are public-readable, so the default `GITHUB_TOKEN` is
# sufficient even when GH002 had to `skip` for lack of admin scope.
REPO_DESC=""
REPO_HOMEPAGE=""
REPO_TOPICS=""
REPO_TOPICS_COUNT=0
REPO_DESC_LEN=0

rm_skip_all() {
  local reason="$1"
  for id in RM001 RM002 RM003 RM004 RM005; do
    record "${id}" skip "${reason}"
  done
}

if [ -z "${GH_TOKEN}" ]; then
  rm_skip_all "no github_token -- skipped (pass \`github_token: \${{ github.token }}\` to enable repo About-box checks)"
elif [ -z "${SAS_JSON}" ]; then
  rm_skip_all "repo metadata lookup failed -- token may lack \`metadata: read\`, or repo not found"
else
  # Extract description/homepage/topics AND the home-page tab
  # toggles (`has_issues`, `has_projects`, `has_wiki`, `has_pages`,
  # `has_discussions`, `has_downloads`) from the single repo GET.
  # The sidebar widget toggles (Releases / Deployments / Packages)
  # are NOT exposed by `GET /repos/{owner}/{repo}` -- the
  # `repo-metadata` composite writes them best-effort on release,
  # but there's no read-side endpoint to confirm them here.
  # python3 is already a hard dep of this script.
  RM_FIELDS="$(printf '%s' "${SAS_JSON}" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
desc = d.get("description") or ""
home = d.get("homepage") or ""
topics = d.get("topics") or []
desc = " ".join(desc.split())
def b(k):
    v = d.get(k)
    return "true" if v else "false"
print(desc)
print(home)
print(" ".join(t for t in topics if t))
print(b("has_issues"))
print(b("has_projects"))
print(b("has_wiki"))
print(b("has_pages"))
print(b("has_discussions"))
print(b("has_downloads"))
' 2>/dev/null || true)"
  # Parse the lines back out.
  REPO_DESC="$(printf '%s\n' "${RM_FIELDS}" | sed -n '1p')"
  REPO_HOMEPAGE="$(printf '%s\n' "${RM_FIELDS}" | sed -n '2p')"
  REPO_TOPICS="$(printf '%s\n' "${RM_FIELDS}" | sed -n '3p')"
  REPO_HAS_ISSUES="$(printf '%s\n' "${RM_FIELDS}" | sed -n '4p')"
  REPO_HAS_PROJECTS="$(printf '%s\n' "${RM_FIELDS}" | sed -n '5p')"
  REPO_HAS_WIKI="$(printf '%s\n' "${RM_FIELDS}" | sed -n '6p')"
  REPO_HAS_PAGES="$(printf '%s\n' "${RM_FIELDS}" | sed -n '7p')"
  REPO_HAS_DISCUSSIONS="$(printf '%s\n' "${RM_FIELDS}" | sed -n '8p')"
  REPO_HAS_DOWNLOADS="$(printf '%s\n' "${RM_FIELDS}" | sed -n '9p')"
  REPO_DESC_LEN="${#REPO_DESC}"
  if [ -n "${REPO_TOPICS}" ]; then
    # shellcheck disable=SC2086
    set -- ${REPO_TOPICS}
    REPO_TOPICS_COUNT="$#"
    set --
  fi

  # ----- RM001: description present -------------------------------
  if [ "${REQ_REPO_DESCRIPTION}" = "skip" ]; then
    record RM001 skip "repo description check disabled via require_repo_description"
  elif [ -n "${REPO_DESC}" ]; then
    record RM001 pass "repo description present (${REPO_DESC_LEN} chars)"
  else
    record RM001 "${REQ_REPO_DESCRIPTION}" "repo description is empty -- set it via Settings > General, or run the \`repo-metadata\` composite on release"
  fi

  # ----- RM002: description length within bounds ------------------
  # GitHub stores up to 350 chars (configurable). Above the cap the
  # next PATCH would be rejected. Very short descriptions are a
  # quality warning, not a hard fail.
  if [ "${REQ_REPO_DESCRIPTION}" = "skip" ]; then
    record RM002 skip "repo description length check disabled via require_repo_description"
  elif [ -z "${REPO_DESC}" ]; then
    record RM002 skip "no repo description to measure (see RM001)"
  elif [ "${REPO_DESC_LEN}" -gt "${REPO_DESC_MAX_LEN}" ]; then
    record RM002 fail "repo description is ${REPO_DESC_LEN} chars (>${REPO_DESC_MAX_LEN}) -- GitHub will reject the next PATCH; trim to <=${REPO_DESC_MAX_LEN}"
  elif [ "${REPO_DESC_MIN_LEN}" -gt 0 ] && [ "${REPO_DESC_LEN}" -lt "${REPO_DESC_MIN_LEN}" ]; then
    record RM002 warn "repo description is only ${REPO_DESC_LEN} chars (<${REPO_DESC_MIN_LEN}); consider a fuller summary (the About box has room — the Marketplace card limit of 125 chars only applies to \`action.yml\`)"
  else
    record RM002 pass "repo description length ${REPO_DESC_LEN} chars within bounds (>=${REPO_DESC_MIN_LEN}, <=${REPO_DESC_MAX_LEN})"
  fi

  # ----- RM003: homepage set + URL-shaped -------------------------
  # Homepage presence is opt-in (default `skip`). But IF a homepage
  # is set, it MUST be an http(s) URL — a non-URL value is always
  # reported as `fail`, since it indicates a misconfiguration that
  # renders as a broken link in the About box.
  if [ -z "${REPO_HOMEPAGE}" ]; then
    if [ "${REQ_REPO_HOMEPAGE}" = "skip" ]; then
      record RM003 skip "repo homepage check disabled via require_repo_homepage"
    else
      record RM003 "${REQ_REPO_HOMEPAGE}" "repo homepage is empty -- set it via Settings > General, or pass \`homepage:\` to the \`repo-metadata\` composite"
    fi
  else
    case "${REPO_HOMEPAGE}" in
      http://*|https://*)
        record RM003 pass "repo homepage set: ${REPO_HOMEPAGE}"
        ;;
      *)
        record RM003 fail "repo homepage is set but not an http(s) URL: '${REPO_HOMEPAGE}'"
        ;;
    esac
  fi

  # ----- RM004: topic count ---------------------------------------
  # GitHub caps at 20 topics — exceeding is always fail.
  if [ "${REPO_TOPICS_COUNT}" -gt 20 ]; then
    record RM004 fail "repo has ${REPO_TOPICS_COUNT} topics (>20) -- GitHub caps at 20; trim the list"
  elif [ "${REQ_REPO_TOPICS}" = "skip" ]; then
    record RM004 skip "repo topics check disabled via require_repo_topics"
  elif [ "${REPO_TOPICS_COUNT}" -eq 0 ]; then
    record RM004 "${REQ_REPO_TOPICS}" "repo has no topics -- topics drive Marketplace + search discoverability; set them via Settings > General or the \`repo-metadata\` composite"
  else
    record RM004 pass "repo has ${REPO_TOPICS_COUNT} topic(s) (<=20)"
  fi

  # ----- RM005: topic format validity -----------------------------
  # GitHub rules: lowercase, [a-z0-9-], <=50 chars, must start and
  # end with a letter or digit (no leading/trailing hyphen). Format
  # violations always fail — they indicate data the API would
  # reject on the next PUT /topics.
  if [ "${REPO_TOPICS_COUNT}" -eq 0 ]; then
    record RM005 skip "no topics to validate (see RM004)"
  else
    INVALID_TOPICS=""
    # shellcheck disable=SC2086
    set -- ${REPO_TOPICS}
    for t in "$@"; do
      if [ "${#t}" -gt 50 ] || ! printf '%s' "${t}" | grep -Eq '^([a-z0-9]|[a-z0-9][a-z0-9-]*[a-z0-9])$'; then
        INVALID_TOPICS="${INVALID_TOPICS} ${t}"
      fi
    done
    set --
    INVALID_TOPICS="$(printf '%s' "${INVALID_TOPICS}" | sed -E 's/^[[:space:]]+//')"
    if [ -n "${INVALID_TOPICS}" ]; then
      record RM005 fail "repo topic(s) violate GitHub format rules (lowercase, [a-z0-9-], <=50 chars, no leading/trailing hyphen): ${INVALID_TOPICS}"
    else
      record RM005 pass "all ${REPO_TOPICS_COUNT} repo topic(s) match GitHub format rules"
    fi
  fi
fi

# ----- Aggregate + emit -------------------------------------------
PASSED="$(awk -F'|' '$2=="pass"{n++} END{print n+0}' "${REPORT_FILE}")"
FAILED="$(awk -F'|' '$2=="fail"{n++} END{print n+0}' "${REPORT_FILE}")"
WARNED="$(awk -F'|' '$2=="warn"{n++} END{print n+0}' "${REPORT_FILE}")"
SKIPPED="$(awk -F'|' '$2=="skip"{n++} END{print n+0}' "${REPORT_FILE}")"

# Sort report by ID for deterministic output.
SORTED_REPORT="$(sort -t'|' -k1,1 "${REPORT_FILE}")"

# Emit job summary as a markdown table.
{
  echo "## Marketplace pre-publish check"
  echo ""
  echo "**${PASSED} passed · ${FAILED} failed · ${WARNED} warnings · ${SKIPPED} skipped**"
  echo ""
  echo "| ID | Status | Message |"
  echo "|----|--------|---------|"
  printf '%s\n' "${SORTED_REPORT}" | awk -F'|' '{
    icon = $2;
    if ($2=="pass") icon = "✅ pass";
    else if ($2=="fail") icon = "❌ fail";
    else if ($2=="warn") icon = "⚠️ warn";
    else if ($2=="skip") icon = "➖ skip";
    # Escape pipes in the message body so the table renders.
    gsub(/\|/, "\\|", $3);
    printf "| `%s` | %s | %s |\n", $1, icon, $3;
  }'

  # Snapshot of the live repo "About" box so the reader sees the
  # actual values their consumers see, without re-checking the
  # repo. Only emitted when the GH API lookup succeeded; otherwise
  # the RM rows already explain why we have nothing to show.
  if [ -n "${SAS_JSON:-}" ]; then
    echo ""
    echo "### Current repo About box"
    echo ""
    echo "| Field | Value |"
    echo "|---|---|"
    # Escape pipes in user-visible fields so the table renders.
    desc_md="${REPO_DESC:-_(empty)_}"
    desc_md="$(printf '%s' "${desc_md}" | sed -e 's/|/\\|/g')"
    home_md="${REPO_HOMEPAGE:-_(empty)_}"
    home_md="$(printf '%s' "${home_md}" | sed -e 's/|/\\|/g')"
    echo "| Description (${REPO_DESC_LEN:-0} chars) | ${desc_md} |"
    echo "| Homepage | ${home_md} |"
    if [ "${REPO_TOPICS_COUNT:-0}" -gt 0 ]; then
      topics_md="$(printf '%s' "${REPO_TOPICS}" | sed -e 's/|/\\|/g' -e 's/ /`, `/g')"
      echo "| Topics (${REPO_TOPICS_COUNT}) | \`${topics_md}\` |"
    else
      echo "| Topics | _(none)_ |"
    fi

    # Home-page tab toggles (readable via REST).
    echo ""
    echo "### Repo home-page tabs"
    echo ""
    echo "| Tab | Enabled |"
    echo "|---|---|"
    echo "| Issues       | \`${REPO_HAS_ISSUES:-unknown}\` |"
    echo "| Projects     | \`${REPO_HAS_PROJECTS:-unknown}\` |"
    echo "| Wiki         | \`${REPO_HAS_WIKI:-unknown}\` |"
    echo "| Pages        | \`${REPO_HAS_PAGES:-unknown}\` |"
    echo "| Discussions  | \`${REPO_HAS_DISCUSSIONS:-unknown}\` |"
    echo "| Downloads    | \`${REPO_HAS_DOWNLOADS:-unknown}\` |"

    # Sidebar widget toggles -- write-only on the REST surface.
    # The `repo-metadata` composite PATCHes these on release
    # (`show_releases` / `show_deployments` / `show_packages`)
    # but `GET /repos/{owner}/{repo}` does not return them, so
    # this section documents the intended convention rather
    # than measuring the live state.
    echo ""
    echo "### Sidebar widgets (\"Include in the home page\")"
    echo ""
    # shellcheck disable=SC2006  # markdown backticks in literal string, not command substitution
    echo "_The Releases / Deployments / Packages widget toggles are not exposed by the GitHub REST API. Set them via the [\`repo-metadata\`](https://github.com/blackoutsecure/bos-marketplace-kit#repo-about-box-sync-repo-metadata) composite on release (defaults: Releases on, Deployments off, Packages off) or in Settings → General._"
  fi

  # Remediation digest: failures then warnings, so a red build shows the
  # fix list without re-reading the full rule table.
  if [ "${FAILED}" -gt 0 ] || [ "${WARNED}" -gt 0 ]; then
    echo ""
    echo "### Action required"
    echo ""
    printf '%s\n' "${SORTED_REPORT}" | awk -F'|' '
      $2=="fail" { gsub(/\|/, "\\|", $3); printf "- ❌ **%s** — %s\n", $1, $3 }'
    printf '%s\n' "${SORTED_REPORT}" | awk -F'|' '
      $2=="warn" { gsub(/\|/, "\\|", $3); printf "- ⚠️ **%s** — %s\n", $1, $3 }'
  fi

  # Provenance: which kit build produced the report and which config
  # tiers selected the rules. Exported by `config.py` into $GITHUB_ENV.
  echo ""
  echo "### Run provenance"
  echo ""
  echo "| Field | Value |"
  echo "|---|---|"
  # shellcheck disable=SC2006  # markdown backticks in literal strings, not command substitution
  echo "| Kit | \`${MK_KIT_NAME:-bos-marketplace-kit}\` \`${MK_KIT_VERSION:-unknown}\` (${MK_KIT_METADATA_SOURCE:-bundled}) |"
  echo "| Config cascade | ${MK_CONFIG_TIERS:-runtime defaults} |"
  # shellcheck disable=SC2006  # markdown backticks in literal strings, not command substitution
  echo "| Effective config | \`${MK_CONFIG_SOURCE:-runtime defaults}\` |"
  echo "| Publishing version | \`${MK_PUB_VERSION:-unknown}\` (release tag when auto) |"
  echo "| Publishing license | \`${MK_PUB_LICENSE:-unknown}\` (LICENSE/COPYING when auto) |"
  if [ -n "${MK_CONFIG_SUPPRESSED:-}" ]; then
    echo "| Delegated rules | ${MK_CONFIG_SUPPRESSED} |"
  fi

  echo ""
  echo "Generated by [bos-marketplace-kit](https://github.com/blackoutsecure/bos-marketplace-kit)."
} >> "${GITHUB_STEP_SUMMARY:-/dev/stderr}"

# Outputs.
{
  echo "passed=${PASSED}"
  echo "failed=${FAILED}"
  echo "warnings=${WARNED}"
  echo 'report<<__END_REPORT__'
  printf '%s\n' "${SORTED_REPORT}"
  echo '__END_REPORT__'
} >> "${GITHUB_OUTPUT}"

# Pretty log line per result.
printf '%s\n' "${SORTED_REPORT}" | awk -F'|' '{
  if ($2=="fail")      printf "::error::%s [%s]: %s\n", "Marketplace check", $1, $3;
  else if ($2=="warn") printf "::warning::%s [%s]: %s\n", "Marketplace check", $1, $3;
  else                 printf "  [%s] %s — %s\n", $2, $1, $3;
}'

echo ""
echo "Marketplace check: ${PASSED} passed, ${FAILED} failed, ${WARNED} warnings, ${SKIPPED} skipped."

# Exit policy.
if [ "${FAILED}" -gt 0 ]; then
  die "${FAILED} required check(s) failed — see report above"
fi
if [ "${FAIL_ON_WARN}" = "true" ] && [ "${WARNED}" -gt 0 ]; then
  die "${WARNED} warning(s) treated as failures (fail_on_warning=true)"
fi

echo "Marketplace check: OK."
