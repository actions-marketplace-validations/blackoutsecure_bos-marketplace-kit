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
│   └── branding-preview/               # render the icon + colour SVG
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

See [`docs/publishing.md`](docs/publishing.md) for the full walkthrough.

## Documentation

* [`docs/checks.md`](docs/checks.md) — catalog of every check, with
  rationale and remediation.
* [`docs/publishing.md`](docs/publishing.md) — step-by-step Marketplace
  publish guide using this kit.
* [`docs/architecture.md`](docs/architecture.md) — design choices: why
  composites + workflow + CLI share one codebase, why bash-first, etc.
* [Examples](#examples) — copy-paste workflow snippets for the common
  use cases (below).

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
