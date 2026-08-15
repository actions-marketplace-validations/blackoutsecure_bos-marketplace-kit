# Blackout Secure Marketplace Kit

**Copyright © 2025-2026 Blackout Secure | Apache License 2.0**

[![Marketplace](https://img.shields.io/badge/GitHub%20Marketplace-blue?logo=github)](https://github.com/marketplace/actions/blackout-secure-marketplace-kit)
[![GitHub release](https://img.shields.io/github/v/release/blackoutsecure/bos-marketplace-kit?sort=semver)](https://github.com/blackoutsecure/bos-marketplace-kit/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![Made by BlackoutSecure](https://img.shields.io/badge/made%20by-BlackoutSecure-1f1f1f)](https://github.com/blackoutsecure)

> Lint, gate, and publish GitHub Marketplace Actions — without the boilerplate.

A drop-in composite GitHub Action that reads JSON config → validates your
Marketplace manifest, community-health surface, and live repo settings →
reports what to fix, or blocks the PR.

Everything in one Marketplace install: a pre-publish rule catalogue, a PR
guard for your publish surface, a `dev` → `main` promoter, name and branding
previews, and a local CLI that runs the same checks offline.

## ✨ Features

* **Layered JSON config** — bundled Marketplace best practices are merged with
  an optional organization config and an optional repository config. Zero
  configuration gets you the recommended posture; one file changes it for a
  whole org.
* **40+ rules across ten families** — `MP###` Marketplace requirements, `OP###`
  operational polish, `SC###` security hygiene, `CH###` community health,
  `DP###`/`CQ###`/`LT###` supply-chain and lint config, `GH###` Advanced
  Security toggles, `MS###`/`SR###` opt-in scanners, and `RM###` live repo
  *About* box. Every rule's severity is `fail`, `warn`, or `skip`.
* **Org-aware community health** — each `CH###`/`SC###` rule can require a file
  `local`ly, `inherit` it from your org `.github` repo, or accept `either`.
* **Publish-surface guard + promoter** — `guard` blocks PRs that touch
  `action.yml`, `dist/**`, or anything else on your Marketplace surface;
  `promote` wipe-and-replays an allowlisted file set from `dev` to `main`,
  then tags and releases.
* **AI-assisted remediation** — findings are summarised with GitHub Models
  when a usable token is present, or any OpenAI-compatible provider, and
  always fall back to deterministic local remediation. Disable with
  `enable_ai_findings_summary: false`.
* **Independent package metadata** — package identity stays available even
  when repository policy is absent, overridden, or failed to load.
* **Job summary** — every run writes a markdown report of the resolved
  configuration, per-rule results, and the remediation summary.
* **Pure-stdlib Python core** — the config resolver, AI layer, and CLI need
  nothing beyond the standard library (`PyYAML` only for manifest parsing).
  The composite runs its bundled source directly, with no package install.

## 📖 Table of Contents

* [Blackout Secure Marketplace Kit](#blackout-secure-marketplace-kit)
  * [✨ Features](#-features)
  * [📖 Table of Contents](#-table-of-contents)
  * [📋 Prerequisites](#-prerequisites)
  * [🚀 Quick start](#-quick-start)
    * [Version pinning](#version-pinning)
    * [AI triage and data handling](#ai-triage-and-data-handling)
  * [⚙️ Action inputs](#️-action-inputs)
  * [📤 Action outputs](#-action-outputs)
  * [🧰 What's in the box](#-whats-in-the-box)
  * [🏗️ Configuration inheritance and layering](#️-configuration-inheritance-and-layering)
    * [Composing with bos-code-scanning-kit](#composing-with-bos-code-scanning-kit)
    * [Posture profiles](#posture-profiles)
  * [📦 Package metadata](#-package-metadata)
  * [✅ Check rule catalogue](#-check-rule-catalogue)
  * [🚢 Publishing to Marketplace](#-publishing-to-marketplace)
  * [🧪 Examples](#-examples)
  * [💻 Local usage (CLI)](#-local-usage-cli)
  * [⚠️ Runtime and repository notes](#️-runtime-and-repository-notes)
  * [🔐 Security](#-security)
  * [🏷️ Versioning](#️-versioning)
  * [🤝 Contributing](#-contributing)
  * [📜 License](#-license)

## 📋 Prerequisites

* **GitHub-hosted Linux runner** (`ubuntu-latest` or newer). The action
  installs `actionlint` itself and verifies it against a pinned SHA-256 for
  the runner's architecture.
* **`actions/checkout` before the kit runs**, so there is a working tree to
  validate.
* **`contents: read`** is enough for the manifest, community-health, and lint
  rules.
* **A token** for the `CH###` org-health lookups, the `GH###` Advanced
  Security probes, and the `RM###` *About* box rules. The default
  `${{ github.token }}` covers `RM###` and the org-health lookup; `GH003`
  (Dependabot alerts) is admin-scoped and needs a PAT.
* **`models: read`** only if you want the AI remediation summary. Without it
  the kit silently uses local remediation.
* **Python 3.10+** for the optional local CLI.

## 🚀 Quick start

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

That's it. The repo config and the optional org global config are
auto-discovered, so the workflow does not repeat config paths. Every policy
input can still override the config for a single run.

For the local CLI, see [💻 Local usage (CLI)](#-local-usage-cli).

### Version pinning

Pick a `uses:` ref shape based on how strict your supply-chain posture needs
to be. All three forms are supported equally.

| Form | Example | When to use |
|------|---------|-------------|
| Floating major (default) | `blackoutsecure/bos-marketplace-kit@v1` | Friendly default. Auto-tracks every `v1.x.y` release as we ship fixes and new rules. Recommended for most callers. |
| Immutable tag | `blackoutsecure/bos-marketplace-kit@v1.0.0` | Pin to a specific release. Identical rule results across runs; requires manual bumps. Recommended when a new rule turning `warn` would break a pipeline. |
| SHA-pinned | `blackoutsecure/bos-marketplace-kit@<40-char-sha> # v1.0.0` | Strictest. Survives even a malicious tag-move on this repo. Recommended for regulated / high-security callers. Use Dependabot's `package-ecosystem: github-actions` to keep the pin current. |

The SHA for any tag is `git rev-list -n 1 v1.0.0` against this repo, or the
`commit` field of the GitHub Release JSON.

### AI triage and data handling

The bundled Marketplace config enables AI remediation in `auto` mode. The
action first looks for GitHub Models credentials, then for an explicitly
configured external provider. If no provider is usable, or a request fails,
the run continues with deterministic local remediation and the job summary
records the fallback reason. **A model is never on the critical path** — it
cannot fail a build.

Only the `fail` / `warn` finding rows selected for the summary are sent to a
model, and only when a provider is detected. Passing rows, repository
contents, config files, and secrets are never sent.

To prohibit model calls for an organization or repository, add this to its
global or repo config:

```json
{
  "marketplace_kit": {
    "enable_ai_findings_summary": false
  }
}
```

| Provider | Selected when | Credentials |
|----------|---------------|-------------|
| `github-models` | `auto` (first choice) or set explicitly | `GITHUB_MODELS_TOKEN`, else the workflow `GITHUB_TOKEN`. Optional `GITHUB_MODELS_ENDPOINT` / `GITHUB_MODELS_MODEL`. Needs `models: read`. |
| `external` | `auto` (fallback) or set explicitly | `OPENAI_API_KEY` **and** `OPENAI_API_ENDPOINT` (any OpenAI-compatible endpoint). Optional `OPENAI_API_MODEL`. |
| `none` | Set explicitly | — |

Endpoints must be `https`. A token without model access is treated as
unavailable; it does not fail the scan. Keep credentials in Actions secrets
or the runner environment — never in a config file.

The same layer powers `marketplace-kit generate-policy --ai` and
`marketplace-kit install --ai`, which tailor a community-health template to
your project and silently fall back to the static template when no provider
is reachable.

## ⚙️ Action inputs

These are the inputs of the root action, which delegates to
`.github/actions/check`. Every policy input defaults to `''` (or `auto`),
meaning *take the value from the [config cascade](#️-configuration-inheritance-and-layering)*.

<!-- BEGIN GENERATED: action-inputs -->

| Input | Default | Description |
|-------|---------|-------------|
| `use_marketplace_config` | `auto` | `auto`, `true`, or `false`. Built-in best-practice defaults, on by default. |
| `use_global_config` | `auto` | `auto` loads `.github/marketplace-kit-global-config.json` when present; `true` requires it; `false` disables it. |
| `global_config_path` | (config) | Org/hub-level config path. Empty uses the conventional path. |
| `config_path` | (config) | Repo config path. Empty auto-discovers `.github/bos-universal-config.json`. |
| `action_yml_path` | (config) | Path to the action manifest. Default `action.yml`. |
| `fail_on_warning` | (config) | `true` to treat OP### warnings as failures. |
| `skip_checks` | (config) | Comma-separated check IDs to skip (e.g. `OP003,SC002`). |
| `workflow_dir` | `auto` | Workflow directory to scan. `auto` uses the config value; "" skips. |
| `github_token` | `${{ github.token }}` | Token used for org-health API lookups. Defaults to `github.token`; set explicitly to use a PAT/fine-grained token with cross-repo contents:read. |
| `org_health_repo` | (config) | `owner/repo` containing fallback community-health files (e.g. `blackoutsecure/.github`). Defaults to `${owner}/.github` if empty. |
| `check_org_health` | (config) | `true` to enable org-health lookups for CH### rules. |
| `require_security` | (config) | CH001 severity: 'fail', 'warn', or 'skip'. |
| `require_code_of_conduct` | (config) | CH002 severity: 'fail', 'warn', or 'skip'. |
| `require_contributing` | (config) | CH003 severity: 'fail', 'warn', or 'skip'. |
| `require_support` | (config) | CH004 severity: 'fail', 'warn', or 'skip'. |
| `require_issue_templates` | (config) | CH005 severity: 'fail', 'warn', or 'skip'. |
| `require_pr_template` | (config) | CH006 severity: 'fail', 'warn', or 'skip'. |
| `require_funding` | (config) | CH### funding severity: 'fail', 'warn', or 'skip'. |
| `community_health_source` | (config) | Global source mode: 'local', 'inherit', or 'either'. |
| `security_source` | (config) | SC003 source override (or empty to use global). |
| `code_of_conduct_source` | (config) | CH001 source override (or empty to use global). |
| `contributing_source` | (config) | CH002 source override (or empty to use global). |
| `support_source` | (config) | CH003 source override (or empty to use global). |
| `issue_templates_source` | (config) | CH004 source override (or empty to use global). |
| `pr_template_source` | (config) | CH005 source override (or empty to use global). |
| `funding_source` | (config) | CH006 source override (or empty to use global). |
| `auto_generate_missing` | (config) | [FUTURE] When `true`, use an LLM to draft missing community-health files and open a PR. Stub today; reserved for a future release. |
| `profile` | (config) | `baseline` (default) or `strict` — see the README config schema. |
| `enable_security_scan` | (config) | Run the security-posture rule families (SC/CQ/GH/MS/SR). Default `true`. |
| `defer_to_code_scanning_kit` | (config) | `auto`, `true`, or `false`. Skip rules already owned by bos-code-scanning-kit. |
| `enable_ai_findings_summary` | (config) | Summarise findings with an AI provider when reachable. Always falls back to local remediation. |
| `ai_findings_summary_provider` | (config) | `auto`, `none`, `github-models`, or `external`. |
| `ai_model` | (config) | Model identifier for the AI summary (e.g. `openai/gpt-4o-mini`). |
| `local_heuristic_fallback` | (config) | Emit deterministic local remediation when no model is available. |
| `require_dependabot` | (config) | DP001 severity: 'fail', 'warn', or 'skip'. |
| `require_codeql` | (config) | CQ001 severity: 'fail', 'warn', or 'skip'. |
| `require_editorconfig` | (config) | LT001 severity: 'fail', 'warn', or 'skip'. |
| `require_gitattributes` | (config) | LT002 severity: 'fail', 'warn', or 'skip'. |
| `require_gitignore` | (config) | LT003 severity: 'fail', 'warn', or 'skip'. |
| `require_markdownlint` | (config) | LT004 severity: 'fail', 'warn', or 'skip'. |
| `require_yamllint` | (config) | LT005 severity: 'fail', 'warn', or 'skip'. |
| `require_ghas_code_scanning` | (config) | GH001 severity: 'fail', 'warn', or 'skip'. |
| `require_ghas_secret_scanning` | (config) | GH002 severity: 'fail', 'warn', or 'skip'. |
| `require_dependabot_alerts` | (config) | GH003 severity: 'fail', 'warn', or 'skip'. |
| `require_security_devops` | (config) | MS001 severity: 'fail', 'warn', or 'skip'. |
| `require_scorecard` | (config) | SR001 severity: 'fail', 'warn', or 'skip'. |
| `require_repo_description` | (config) | RM001/RM002 severity (repo About-box description): 'fail', 'warn', or 'skip'. |
| `require_repo_homepage` | (config) | RM003 severity (repo About-box homepage URL): 'fail', 'warn', or 'skip'. Malformed URLs always fail. |
| `require_repo_topics` | (config) | RM004/RM005 severity (repo About-box topics): 'fail', 'warn', or 'skip'. Format violations and >20 topics always fail. |
| `repo_description_max_length` | (config) | Hard upper bound for the repo description (RM002). Default 350 (GitHub limit). |
| `repo_description_min_length` | (config) | Lower bound below which the repo description triggers a warning (RM002). Default 30. Set 0 to disable. |

<!-- END GENERATED: action-inputs -->

> **Note**
> The table above is auto-generated from `action.yml` by
> [`scripts/render_readme_inputs.py`](scripts/render_readme_inputs.py).
> Edit `action.yml` and run `python3 scripts/render_readme_inputs.py --write`.

The kit's other composites (`guard`, `promote`, `name-check`,
`branding-preview`, `dist-check`, `lint`, `branch-protection`,
`repo-metadata`) have their own inputs — see
[🧰 What's in the box](#-whats-in-the-box) and each composite's `action.yml`.
Render any of them locally with `marketplace-kit doc-inputs --action-yml
.github/actions/guard/action.yml`.

## 📤 Action outputs

<!-- BEGIN GENERATED: action-outputs -->

| Output | Description |
|--------|-------------|
| `passed` | Number of checks that passed. |
| `failed` | Number of checks that failed. |
| `warnings` | Number of warnings. |
| `report` | Newline-separated `id\|status\|message` rows. |

<!-- END GENERATED: action-outputs -->

Exit behaviour: the step exits `0` when every rule passes (or only warns),
`1` when a rule fails — or when a rule warns and `fail_on_warning` is
enabled — and `2` on a configuration error.

## 🧰 What's in the box

Publishing on the Marketplace has rules that are easy to miss:

* `action.yml` must be at the root of the default branch.
* The default branch should contain only what the action needs. GitHub does
  **not** forbid `.github/workflows/*` there — see
  [Marketplace requirements vs. kit policy](#marketplace-requirements-vs-kit-policy).
* The `name:` field has four sub-rules (unique, not a user/org, not a
  category, not a reserved feature).
* `branding.icon` must come from a specific snapshot of Feather Icons.
* `branding.color` must be one of nine allowed values.
* Verified Creator status requires manual outreach.

You can't catch any of this until your release pipeline runs (or worse,
until your listing rejects the publish). This kit catches all of it
*before* the PR merges.

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
│   ├── branch-protection/               # branch-protection compliance (check + enforce)
│   └── repo-metadata/                   # sync About box (description/homepage/topics) on release
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

### A note on the bundled helpers

Two composites ship inline Python helpers next to their `action.yml`:

* `branch-protection/_bp.py` — drift detection + payload builder.
* `repo-metadata/helper.py` — README prose extraction, description
  clamping, GitHub-valid topic sanitization.

Neither helper is part of the PyPI package — they live next to their
consumer so downstream users who pin the composite (e.g.
`uses: blackoutsecure/bos-marketplace-kit/.github/actions/repo-metadata@v1`)
get them for free, with no `pip install` required.

The composites invoke them as
`python3 "${GITHUB_ACTION_PATH}/<helper>.py" <subcommand>`.
The test suite imports them via `importlib.util.spec_from_file_location`
in `test/conftest.py` so it can exercise the same code paths the
composites run at action time.

## 🏗️ Configuration inheritance and layering

Every policy input on the `check` action is backed by a JSON config
cascade, so a repo (or a whole org) can set its posture once instead of
repeating twenty `with:` lines in every workflow.

### Configuration tiers

Tiers merge in order — each one overrides the one above it:

1. **Runtime defaults** — conservative built-ins compiled into
   `src/marketplace_kit/config.py`. Every `require_*` rule is `skip`.
   Only used when the marketplace tier is switched off.
2. **Marketplace config (built-in, default ON)** — the kit's recommended
   values, shipped at `src/marketplace_kit/data/marketplace-kit-marketplace-config.json`.
   This is what makes `- uses: blackoutsecure/bos-marketplace-kit@v1`
   with no inputs do something sensible. Turn it off with
   `"use_marketplace_config": false` in any lower tier.
3. **Global config (optional)** — org/hub-level defaults, auto-discovered
   at `.github/marketplace-kit-global-config.json`. Create it only if
   you want org-wide policy; nothing breaks when it is absent.
4. **Repo config (optional)** — per-repo overrides in the `marketplace_kit`
   section of `.github/bos-universal-config.json` (preferred, and the path
   every automation-hub kicker passes explicitly), or
   `bos-universal-config.json`, `marketplace-kit.json`,
   `.marketplace-kit.json`.
5. **Workflow inputs** — anything you set non-empty in `with:` wins over
   every file tier. Inputs left at their default (`''`, or `auto` for
   `workflow_dir`) fall through to the config.

Because the built-in tier carries the same values the inputs used to
default to, upgrading changes nothing until you add a config file.

### Scaffold the files

```bash
# Optional org-wide policy (commit into each repo, or sync it with
# bos-managed-file-sync-action).
marketplace-kit install global-config

# Optional per-repo overrides.
marketplace-kit install repo-config

# Show exactly what the cascade resolves to, and which tiers applied.
marketplace-kit config
marketplace-kit config --json
```

`install` never overwrites an existing file without `--force`.

### Schema

The `marketplace_kit` section accepts every `check` input by name. A
document with no `marketplace_kit` key is treated as the section itself,
so a standalone `marketplace-kit.json` can be flat. Unknown keys are
ignored, so a newer kit can extend the schema without breaking older
callers.

| Key | Type | Notes |
|-----|------|-------|
| `use_marketplace_config` | boolean | Default `true`. `false` drops the built-in best-practice tier. |
| `use_marketplace_skip_checks` | boolean | Default `true` — `skip_checks` appends across tiers. `false` replaces the inherited list. |
| `action_yml_path` | string | Repo-relative. Absolute paths and `..` are rejected. |
| `fail_on_warning` | boolean | Treat OP### warnings as failures. |
| `skip_checks` | array or string | Rule IDs to skip, e.g. `["OP003", "SC002"]`. |
| `workflow_dir` | string | `""` skips workflow linting. |
| `check_org_health` / `org_health_repo` | boolean / string | Org `.github` fallback lookup. |
| `community_health_source` | string | `local`, `inherit`, or `either`. |
| `require_*` | string | `fail`, `warn`, or `skip` — one per CH/SC/DP/CQ/LT/GH/MS/SR/RM rule. |
| `*_source` | string | Per-rule override of `community_health_source`. |
| `repo_description_max_length` / `repo_description_min_length` | integer | RM002 bounds. |
| `enable_ai_findings_summary` | boolean | Default `true`. `false` prohibits every model call. |
| `ai_findings_summary_provider` | string | `auto`, `none`, `github-models`, or `external`. |
| `ai_model` | string | Model identifier. Empty uses the provider default. |
| `local_heuristic_fallback` | boolean | Default `true`. Emit deterministic remediation when no model is used. |
| `profile` | string | `baseline` (default) or `strict`. See [Posture profiles](#posture-profiles). |
| `enable_security_scan` | boolean | Default `true`. `false` skips the whole security-posture rule group. |
| `defer_to_code_scanning_kit` | `auto` / boolean | Default `auto`. Skip rules owned by `bos-code-scanning-kit`. |

Values are validated before any check runs: a bad enum, a negative
length, or a path escaping the repo fails the step with exit code `2`
instead of silently degrading to a default.

### Examples

**Org config** — `.github/marketplace-kit-global-config.json`:

```json
{
  "marketplace_kit": {
    "require_security": "fail",
    "require_codeql": "fail",
    "org_health_repo": "blackoutsecure/.github",
    "community_health_source": "inherit"
  }
}
```

**Repo override** — `.github/bos-universal-config.json`:

```json
{
  "marketplace_kit": {
    "require_codeql": "warn",
    "skip_checks": ["OP003"]
  }
}
```

**Workflow** — no policy inputs needed:

```yaml
- uses: blackoutsecure/bos-marketplace-kit@v1
  with:
    github_token: ${{ github.token }}
```

Resulting policy: `require_security: fail` (org), `require_codeql: warn`
(repo wins), `OP003` skipped, everything else from the built-in
marketplace defaults.

**Opt out of the built-in defaults** entirely:

```json
{
  "marketplace_kit": {
    "use_marketplace_config": false,
    "require_security": "fail"
  }
}
```

Only `require_security` is enforced; every other rule falls back to the
conservative runtime default of `skip`.

### Composing with `bos-code-scanning-kit`

The two kits are deliberately complementary, but four rules overlap. When a
workflow in your repo already calls
[`blackoutsecure/bos-code-scanning-kit`](https://github.com/blackoutsecure/bos-code-scanning-kit),
this kit **defers** those rules to it rather than double-reporting the same
control on the Security tab and in two job summaries.

| This kit | Code-scanning kit | Who wins by default |
|----------|-------------------|---------------------|
| `GH001` code scanning enabled | `PS001` | code-scanning kit (probes Default **and** Advanced setup) |
| `GH002` secret scanning enabled | `PS002` | code-scanning kit |
| `GH003` Dependabot alerts enabled | `PS003` | code-scanning kit |
| `MS001` Security DevOps workflow | `PS013` | code-scanning kit |

Everything else stays here — `MP###`, `OP###`, `SC###`, `CH###`, `DP001`,
`CQ001`, `LT###`, `SR001`, `RM###` have no code-scanning-kit equivalent. And
`PS004` (push protection), `PS010`–`PS012` (workflow permissions, SHA pins),
`PS020`–`PS025` (branch protection) and `PS030`–`PS033` (CODEOWNERS) have no
equivalent here, so nothing is lost by deferring.

`defer_to_code_scanning_kit` controls this:

| Value | Behaviour |
|-------|-----------|
| `auto` (default) | Defer only when a workflow in the repo references the code-scanning kit. |
| `true` | Always defer — use it when the kit runs from an org-level workflow this repo cannot see. |
| `false` | Never defer; run both. Useful while migrating. |

`auto` matches a literal `blackoutsecure/bos-code-scanning-kit` reference in
`.github/workflows/*.y*ml`. It deliberately does **not** follow reusable
workflows: if your repo calls a hub reusable that in turn calls the kit, the
reference is not visible here, so set `defer_to_code_scanning_kit: true`
explicitly. This repository does exactly that — see
[`.github/bos-universal-config.json`](.github/bos-universal-config.json).

Deferred rules are reported as `skip` with the reason, and listed under
**Suppressed** in `marketplace-kit config` — they are never silently dropped:

```console
$ marketplace-kit config
## Suppressed (forced to `skip`)
  require_ghas_code_scanning     owned by blackoutsecure/bos-code-scanning-kit (PS001)
```

So: if the code-scanning kit already covers a control, you do **not** need to
name it in this kit's config. Leave it at the built-in default and the
cascade sorts it out.

### Posture profiles

`profile` selects how strong the built-in recommendation is. It applies
between the marketplace tier and your global/repo config, so you can adopt a
profile and still relax one rule.

| Profile | Meaning |
|---------|---------|
| `baseline` (default) | The kit's conservative recommendation. Adding the kit to an existing repo never breaks CI on day one. |
| `strict` | The **recommended target state**. Promotes the controls that are free on public repos — `SECURITY.md`, CodeQL, Dependabot config + alerts, GHAS toggles, `.editorconfig`/`.gitattributes`/`.gitignore`, repo description and topics — from `warn` to `fail`, and turns markdownlint/yamllint/Scorecard on at `warn`. |

```json
{
  "marketplace_kit": {
    "profile": "strict",
    "require_codeql": "warn"
  }
}
```

Adopt `strict` once a repo is clean under `baseline`; the per-rule override
above is the escape hatch for the one control you are not ready for.

### Turning the security scan off

`enable_security_scan` is a single switch over the whole security-posture
group (`require_security`, `require_codeql`, the three `GH###` rules,
`MS001`, `SR001`). It is **`true` by default**:

```json
{
  "marketplace_kit": {
    "enable_security_scan": false
  }
}
```

Every rule in the group is forced to `skip` and listed under **Suppressed**
with the reason. Use it when a dedicated scanner owns security posture for
the repo and you want this kit to cover Marketplace readiness only. It does
not touch `MP###`, `OP###`, `CH###`, `LT###`, or `RM###`.

### Config inputs on the action

| Input | Default | Meaning |
|-------|---------|---------|
| `use_marketplace_config` | `auto` | `auto` honours the config files; `true`/`false` force the built-in tier on or off. |
| `use_global_config` | `auto` | `auto` loads the global config when present; `true` requires it; `false` disables discovery. |
| `global_config_path` | (conventional) | Override the global config path. |
| `config_path` | (auto-discovered) | Override the repo config path. |

Configuration is pure data: the resolver is stdlib Python, makes no
network calls, and never evaluates config content. Package identity is
resolved separately — see [📦 Package metadata](#-package-metadata).

## 📦 Package metadata

Package identity is deliberately **separate** from the policy cascade above.
The package name, version, author, license, and homepage come from the
installed distribution metadata and remain available even when repository
policy is absent, overridden, or failed to load.

`marketplace-kit config` prints that metadata before the configuration
cascade, so a broken config never hides which build you are running:

```console
$ marketplace-kit config
# package metadata

  name             bos-marketplace-kit
  version          0.2.0
  author           Blackout Secure
  license          Apache-2.0
  homepage         https://github.com/blackoutsecure/bos-marketplace-kit
  metadata source  distribution

# resolved marketplace-kit configuration
...
```

`metadata source` is `distribution` when the kit was `pip install`ed, and
`bundled` when the composite action runs `src/` straight off a runner
without a package install. The bundled fallback is kept in lockstep with
`pyproject.toml` by the test suite.

**Package metadata is not policy.** `action.yml`, `pyproject.toml`, and the
installed distribution own identity; the global and repository configs own
policy. Ignoring or overriding policy does not remove package identity.

### Marketplace requirements vs. kit policy

Three claims are commonly conflated. Per
[GitHub's publishing docs](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace):

| Claim | Verdict | Detail |
|-------|---------|--------|
| `action.yml` must be at the repo root of the default branch | **GitHub requirement** | Enforced by `MP007`. |
| A repo may contain only one action | **Partly** — one *listed* action. Sub-folder manifests are explicitly allowed, they just are not listed. | This is why the kit's nine composites live under `.github/actions/**`. |
| The default branch must not contain `.github/workflows/**` | **Not a GitHub rule.** | The docs only ask that the repo contain "the metadata file, code, and files necessary for the action". Keeping workflows off `main` is *this kit's policy*, implemented by `promote` + `guard`. |
| A composite action may `uses:` another action | **Allowed** since composite `uses:` support shipped in 2021. | Nested `uses:` must still be SHA-pinned (`SC002`). |

The practical consequence: the `dev` → `main` promote model is a **hardening
choice**, not a publishing prerequisite. It keeps the published surface
minimal and auditable — a consumer pinning `@v1` gets `action.yml`, `src/`,
`.github/actions/**`, `README`, `LICENSE`, and `NOTICE`, and nothing else. If
you prefer a single-branch repo, publishing still works; you simply lose that
guarantee. Nothing in `check` fails a repo for keeping workflows on its
default branch.

### Why a root action that delegates

The root [`action.yml`](action.yml) is a thin pass-through to
`.github/actions/check`. That is deliberate, and it is the only shape that
satisfies both constraints at once:

* Marketplace lists exactly one manifest, and it must be at the root.
* The check logic is ~500 lines of manifest plus a 900-line `run.sh`, shared
  with callers who address the nested composite directly.

Duplicating the manifest at the root would create two sources of truth for 50
inputs. Delegation keeps one. The cost is one extra step in the job log.

### Action roster review

| Composite | Keep? | Rationale |
|-----------|-------|-----------|
| `check` | ✅ | The listed surface. Everything else is opt-in. |
| `guard` | ✅ | Distinct trigger (`pull_request`) and permissions from `check`; no overlap. |
| `promote` | ✅ | Release-time, `contents: write`. Cannot merge into `check`. |
| `name-check` | ✅ | Network calls to github.com; deliberately not in the PR path. |
| `branding-preview` | ✅ | Writes a PR comment; different permission set. |
| `dist-check` | ✅ | Only meaningful for bundled JS actions. Correctly opt-in. |
| `lint` | ✅ | Orchestrates markdownlint/yamllint/shellcheck/actionlint. Overlaps `bos-code-scanning-kit`'s actionlint + shellcheck stage — prefer that kit when both are installed. |
| `branch-protection` | ⚠️ | Overlaps `PS020`–`PS025`. This one *applies* settings; the code-scanning kit only *audits* them. Keep both; do not run them against each other's expectations. |
| `repo-metadata` | ✅ | Writes the About box; the `RM###` rules audit it. Read/write pair, not a duplicate. |

No composite references an external action: `check` downloads `actionlint`
over HTTPS and verifies it against a per-architecture SHA-256 pinned in
`action.yml`. There is no `uses:` of a third-party action anywhere in
`.github/actions/**`, so `SC002` and the code-scanning kit's `PS012` are
satisfied by construction rather than by policy.

## ✅ Check rule catalogue

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
| `RM###` | Configurable | Live repo "About" box (description, homepage, topics) missing or non-compliant. Reads `GET /repos/{owner}/{repo}` (default `GITHUB_TOKEN` is sufficient). Companion to the `repo-metadata` composite. |

### MP001 — Top-level manifest keys

**Required:** `name`, `description`, `runs` MUST be present at the
root of `action.yml`. `runs:` must be a mapping containing at least
`using:`.

### MP002 — `name` is non-empty

`name:` must be a non-empty string. Marketplace displays this on the
listing card and across search results.

### MP003 — `description` is non-empty

`description:` is the one-line subtitle on the Marketplace card. See
also: [MP010](#mp010--description-is-too-long).

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

Marketplace only lists a single manifest at the root of the default
branch. Subdirectory manifests (e.g. `.github/actions/foo/action.yml`)
are permitted in the repository but are **not** listable — GitHub's docs
state "repositories may include other actions metadata files in
sub-folders, but they will not be automatically listed in the
marketplace". The `promote` action's allowlist should include
`action.yml`.

### MP008 — Name is not too short

Marketplace rejects single-character action names and very short
names that collide with reserved features. Use a name of at least 3
characters and run the kit's `name-check` action to validate
availability.

### MP009 — Description is not too short

A description shorter than 10 characters is unlikely to be useful on
the Marketplace card and may be rejected. Expand to a complete
sentence (~30-125 chars).

### MP010 — Description is too long

`description:` must be **125 characters or fewer**. Marketplace
truncates anything past the limit in the card view, so a longer
description ships a truncated subtitle to consumers — a hard fail by
default. Tighten to a single short sentence; use `README.md` for
elaboration.

Enforced by both the `check` composite action and the
`bos-marketplace-kit` CLI; cannot be downgraded to a warning.

### OP003 — `author` is set

Optional but strongly recommended. Marketplace shows the author on
the listing card. Add `author: Your Org Name`.

### OP004 — README has a Usage / Quickstart / Example section

Marketplace consumers scan READMEs looking for a copy-pasteable
snippet. The check looks for a heading matching
`Usage`, `Quickstart`, `Getting Started`, or `Example` (any depth).
Add one to your `README.md`:

````markdown
## Usage

```yaml
- uses: your-org/your-action@v1
  with:
    foo: bar
```
````

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

Worked example: the kit itself ships **none** of the seven
community-health files locally — they all live in
`blackoutsecure/.github` and inherit. The kit's [self-check
workflow](.github/workflows/self-check.yml) wires it up like this:

```yaml
- uses: blackoutsecure/bos-marketplace-kit@v1
  with:
    github_token:            ${{ github.token }}
    require_security:        warn
    require_code_of_conduct: warn
    require_contributing:    warn
    require_support:         warn
    require_funding:         warn
    # Inherit all community-health files from the org `.github` repo:
    community_health_source: inherit
```

A more typical consumer keeps a repo-specific `CONTRIBUTING.md`
(local release flow, dev-loop commands, etc.) and inherits the rest
from their org `.github` repo:

```yaml
- uses: blackoutsecure/bos-marketplace-kit@v1
  with:
    github_token:            ${{ github.token }}
    require_security:        warn
    require_code_of_conduct: warn
    require_contributing:    warn
    require_support:         warn
    require_funding:         warn
    # Default everything to inherit ...
    community_health_source: inherit
    # ... but keep the contributor guide local because it has
    # repo-specific release / dev-loop content:
    contributing_source:     local
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

#### Install one (or every) recommended file

`generate-policy` is the low-level emitter. `install` is the safe
one-shot scaffolder you reach for when bootstrapping a fresh repo
— it writes to canonical paths, refuses to overwrite existing files
by default, and can install every recommended kind in one call:

```bash
# Scaffold a single kind at its canonical path. Refuses to
# overwrite an existing file — pass --force to replace it.
marketplace-kit install codeql-workflow --owner my-org

# Install every recommended community-health, supply-chain, and
# lint file that isn't already present. Existing files are left
# alone (use --force to overwrite all). Use --dry-run to preview.
marketplace-kit install --all --owner my-org

# Preview without touching anything.
marketplace-kit install --all --owner my-org --dry-run
```

What `install --all` covers: `security`, `code-of-conduct`,
`contributing`, `support`, `issue-bug`, `issue-feature`,
`pr-template`, `funding`, `dependabot`, `codeql-workflow`,
`markdownlint`, `yamllint`. Opt-in kinds (`scorecard-workflow`,
`security-devops-workflow`, `shellcheckrc`) must be installed
explicitly by name to avoid surprising consumers who don't want them.

After `install`, run `marketplace-kit check` to confirm the kit's
rules pass — the canonical pipeline is **check → install → commit →
check passes → CI green**.

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
| CQ001 | any workflow referencing `github/codeql-action`                            | `warn`         | `codeql-workflow` *or* `code-scan-workflow` (mutually exclusive — pick one) |
| LT001 | `.editorconfig`                                                            | `warn`         | (no template; trivial)     |
| LT002 | `.gitattributes`                                                           | `warn`         | (no template; repo-shaped) |
| LT003 | `.gitignore`                                                               | `warn`         | (no template; repo-shaped) |
| LT004 | `.markdownlint.yaml` / `.markdownlint-cli2.yaml` / `.markdownlint.json`    | `skip`         | `markdownlint`             |
| LT005 | `.yamllint.yml` / `.yamllint.yaml` / `.yamllint`                           | `skip`         | `yamllint`                 |

The lint rules default to `skip` (LT004/LT005) or `warn` (LT001-003)
so legacy repos can adopt the kit without immediate cleanup. Promote
to `fail` as your repo catches up.

#### CQ001 — choose ONE of `codeql-workflow` or `code-scan-workflow`

Two templates satisfy CQ001; pick exactly one. Running both doubles
CodeQL spend on every dev push (same `github/codeql-action`, same
SARIF, twice the minutes) and splits the SHA-bump source of truth
across two files.

| | `codeql-workflow` | `code-scan-workflow` |
|---|---|---|
| **What ships** | Standalone `.github/workflows/codeql.yml` with `github/codeql-action` SHAs pinned inline | `.github/workflows/bos-universal-launchpad.yml` that calls the hub reusable `blackoutsecure/bos-automation-hub/.github/workflows/bos-universal-launchpad.yml@main` |
| **SHA rollouts** | You bump SHAs in this repo on every CodeQL release | One hub commit propagates to every consumer on next run |
| **Covers** | CodeQL only | CodeQL **and** the `bos-code-scanning-kit@v1` composite (posture audit + actionlint / gitleaks / shellcheck) |
| **Cross-org / external use** | Self-contained — no hub dependency | Requires read access to `blackoutsecure/bos-automation-hub` |
| **Producer-kit escape hatch** | n/a | Set `enable_kit_composite: false` if this repo IS the producer of `bos-code-scanning-kit@v1` |
| **Advanced posture probes (PS002/PS003)** | n/a | Built-in preflight + `SCANNING_PAT` plumbing |

The `marketplace-kit install` command emits a warning if you try to
scaffold one template next to an existing canonical file for the
other. The recommended migration path:

```bash
# Migrate from standalone CodeQL to the hub-reusable form:
marketplace-kit install code-scan-workflow --owner my-org
rm .github/workflows/codeql.yml                       # commit in same PR
```

Both templates produce a top-level workflow file referencing
`github/codeql-action` (the latter as a `# uses:` documentary
comment in the header), which is what CQ001 actually keys off — it
inspects workflow files at the repo's surface, not transitive
reusable callees.

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

### RM001-RM005 — Live repo "About" box (description, homepage, topics)

Validates what the public sees in the repo sidebar — the same
fields the companion [`repo-metadata`](#repo-about-box-sync-repo-metadata)
composite writes on release. Each rule reads
`GET /repos/{owner}/{repo}`; the default `GITHUB_TOKEN` is enough
(these fields are public-readable). The job summary additionally
emits a **Current repo About box** sub-section showing the actual
live values so you can confirm what consumers see without leaving
the workflow log.

| ID    | Field                | Pass criterion                                                         | Default policy | Hard rules                                              |
|-------|----------------------|------------------------------------------------------------------------|----------------|---------------------------------------------------------|
| RM001 | `description` set    | Non-empty                                                              | `warn`         | —                                                       |
| RM002 | `description` length | `repo_description_min_length` ≤ len ≤ `repo_description_max_length`    | `warn`         | `>repo_description_max_length` (default 350) → **fail** |
| RM003 | `homepage`           | http(s) URL                                                            | `skip`         | Set but non-URL → **fail** (regardless of policy)       |
| RM004 | `topics` count       | 1 ≤ count ≤ 20                                                         | `warn`         | `count > 20` → **fail** (GitHub cap; regardless of policy) |
| RM005 | `topics` format      | Lowercase, `[a-z0-9-]`, ≤ 50 chars each, no leading/trailing hyphen   | (inherits)     | Any malformed topic → **fail** (regardless of policy)   |

**Why "hard fail regardless of policy" on some rules?** When values
violate GitHub's own format/cap rules, the *next* `PATCH /repos/{}`
or `PUT /repos/{}/topics` call would be rejected — so a warning would
mask a soon-to-be broken release. Format violations are always
blocking; absence is configurable.

**Tuning the bounds** (per-repo overrides):

```yaml
- uses: blackoutsecure/bos-marketplace-kit/.github/actions/check@v1
  with:
    github_token: ${{ github.token }}
    # Make every RM rule blocking on the publish branch:
    require_repo_description: 'fail'
    require_repo_homepage:    'fail'
    require_repo_topics:      'fail'
    # Allow shorter "tagline-style" descriptions:
    repo_description_min_length: '0'
    # Raise the upper cap (rare — GitHub still hard-caps at 350):
    repo_description_max_length: '350'
```

**Default `GITHUB_TOKEN` is enough** for RM001-RM005 — unlike the
`repo-metadata` composite which *writes* these fields and needs
`Administration: write`, the check action only *reads* them, which
`metadata: read` (granted by default to `GITHUB_TOKEN`) already
covers.

### Adding new rules

Open a PR against `dev` that:

1. Adds the rule to `.github/actions/check/action.yml`.
2. Documents it in the [Check rule catalogue](#check-rule-catalogue)
   section above with a stable ID.
3. Adds a unit test under `test/` covering the failure case.
4. Bumps the kit's minor version.

The kit promises stability for `MP###`/`OP###`/`SC###`/`CH###` rule
IDs across minor versions — adding a rule never reuses an existing
ID.

## 🚢 Publishing to Marketplace

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
5. Refreshes the repo `About` box (description / topics / sidebar
   widgets) via the bundled `repo-metadata` composite — soft step,
   gated on at least one of `secrets.REPO_ADMIN_PAT` /
   `secrets.RELEASE_PAT` being set. The job prefers
   `REPO_ADMIN_PAT` when explicitly configured (advanced
   blast-radius separation) and otherwise falls back to
   `RELEASE_PAT` (the default single-PAT path). When neither secret
   is set the job auto-skips with a notice — the release itself is
   already published and a failed metadata sync should not roll it
   back. Suppress unconditionally with `skip_repo_metadata: true`
   on dispatch.

### Step 5b — Tokens, secrets, and variables

The release workflow needs auth to push the promotion commit + tag
to `main`. The kit's own [release.yml](.github/workflows/release.yml)
already implements every pattern below; this section is the contract
for anyone copying that template into another repo.

#### Tokens

| Token | Required? | Identity | Used for | Scopes / permissions | Why |
|-------|-----------|----------|----------|----------------------|-----|
| `secrets.GITHUB_TOKEN` | **Mandatory** (auto-provided by Actions) | `github-actions[bot]` (Integration App ID `15368`) | `actions/checkout`, default `git push` to `main` + tag, `gh release create`, all `gh api` probes (FUNDING resolver) | Job-level `permissions: { contents: write }` on the `promote` job; `contents: write` on the `release` job for the GitHub Release create. | Cannot be disabled. Every workflow run is auto-issued one per job (TTL = job lifetime). Without it, `actions/checkout` cannot clone, `gh api` cannot authenticate, and the workflow simply cannot run. There is no "off" mode. |
| `secrets.RELEASE_PAT` | Optional (opt-in) | The PAT owner (user) or the GitHub App backing a fine-grained PAT | Same push as above, when `GITHUB_TOKEN` cannot satisfy branch protection | **Fine-grained (recommended):** Contents = Read & Write on the action repo, Metadata = Read-only. **Classic:** the `repo` scope (see [classic PAT specifics (RELEASE_PAT)](#classic-pat-specifics-release_pat) below for the explicit checkbox list). | Only needed when `main` is locked behind a ruleset or classic protection that `GITHUB_TOKEN` cannot bypass. The PAT's identity (or its backing App) MUST be listed in the ruleset's `bypass_actors`. The resolver probes `/user` (validity), `repos/<repo>.permissions.push` (identity), AND `POST /repos/<repo>/git/blobs` (token scope) BEFORE checkout and fails the job with a remediation hint on any misconfiguration — silent fallback would hide operator intent. When unset, the resolver emits a notice and falls through to `GITHUB_TOKEN`. |
| `secrets.REPO_ADMIN_PAT` | Optional (advanced; not needed for the single-PAT path) | The PAT owner (user) or the GitHub App backing a fine-grained PAT | Post-release `repo-metadata` composite: PATCH `/repos/{owner}/{repo}` (description / homepage / sidebar widgets) + PUT `/repos/{owner}/{repo}/topics`. **Only consulted when explicitly set** — if unset, the job falls back to `RELEASE_PAT` (which already has the same authority for classic PATs, and the same authority for fine-grained PATs once you add `Administration: Read & Write` to it). | **Fine-grained:** Administration = Read & Write AND Metadata = Read-only on the action repo. **Classic:** the `repo` scope — same checkbox list as `RELEASE_PAT` (see [classic PAT specifics (RELEASE_PAT)](#classic-pat-specifics-release_pat)). Classic does not have a granular Administration-write scope. | Provision this only when you want the metadata sync's blast radius isolated from the release push — a fine-grained PAT scoped purely to `Administration:Write` (no Contents:Write) writes the About box but cannot push code, so a leak cannot create a malicious release. Most operators do not need this and should use the single-PAT path described under [Single-PAT default vs separate-PATs (advanced)](#single-pat-default-vs-separate-pats-advanced). |

##### Classic PAT specifics (`RELEASE_PAT`)

Created at <https://github.com/settings/tokens> → **Generate new
token (classic)**. The kit has been tested against classic PATs as
well as fine-grained; classic remains supported because some org
policies disable fine-grained PATs entirely. Use the minimum-scope
recipe below — anything broader is unnecessary.

**Required (tick exactly these):**

| Scope (top-level) | Tick? | Why |
|---|---|---|
| `repo` (Full control of private repositories) | ✅ **Yes** | This single top-level scope auto-selects `repo:status`, `repo_deployment`, `public_repo`, `repo:invite`, and `security_events`. It is the only classic scope that grants `git push` + ref/tag write. There is no "contents only" granular variant in classic — `repo` is the smallest unit that works. |

**Do NOT tick (over-scoped for this PAT's single job):**

| Scope | Why not |
|---|---|
| `workflow` | Promote intentionally never writes `.github/workflows/**` to `main` (the guard hard-blocks it). |
| `admin:org`, `write:org`, `read:org`, `manage_runners:org` | Org admin is not needed to push a tag to a single repo. |
| `admin:enterprise`, `manage_runners:enterprise`, `manage_billing:enterprise`, `read:enterprise`, `scim:enterprise` | Enterprise-level access is never required for a per-repo release. |
| `delete_repo`, `delete:packages` | Destructive scopes irrelevant to release publishing. |
| `admin:public_key`, `admin:repo_hook`, `admin:org_hook` | Not used. |
| `gist`, `notifications`, `user`, `write:discussion`, `read:discussion` | Not used. |
| `audit_log`, `codespace`, `project`, `copilot`, `read:packages`, `write:packages` | Not used. |

**SAML SSO authorize (mandatory for `blackoutsecure` and any other
SAML-enforced org):**

1. On the token-create / token-edit page, under **"Configure SSO"**
   next to the saved token, click *Authorize* for each SAML org you
   need access to.
2. Save. Without this, every API call against the org returns HTTP
   403 with body `Resource protected by organization SAML
   enforcement` and the `resolve-token` step in `release.yml` will
   fail fast with a SAML-specific remediation pointing back at this
   step.

**Expiration:** ≤ 90 days. Rotate on schedule — a leaked classic PAT
with `repo` is more dangerous than a leaked fine-grained PAT because
it can write to every private repo the owner can see, not just the
selected ones.

**Storage:** save as `RELEASE_PAT` under repo Settings → Secrets and
variables → Actions → Secrets (not Variables — secrets are masked in
logs).

**Recommendation:** unless your `main` is behind protection that
`GITHUB_TOKEN` (`github-actions[bot]`, App `15368`) cannot bypass,
leave `RELEASE_PAT` unset. The resolver falls through to
`GITHUB_TOKEN` cleanly, with no SAML cycle, no scope mistakes, and
no rotation overhead. Configure `RELEASE_PAT` only when an audit
trail requires the release commit + tag to be attributed to a human
identity, or when a ruleset's `bypass_actors` explicitly names the
PAT owner.

##### Single-PAT default vs separate-PATs (advanced)

The `repo-metadata` job needs `Administration: write` on the action
repo, which `GITHUB_TOKEN` cannot grant. There are two operator
shapes for supplying that authority — pick one:

**Single-PAT path (recommended for almost everyone).** Configure
`RELEASE_PAT` only and reuse it for the metadata sync. The workflow
does this automatically when `REPO_ADMIN_PAT` is unset.

* **Classic:** the `repo` scope is the smallest unit GitHub offers
  and it already grants every API surface both jobs use —
  `git push` to `main` + tag (release) AND `PATCH /repos/{}` plus
  `PUT /repos/{}/topics` (metadata sync). A second classic PAT with
  the same `repo` scope adds zero isolation — it is the same
  authority duplicated, with double the rotation, SAML
  authorization, and leak surface.
* **Fine-grained:** issue one PAT with **Contents: Read & Write**
  + **Administration: Read & Write** + **Metadata: Read-only** on
  the action repo. The release push uses Contents, the metadata
  sync uses Administration, both share the same PAT.
* Result: one secret to rotate, one SAML authorization to maintain,
  one identity in the audit trail.

**Separate-PATs path (advanced; fine-grained only).** Provision
`REPO_ADMIN_PAT` as a second fine-grained PAT scoped to
**Administration: Read & Write** (and Metadata: Read-only) but
**without Contents: Write**. Keep `RELEASE_PAT` scoped to just
Contents + Metadata. The workflow honours `REPO_ADMIN_PAT` first
when it is set.

* Why bother: a leak of `RELEASE_PAT` can push code but cannot
  rename the repo, flip visibility, or change branch protection.
  A leak of `REPO_ADMIN_PAT` can mutate repo settings but cannot
  push code or tags. Useful when those blast radii need to be
  rotated independently or attributed to different humans in the
  audit log.
* Why NOT bother for classic: classic has no granular
  Administration scope. Both PATs would need `repo`, which carries
  Contents:Write transitively — so the separation is theatre.
  Stick to the single-PAT path with classic.

When neither secret is set the metadata-sync job auto-skips with a
notice; the release itself still publishes cleanly. Setting only
`REPO_ADMIN_PAT` with no `RELEASE_PAT` is valid but unusual — you
gain metadata sync but lose the protected-branch fallback the
release push otherwise gets from `RELEASE_PAT`.

#### Repository variables

Configure under **Settings → Secrets and variables → Actions → Variables**.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DEFAULT_RUNNER` | *(required)* | Either a bare runner label (e.g. `ubuntu-latest`) or a JSON array string (e.g. `'["self-hosted","linux","x64"]'`). Both shape and presence are enforced by the `preflight-runner-config` job. |
| `BOS_FUNDING_ENABLED` | `true` (when unset) | Master switch for the FUNDING.yml resolver. When `true`/`1`/`yes`/`on`, the resolver checks per-repo → org `.github` → emits notices/warnings. When set to anything else (`false`, `0`, etc.), the resolver skips all probes, excludes `.github/FUNDING.yml` from the allowlist, and emits one notice acknowledging the opt-out. The Sponsor button on the Marketplace listing/repo header will be absent. |

#### What the FUNDING resolver decides

The `resolve-funding` step in [release.yml](.github/workflows/release.yml)
classifies every release into one of seven outcomes (surfaced as the
job output `funding_status` and shown in the job summary):

| `funding_status` | Allowlist | Surface | Trigger |
|------------------|-----------|---------|---------|
| `disabled` | excluded | `::notice::` | `vars.BOS_FUNDING_ENABLED` is non-truthy |
| `per-repo` | **included** | `::notice::` | `.github/FUNDING.yml` exists on `dev` (promoted to `main` as an override) |
| `inherited` | excluded | `::notice::` | Owner is an org, `<org>/.github` is public and contains FUNDING.yml (root, `.github/`, or `docs/`) |
| `user-no-inheritance` | excluded | `::warning::` | Repo owner is a user account — GitHub does not inherit default community files for user repos |
| `no-org-dotgithub` | excluded | `::warning::` | `<org>/.github` is missing or private/internal (inheritance is public-only) |
| `org-dotgithub-not-public` | excluded | `::warning::` | `<org>/.github` exists but is `private`/`internal` |
| `org-missing-funding` | excluded | `::warning::` | `<org>/.github` is public but contains no FUNDING.yml in any of the three honored locations |

Every warning includes a remediation hint. The resolver itself never
fails the release — it informs.

#### Sponsor button alignment

Independently of FUNDING.yml content, the repo-level **Settings →
Features → Sponsorships** checkbox controls whether the Sponsor
button renders at all. The `check-funding-alignment` step in
[release.yml](.github/workflows/release.yml) cross-references the
resolver's `funding_status` against the rendered feature flag
(`Repository.hasSponsorshipsEnabled`) and the effective link list
(`Repository.fundingLinks`, read via GraphQL with `GITHUB_TOKEN`).

| `alignment_status` | Sponsorships feature | Effective links rendered | Verdict | Surface |
|--------------------|----------------------|--------------------------|---------|---------|
| `aligned` | on | >0 | Working as intended | `::notice::` |
| `aligned-off` | off | 0 | Intentionally off; consistent | `::notice::` |
| `button-empty` | on | 0 | **Misaligned** — Sponsor button opens an empty modal | `::warning::` |
| `links-hidden` | off | (n/a) | **Misaligned** — FUNDING content exists but no button renders | `::warning::` |
| `unknown` | (GraphQL probe failed) | n/a | Diagnostic-only; release proceeds | `::notice::` |

GitHub exposes **no public API to flip the Sponsorships feature flag**
(no REST field on `PATCH /repos/{}`, no GraphQL mutation — it is
intentionally human-gated). This step is therefore detection-only: it
emits a warning with a one-click Settings URL on misalignment and
never fails the release. Fix the button-empty / links-hidden cases
once by ticking or unticking the checkbox at
`https://github.com/<owner>/<repo>/settings` and the warning goes
silent on the next release.

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

## 🧪 Examples

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

**Configs — packaged defaults with per-repo override.** The composite
ships sensible default configs for `markdownlint-cli2`, `yamllint`,
and `shellcheck` inside the action under
[`.github/actions/lint/configs/`](.github/actions/lint/configs/). They
are tuned for GitHub Actions YAML, documentation-heavy READMEs, and
composite-action shell snippets. Consumers get them automatically with
zero setup. To override, drop the corresponding file at the consumer
repo root and each linter's normal auto-discovery (which takes
precedence over the packaged fallback) picks it up:

| Linter             | Repo-root override                                     |
| ------------------ | ------------------------------------------------------ |
| `markdownlint-cli2`| `.markdownlint.{yaml,yml,jsonc,json,cjs}`              |
| `yamllint`         | `.yamllint` / `.yamllint.yml` / `.yamllint.yaml`       |
| `shellcheck`       | `.shellcheckrc`                                        |

The fallback fires only when no repo-local file is present, so a
consumer that wants stricter or looser rules (e.g. `line-length: 250`
for KQL-heavy workflows) keeps full control by shipping its own
config — same escape hatch as every other lint composite in the
ecosystem.

`marketplace-kit generate-policy markdownlint`, `yamllint`, or
`shellcheckrc` still emits a starter file if you want to scaffold an
override.

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

### Repo `About` box sync (`repo-metadata`)

Keeps the public-facing repo `About` box honest after each release.
Each of the three user-visible fields — **description**, **homepage**,
and **topics** — can be set in one of three ways:

1. **Explicit input** (`description:` / `homepage:` / `topics:`) —
   when non-empty, this always wins. AI is never consulted.
2. **AI-generated from the README** — falls back here when the
   explicit input is empty and AI is enabled (`ai_enabled: true`,
   default). `homepage` is never AI-derived; it's caller-supplied or
   left alone.
3. **Deterministic fallback** — for description, the raw README seed
   paragraph (still clamped). For topics, the `topics_fallback`
   list. For homepage, the existing value is left untouched.

All values pass through the same sanitizers regardless of source:
description ≤ 350 chars (word-boundary clamp + ellipsis), topics
lowercase `a-z0-9-`, ≤ 50 chars each, ≤ 20 total. You can mix and
match — e.g. set `description` explicitly, let AI pick `topics`,
leave `homepage` alone.

Defaults are framed around "this is a release":

* `show_releases: true` — the Releases sidebar widget is on.
* `show_deployments: false` / `show_packages: false` — opt-in.
* `generate_topics: false` — opt-in. Set `true` and (optionally)
  pass `topics_fallback` for when AI is unavailable.
* `ai_enabled: true`, `ai_model: openai/gpt-4o-mini`. Falls back
  deterministically to the raw README seed when the AI call fails
  (most commonly because the job lacks `models: read`).

Tokens: the standard `${{ github.token }}` is **not** enough — this
composite PATCHes the repo and needs `Administration: write`. Pass a
fine-grained PAT or an installation token in `github_token`. In the
kit's own [release.yml](.github/workflows/release.yml) this comes
from `secrets.REPO_ADMIN_PAT` when set, otherwise from
`secrets.RELEASE_PAT` — see
[Step 5b — Tokens, secrets, and variables](#step-5b--tokens-secrets-and-variables)
for the full token contract and the
[single-PAT vs separate-PATs](#single-pat-default-vs-separate-pats-advanced)
decision.

#### Fully explicit (no AI)

Set every field yourself; no `models: read` needed, no surprises.

```yaml
jobs:
  sync-about-box:
    runs-on: ubuntu-latest
    needs: release
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v5
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/repo-metadata@v1
        with:
          # RELEASE_PAT is the default; REPO_ADMIN_PAT is honoured
          # first when set (advanced blast-radius separation). See
          # Step 5b — Tokens, secrets, and variables.
          github_token: ${{ secrets.REPO_ADMIN_PAT || secrets.RELEASE_PAT }}
          description: 'Lint, gate, and publish GitHub Marketplace Actions — without the boilerplate.'
          homepage:    'https://github.com/marketplace/actions/blackout-secure-marketplace-kit'
          topics:      'github-actions marketplace devops linting branch-protection'
          ai_enabled:  'false'   # belt-and-braces; explicit values would win anyway
```

#### AI-assisted

Let GitHub Models rewrite the README lead paragraph as the
description and derive topics. Explicit values still override
individual fields when you want to.

```yaml
jobs:
  sync-about-box:
    runs-on: ubuntu-latest
    needs: release
    permissions:
      contents: read
      models: read           # required for the AI rewrite; fallback still works without it
    steps:
      - uses: actions/checkout@v5
      - uses: blackoutsecure/bos-marketplace-kit/.github/actions/repo-metadata@v1
        with:
          # Admin-capable PAT — default GITHUB_TOKEN cannot PATCH repo
          # metadata. RELEASE_PAT is the default; REPO_ADMIN_PAT wins
          # when set (advanced blast-radius separation). See Step 5b.
          github_token: ${{ secrets.REPO_ADMIN_PAT || secrets.RELEASE_PAT }}
          homepage: 'https://github.com/marketplace/actions/my-cool-action'
          generate_topics: 'true'
          topics_fallback: 'github-actions devops marketplace'
          # Defaults already match a release: show_releases=true,
          # show_deployments=false, show_packages=false.
          show_packages: 'true'   # opt in if your repo publishes packages
```

Widget toggles caveat: GitHub does not (as of this writing) document
the `show_releases` / `show_deployments` / `show_packages` fields on
the public REST API. The composite sends them on the standard repo
PATCH anyway (the call succeeds because PATCH is permissive about
unknown fields) and emits a `::notice::` so operators know the toggle
part is best-effort. `description`, `homepage`, and `topics` are
always applied through documented authoritative endpoints.

Outputs: `description`, `description_source` (`explicit` | `ai` |
`readme` | `existing`), `homepage`, `topics`, `topics_source`
(`explicit` | `ai` | `fallback` | `skipped`), `ai_used`, `applied`.
Use `dry_run: 'true'` to render the proposed payload to the job
summary without calling the API.

## 💻 Local usage (CLI)

The kit ships a standalone `marketplace-kit` CLI for local triage or
non-GitHub CI. It runs the same manifest rules as the composite, resolves the
same config cascade, and needs no network unless you ask for a name check or
an AI summary.

```bash
pipx install bos-marketplace-kit      # or: pip install bos-marketplace-kit
```

```bash
# Validate action.yml against the MP/OP/SC rules
marketplace-kit check
marketplace-kit check --fail-on-warning --skip OP003

# Full readiness summary (manifest + community-health files + branches)
marketplace-kit doctor

# Package metadata + the resolved config cascade, and which tiers applied
marketplace-kit config
marketplace-kit config --json
marketplace-kit config --use-marketplace-config false   # what changes without it?

# Explain the findings and how to fix them (AI when reachable, local otherwise)
marketplace-kit explain
marketplace-kit explain --no-ai            # never call a model
marketplace-kit explain --provider external --model acme/m1

# Check that a proposed action name is available on the Marketplace
marketplace-kit name-check "my-cool-deployer"

# Render a markdown table of inputs/outputs for your README
marketplace-kit doc-inputs
marketplace-kit doc-inputs --action-yml .github/actions/guard/action.yml

# Scaffold policy files (see the catalogue for every kind)
marketplace-kit generate-policy list
marketplace-kit generate-policy security --owner my-org
marketplace-kit install --all --owner my-org
marketplace-kit install global-config         # optional org-wide config
marketplace-kit install repo-config           # optional per-repo config
marketplace-kit install security --ai         # AI-tailored, static fallback

marketplace-kit version
```

Exit codes: `0` clean, `1` a rule failed (or warned with
`--fail-on-warning`), `2` a usage or configuration error.

## ⚠️ Runtime and repository notes

* **Checkout is required.** Put `actions/checkout` before the kit. The action
  validates `${{ github.workspace }}`; without a checkout there is nothing to
  inspect.
* **`action.yml` must be at the repo root of the default branch.** That is a
  Marketplace requirement, not a kit one — `MP007` catches it early.
  Additional manifests under `.github/actions/**` are explicitly permitted;
  they simply are not listed.
* **Keeping `.github/workflows/**` off `main` is kit policy, not a GitHub
  rule.** See
  [Marketplace requirements vs. kit policy](#marketplace-requirements-vs-kit-policy).
* **Skips are not passes.** A rule set to `skip`, or one whose token lacked
  permission, reports as skipped rather than as evidence that the control is
  in place. `GH003` in particular needs an admin-scoped token.
* **Live-state rules need network access.** `GH###` and `RM###` call the
  GitHub REST API; `name-check` calls github.com. Everything else is offline.
* **AI is optional and non-blocking.** No provider, a disabled provider, or a
  provider error degrades to local remediation. See
  [AI triage and data handling](#ai-triage-and-data-handling).
* **Protect central config.** Anyone who can change the org global config
  changes policy in every repo that consumes it. Protect those repos and pin
  this action to a tag or SHA.
* **No secrets in config.** Keep credentials out of `marketplace_kit` config
  files. Use Actions secrets for sensitive values and Actions variables for
  non-sensitive shared ones.
* **Untrusted pull requests.** Run checks with `pull_request` (never
  `pull_request_target` with a PR-head checkout) and no write permissions.

## 🔐 Security

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

## 🏷️ Versioning

Semantic versioning. The floating `@v1` tag follows the latest `v1.x.x`
release. Pin by SHA in security-sensitive workflows; pin by major-tag
for ergonomic upgrades.

## 🤝 Contributing

General contribution guidelines (issue triage, PR style, test
expectations, security review) come from the organisation default at
[`blackoutsecure/.github/CONTRIBUTING.md`](https://github.com/blackoutsecure/.github/blob/main/CONTRIBUTING.md),
which applies to every repo in the org. The kit-specific bits are
below.

All PRs target the **`dev`** branch. The `main` branch is built by
the release pipeline (see
[Publishing to Marketplace](#publishing-to-marketplace)) and is
read-only to humans — PRs opened against `main` will be closed.

### Local development

```bash
# Install dev deps (Python 3.10+)
pip install -e '.[dev]'

# Run the test suite (this is what CI runs)
python3 -m pytest test/ -v

# Lint
python3 -m ruff check src test scripts

# Keep the README's generated action tables in sync with action.yml
python3 scripts/render_readme_inputs.py --check
python3 scripts/render_readme_inputs.py --write

# Run the CLI against the local repo
marketplace-kit check
marketplace-kit config
```

The composite actions under `.github/actions/` are pure bash and
runnable on any Linux host with `git`, `jq`, and `curl` — no Python
needed if you only want to exercise the action surface.

### Style

* **Bash**: `shellcheck` clean at `--severity=warning`,
  `set -euo pipefail`, `${VAR}` braces consistently.
* **Python**: type hints on public APIs, stdlib only in the CLI.
* **YAML (workflows)**: `actionlint` clean, pin third-party actions
  by SHA (not tag), minimise `permissions:` per job.

Lint configs live under `.markdownlint.yaml`, `.yamllint.yml`, and
`.shellcheckrc`. The `lint` composite action under `.github/actions/lint/`
runs the full battery the same way CI does.

### Adding a new check rule

See [Adding new rules](#adding-new-rules) above for the full
checklist (next sequential `MP###`/`OP###`/`SC###`/`CH###` ID, test
fixture under `test/`, README catalogue row, `remediation` string,
minor-version bump).

### Releasing

Releases are operator-triggered, not automated. See
[Publishing to Marketplace](#publishing-to-marketplace) for the full
step-by-step (`release.yml` dispatch on `dev` with the desired tag —
the workflow promotes the allowlisted file set from `dev` to `main`,
tags `main`, and creates the GitHub Release).

## 📜 License

[Apache License 2.0](LICENSE). See [`NOTICE`](NOTICE) for third-party attributions.
