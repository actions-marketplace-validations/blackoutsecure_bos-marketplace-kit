# Blackout Secure Marketplace Kit

**Copyright © 2025-2026 Blackout Secure | Apache License 2.0**

[![Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-blue?logo=github)](https://github.com/marketplace/actions/blackout-secure-marketplace-kit)
[![GitHub release](https://img.shields.io/github/v/release/blackoutsecure/bos-marketplace-kit?sort=semver)](https://github.com/blackoutsecure/bos-marketplace-kit/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Made by BlackoutSecure](https://img.shields.io/badge/made%20by-BlackoutSecure-1f1f1f)](https://github.com/blackoutsecure)

> Lint, gate, and publish GitHub Marketplace Actions — without the boilerplate.

**bos-marketplace-kit** is a self-contained toolkit for shipping
GitHub Marketplace Actions safely:

* **`check`** — pre-publish readiness validator. 19+ rules cover
  Marketplace metadata, naming, branding (Feather icon + colour),
  reserved-name conflicts, README conventions, and security defaults.
* **`guard`** — block PRs that touch your Marketplace publish surface
  (`action.yml` at root, `dist/**`, etc.) so reviewers see them every
  time. Configurable allow / block / require lists.
* **`promote`** — wipe-and-replay an allowlisted file set from your
  working branch (`dev`) to your Marketplace-facing branch (`main`),
  then tag and release. Designed for the **dev-as-source, main-as-API**
  pattern that Marketplace requires.
* **`name-check`** — verify a proposed action name is available on the
  Marketplace and is not a reserved category or feature slug.
* **`branding-preview`** — render the SVG that the Marketplace will
  display, and post it as a PR comment. No more guessing.
* **`dist-check`** — for bundled JS Actions (e.g. `@vercel/ncc`,
  `esbuild`, `tsup`), rebuild `dist/` from `src/` and fail the PR if
  the committed bundle is stale. Stops the classic Marketplace bug
  where merged source changes ship with the previous build.

Use it as a **composite action**, as a **reusable workflow**, or as a
**local CLI**. Same checks. Same output.

---

## Why this exists

Publishing on the Marketplace has rules that are easy to miss:

* `action.yml` must be at the root of the default branch.
* The default branch must not contain any `.github/workflows/*` files.
* The `name:` field has four sub-rules (unique, not a user/org, not a
  category, not a reserved feature).
* `branding.icon` must come from a specific snapshot of Feather Icons.
* `branding.color` must be one of nine allowed values.
* Verified Creator status requires manual outreach.

You can't catch any of this until your release pipeline runs (or worse,
until your listing rejects the publish). This kit catches all of it
*before* the PR merges.

## Quick start

### As a GitHub Action (recommended)

In a workflow on your **`dev`** branch:

```yaml
name: pre-publish check

on:
  pull_request:
    branches: [dev]

permissions:
  contents: read

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: blackoutsecure/bos-marketplace-kit@v1
        with:
          # everything optional; sensible defaults
          fail_on_warning: false
```

### As a CLI

```bash
pipx install bos-marketplace-kit

# Lint the current directory
marketplace-kit check .

# Lint a remote repo without cloning (uses GitHub API)
marketplace-kit check owner/repo

# Check a proposed action name
marketplace-kit name-check "my-cool-deployer"

# Get JSON for CI/dashboards
marketplace-kit check . --json
```

> The CLI is in active development. The composite actions are the
> shipping interface today.

## What's in the box

```
bos-marketplace-kit/
├── action.yml                          # root = pre-publish `check`
├── .github/actions/                    # composite actions (Marketplace surface)
│   ├── check/                          # pre-publish readiness validator
│   ├── guard/                          # PR-time publish-surface gate
│   ├── promote/                        # dev → main wipe-and-replay
│   ├── name-check/                     # Marketplace name uniqueness
│   ├── branding-preview/                # render the icon + colour SVG
│   ├── dist-check/                      # bundled-dist freshness check (JS Actions)
│   ├── lint/                            # markdown/yaml/shell/actions linter
│   └── branch-protection/               # branch-protection compliance (check + enforce)
├── .github/workflows/                  # dev-only CI; NEVER promoted to main
│   ├── tests.yml                       # Python CLI smoke + pytest
│   ├── codeql.yml                      # CodeQL static analysis
│   ├── release.yml                     # dev → main promote + tag + release
│   ├── self-check.yml                  # dogfood: check + name + branding + lint + protection
│   └── self-guard.yml                  # dogfood: guard own PRs (publish-surface gate)
├── scripts/
│   ├── bootstrap-ruleset.sh            # one-shot main-branch protection
│   └── bootstrap-branch-protection.sh  # legacy fallback
└── src/marketplace_kit/                # Python CLI
```

### Composites vs `scripts/` — when to use which

The kit ships **two** kinds of automation, and they answer different questions:

| | `.github/actions/*` (composites) | `scripts/*.sh` (operator one-shots) |
|---|---|---|
| **Runs where?** | Inside a workflow, on every PR / push / release. | On your laptop, once per repo. |
| **Auth?** | `GITHUB_TOKEN` (limited — `contents: read`, `pull-requests: write`, etc.). | Operator's `gh auth login` token, often with `admin:org` scope. |
| **What it does** | Recurring, idempotent checks: validate manifest, lint, drift-detect branch protection, guard the publish surface. | Privileged bootstrap: create an org-level ruleset, configure classic branch protection. |
| **Failure mode** | A red ❌ on the PR / commit. | A loud `exit 1` in the operator's terminal. |
| **Frequency** | Every event. | Once, then forget — until your release-bot rotates. |

Rule of thumb: if a maintainer needs to *re-grant* a scope to make
it work, it lives in `scripts/`. Everything else is a composite.

### A note on the bundled `_bp.py`

The `branch-protection` composite ships an inline Python helper at
`.github/actions/branch-protection/_bp.py`. It is **not** part of the
PyPI package — it lives next to its consumer so that downstream users
who pin the composite (`uses: blackoutsecure/bos-marketplace-kit/.github/actions/branch-protection@v1`)
get the helper for free, with no `pip install` required.

The composite invokes it as
`python3 "${GITHUB_ACTION_PATH}/_bp.py" build|compare|parse-restrict`.
The test suite imports it via `importlib.util.spec_from_file_location`
in `tests/conftest.py` so it can exercise the same code paths the
composite runs at action time.

## The dev → main publish model

Marketplace publishing has one weird trick: the default branch must
contain `action.yml` but **not** any `.github/workflows/*`. So your
day-to-day branch with CI cannot be the published branch.

This kit codifies a two-branch model:

```
                 ┌─────────────────────────────────────────┐
                 │  dev   ← all PRs land here              │
                 │        ← workflows + tests + src        │
                 │        ← @v1.x.x floating tag           │
                 └─────────────────┬───────────────────────┘
                                   │
                            promote (allowlist)
                                   ▼
                 ┌─────────────────────────────────────────┐
                 │  main  ← Marketplace-facing surface     │
                 │        ← action.yml + dist/ + README    │
                 │        ← @v1.2.3 immutable tags         │
                 │        ← NO workflows on this branch    │
                 └─────────────────────────────────────────┘
```

The `promote` composite handles the wipe-and-replay. The `guard`
composite enforces the rules during PR review.

See [Publishing to Marketplace](#publishing-to-marketplace) below for
the full step-by-step walkthrough, and the
[Check rule catalogue](#check-rule-catalogue) for the complete list
of enforced rules.

## Examples

### Minimal pre-publish check

Drop this at `.github/workflows/marketplace-check.yml` in your
Marketplace Action repo. Runs on every PR and push to `main`; fails
the PR if any `MP###` / `SC###` check fails.

```yaml
name: marketplace-check

"on":
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  check:
    name: bos-marketplace-kit check
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      # Pin to a release tag (`@v1`) for ergonomic upgrades, or to a
      # SHA for maximum supply-chain safety.
      - uses: blackoutsecure/bos-marketplace-kit@v1
        with:
          action_yml_path: action.yml
          # Set `true` to surface OP### best-practice warnings as
          # failures. Default `false` keeps the PR green on style nits.
          fail_on_warning: 'false'
```

### Full lifecycle (check + guard + promote)

Split the snippets below into three files under
`.github/workflows/` on your **`dev`** branch (never on `main` —
Marketplace publishing prohibits workflows on the default branch).

Prerequisites:

* Default branch is `main`.
* Working branch is `dev` (or your equivalent).
* `vars.MARKETPLACE_BYPASS_ACTOR_ID` is set if you've enabled the org
  ruleset (see [`scripts/bootstrap-ruleset.sh`](scripts/bootstrap-ruleset.sh)).

#### File 1 — `.github/workflows/marketplace-check.yml`

```yaml
name: marketplace-check

"on":
  push:
    branches: [dev]
  pull_request:
    branches: [dev]

permissions:
  contents: read

jobs:
  check:
    name: Pre-publish validate
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - uses: blackoutsecure/bos-marketplace-kit@v1
        with:
          action_yml_path: action.yml
          fail_on_warning: 'true'

  name-check:
    # Only run on PRs (one external API call per check).
    if: github.event_name == 'pull_request'
    name: Marketplace name availability
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - id: name
        run: |
          set -euo pipefail
          name="$(python3 -c "import yaml; print(yaml.safe_load(open('action.yml'))['name'])")"
          echo "name=${name}" >> "${GITHUB_OUTPUT}"
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/name-check@v1
        with:
          proposed_name: ${{ steps.name.outputs.name }}
          # After first publish your own listing collides — switch
          # this to 'false' once you've published.
          fail_on_collision: 'true'

  branding:
    name: Render branding preview
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 3
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - id: bp
        uses: blackoutsecure/bos-marketplace-kit/.github/actions/branding-preview@v1
      - uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2
        with:
          name: marketplace-branding-preview
          path: ${{ steps.bp.outputs.card_path }}
```

#### File 2 — `.github/workflows/marketplace-guard.yml`

Defence-in-depth against accidentally adding a workflow to `main`.
Triggers on PRs into `main` from `dev`.

```yaml
name: marketplace-guard

"on":
  pull_request_target:
    branches: [main]

permissions:
  contents: read

jobs:
  guard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          ref: ${{ github.event.pull_request.base.ref }}
          fetch-depth: 0
          persist-credentials: false
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/guard@v1
        with:
          pr_base_sha:        ${{ github.event.pull_request.base.sha }}
          pr_head_sha:        ${{ github.event.pull_request.head.sha }}
          check_pr_diff:      'true'
          check_tree_state:   'true'
          require_action_yml: 'true'
```

#### File 3 — `.github/workflows/release.yml`

Manual release: operator invokes via `gh workflow run release.yml`.
Promotes `dev` → `main` (allowlist), tags `main`, and publishes a
GitHub Release.

```yaml
name: release

"on":
  workflow_dispatch:
    inputs:
      tag_name:
        description: 'Tag (SemVer, e.g. v1.0.0).'
        required: true
      dry_run:
        description: 'Stage diff but do not push.'
        type: boolean
        default: false

permissions:
  contents: read

jobs:
  promote:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          ref: dev
          fetch-depth: 0
          persist-credentials: true
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/promote@v1
        with:
          source_branch:  dev
          target_branch:  main
          tag_name:       ${{ inputs.tag_name }}
          dry_run:        ${{ inputs.dry_run }}
          allowlist_paths: |
            action.yml
            LICENSE
            README.md
          extra_allowlist_paths: |
            .github/dependabot.yml
```

### Bundled-JS-Action dist freshness (`dist-check`)

For JS-based Actions whose `runs.main:` points at a bundled file
(typically `dist/index.js`, built via `@vercel/ncc`, `esbuild`, or
`tsup`), `dist-check` rebuilds from `src/` and fails the PR if the
committed bundle is stale. Drop it as an extra job alongside the
checks above:

```yaml
jobs:
  dist-check:
    name: dist/ freshness
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - uses: actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444 # v5.0.0
        with:
          node-version: '20'
          cache: 'npm'
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/dist-check@v1
        with:
          # All inputs optional; sensible defaults for ncc-style projects.
          dist_path:     'dist'
          build_command: 'npm ci && npm run build'
          fail_on_drift: 'true'
```

`dist-check` is opt-in (not part of the root `check` composite)
because it is JS-specific and requires a Node toolchain on the
runner. For non-npm projects, override `build_command` (e.g.
`pnpm install --frozen-lockfile && pnpm build`).

### Lint markdown / yaml / shell / actions (`lint`)

The `lint` composite runs the four lint tools the kit ships configs
for. Drop it as a dev-branch job:

```yaml
jobs:
  lint:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/lint@v1
        with:
          severity: 'fail'        # 'warn' or 'skip' to downgrade
          # All four linters on by default. Set false to opt out.
          run_markdownlint: 'true'
          run_yamllint:     'true'
          run_shellcheck:   'true'
          run_actionlint:   'true'
```

The composite auto-detects file globs (`**/*.md`, `**/*.yml`,
`**/*.sh`, `.github/workflows/**/*.yml`), installs each tool on
demand with pinned versions (markdownlint-cli2 `0.18.1`, yamllint
`1.37.0`, actionlint `v1.7.7`; shellcheck is preinstalled on
`ubuntu-latest`), and emits a markdown table to the job summary.

Need configs? `marketplace-kit generate-policy markdownlint`,
`yamllint`, or `shellcheckrc`.

### Branch-protection compliance (`branch-protection`)

The `branch-protection` composite has two modes:

* **`check`** (default, safe): read the current branch-protection
  state via `GET /repos/{}/branches/{branch}/protection` and report
  drift against your declared intent. No write permissions needed.
* **`enforce`**: `PUT` the declared intent (idempotent). Requires a
  token with `Administration: write`.

```yaml
jobs:
  branch-protection-compliance:
    runs-on: ubuntu-latest
    steps:
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/branch-protection@v1
        with:
          github_token: ${{ github.token }}
          mode: 'check'          # 'enforce' to apply
          severity: 'warn'       # 'fail' to break PRs on drift
          branch: 'main'
          bp_require_pull_request:     'true'
          bp_required_approvals:       '1'
          bp_no_force_push:            'true'
          bp_no_deletion:              'true'
          bp_require_linear_history:   'true'
          bp_require_signed_commits:   'false'
          bp_required_status_checks: |
            check
            guard
          bp_required_strict_status_checks: 'true'
          # `include_administrators` defaults to false (solo-maintainer
          # friendly). Set true when you want EVERYONE to need a PR.
          bp_include_administrators: 'false'
```

The composite outputs `is_compliant`, `drift_summary` (multi-line),
and `mode_applied`. Use these to gate downstream jobs or post a
summary comment.

## Publishing to Marketplace

This section walks you through publishing a Marketplace-listed Action
using `bos-marketplace-kit`. It assumes you have a working action
repo and the rights to publish from that repo.

Marketplace has FIVE non-negotiable prerequisites:

1. A single `action.yml` at the root of the **default branch**.
2. NO workflow files (`.github/workflows/*.yml`) on the default branch.
3. A unique `name:` that is not a GitHub user/org, not a reserved
   category, and not a reserved feature.
4. `branding.icon` is a Feather v4.28.0 icon name.
5. `branding.color` is in `{white, yellow, blue, green, orange, red, purple, gray-dark}`.

The kit's dev→main lifecycle is designed around these constraints. CI
lives on `dev`; the Marketplace surface lives on `main`.

### Step 1 — Set up branches

Default branch on your action repo should be `main`. Working branch
is `dev`.

```bash
git checkout -b dev
git push -u origin dev
```

In the repo Settings → Branches, set the default branch to `main`.

### Step 2 — Add the kit's CI on `dev`

Create `.github/workflows/marketplace-check.yml` on `dev` (see the
[Minimal pre-publish check](#minimal-pre-publish-check) example
above). Then run it locally first using the CLI:

```bash
pip install bos-marketplace-kit
marketplace-kit check
```

Fix any `MP###` or `SC###` failures before continuing. `OP###`
warnings are optional but recommended.

### Step 3 — Verify the name

```bash
marketplace-kit name-check "Your Action Name"
```

If this reports any collision, rename before publishing. Renaming
**after** publishing requires a new repo URL — much more painful.

### Step 4 — Render the branding preview

In CI the `branding-preview` composite renders an SVG and uploads it
as an artifact. Open the SVG artifact in the PR run. If the icon or
colour is wrong, fix it in `action.yml` and re-run.

### Step 5 — Add the release workflow on `dev`

Create `.github/workflows/release.yml` on `dev` (see
[File 3 in the Full lifecycle example](#full-lifecycle-check--guard--promote)
above for the full template).

The release workflow:

1. Validates the SemVer tag input.
2. Promotes `dev` → `main` using the kit's `promote` action.
3. The `promote` action HARD-BLOCKS any `.github/workflows/**` entry
   in the allowlist, transitively strips workflows pulled in via
   parent directories, removes anything not in the allowlist from
   `main`, and pushes a clean commit + tag.
4. Creates a GitHub Release on the new tag.

### Step 6 — Configure branch protection on `main`

Two options, in order of preference:

#### Option A: Org-level ruleset (recommended)

```bash
# From a clone of your action repo:
export ORG=your-org
export REPO=your-action-repo
export BYPASS_ACTOR_ID=<your-release-bot-app-installation-id>

scripts/bootstrap-ruleset.sh
```

The ruleset enforces `file_path_restriction` on `.github/workflows/**`
at the GitHub-platform layer. No commit containing those paths can
land on `main`, **regardless of how it got there** (PR merge, push,
API). The bypass actor is the only identity that can push files
matching the restriction — and it should be your release bot ONLY.

#### Option B: Branch protection (fallback)

If you don't have org-level ruleset access:

```bash
scripts/bootstrap-branch-protection.sh
```

This sets:

* `required_status_checks`: marketplace-check
* `enforce_admins`: true
* `allow_force_pushes`: false
* `allow_deletions`: false

**Caveat:** Branch protection does NOT enforce file-path restrictions.
You're relying entirely on the kit's `guard` + `promote` actions to
keep workflows off `main`. This is brittle without the org ruleset.

### Step 7 — First release

From `dev`:

```bash
gh workflow run release.yml -f tag_name=v1.0.0 -f dry_run=true
```

Inspect the dry-run output:

* `removed_paths` — verify nothing surprising is being deleted from `main`.
* `removed_violations` — should be empty (or list pre-existing drift to clean up).

Once happy:

```bash
gh workflow run release.yml -f tag_name=v1.0.0
```

The promote workflow will:

* Push a new commit to `main` with ONLY the allowlisted paths.
* Tag `main` at that commit with `v1.0.0`.
* Create a GitHub Release.

### Step 8 — Publish to Marketplace

Navigate to your repo's Releases page on GitHub. On the `v1.0.0`
release, click **Edit**. Tick **"Publish this Action to the GitHub
Marketplace"**. Choose a primary category and optional secondary
category. Click **Update release**.

The action appears at `https://github.com/marketplace/actions/<your-slug>`
within minutes.

### Step 9 — Set up the guard on PRs

Defense-in-depth: add `.github/workflows/marketplace-guard.yml` on
`dev` (see
[File 2 in the Full lifecycle example](#full-lifecycle-check--guard--promote)
above). This runs on every PR targeting `main` and fails fast if the
PR would introduce a prohibited path.

Without the guard, you'd discover violations at promote time (too
late — your operator typed the version and hit go). The guard
surfaces them in the PR check list.

### Updating the action

1. Branch off `dev`, make changes.
2. Open PR → `dev`. CI runs (check + guard + branding preview).
3. Merge to `dev`.
4. Tag and release: `gh workflow run release.yml -f tag_name=v1.0.1`.

The Marketplace listing auto-updates as soon as the tag exists.

### Troubleshooting

**"Failed to publish: this repository contains workflow files"**

Your `main` has at least one `.github/workflows/*.yml`. Find them:

```bash
git ls-tree -r --name-only main | grep '^\.github/workflows/'
```

The `promote` action will strip them automatically on the next
release:

```bash
gh workflow run release.yml -f tag_name=v1.0.1
```

**Branding icon is wrong.** Run `marketplace-kit check` — the
`branding-preview` composite or the local CLI will tell you the exact
Feather icon name. Fix on `dev` and re-release.

**"Action name 'X' is already taken".** Rename early. After
publishing, the slug is permanent on your repo. Renaming requires
creating a new repo, transferring stars, and re-publishing.

**Promote fails with `removed_violations`.** Your `main` had
`.github/workflows/**` paths before this promote. The kit removed
them — verify with the dry-run output, then re-run.

### Further reading

* [Check rule catalogue](#check-rule-catalogue) below.
* [GitHub Marketplace publishing docs](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace)
* [Feather icon set](https://feathericons.com/) (v4.28.0)

## Check rule catalogue

The `check` action enforces a layered set of rules against your
`action.yml`. Each rule has a stable ID across versions; skip
individual rules with the `skip_checks` input.

Rule families:

| Prefix  | Severity   | Failure causes |
|---------|------------|----------------|
| `MP###` | **Fatal**  | Marketplace publish prerequisite missing or invalid. Action would not be acceptable to GitHub. |
| `OP###` | Warning    | Best-practice violation. Non-fatal by default; set `fail_on_warning: true` to promote. |
| `SC###` | **Fatal**  | Security-impacting default missing. Failure indicates a supply-chain or token-exposure risk. |
| `CH###` | Configurable | Community-health file missing. Default `warn` or `skip` per file; promote to `fail` via the matching `require_*` input. |
| `DP###` | Configurable | Dependabot config missing. Default `warn`. |
| `CQ###` | Configurable | CodeQL workflow missing. Default `warn`. |
| `LT###` | Configurable | Lint config file missing (`.editorconfig`, `.gitattributes`, `.gitignore`, markdownlint, yamllint). |
| `GH###` | Configurable | GitHub Advanced Security toggle disabled (code scanning, secret scanning, Dependabot alerts). Requires `github_token`. |
| `MS###` | Configurable | Microsoft Security DevOps workflow missing. Default `skip` (opt-in). |
| `SR###` | Configurable | OpenSSF Scorecard workflow missing. Default `skip` (opt-in). |

### MP001 — Top-level manifest keys

**Required:** `name`, `description`, `runs` MUST be present at the
root of `action.yml`. `runs:` must be a mapping containing at least
`using:`.

### MP002 — `name` is non-empty

`name:` must be a non-empty string. Marketplace displays this on the
listing card and across search results.

### MP003 — `description` is non-empty

`description:` is the one-line subtitle on the Marketplace card. See
also: [OP001](#op001--description-length).

### MP004 — `runs.using` is present

`runs:` must declare an execution model: `composite`, `node20` (or
newer LTS), or `docker`. Set `runs.using: composite` for most
shell-driven actions.

### MP005 — `branding.icon` is present

Marketplace requires a Feather icon name in `branding.icon`. The
icon set is pinned to Feather v4.28.0 by GitHub. Use the kit's
`branding-preview` action to render the resulting card before
pushing.

```yaml
branding:
  icon: check-circle
  color: green
```

### MP006 — `branding.color` is in the allowed enum

Allowed: `white`, `yellow`, `blue`, `green`, `orange`, `red`,
`purple`, `gray-dark`. No hex codes, no other names.

### MP007 — `action.yml` lives at the repo root

Marketplace ONLY detects a single manifest at the root of the default
branch. Subdirectory manifests (e.g. `.github/actions/foo/action.yml`)
are NOT listable on Marketplace. The `promote` action's allowlist
should include `action.yml`.

### MP008 — Name is not too short

Marketplace rejects single-character action names and very short
names that collide with reserved features. Use a name of at least 3
characters and run the kit's `name-check` action to validate
availability.

### MP009 — Description is not too short

A description shorter than 10 characters is unlikely to be useful on
the Marketplace card and may be rejected. Expand to a complete
sentence (~30-125 chars).

### OP001 — Description length

Marketplace truncates description >125 characters in card view.
Tighten the description to a single short sentence; use `README.md`
for elaboration.

### OP003 — `author` is set

Optional but strongly recommended. Marketplace shows the author on
the listing card. Add `author: Your Org Name`.

### OP004 — README has a Usage / Quickstart / Example section

Marketplace consumers scan READMEs looking for a copy-pasteable
snippet. The check looks for a heading matching
`Usage`, `Quickstart`, `Getting Started`, or `Example` (any depth).
Add one to your `README.md`:

```markdown
## Usage

```yaml
- uses: your-org/your-action@v1
  with:
    foo: bar
```
```

### OP005 — README is a reasonable size

A README under 512 bytes reads as low-effort to Marketplace
consumers; one above 128 KB hits the GitHub-side render limit. The
check passes when `README.md` is between 512 B and 128 KB.

### OP006 — README contains at least one image or badge

Listings without any visual element look notably less polished. A
status badge (e.g. CI passing, version) or a single screenshot is
enough. Any markdown image syntax `![alt](url)` satisfies the rule.

### OP007 — README contains at least 3 fenced code blocks

Marketplace consumers expect copy-pasteable snippets. The check
counts triple-backtick fenced blocks (`` ``` ``) and warns if fewer
than 3 are present.

### SC001 — Composite actions don't interpolate user input into `run:`

When a composite action interpolates `${{ inputs.* }}` or
`${{ github.event.* }}` directly inside a `run:` block, an attacker
who controls the input value (e.g. via a PR title) can break out of
the shell context and execute arbitrary code on the runner. Plumb
untrusted values via the step's `env:` block instead, then reference
the shell variable inside the script:

```yaml
- shell: bash
  env:
    TITLE: ${{ github.event.pull_request.title }}
  run: echo "$TITLE"
```

This rule is enforced by the bundled `check` composite action (which
scans every `run:` block under `.github/actions/**`). The CLI's
equivalent SHA-pinning rule is `SC002`.

### SC002 — Third-party actions are pinned by SHA

Tag/branch refs (`@v4`, `@main`) are mutable. A compromised tag move
can inject arbitrary code into your runner. SHA pins (`@<40-hex>`)
are immutable. Use Dependabot or `bos-upstream-watcher` to bump pins
automatically.

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
```

### SC003 — Security policy is discoverable

Public Marketplace listings should advertise a private reporting
channel for security issues. The check looks for any of:

* `SECURITY.md`, `.github/SECURITY.md`, or `docs/SECURITY.md` in the
  calling repo,
* the same files in the org's `.github` repository (when
  `check_org_health: true` and a token is supplied), **or**
* a README that mentions `security policy`, `SECURITY.md`, or
  `report ... vulnerability`.

Strictness is controlled by the `require_security` input:

| Value  | Behaviour on a missing policy                                                                     |
|--------|---------------------------------------------------------------------------------------------------|
| `fail` | Hard failure — the README escape hatch is also disabled at this level.                            |
| `warn` | **Default.** Records a warning. The action overall still passes unless `fail_on_warning: true`.   |
| `skip` | Rule short-circuits to a `skip` status — equivalent to listing `SC003` in `skip_checks`.          |

Generate a template:

```bash
marketplace-kit generate-policy security \
  --owner my-org --repo my-action --email security@example.com
```

### CH001-CH006 — Community-health files (org-aware)

The kit checks a small set of community-health files Marketplace
consumers expect on a popular public action. Each rule looks in this
repo first; if the file is missing, it falls back to the org's
`.github` repository (canonical home for shared defaults) when
`check_org_health: true` and `github_token` is non-empty. If found
in either location the rule passes; the report message records which
location was used.

| ID    | File                                                              | Default policy | Generator kind     |
|-------|-------------------------------------------------------------------|----------------|--------------------|
| CH001 | `CODE_OF_CONDUCT.md` (also `.github/`, `docs/`)                   | `warn`         | `code-of-conduct`  |
| CH002 | `CONTRIBUTING.md` (also `.github/`, `docs/`)                      | `warn`         | `contributing`     |
| CH003 | `SUPPORT.md` (also `.github/`, `docs/`)                           | `skip`         | `support`          |
| CH004 | `.github/ISSUE_TEMPLATE/` directory or `.github/ISSUE_TEMPLATE.md` | `skip`         | `issue-bug` / `issue-feature` |
| CH005 | `.github/PULL_REQUEST_TEMPLATE.md`                                | `skip`         | `pr-template`      |
| CH006 | `.github/FUNDING.yml`                                             | `skip`         | `funding`          |

Each rule takes a matching `require_*` input (`require_code_of_conduct`,
`require_contributing`, `require_support`, `require_issue_templates`,
`require_pr_template`, `require_funding`) with values `fail | warn |
skip` and the same semantics as `require_security` above.

#### Source mode — local vs inherited from the org `.github` repo

Each CH/SC rule additionally accepts a `*_source` input describing
*where* the file is expected to live. This lets you express the
"don't ship CoC/SECURITY/SUPPORT in every repo; inherit them from
the org `.github` repo" pattern without losing the safety net of an
explicit check.

| Mode      | Local check | Org fallback | Pass when                                                  |
|-----------|-------------|--------------|------------------------------------------------------------|
| `local`   | yes         | **disabled** | the file exists in this repo.                              |
| `inherit` | **skipped** | yes          | the file exists in `${org_health_repo}`.                   |
| `either`  | yes         | yes          | the file exists in either location (default — back-compat). |

Two layers of inputs:

* **`community_health_source`** sets the global default (one of
  `local | inherit | either`; default `either`).
* **Per-rule overrides** — `security_source`, `code_of_conduct_source`,
  `contributing_source`, `support_source`, `issue_templates_source`,
  `pr_template_source`, `funding_source` — take precedence when
  non-empty (default empty = use global).

Worked example: the kit itself ships only a repo-specific
`CONTRIBUTING.md` and the issue/PR templates; CoC, SECURITY, SUPPORT,
and FUNDING are inherited from `blackoutsecure/.github`:

```yaml
- uses: blackoutsecure/bos-marketplace-kit@v1
  with:
    github_token:          ${{ github.token }}
    require_security:      warn
    require_code_of_conduct: warn
    require_contributing:  warn
    require_support:       warn
    require_funding:       warn
    # Inherit these from the org `.github` repo:
    security_source:        inherit
    code_of_conduct_source: inherit
    support_source:         inherit
    funding_source:         inherit
    # Local-only (repo-specific content):
    contributing_source:    local
    issue_templates_source: local
    pr_template_source:     local
```

When a rule's source is `inherit` and the org lookup is unavailable
(token missing, `check_org_health: false`, or the probe fails), the
rule emits the configured severity with an explicit reason rather
than silently falling back. This guarantees that "inherit" never
means "silently pass".

#### Org-aware lookup

Set `check_org_health: true` (default) and pass `github_token:
${{ github.token }}` to enable the org-wide fallback. The check
makes at most:

* **one** `GET /repos/{owner}/.github` call to confirm the org
  health repo exists, and
* **one** `GET /repos/{owner}/.github/contents/{path}` per missing
  file (so 0-6 additional cheap API calls per run).

Override the destination repo with `org_health_repo: my-org/.github`
if your org uses a non-default location.

#### Generate a starter template

The kit ships a small, opinionated set of policy templates and a CLI
to emit them with placeholder substitution:

```bash
# List available kinds.
marketplace-kit generate-policy list

# Emit to the canonical path.
marketplace-kit generate-policy code-of-conduct \
  --owner my-org --repo my-action --email contact@example.com

# Or just print to stdout.
marketplace-kit generate-policy contributing --stdout
```

Placeholders: `{{owner}}`, `{{repo_name}}`, `{{contact_email}}`,
`{{project_name}}`. Unsubstituted placeholders fall back to
conservative defaults (`YOUR-ORG`, CWD basename,
`security@example.com`).

#### `auto_generate_missing` — reserved for a future iteration

A `auto_generate_missing: false | true` input is declared (default
`false`) to reserve the API for a future feature: when set to
`true`, missing files would be drafted by an LLM at workflow time
and opened as a PR (against this repo for `local`/`either` rules,
or against `${org_health_repo}` for `inherit`-mode rules) so policy
files stay current as guidance evolves.

This input is a forward-compatible stub today — setting `true`
emits a one-time warning and otherwise has no effect. Existing
callers don't need to change anything once the implementation lands.
The static `marketplace-kit generate-policy` command continues to
work today and is the supported way to bootstrap a file.

### DP001 / CQ001 / LT001-005 — CI / supply-chain hygiene

Adjacent to the community-health rules, the kit checks for the
standard supply-chain and lint config files a healthy Marketplace
repo should ship. These follow the same `fail | warn | skip` policy
pattern and the same generator-template story (`marketplace-kit
generate-policy <kind>`).

| ID    | File(s)                                                                    | Default policy | Generator kind             |
|-------|----------------------------------------------------------------------------|----------------|----------------------------|
| DP001 | `.github/dependabot.yml` / `.dependabot.yaml`                              | `warn`         | `dependabot`               |
| CQ001 | any workflow referencing `github/codeql-action`                            | `warn`         | `codeql-workflow`          |
| LT001 | `.editorconfig`                                                            | `warn`         | (no template; trivial)     |
| LT002 | `.gitattributes`                                                           | `warn`         | (no template; repo-shaped) |
| LT003 | `.gitignore`                                                               | `warn`         | (no template; repo-shaped) |
| LT004 | `.markdownlint.yaml` / `.markdownlint-cli2.yaml` / `.markdownlint.json`    | `skip`         | `markdownlint`             |
| LT005 | `.yamllint.yml` / `.yamllint.yaml` / `.yamllint`                           | `skip`         | `yamllint`                 |

The lint rules default to `skip` (LT004/LT005) or `warn` (LT001-003)
so legacy repos can adopt the kit without immediate cleanup. Promote
to `fail` as your repo catches up.

### GH001-GH003 — GitHub Advanced Security toggles (live repo settings)

These rules call the GitHub API to verify your repo-level security
toggles are actually enabled — surfacing drift between intent ("we
turned on secret scanning") and reality. Each requires `github_token`
with the appropriate scope.

| ID    | Setting                              | API                                                                    | Token scope                       | Default |
|-------|--------------------------------------|------------------------------------------------------------------------|-----------------------------------|---------|
| GH001 | Code scanning (CodeQL default-setup OR workflow) | `GET /repos/{}/code-scanning/default-setup`                | `metadata: read`                  | `warn`  |
| GH002 | Secret scanning                      | `GET /repos/{}` → `security_and_analysis.secret_scanning.status`        | admin/write on repo (PAT/App)†    | `warn`  |
| GH003 | Dependabot alerts                    | `GET /repos/{}/vulnerability-alerts` (204/404)                          | `Administration: read` (PAT/App)  | `warn`  |

† **About GH002:** `security_and_analysis` is only present in
`GET /repos/{}` responses when the caller has admin or write access
to the repo. The default `GITHUB_TOKEN` does NOT see this field
even though it can read the rest of the repo metadata. When the
field is absent, GH002 emits `skip` with a remediation hint rather
than a false-positive `disabled` -- supply a PAT or App
installation token with admin/write to introspect.

**Public repos:** all three features are free; default-on for new
repos created after 2023 and recommended for everything else.

**Private repos:** require a GitHub Advanced Security license. Set
`require_ghas_*: skip` if you're on a plan without GHAS.

If the token lacks scope the rule emits `skip` (not `fail`) with an
explanation, so a missing `Administration: read` doesn't silently
mask the broader check.

### MS001 — Microsoft Security DevOps workflow (opt-in)

`microsoft/security-devops-action` wraps a curated set of OSS scanners
(Bandit, Checkov, ESLint, Terrascan, Trivy, BinSkim, PSRule, …) and
surfaces findings as SARIF in GHAS code-scanning. For Azure-connected
repos, findings also flow into Microsoft Defender for Cloud.

* **Default:** `skip` — high signal for repos shipping IaC or
  container images, marginal noise for pure source repos.
* **Generator:** `marketplace-kit generate-policy security-devops-workflow`.
* Set `require_security_devops: warn` (or `fail`) for IaC-heavy or
  containerised repos.

### SR001 — OpenSSF Scorecard workflow (opt-in)

`ossf/scorecard-action` scores your repo's supply-chain posture
against the OpenSSF Scorecard checks (Branch-Protection, Pinned-Deps,
Token-Permissions, etc.) and publishes the result at
<https://scorecard.dev>. Free for public repos.

* **Default:** `skip`.
* **Generator:** `marketplace-kit generate-policy scorecard-workflow`.
* Recommended for public Marketplace actions — your Scorecard becomes
  a public quality signal alongside the Marketplace listing.

### Adding new rules

Open a PR against `dev` that:

1. Adds the rule to `.github/actions/check/action.yml`.
2. Documents it in the [Check rule catalogue](#check-rule-catalogue)
   section above with a stable ID.
3. Adds a unit test under `tests/` covering the failure case.
4. Bumps the kit's minor version.

The kit promises stability for `MP###`/`OP###`/`SC###`/`CH###` rule
IDs across minor versions — adding a rule never reuses an existing
ID.

## Versioning

Semantic versioning. The floating `@v1` tag follows the latest `v1.x.x`
release. Pin by SHA in security-sensitive workflows; pin by major-tag
for ergonomic upgrades.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). All PRs target the `dev`
branch — the `main` branch is built by the release pipeline and is
read-only to humans.

## Security

This repo's security policy is **inherited** from the organisation
defaults at [`blackoutsecure/.github`][org-health], which lists the
private channels for reporting vulnerabilities. Do not file public
issues for security reports.

### Reporting

Use one of the following private channels:

1. GitHub's [private vulnerability reporting][gh-pvr] (preferred).
   Navigate to the repo's **Security → Report a vulnerability** tab.
2. Email `security@blackoutsecure.com` with a clear subject line
   that starts with `[bos-marketplace-kit]`.

### Scope (kit-specific)

In scope:

* The composite actions under `.github/actions/**`.
* The Python CLI under `src/marketplace_kit/**`.
* The reusable workflows under `.github/workflows/**`.
* The bootstrap scripts under `scripts/**`.

Out of scope:

* GitHub Marketplace itself (report to GitHub via
  <https://github.com/security>).
* Third-party tools we invoke (`actionlint`, `action-validator`, etc.) —
  report upstream.
* Bugs in consumer repos that this tool happens to lint.

### Hardening notes for consumers

If you wire this kit into your own CI:

* Pin our actions by **commit SHA**, not tag. Tags can be moved.
* Set the **minimum required `permissions:`** on the calling workflow.
  `guard` needs `contents: read` + `pull-requests: read`. `promote`
  needs `contents: write`. `check` needs `contents: read`.
* When calling `guard` via `pull_request_target`, do **not** check
  out the PR head. The default checkout of the base ref is correct
  and safe.
* When calling `promote`, use a deploy key or a fine-grained PAT
  scoped to the target repo only. Do not use a classic PAT with
  broad scope.

[org-health]: https://github.com/blackoutsecure/.github
[gh-pvr]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability

## License

[Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE) for third-party attributions.
