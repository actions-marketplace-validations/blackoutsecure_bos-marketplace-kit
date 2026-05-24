# Check rule catalogue

`bos-marketplace-kit`'s `check` action enforces a layered set of
rules against your `action.yml`. Each rule has a stable ID across
versions; skip individual rules with the `skip_checks` input.

Rule families:

| Prefix | Severity | Failure causes |
|--------|----------|----------------|
| `MP###` | **Fatal** | Marketplace publish prerequisite missing or invalid. Action would not be acceptable to GitHub. |
| `OP###` | Warning  | Best-practice violation. Non-fatal by default; set `fail_on_warning: true` to promote. |
| `SC###` | **Fatal** | Security-impacting default missing. Failure indicates a supply-chain or token-exposure risk. |

---

## MP001 — Top-level manifest keys

**Required:** `name`, `description`, `runs` MUST be present at the
root of `action.yml`.

**Fix:** Add the missing keys. `runs:` must be a mapping containing
at least `using:`.

---

## MP002 — `name` is non-empty

`name:` must be a non-empty string. Marketplace displays this on the
listing card and across search results.

**Fix:** Set `name: Your Action Name`.

---

## MP003 — `description` is non-empty

`description:` is the one-line subtitle on the Marketplace card.

**Fix:** Set `description: One sentence describing what the action does.`.

See also: [OP001](#op001--description-length).

---

## MP004 — `runs.using` is present

`runs:` must declare an execution model:

* `composite`
* `node20` (or newer LTS)
* `docker`

**Fix:** Set `runs.using: composite` (most common for shell-driven
actions).

---

## MP005 — `branding.icon` is present

Marketplace requires a Feather icon name in `branding.icon`. The
icon set is pinned to Feather v4.28.0 by GitHub.

**Fix:** Add a valid Feather icon name. See the kit's `branding-preview`
action to render the resulting card before pushing.

```yaml
branding:
  icon: check-circle
  color: green
```

---

## MP006 — `branding.color` is in the allowed enum

Allowed: `white`, `yellow`, `blue`, `green`, `orange`, `red`,
`purple`, `gray-dark`.

**Fix:** Use one of the eight allowed values exactly. No hex codes,
no other names.

---

## MP007 — `action.yml` lives at the repo root

Marketplace ONLY detects a single manifest at the root of the default
branch. Subdirectory manifests (e.g. `.github/actions/foo/action.yml`)
are NOT listable on Marketplace.

**Fix:** Move the manifest you want to publish to the repo root. The
kit's `promote` action's allowlist should include `action.yml`.

---

## MP008 — Name is not too short

Marketplace rejects single-character action names and very short
names that collide with reserved features (see name-check).

**Fix:** Use a name of at least 3 characters. Run the kit's
`name-check` action to validate availability.

---

## MP009 — Description is not too short

A description shorter than 10 characters is unlikely to be useful on
the Marketplace card and may be rejected.

**Fix:** Expand the description to a complete sentence (~30-125 chars).

---

## OP001 — Description length

Marketplace truncates description >125 characters in card view.
Warning emitted when description exceeds this soft cap.

**Fix:** Tighten the description to a single short sentence. Use
README.md for elaboration.

---

## OP003 — `author` is set

Optional but strongly recommended. Marketplace shows the author on
the listing card.

**Fix:** Add `author: Your Org Name`.

---

## OP004 — Composite actions declare a `shell:` on each `run:` step

GitHub does NOT default the shell for composite-action run steps —
omitting `shell:` is an error at runtime. The check surfaces this
statically.

**Fix:** Add `shell: bash` (or another supported shell) to every
`run:` step in a composite manifest.

---

## SC001 — Third-party actions are pinned by SHA

Tag/branch refs (`@v4`, `@main`) are mutable. A compromised tag move
can inject arbitrary code into your runner. SHA pins (`@<40-hex>`)
are immutable.

**Fix:** Replace tag/branch refs with the full commit SHA. Use
Dependabot or `bos-upstream-watcher` to bump pins automatically.

```yaml
- uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
```

---

## SC003 — Security policy is discoverable

Public Marketplace listings should advertise a private reporting
channel for security issues. The check looks for any of:

* `SECURITY.md`, `.github/SECURITY.md`, or `docs/SECURITY.md` in the
  calling repo,
* the same files in the org's `.github` repository (when
  `check_org_health: true` and a token is supplied), **or**
* a README that mentions `security policy`, `SECURITY.md`, or
  `report ... vulnerability`.

The strictness is controlled by the `require_security` input:

| Value  | Behaviour on a missing policy                                                                     |
|--------|---------------------------------------------------------------------------------------------------|
| `fail` | Hard failure — the README escape hatch is also disabled at this level.                            |
| `warn` | **Default.** Records a warning. The action overall still passes unless `fail_on_warning: true`.   |
| `skip` | Rule short-circuits to a `skip` status — equivalent to listing `SC003` in `skip_checks`.          |

**Generate a template:**

```bash
marketplace-kit generate-policy security \
  --owner my-org --repo my-action --email security@example.com
```

---

## CH001-CH006 — Community-health files (org-aware)

The kit checks a small set of community-health files Marketplace
consumers expect to find on a popular public action. Each rule looks
in this repo first; if the file is missing, it falls back to the
org's `.github` repository (canonical home for shared defaults) when
`check_org_health: true` and `github_token` is non-empty. If found in
either location the rule passes; the report message records which
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

### Org-aware lookup

Set `check_org_health: true` (default) and pass `github_token:
${{ github.token }}` to enable the org-wide fallback. The check
makes at most:

* **one** `GET /repos/{owner}/.github` call to confirm the org
  health repo exists, and
* **one** `GET /repos/{owner}/.github/contents/{path}` per missing
  file (so 0-6 additional cheap API calls per run).

Override the destination repo with `org_health_repo: my-org/.github`
if your org uses a non-default location.

### Generate a starter template

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

---

## Adding new rules

Open a PR against `dev` that:

1. Adds the rule to `.github/actions/check/action.yml`.
2. Documents it here with a stable ID.
3. Adds a unit test under `tests/` covering the failure case.
4. Bumps the kit's minor version.

The kit promises stability for `MP###`/`OP###`/`SC###` rule IDs across
minor versions — adding a rule never reuses an existing ID.
