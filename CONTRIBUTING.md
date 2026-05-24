# Contributing to bos-marketplace-kit

Thanks for your interest! This guide covers how to file issues, propose
changes, and ship code.

## TL;DR

* All work targets the **`dev`** branch. PRs against `main` will be closed
  (Marketplace publishing forbids workflow files on the default branch, so
  `main` is auto-built from `dev` by the release pipeline).
* Run the local check before pushing: `make check` (or see the manual
  commands in [Local development](#local-development) below).
* Sign your commits if you can (`git commit -S`); not required.

## Reporting issues

Open an issue at <https://github.com/blackoutsecure/bos-marketplace-kit/issues>.
Please include:

1. Tool surface (`check`, `guard`, `promote`, `name-check`, etc.).
2. Reproduction (the smallest possible repo or workflow snippet that
   triggers the behaviour).
3. Expected vs. actual output. Paste the JSON report (`--json`) when
   relevant — it's machine-readable and easy to diff.

For suspected security issues see [`SECURITY.md`](SECURITY.md). Do **not**
file public issues for security reports.

## Proposing changes

1. Fork the repo or create a branch off `dev`.
2. Make your change.
3. Add or update tests under `tests/` if you touched check logic.
4. Run `make check` (lints + tests) before opening the PR.
5. Open a PR against `dev`. Describe the user-visible effect, not the
   implementation.
6. CI must be green. Maintainer review may request changes.

PRs that add a new check rule MUST include:

* The rule ID (next sequential `MP###`/`OP###`/`SC###`).
* A test fixture under `tests/fixtures/`.
* A row in [`docs/checks.md`](docs/checks.md).
* A `remediation` string on the check (not just a failure message).

## Local development

```bash
# Install dev deps (Python 3.11+)
pipx install --editable .[dev]

# Run lints
make lint

# Run tests
make test

# Run the CLI against the local repo
marketplace-kit check .

# Run the CLI against a remote repo (uses GitHub API, no clone)
marketplace-kit check owner/repo
```

If you don't want to install Python tooling, the composite actions under
`actions/` are pure bash and runnable on any Linux host with `git`,
`jq`, and `curl`.

## Style

* **Bash**: shellcheck clean at `--severity=warning`. Use `set -euo pipefail`.
  Use `${VAR}` braces consistently. Prefer `[ ]` over `[[ ]]` for portability.
* **Python**: ruff + black defaults. Type hints required on public APIs.
* **YAML (workflows)**: actionlint clean. Pin third-party actions by SHA
  (not tag). Minimize `permissions:` per job.
* **Markdown**: reference-style links for repeat URLs.

## Release process

Releases are operator-triggered, not automated:

1. Maintainer dispatches `release.yml` on `dev` with the desired tag.
2. The workflow promotes the allowlisted file set from `dev` to `main`,
   tags `main`, and creates a GitHub Release.
3. Marketplace pickup is automatic for the first release (UI checkbox)
   and continuous for subsequent releases.

The tool dogfoods itself: `self-check.yml` runs `check` against this repo
on every PR, and `release.yml` uses `promote` to do the actual promotion.

## License

By contributing you agree that your contributions are licensed under the
Apache License 2.0 (see [`LICENSE`](LICENSE)).
