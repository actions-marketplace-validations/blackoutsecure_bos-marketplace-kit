# bos-marketplace-kit

> Lint, gate, and publish GitHub Marketplace Actions — without the boilerplate.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Made by BlackoutSecure](https://img.shields.io/badge/made%20by-BlackoutSecure-1f1f1f)](https://github.com/blackoutsecure)

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
├── .github/actions/
│   ├── check/                          # pre-publish readiness validator
│   ├── guard/                          # PR-time publish-surface gate
│   ├── promote/                        # dev → main wipe-and-replay
│   ├── name-check/                     # Marketplace name uniqueness
│   └── branding-preview/               # render the icon + colour SVG
├── .github/workflows/
│   ├── lifecycle.yml                   # reusable orchestrator
│   ├── release-promote.yml             # reusable promote pipeline
│   └── marketplace-guard.yml           # reusable PR gate pipeline
├── scripts/
│   ├── bootstrap-ruleset.sh            # one-shot main-branch protection
│   └── bootstrap-branch-protection.sh  # legacy fallback
├── src/marketplace_kit/                # Python CLI
└── examples/                           # copy-paste workflow snippets
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
* [`examples/`](examples/) — copy-paste workflow snippets for the common
  use cases.

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

[MIT](LICENSE). See [`NOTICE`](NOTICE) for third-party attributions.
