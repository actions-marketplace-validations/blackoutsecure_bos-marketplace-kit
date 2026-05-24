"""Policy file templates for `marketplace-kit generate-policy`.

Each template is a plain-text file with `{{placeholder}}` markers
that the CLI's `generate-policy` subcommand substitutes at render
time. Templates live as data files so they're trivially editable
and round-trip through `git diff` without code changes.

Placeholders:
    * `{{owner}}`         — repo / org slug (e.g. `blackoutsecure`)
    * `{{repo_name}}`     — repository name (e.g. `bos-marketplace-kit`)
    * `{{contact_email}}` — security / support contact
    * `{{project_name}}`  — human-readable name (defaults to repo_name)
"""
