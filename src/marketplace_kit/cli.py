"""CLI entrypoint for the BOS Marketplace Kit.

Mirrors a subset of the composite-action surface so operators can
sanity-check their manifests locally before pushing. Keeps the
implementation deliberately small — the canonical enforcement lives
in the composites; this CLI is a developer ergonomics layer.

Subcommands:
    check            — validate `action.yml` against MP###/OP###/SC### rules
    name-check       — verify the Marketplace name is available
    generate-policy  — emit a community-health policy file from a template
    version          — print version info
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path
from typing import NamedTuple

from . import __version__


# ---------------------------------------------------------------------------
# Rule catalogue
# ---------------------------------------------------------------------------

# Branding enum from the GitHub Marketplace docs.
ALLOWED_COLORS = {
    "white",
    "yellow",
    "blue",
    "green",
    "orange",
    "red",
    "purple",
    "gray-dark",
}

# Top-level keys required in any Marketplace manifest.
REQUIRED_KEYS = {"name", "description", "runs"}

# Description hard upper bound (Marketplace truncates >125 chars in
# card view; we warn at 125 and error if absent).
DESC_SOFT_MAX = 125


class CheckResult(NamedTuple):
    rule_id: str
    status: str  # "pass" | "fail" | "warn" | "skip"
    message: str


def _emoji(status: str) -> str:
    return {
        "pass": "PASS",
        "fail": "FAIL",
        "warn": "WARN",
        "skip": "SKIP",
    }.get(status, "?")


# ---------------------------------------------------------------------------
# YAML loader (lazy import so --help works without PyYAML)
# ---------------------------------------------------------------------------

def _load_manifest(path: Path) -> dict:
    try:
        import yaml  # noqa: WPS433 (lazy import on purpose)
    except ImportError:
        sys.stderr.write("error: PyYAML is required. Install with: pip install bos-marketplace-kit\n")
        raise SystemExit(2)

    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.stderr.write(f"error: manifest not found: {path}\n")
        raise SystemExit(2)
    except yaml.YAMLError as exc:
        sys.stderr.write(f"error: invalid YAML in {path}: {exc}\n")
        raise SystemExit(2)

    if not isinstance(doc, dict):
        sys.stderr.write(f"error: {path} did not parse as a YAML mapping\n")
        raise SystemExit(2)

    return doc


# ---------------------------------------------------------------------------
# Subcommand: check
# ---------------------------------------------------------------------------

def _run_checks(manifest: dict) -> list[CheckResult]:
    results: list[CheckResult] = []

    # MP001 — top-level required keys.
    for key in sorted(REQUIRED_KEYS):
        if key in manifest:
            results.append(CheckResult("MP001", "pass", f"`{key}` present"))
        else:
            results.append(CheckResult("MP001", "fail", f"`{key}` missing from manifest"))

    # MP002 — name non-empty.
    name = (manifest.get("name") or "").strip()
    if name:
        results.append(CheckResult("MP002", "pass", f"name=`{name}`"))
    else:
        results.append(CheckResult("MP002", "fail", "`name` is empty"))

    # MP003 — description present.
    desc = (manifest.get("description") or "").strip()
    if desc:
        results.append(CheckResult("MP003", "pass", f"description ({len(desc)} chars)"))
    else:
        results.append(CheckResult("MP003", "fail", "`description` is empty"))

    # OP001 — description length hint.
    if desc and len(desc) > DESC_SOFT_MAX:
        results.append(CheckResult("OP001", "warn", f"description >{DESC_SOFT_MAX} chars — Marketplace truncates in card view"))
    elif desc:
        results.append(CheckResult("OP001", "pass", f"description length {len(desc)} <= {DESC_SOFT_MAX}"))

    # MP004 — `runs.using` present.
    runs = manifest.get("runs") or {}
    using = (runs.get("using") or "").strip() if isinstance(runs, dict) else ""
    if using:
        results.append(CheckResult("MP004", "pass", f"runs.using=`{using}`"))
    else:
        results.append(CheckResult("MP004", "fail", "`runs.using` missing"))

    # MP005 — branding.icon present.
    branding = manifest.get("branding") or {}
    icon = (branding.get("icon") or "").strip() if isinstance(branding, dict) else ""
    if icon:
        results.append(CheckResult("MP005", "pass", f"branding.icon=`{icon}`"))
    else:
        results.append(CheckResult("MP005", "fail", "`branding.icon` missing"))

    # MP006 — branding.color present + in enum.
    color = (branding.get("color") or "").strip() if isinstance(branding, dict) else ""
    if not color:
        results.append(CheckResult("MP006", "fail", "`branding.color` missing"))
    elif color not in ALLOWED_COLORS:
        results.append(CheckResult(
            "MP006",
            "fail",
            f"`branding.color`=`{color}` not in {sorted(ALLOWED_COLORS)}",
        ))
    else:
        results.append(CheckResult("MP006", "pass", f"branding.color=`{color}`"))

    # OP003 — author present.
    if (manifest.get("author") or "").strip():
        results.append(CheckResult("OP003", "pass", f"author=`{manifest['author']}`"))
    else:
        results.append(CheckResult("OP003", "warn", "`author` not set — recommended for Marketplace listings"))

    # SC002 — composite actions should pin third-party uses by SHA.
    # (Heuristic: flag any `uses: <owner>/<repo>@<non-sha-ref>` where
    # the ref is not 40 hex chars and not `./` local.)
    # Note: ID `SC001` is reserved for the composite's shell-injection
    # check (in `.github/actions/check/action.yml`); keep this CLI
    # rule under a distinct ID so consumers can target either.
    if isinstance(runs, dict) and runs.get("using") == "composite":
        steps = runs.get("steps") or []
        unpinned: list[str] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            uses = (step.get("uses") or "").strip()
            if not uses or uses.startswith("./"):
                continue
            if "@" not in uses:
                unpinned.append(uses)
                continue
            ref = uses.rsplit("@", 1)[1]
            if not re.fullmatch(r"[0-9a-f]{40}", ref):
                unpinned.append(uses)
        if unpinned:
            results.append(CheckResult(
                "SC002",
                "warn",
                f"third-party `uses` not SHA-pinned: {', '.join(unpinned)}",
            ))
        else:
            results.append(CheckResult("SC002", "pass", "all third-party `uses` are SHA-pinned"))

    return results


def cmd_check(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.action_yml))
    results = _run_checks(manifest)

    skip_ids = {s.strip() for s in (args.skip or "").split(",") if s.strip()}
    filtered = [r for r in results if r.rule_id not in skip_ids]

    fail = sum(1 for r in filtered if r.status == "fail")
    warn = sum(1 for r in filtered if r.status == "warn")
    ok   = sum(1 for r in filtered if r.status == "pass")

    print(f"{'RULE':<8} {'STATUS':<6} MESSAGE")
    for r in filtered:
        print(f"{r.rule_id:<8} {_emoji(r.status):<6} {r.message}")
    print()
    print(f"summary: {ok} pass, {fail} fail, {warn} warn")

    if fail > 0:
        return 1
    if warn > 0 and args.fail_on_warning:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Subcommand: name-check
# ---------------------------------------------------------------------------

# (Tiny mirrors of the composite's reserved-name lists. The composite
# is authoritative — these are duplicated for local convenience.)
RESERVED_CATEGORIES = frozenset({
    "ai-assisted", "api-management", "chat", "code-quality", "code-review",
    "continuous-integration", "dependency-management", "deployment", "ides",
    "learning", "localization", "mobile", "monitoring",
    "open-source-management", "project-management", "publishing", "security",
    "support", "testing", "utilities",
})

RESERVED_FEATURES = frozenset({
    "actions", "advisories", "api", "assets", "billing", "blog", "codespaces",
    "collections", "contact", "dashboard", "discussions", "discover",
    "enterprise", "events", "explore", "features", "gist", "gists", "help",
    "home", "integrations", "issues", "login", "logout", "marketplace", "new",
    "notifications", "orgs", "packages", "pages", "partners", "pricing",
    "projects", "pulls", "pull-requests", "releases", "search", "security",
    "settings", "signup", "site", "sponsors", "stars", "status", "support",
    "teams", "tos", "trending", "users", "watching", "webhooks",
})


def _slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def _http_status(url: str, *, user_agent: str = "bos-marketplace-kit") -> int | None:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def cmd_name_check(args: argparse.Namespace) -> int:
    name = args.name
    slug = _slugify(name)
    if not slug:
        print(f"error: '{name}' normalises to an empty slug", file=sys.stderr)
        return 2

    print(f"name : {name}")
    print(f"slug : {slug}")
    print()

    user_status = _http_status(f"https://api.github.com/users/{slug}")
    user_taken = user_status == 200

    mp_status = _http_status(f"https://github.com/marketplace/actions/{slug}")
    mp_taken = mp_status in (200, 301, 302)

    cat_taken = slug in RESERVED_CATEGORIES
    feat_taken = slug in RESERVED_FEATURES

    def report(label: str, taken: bool) -> None:
        verdict = "TAKEN" if taken else "AVAILABLE"
        print(f"  {label:<32} {verdict}")

    report("GitHub user/org", user_taken)
    report("Marketplace listing", mp_taken)
    report("Reserved Marketplace category", cat_taken)
    report("Reserved GitHub feature", feat_taken)

    if any((user_taken, mp_taken, cat_taken, feat_taken)):
        if args.fail_on_collision:
            return 1
        print("\nwarning: collisions detected (continuing because --no-fail)", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# Subcommand: version
# ---------------------------------------------------------------------------

def cmd_version(_args: argparse.Namespace) -> int:
    print(f"bos-marketplace-kit {__version__}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: doctor
# ---------------------------------------------------------------------------

# Files that should be present at the root of a Marketplace-publishable repo.
# Format: (path, severity) where severity is "fail" or "warn".
_DOCTOR_FILES: tuple[tuple[str, str], ...] = (
    ("action.yml",         "fail"),
    ("README.md",          "fail"),
    ("LICENSE",            "fail"),
    ("SECURITY.md",        "warn"),
    ("CODE_OF_CONDUCT.md", "warn"),
)


def cmd_doctor(args: argparse.Namespace) -> int:
    """End-to-end repo readiness summary.

    Runs all of:
      * the manifest check (`cmd_check` equivalents),
      * a presence check for community-health files,
      * a presence check for the `dev` and `main` branches.

    Exits non-zero if any FAIL is recorded, regardless of warnings.
    """
    import subprocess

    manifest_path = Path(args.action_yml)
    fails = 0
    warns = 0

    print(f"# marketplace-kit doctor (manifest: {manifest_path})")
    print()

    # ----- 1. Run the static rules ----------------------------------------
    print("## Manifest checks")
    if not manifest_path.is_file():
        print(f"FAIL  manifest-present  {manifest_path} not found")
        fails += 1
    else:
        manifest = _load_manifest(manifest_path)
        for r in _run_checks(manifest):
            line = f"{_emoji(r.status):<5} {r.rule_id:<6} {r.message}"
            print(line)
            if r.status == "fail":
                fails += 1
            elif r.status == "warn":
                warns += 1
    print()

    # ----- 2. Community-health files --------------------------------------
    print("## Community-health files")
    for relpath, severity in _DOCTOR_FILES:
        present = Path(relpath).is_file()
        if present:
            print(f"PASS  doctor  {relpath} present")
        elif severity == "fail":
            print(f"FAIL  doctor  {relpath} missing (required)")
            fails += 1
        else:
            print(f"WARN  doctor  {relpath} missing — generate with `marketplace-kit generate-policy`")
            warns += 1
    print()

    # ----- 3. Branch presence ---------------------------------------------
    print("## Branches")
    for branch in ("dev", "main"):
        try:
            subprocess.run(
                ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"PASS  branch  local `{branch}` exists")
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                subprocess.run(
                    ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                print(f"PASS  branch  remote `origin/{branch}` exists (no local checkout)")
            except (subprocess.CalledProcessError, FileNotFoundError):
                print(f"WARN  branch  `{branch}` not found locally or on origin")
                warns += 1
    print()

    print(f"Summary: {fails} fail / {warns} warn")
    if fails:
        return 1
    if warns and getattr(args, "fail_on_warning", False):
        return 1
    return 0


# ---------------------------------------------------------------------------
# Subcommand: doc-inputs
# ---------------------------------------------------------------------------

def cmd_doc_inputs(args: argparse.Namespace) -> int:
    """Emit a markdown table of `inputs:` and `outputs:` from an action.yml.

    Handy for keeping README synced with the manifest. Output goes to
    stdout — pipe into your README between markers.
    """
    manifest = _load_manifest(Path(args.action_yml))
    inputs = manifest.get("inputs") or {}
    outputs = manifest.get("outputs") or {}

    def _row(name: str, body: dict) -> str:
        if not isinstance(body, dict):
            return f"| `{name}` | | | |"
        desc = (body.get("description") or "").strip().replace("\n", " ").replace("|", "\\|")
        required = "yes" if body.get("required") else "no"
        default = body.get("default")
        if default is None or default == "":
            default_md = ""
        else:
            default_md = f"`{default}`".replace("|", "\\|")
        return f"| `{name}` | {required} | {default_md} | {desc} |"

    print(f"<!-- generated by `marketplace-kit doc-inputs {args.action_yml}` -->")
    print()
    if inputs:
        print("### Inputs")
        print()
        print("| Name | Required | Default | Description |")
        print("|------|----------|---------|-------------|")
        for name, body in inputs.items():
            print(_row(str(name), body if isinstance(body, dict) else {}))
        print()
    if outputs:
        print("### Outputs")
        print()
        print("| Name | Description |")
        print("|------|-------------|")
        for name, body in outputs.items():
            desc = ""
            if isinstance(body, dict):
                desc = (body.get("description") or "").strip().replace("\n", " ").replace("|", "\\|")
            print(f"| `{name}` | {desc} |")
        print()
    return 0


# ---------------------------------------------------------------------------
# Subcommand: generate-policy
# ---------------------------------------------------------------------------

# Map of `--kind` argument → (template_file, default_output_path,
# pretty_label_for_messages).
POLICY_KINDS: dict[str, tuple[str, str, str]] = {
    "security":         ("security.md",                 "SECURITY.md",                              "Security policy"),
    "code-of-conduct":  ("code-of-conduct.md",          "CODE_OF_CONDUCT.md",                       "Code of Conduct"),
    "contributing":     ("contributing.md",             "CONTRIBUTING.md",                          "Contributing guide"),
    "support":          ("support.md",                  "SUPPORT.md",                               "Support guide"),
    "issue-bug":        ("issue-template-bug.md",       ".github/ISSUE_TEMPLATE/bug_report.md",       "Bug-report issue template"),
    "issue-feature":    ("issue-template-feature.md",   ".github/ISSUE_TEMPLATE/feature_request.md", "Feature-request issue template"),
    "pr-template":      ("pull-request-template.md",    ".github/PULL_REQUEST_TEMPLATE.md",          "Pull-request template"),
    "funding":          ("funding.yml",                 ".github/FUNDING.yml",                       "Funding manifest"),
}


def _load_template(template_file: str) -> str:
    """Read a policy template from the package data."""
    try:
        # Python 3.9+ resources API.
        return resources.files("marketplace_kit.data.policies").joinpath(template_file).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        sys.stderr.write(f"error: missing policy template {template_file!r}: {exc}\n")
        raise SystemExit(2)


def _render_template(text: str, *, owner: str, repo_name: str, contact_email: str, project_name: str) -> str:
    """Substitute `{{placeholder}}` markers. Pure string replace — no
    fancy templating engine, no external dependency."""
    return (
        text
        .replace("{{owner}}", owner)
        .replace("{{repo_name}}", repo_name)
        .replace("{{contact_email}}", contact_email)
        .replace("{{project_name}}", project_name)
    )


def cmd_generate_policy(args: argparse.Namespace) -> int:
    kind = args.kind
    if kind == "list":
        for k, (_, default_out, label) in sorted(POLICY_KINDS.items()):
            print(f"  {k:<18} {label:<35} -> {default_out}")
        return 0

    if kind not in POLICY_KINDS:
        sys.stderr.write(
            f"error: unknown kind {kind!r}. Choices: {sorted(POLICY_KINDS)} or 'list'.\n"
        )
        return 2

    template_file, default_out, label = POLICY_KINDS[kind]
    text = _load_template(template_file)

    repo_name = args.repo or Path.cwd().name
    project_name = args.project_name or repo_name
    rendered = _render_template(
        text,
        owner=args.owner or "YOUR-ORG",
        repo_name=repo_name,
        contact_email=args.email or "security@example.com",
        project_name=project_name,
    )

    if args.ai:
        sys.stderr.write(
            "note: --ai is not yet implemented. Falling back to the static template.\n"
            "      Track progress: https://github.com/blackoutsecure/bos-marketplace-kit/issues\n"
        )

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    out_path = Path(args.output) if args.output else Path(default_out)
    if out_path.exists() and not args.force:
        sys.stderr.write(
            f"error: {out_path} already exists. Use --force to overwrite, "
            "--stdout to print, or --output to choose a different path.\n"
        )
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    sys.stderr.write(f"wrote {label} → {out_path} ({len(rendered)} bytes)\n")
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketplace-kit",
        description="Local CLI companion to the BOS Marketplace Kit.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check", help="Validate action.yml against MP/OP/SC rules.")
    p_check.add_argument("--action-yml", default="action.yml", help="Path to manifest. Default `action.yml`.")
    p_check.add_argument("--fail-on-warning", action="store_true", help="Treat OP### warnings as failures.")
    p_check.add_argument("--skip", default="", help="Comma-separated rule IDs to skip.")
    p_check.set_defaults(func=cmd_check)

    p_nc = sub.add_parser("name-check", help="Check Marketplace name availability.")
    p_nc.add_argument("name", help="Proposed action name (from `action.yml`'s `name:`).")
    p_nc.add_argument(
        "--no-fail",
        dest="fail_on_collision",
        action="store_false",
        help="Do not exit non-zero on collision (warnings only).",
    )
    p_nc.set_defaults(func=cmd_name_check, fail_on_collision=True)

    p_gp = sub.add_parser(
        "generate-policy",
        help="Emit a community-health policy file (SECURITY.md, CODE_OF_CONDUCT.md, …) from a template.",
    )
    p_gp.add_argument(
        "kind",
        help=(
            "Policy kind. Use 'list' to enumerate available kinds. "
            "Choices: " + ", ".join(sorted(POLICY_KINDS)) + ", list."
        ),
    )
    p_gp.add_argument("--owner", default=None, help="Org / user slug to substitute for {{owner}}.")
    p_gp.add_argument("--repo", default=None, help="Repository name to substitute for {{repo_name}}. Defaults to CWD basename.")
    p_gp.add_argument("--project-name", default=None, help="Human-readable project name (defaults to --repo).")
    p_gp.add_argument("--email", default=None, help="Contact email to substitute for {{contact_email}}.")
    p_gp.add_argument("--output", "-o", default=None, help="Path to write to. Defaults to the canonical location for this kind.")
    p_gp.add_argument("--stdout", action="store_true", help="Print to stdout instead of writing a file.")
    p_gp.add_argument("--force", "-f", action="store_true", help="Overwrite the output file if it already exists.")
    p_gp.add_argument("--ai", action="store_true", help="(Future) ask an AI to draft the policy instead of using the static template.")
    p_gp.set_defaults(func=cmd_generate_policy)

    p_v = sub.add_parser("version", help="Print version and exit.")
    p_v.set_defaults(func=cmd_version)

    p_doc = sub.add_parser(
        "doctor",
        help="End-to-end repo readiness summary (manifest + community-health + branches).",
    )
    p_doc.add_argument("--action-yml", default="action.yml", help="Path to manifest. Default `action.yml`.")
    p_doc.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Exit non-zero if any rule warns (default: only fail on FAIL).",
    )
    p_doc.set_defaults(func=cmd_doctor)

    p_di = sub.add_parser(
        "doc-inputs",
        help="Emit a markdown table of inputs/outputs from an action.yml (stdout).",
    )
    p_di.add_argument("--action-yml", default="action.yml", help="Path to manifest. Default `action.yml`.")
    p_di.set_defaults(func=cmd_doc_inputs)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
