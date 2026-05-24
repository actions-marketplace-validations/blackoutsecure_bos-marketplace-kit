# Security policy

## Supported versions

Only the latest published Marketplace release is supported. Older releases
do not receive security fixes — upgrade to the latest tag.

## Reporting a vulnerability

**Do not file public GitHub issues for security reports.**

Use one of the following private channels:

1. GitHub's [private vulnerability reporting][gh-pvr] (preferred). Navigate
   to the repo's **Security → Report a vulnerability** tab.
2. Email `security@blackoutsecure.com` with a clear subject line that
   starts with `[bos-marketplace-kit]`.

Please include:

* A short description of the issue.
* The minimum reproduction.
* Your assessment of impact (confidentiality / integrity / availability).
* Any suggested mitigation.

We aim to acknowledge reports within 3 business days and to ship a fix or
publish a workaround within 90 days, whichever comes sooner. Critical
issues (CVSS ≥ 9.0) will be addressed faster.

## Scope

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

## Hardening notes for consumers

If you wire this tool into your own CI:

* Pin our actions by **commit SHA**, not tag. Tags can be moved.
* Set the **minimum required `permissions:`** on the calling workflow.
  `guard` needs `contents: read` + `pull-requests: read`. `promote` needs
  `contents: write`. `check` needs `contents: read`.
* When calling `guard` via `pull_request_target`, do **not** check out the
  PR head. The default checkout of the base ref is correct and safe.
* When calling `promote`, use a deploy key or a fine-grained PAT
  scoped to the target repo only. Do not use a classic PAT with broad
  scope.

[gh-pvr]: https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability
