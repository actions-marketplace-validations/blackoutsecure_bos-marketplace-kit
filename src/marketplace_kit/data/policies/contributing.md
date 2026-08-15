# Contributing to `{{project_name}}`

Thanks for your interest in contributing! This document covers the
basics of how we work.

## Ways to contribute

* **Report a bug** — open a GitHub issue with reproduction steps.
* **Propose a feature** — open an issue first to discuss the design
  before sinking time into a PR.
* **Improve docs** — typo fixes and clarifications are very welcome.
* **Submit a PR** — see the workflow below.

## Pull-request workflow

1. **Fork** the repository and create a feature branch from `main`
   (or `dev` if the repo uses a `dev` → `main` promotion model).
2. **Write tests** that cover your change. PRs without tests for
   non-trivial logic will be sent back.
3. **Keep PRs small and focused.** One logical change per PR makes
   review fast and revert safe.
4. **Sign off your commits** with `git commit -s` if the repo
   enforces DCO (the CI will tell you).
5. **Run the full test suite** locally before pushing.

## Code style

* Match the surrounding code; the project's existing style takes
  precedence over your personal preferences.
* No trailing whitespace, files end with a single newline.
* Comments explain *why*, not *what* — the code shows the *what*.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/) where
practical:

```
feat(scope): short summary

Longer body explaining motivation and trade-offs.
Closes #123.
```

## Reporting security issues

**Do not** open a public issue for security reports. See
[SECURITY.md](SECURITY.md) for the private reporting process.

## Code of Conduct

By participating in this project you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Questions?

Open a [Discussion](https://github.com/{{owner}}/{{repo_name}}/discussions)
or reach out to {{contact_email}}.
