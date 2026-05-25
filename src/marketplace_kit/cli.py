"""CLI companion to the BOS Marketplace Kit composite actions.

The canonical enforcement surface is the composite actions under
`.github/actions/`. This CLI mirrors a useful subset so operators can
sanity-check a Marketplace Action locally before pushing.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path
from typing import Any, Iterable, NamedTuple

from . import __version__


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Branding enum from the GitHub Marketplace docs.
ALLOWED_COLORS: frozenset[str] = frozenset({
    "white", "yellow", "blue", "green",
    "orange", "red", "purple", "gray-dark",
})

# Required top-level keys in any Marketplace manifest.
REQUIRED_KEYS: tuple[str, ...] = ("name", "description", "runs")

# Marketplace truncates descriptions >125 chars in the card view.
DESC_SOFT_MAX = 125

# Status labels used in console output and the doctor summary.
STATUSES = ("pass", "fail", "warn", "skip")


class CheckResult(NamedTuple):
    rule_id: str
    status: str  # one of STATUSES
    message: str


# ---------------------------------------------------------------------------
# Small typed accessors — keep callers free of `isinstance` boilerplate
# ---------------------------------------------------------------------------

def _as_dict(value: Any) -> dict:
    """Return ``value`` if it's a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def _as_str(value: Any) -> str:
    """Return the stripped string form of ``value``, or '' if absent."""
    return (value or "").strip() if isinstance(value, str) else ""


def _md_escape(text: str) -> str:
    """Escape characters that would break a markdown table cell."""
    return text.replace("\n", " ").replace("|", "\\|")


# ---------------------------------------------------------------------------
# YAML loader (lazy import so `--help` works without PyYAML installed)
# ---------------------------------------------------------------------------

def _load_manifest(path: Path) -> dict:
    try:
        import yaml
    except ImportError:
        sys.stderr.write(
            "error: PyYAML is required. Install with: pip install bos-marketplace-kit\n"
        )
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

    def add(rule_id: str, status: str, message: str) -> None:
        results.append(CheckResult(rule_id, status, message))

    # MP001 — top-level required keys.
    for key in REQUIRED_KEYS:
        if key in manifest:
            add("MP001", "pass", f"`{key}` present")
        else:
            add("MP001", "fail", f"`{key}` missing from manifest")

    # MP002 — name non-empty.
    name = _as_str(manifest.get("name"))
    add("MP002", "pass" if name else "fail",
        f"name=`{name}`" if name else "`name` is empty")

    # MP003 — description non-empty.
    desc = _as_str(manifest.get("description"))
    add("MP003", "pass" if desc else "fail",
        f"description ({len(desc)} chars)" if desc else "`description` is empty")

    # OP001 — description length hint.
    if desc:
        if len(desc) > DESC_SOFT_MAX:
            add("OP001", "warn",
                f"description >{DESC_SOFT_MAX} chars — Marketplace truncates in card view")
        else:
            add("OP001", "pass", f"description length {len(desc)} <= {DESC_SOFT_MAX}")

    # MP004 — runs.using present.
    runs = _as_dict(manifest.get("runs"))
    using = _as_str(runs.get("using"))
    add("MP004", "pass" if using else "fail",
        f"runs.using=`{using}`" if using else "`runs.using` missing")

    # MP005/MP006 — branding.
    branding = _as_dict(manifest.get("branding"))
    icon = _as_str(branding.get("icon"))
    add("MP005", "pass" if icon else "fail",
        f"branding.icon=`{icon}`" if icon else "`branding.icon` missing")

    color = _as_str(branding.get("color"))
    if not color:
        add("MP006", "fail", "`branding.color` missing")
    elif color not in ALLOWED_COLORS:
        add("MP006", "fail",
            f"`branding.color`=`{color}` not in {sorted(ALLOWED_COLORS)}")
    else:
        add("MP006", "pass", f"branding.color=`{color}`")

    # OP003 — author present.
    author = _as_str(manifest.get("author"))
    add("OP003", "pass" if author else "warn",
        f"author=`{author}`" if author else
        "`author` not set — recommended for Marketplace listings")

    # SC002 — composite actions should pin third-party `uses` by SHA.
    # (SC001 is reserved for the shell-injection scan in the `check`
    # composite; keep this CLI rule under SC002 so consumers can target
    # either independently via `skip_checks`.)
    if using == "composite":
        unpinned = _unpinned_uses(runs.get("steps") or [])
        if unpinned:
            add("SC002", "warn",
                f"third-party `uses` not SHA-pinned: {', '.join(unpinned)}")
        else:
            add("SC002", "pass", "all third-party `uses` are SHA-pinned")

    return results


_SHA_RE = re.compile(r"[0-9a-f]{40}")


def _unpinned_uses(steps: Iterable[Any]) -> list[str]:
    """Return composite-step `uses:` values that aren't SHA-pinned."""
    unpinned: list[str] = []
    for step in steps:
        uses = _as_str(_as_dict(step).get("uses"))
        if not uses or uses.startswith("./"):
            continue
        if "@" not in uses or not _SHA_RE.fullmatch(uses.rsplit("@", 1)[1]):
            unpinned.append(uses)
    return unpinned


def _print_results(results: Iterable[CheckResult]) -> tuple[int, int, int]:
    """Print the standard check table; return (pass, fail, warn) counts."""
    print(f"{'RULE':<8} {'STATUS':<6} MESSAGE")
    ok = fail = warn = 0
    for r in results:
        print(f"{r.rule_id:<8} {r.status.upper():<6} {r.message}")
        if r.status == "pass":
            ok += 1
        elif r.status == "fail":
            fail += 1
        elif r.status == "warn":
            warn += 1
    return ok, fail, warn


def cmd_check(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.action_yml))
    skip_ids = {s.strip() for s in (args.skip or "").split(",") if s.strip()}
    results = [r for r in _run_checks(manifest) if r.rule_id not in skip_ids]

    ok, fail, warn = _print_results(results)
    print()
    print(f"summary: {ok} pass, {fail} fail, {warn} warn")

    if fail:
        return 1
    if warn and args.fail_on_warning:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Subcommand: name-check
# ---------------------------------------------------------------------------

# Local mirror of the composite's reserved-name lists. The composite
# is authoritative — these are duplicated for CLI ergonomics.
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

_SLUG_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SLUG_DASH_RUN = re.compile(r"-+")
_USER_AGENT = "bos-marketplace-kit"
_HTTP_TIMEOUT = 10


def _slugify(name: str) -> str:
    return _SLUG_DASH_RUN.sub("-", _SLUG_NON_ALNUM.sub("-", name.lower())).strip("-")


def _http_status(url: str, *, user_agent: str = _USER_AGENT) -> int | None:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:  # noqa: S310
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def cmd_name_check(args: argparse.Namespace) -> int:
    slug = _slugify(args.name)
    if not slug:
        print(f"error: '{args.name}' normalises to an empty slug", file=sys.stderr)
        return 2

    print(f"name : {args.name}")
    print(f"slug : {slug}")
    print()

    checks = (
        ("GitHub user/org",
            _http_status(f"https://api.github.com/users/{slug}") == 200),
        ("Marketplace listing",
            _http_status(f"https://github.com/marketplace/actions/{slug}") in (200, 301, 302)),
        ("Reserved Marketplace category", slug in RESERVED_CATEGORIES),
        ("Reserved GitHub feature", slug in RESERVED_FEATURES),
    )
    for label, taken in checks:
        print(f"  {label:<32} {'TAKEN' if taken else 'AVAILABLE'}")

    if any(taken for _, taken in checks):
        if args.fail_on_collision:
            return 1
        print("\nwarning: collisions detected (continuing because --no-fail)",
              file=sys.stderr)
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

# Community-health files expected at the repo root, with per-file
# severity when missing.
_DOCTOR_FILES: tuple[tuple[str, str], ...] = (
    ("action.yml",         "fail"),
    ("README.md",          "fail"),
    ("LICENSE",            "fail"),
    ("SECURITY.md",        "warn"),
    ("CODE_OF_CONDUCT.md", "warn"),
)


def _branch_exists(branch: str) -> bool:
    """True if ``branch`` exists either locally or on ``origin``."""
    for cmd in (
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
    ):
        try:
            subprocess.run(cmd, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return False


def cmd_doctor(args: argparse.Namespace) -> int:
    """Repo-readiness summary: manifest + community-health + branches."""
    manifest_path = Path(args.action_yml)
    fails = warns = 0

    print(f"# marketplace-kit doctor (manifest: {manifest_path})")
    print()

    # 1. Manifest rules.
    print("## Manifest checks")
    if not manifest_path.is_file():
        print(f"FAIL  manifest-present  {manifest_path} not found")
        fails += 1
    else:
        for r in _run_checks(_load_manifest(manifest_path)):
            print(f"{r.status.upper():<5} {r.rule_id:<6} {r.message}")
            if r.status == "fail":
                fails += 1
            elif r.status == "warn":
                warns += 1
    print()

    # 2. Community-health files.
    print("## Community-health files")
    for relpath, severity in _DOCTOR_FILES:
        if Path(relpath).is_file():
            print(f"PASS  doctor  {relpath} present")
        elif severity == "fail":
            print(f"FAIL  doctor  {relpath} missing (required)")
            fails += 1
        else:
            print(f"WARN  doctor  {relpath} missing — generate with "
                  "`marketplace-kit generate-policy`")
            warns += 1
    print()

    # 3. Publish-model branches.
    print("## Branches")
    for branch in ("dev", "main"):
        if _branch_exists(branch):
            print(f"PASS  branch  `{branch}` exists")
        else:
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

def _input_row(name: str, body: dict) -> str:
    desc = _md_escape(_as_str(body.get("description")))
    required = "yes" if body.get("required") else "no"
    default = body.get("default")
    default_md = f"`{default}`".replace("|", "\\|") if default not in (None, "") else ""
    return f"| `{name}` | {required} | {default_md} | {desc} |"


def _output_row(name: str, body: dict) -> str:
    return f"| `{name}` | {_md_escape(_as_str(body.get('description')))} |"


def cmd_doc_inputs(args: argparse.Namespace) -> int:
    """Emit a markdown table of `inputs:` / `outputs:` to stdout."""
    manifest = _load_manifest(Path(args.action_yml))
    inputs = manifest.get("inputs") or {}
    outputs = manifest.get("outputs") or {}

    print(f"<!-- generated by `marketplace-kit doc-inputs {args.action_yml}` -->")
    print()
    if inputs:
        print("### Inputs\n")
        print("| Name | Required | Default | Description |")
        print("|------|----------|---------|-------------|")
        for name, body in inputs.items():
            print(_input_row(str(name), _as_dict(body)))
        print()
    if outputs:
        print("### Outputs\n")
        print("| Name | Description |")
        print("|------|-------------|")
        for name, body in outputs.items():
            print(_output_row(str(name), _as_dict(body)))
        print()
    return 0


# ---------------------------------------------------------------------------
# Subcommand: generate-policy
# ---------------------------------------------------------------------------

class _PolicyKind(NamedTuple):
    template: str       # filename under marketplace_kit/data/policies/
    default_out: str    # repo-relative output path
    label: str          # human-friendly name for log messages


# Map of `--kind` argument → policy template spec.
POLICY_KINDS: dict[str, _PolicyKind] = {
    "security":         _PolicyKind("security.md",              "SECURITY.md",                              "Security policy"),
    "code-of-conduct":  _PolicyKind("code-of-conduct.md",       "CODE_OF_CONDUCT.md",                       "Code of Conduct"),
    "contributing":     _PolicyKind("contributing.md",          "CONTRIBUTING.md",                          "Contributing guide"),
    "support":          _PolicyKind("support.md",               "SUPPORT.md",                               "Support guide"),
    "issue-bug":        _PolicyKind("issue-template-bug.md",    ".github/ISSUE_TEMPLATE/bug_report.md",      "Bug-report issue template"),
    "issue-feature":    _PolicyKind("issue-template-feature.md",".github/ISSUE_TEMPLATE/feature_request.md", "Feature-request issue template"),
    "pr-template":      _PolicyKind("pull-request-template.md", ".github/PULL_REQUEST_TEMPLATE.md",          "Pull-request template"),
    "funding":          _PolicyKind("funding.yml",              ".github/FUNDING.yml",                       "Funding manifest"),
    "dependabot":               _PolicyKind("dependabot.yml",               ".github/dependabot.yml",                "Dependabot config"),
    "codeql-workflow":          _PolicyKind("codeql-workflow.yml",          ".github/workflows/codeql.yml",          "CodeQL workflow"),
    "scorecard-workflow":       _PolicyKind("scorecard-workflow.yml",       ".github/workflows/scorecard.yml",       "OpenSSF Scorecard workflow"),
    "security-devops-workflow": _PolicyKind("security-devops-workflow.yml", ".github/workflows/security-devops.yml", "MS Security DevOps workflow"),
    "markdownlint":             _PolicyKind("markdownlint.yaml",            ".markdownlint.yaml",                    "markdownlint config"),
    "yamllint":                 _PolicyKind("yamllint.yml",                 ".yamllint.yml",                         "yamllint config"),
    "shellcheckrc":             _PolicyKind("shellcheckrc",                 ".shellcheckrc",                         "shellcheck config"),
}


def _load_template(template_file: str) -> str:
    try:
        return (resources.files("marketplace_kit.data.policies")
                .joinpath(template_file)
                .read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        sys.stderr.write(f"error: missing policy template {template_file!r}: {exc}\n")
        raise SystemExit(2)


def _render_template(text: str, **subs: str) -> str:
    """Replace ``{{name}}`` markers with values from ``subs`` (no engine)."""
    for key, value in subs.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _render_policy(
    kind: str,
    owner: str | None,
    repo: str | None,
    project_name: str | None,
    email: str | None,
) -> tuple[_PolicyKind, str]:
    """Resolve placeholder values and render ``kind``'s template.

    Shared by ``generate-policy`` (one-kind-at-a-time, flexible
    --output / --stdout) and ``install`` (canonical-path scaffolder,
    optional --all). Keeping the placeholder defaults in one place
    means both commands substitute identically.
    """
    spec = POLICY_KINDS[kind]
    repo_name = repo or Path.cwd().name
    rendered = _render_template(
        _load_template(spec.template),
        owner=owner or "YOUR-ORG",
        repo_name=repo_name,
        contact_email=email or "security@example.com",
        project_name=project_name or repo_name,
    )
    return spec, rendered


def cmd_generate_policy(args: argparse.Namespace) -> int:
    kind = args.kind
    if kind == "list":
        for k in sorted(POLICY_KINDS):
            spec = POLICY_KINDS[k]
            print(f"  {k:<18} {spec.label:<35} -> {spec.default_out}")
        return 0

    if kind not in POLICY_KINDS:
        sys.stderr.write(
            f"error: unknown kind {kind!r}. Choices: {sorted(POLICY_KINDS)} or 'list'.\n"
        )
        return 2

    spec, rendered = _render_policy(
        kind,
        owner=args.owner,
        repo=args.repo,
        project_name=args.project_name,
        email=args.email,
    )

    if args.ai:
        sys.stderr.write(
            "note: --ai is not yet implemented. Falling back to the static template.\n"
        )

    if args.stdout:
        sys.stdout.write(rendered)
        return 0

    out_path = Path(args.output) if args.output else Path(spec.default_out)
    if out_path.exists() and not args.force:
        sys.stderr.write(
            f"error: {out_path} already exists. Use --force to overwrite, "
            "--stdout to print, or --output to choose a different path.\n"
        )
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    sys.stderr.write(f"wrote {spec.label} → {out_path} ({len(rendered)} bytes)\n")
    return 0


# ---------------------------------------------------------------------------
# Install — scaffold one or every policy kind at its canonical path
# ---------------------------------------------------------------------------

# Kinds installed by `install --all`. Excludes templates that are
# legitimately optional or that ship with strong opinions a maintainer
# usually wants to opt into per repo:
#   * `scorecard-workflow`, `security-devops-workflow` — overlap with
#     CodeQL + GHAS default-setup; treat as opt-in.
#   * `shellcheckrc` — only useful when a repo actually ships shell
#     scripts; skip by default.
INSTALL_ALL_KINDS: tuple[str, ...] = (
    "security",
    "code-of-conduct",
    "contributing",
    "support",
    "issue-bug",
    "issue-feature",
    "pr-template",
    "funding",
    "dependabot",
    "codeql-workflow",
    "markdownlint",
    "yamllint",
)


def _install_one(
    kind: str,
    *,
    owner: str | None,
    repo: str | None,
    project_name: str | None,
    email: str | None,
    force: bool,
    dry_run: bool,
    base: Path,
) -> tuple[str, _PolicyKind, Path]:
    """Install ``kind`` at its canonical path under ``base``.

    Returns ``(status, spec, out_path)`` where ``status`` is one of
    ``write``, ``skip`` (already present, no --force), ``force``
    (overwrote), or ``dry-write`` / ``dry-skip`` under --dry-run.
    """
    spec, rendered = _render_policy(
        kind,
        owner=owner,
        repo=repo,
        project_name=project_name,
        email=email,
    )
    out_path = base / spec.default_out
    existed = out_path.exists()

    if existed and not force:
        return ("dry-skip" if dry_run else "skip", spec, out_path)

    status = (
        ("dry-force" if dry_run else "force") if existed
        else ("dry-write" if dry_run else "write")
    )

    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")

    return (status, spec, out_path)


def cmd_install(args: argparse.Namespace) -> int:
    kinds: list[str]
    if args.all:
        if args.kind not in (None, "all"):
            sys.stderr.write(
                "error: pass either KIND or --all, not both.\n"
            )
            return 2
        kinds = list(INSTALL_ALL_KINDS)
    else:
        if not args.kind:
            sys.stderr.write(
                "error: KIND is required (or pass --all). "
                f"Choices: {sorted(POLICY_KINDS)}.\n"
            )
            return 2
        if args.kind not in POLICY_KINDS:
            sys.stderr.write(
                f"error: unknown kind {args.kind!r}. "
                f"Choices: {sorted(POLICY_KINDS)}.\n"
            )
            return 2
        kinds = [args.kind]

    base = Path(args.cwd) if args.cwd else Path.cwd()
    if not base.is_dir():
        sys.stderr.write(f"error: --cwd {base} is not a directory.\n")
        return 2

    written = forced = skipped = 0
    for kind in kinds:
        status, spec, out_path = _install_one(
            kind,
            owner=args.owner,
            repo=args.repo,
            project_name=args.project_name,
            email=args.email,
            force=args.force,
            dry_run=args.dry_run,
            base=base,
        )
        rel = out_path.relative_to(base) if out_path.is_relative_to(base) else out_path
        sys.stderr.write(f"  [{status:<9}] {spec.label:<35} -> {rel}\n")
        if status.endswith("write"):
            written += 1
        elif status.endswith("force"):
            forced += 1
        elif status.endswith("skip"):
            skipped += 1

    prefix = "would " if args.dry_run else ""
    sys.stderr.write(
        f"{prefix}install summary: {written} written, "
        f"{forced} overwritten, {skipped} skipped (already present).\n"
    )
    if args.dry_run:
        sys.stderr.write("dry-run: no files modified.\n")
    return 0



# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="marketplace-kit",
        description="Local CLI companion to the BOS Marketplace Kit.",
    )
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_check = sub.add_parser("check",
        help="Validate action.yml against MP/OP/SC rules.")
    p_check.add_argument("--action-yml", default="action.yml",
        help="Path to manifest. Default `action.yml`.")
    p_check.add_argument("--fail-on-warning", action="store_true",
        help="Treat OP### warnings as failures.")
    p_check.add_argument("--skip", default="",
        help="Comma-separated rule IDs to skip.")
    p_check.set_defaults(func=cmd_check)

    p_nc = sub.add_parser("name-check",
        help="Check Marketplace name availability.")
    p_nc.add_argument("name",
        help="Proposed action name (from `action.yml`'s `name:`).")
    p_nc.add_argument("--no-fail", dest="fail_on_collision",
        action="store_false",
        help="Do not exit non-zero on collision (warnings only).")
    p_nc.set_defaults(func=cmd_name_check, fail_on_collision=True)

    p_gp = sub.add_parser("generate-policy",
        help="Emit a community-health policy file from a template.")
    p_gp.add_argument("kind",
        help="Policy kind. Use 'list' to enumerate. Choices: "
             + ", ".join(sorted(POLICY_KINDS)) + ", list.")
    p_gp.add_argument("--owner",
        help="Org / user slug to substitute for {{owner}}.")
    p_gp.add_argument("--repo",
        help="Repository name to substitute for {{repo_name}}. Defaults to CWD basename.")
    p_gp.add_argument("--project-name",
        help="Human-readable project name (defaults to --repo).")
    p_gp.add_argument("--email",
        help="Contact email to substitute for {{contact_email}}.")
    p_gp.add_argument("--output", "-o",
        help="Path to write to. Defaults to the canonical location for this kind.")
    p_gp.add_argument("--stdout", action="store_true",
        help="Print to stdout instead of writing a file.")
    p_gp.add_argument("--force", "-f", action="store_true",
        help="Overwrite the output file if it already exists.")
    p_gp.add_argument("--ai", action="store_true",
        help="(Reserved) ask an AI to draft the policy. Currently a no-op.")
    p_gp.set_defaults(func=cmd_generate_policy)

    p_inst = sub.add_parser("install",
        help="Scaffold one or every policy file at its canonical path "
             "(`generate-policy` with safe defaults).")
    p_inst.add_argument("kind", nargs="?",
        help="Policy kind to install. Omit when using --all. Choices: "
             + ", ".join(sorted(POLICY_KINDS)) + ".")
    p_inst.add_argument("--all", action="store_true",
        help="Install every recommended kind that isn't already present "
             f"({', '.join(INSTALL_ALL_KINDS)}).")
    p_inst.add_argument("--owner",
        help="Org / user slug to substitute for {{owner}}.")
    p_inst.add_argument("--repo",
        help="Repository name for {{repo_name}}. Defaults to --cwd basename.")
    p_inst.add_argument("--project-name",
        help="Human-readable project name (defaults to --repo).")
    p_inst.add_argument("--email",
        help="Contact email for {{contact_email}}.")
    p_inst.add_argument("--cwd",
        help="Repository root to install into. Defaults to the current "
             "working directory.")
    p_inst.add_argument("--force", "-f", action="store_true",
        help="Overwrite files that already exist.")
    p_inst.add_argument("--dry-run", action="store_true",
        help="Print what would be written without touching the filesystem.")
    p_inst.set_defaults(func=cmd_install)

    p_v = sub.add_parser("version", help="Print version and exit.")
    p_v.set_defaults(func=cmd_version)

    p_doc = sub.add_parser("doctor",
        help="End-to-end repo readiness (manifest + community-health + branches).")
    p_doc.add_argument("--action-yml", default="action.yml",
        help="Path to manifest. Default `action.yml`.")
    p_doc.add_argument("--fail-on-warning", action="store_true",
        help="Exit non-zero if any rule warns.")
    p_doc.set_defaults(func=cmd_doctor)

    p_di = sub.add_parser("doc-inputs",
        help="Emit a markdown table of inputs/outputs from an action.yml.")
    p_di.add_argument("--action-yml", default="action.yml",
        help="Path to manifest. Default `action.yml`.")
    p_di.set_defaults(func=cmd_doc_inputs)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
