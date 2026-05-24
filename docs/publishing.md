# Publishing your action to GitHub Marketplace

This guide walks you through publishing a Marketplace-listed Action
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

---

## Step 1 — Set up branches

Default branch on your action repo should be `main`. Working branch
is `dev`.

```bash
git checkout -b dev
git push -u origin dev
```

In the repo Settings → Branches, set the default branch to `main`.

---

## Step 2 — Add the kit's CI on `dev`

Create `.github/workflows/marketplace-check.yml` on `dev`:

```yaml
name: marketplace-check
"on":
  pull_request:
    branches: [dev]
  push:
    branches: [dev]
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6.0.2
        with:
          persist-credentials: false
      - uses: blackoutsecure/bos-marketplace-kit@v1
        with:
          action_yml_path: action.yml
```

Run it locally first using the CLI:

```bash
pip install bos-marketplace-kit
marketplace-kit check
```

Fix any `MP###` or `SC###` failures before continuing. `OP###`
warnings are optional but recommended.

---

## Step 3 — Verify the name

```bash
marketplace-kit name-check "Your Action Name"
```

If this reports any collision, rename before publishing. Renaming
**after** publishing requires a new repo URL — much more painful.

---

## Step 4 — Render the branding preview

```bash
# In CI: uses the branding-preview composite, uploads as artifact.
# Locally: the SVG renders from your action.yml's branding block.
```

Open the SVG artifact in the PR run. If the icon or colour is wrong,
fix it in `action.yml` and re-run.

---

## Step 5 — Add the release workflow on `dev`

Create `.github/workflows/release.yml` on `dev`. See
[`examples/full-lifecycle.yml`](../examples/full-lifecycle.yml) for
the full template.

The release workflow:

1. Validates the SemVer tag input.
2. Promotes `dev` → `main` using the kit's `promote` action.
3. The `promote` action HARD-BLOCKS any `.github/workflows/**` entry
   in the allowlist, transitively strips workflows pulled in via
   parent directories, removes anything not in the allowlist from
   `main`, and pushes a clean commit + tag.
4. Creates a GitHub Release on the new tag.

---

## Step 6 — Configure branch protection on `main`

Two options, in order of preference:

### Option A: Org-level ruleset (recommended)

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

### Option B: Branch protection (fallback)

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

---

## Step 7 — First release

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

---

## Step 8 — Publish to Marketplace

Navigate to your repo's Releases page on GitHub. On the `v1.0.0`
release, click **Edit**. Tick **"Publish this Action to the GitHub
Marketplace"**. Choose a primary category and optional secondary
category. Click **Update release**.

The action appears at `https://github.com/marketplace/actions/<your-slug>`
within minutes.

---

## Step 9 — Set up the guard on PRs

Defense-in-depth: add `.github/workflows/marketplace-guard.yml` on
`dev` (see `examples/full-lifecycle.yml`). This runs on every PR
targeting `main` and fails fast if the PR would introduce a
prohibited path.

Without the guard, you'd discover violations at promote time (too
late — your operator typed the version and hit go). The guard
surfaces them in the PR check list.

---

## Updating the action

1. Branch off `dev`, make changes.
2. Open PR → `dev`. CI runs (check + guard + branding preview).
3. Merge to `dev`.
4. Tag and release: `gh workflow run release.yml -f tag_name=v1.0.1`.

The Marketplace listing auto-updates as soon as the tag exists.

---

## Troubleshooting

### "Failed to publish: this repository contains workflow files"

Your `main` has at least one `.github/workflows/*.yml`. Run the guard
locally to find them:

```bash
git ls-tree -r --name-only main | grep '^\.github/workflows/'
```

Remove them with a hotfix promote:

```bash
# The promote action will strip them automatically when you next release.
gh workflow run release.yml -f tag_name=v1.0.1
```

### Branding icon is wrong

Run `marketplace-kit check` — the branding-preview composite or the
local CLI will tell you the exact Feather icon name. Fix on `dev` and
re-release.

### "Action name 'X' is already taken"

Rename early. After publishing, the slug is permanent on your repo.
Renaming requires creating a new repo, transferring stars, and
re-publishing.

### Promote fails with "removed_violations"

Your `main` had `.github/workflows/**` paths before this promote.
The kit removed them. Verify with the dry-run output, then re-run.

---

## Further reading

* [Check rule catalogue](checks.md)
* [GitHub Marketplace publishing docs](https://docs.github.com/en/actions/how-tos/create-and-publish-actions/publish-in-github-marketplace)
* [Feather icon set](https://feathericons.com/) (v4.28.0)
