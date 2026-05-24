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
│   └── dist-check/                      # bundled-dist freshness check (JS Actions)
├── .github/workflows/                  # dev-only CI; NEVER promoted to main
│   ├── ci.yml                          # actionlint + shellcheck
│   ├── release.yml                     # dev → main promote + tag + release
│   ├── self-check.yml                  # dogfood: check own action.yml
│   └── self-guard.yml                  # dogfood: guard own PRs
├── scripts/
│   ├── bootstrap-ruleset.sh            # one-shot main-branch protection
│   └── bootstrap-branch-protection.sh  # legacy fallback
└── src/marketplace_kit/                # Python CLI
```

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

The `--ai` flag is reserved for a future iteration that drafts the
policy using a language model; today it falls back to the static
template and prints a notice.

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

See [`SECURITY.md`](SECURITY.md). Do not file public issues for
security reports.

## License

[Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE) for third-party attributions.
