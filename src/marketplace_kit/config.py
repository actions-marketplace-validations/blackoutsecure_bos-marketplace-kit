"""Layered JSON configuration for the BOS Marketplace Kit.

Four tiers are merged in cascade order, each overriding the one above:

1. **Runtime defaults** — conservative built-ins compiled into this
   module. Used when everything else is absent or disabled.
2. **Marketplace config** — the kit's recommended values, shipped in
   ``data/marketplace-config.json``. Enabled by default; disable with
   ``"use_marketplace_config": false`` in any lower tier.
3. **Global config** — optional org/hub-level file, auto-discovered at
   ``.github/bos-marketplace-kit-global-config.json``.
4. **Repo config** — optional per-repo file, auto-discovered at
   ``.github/workflow-configs/bos-universal-config.json`` (preferred,
   matching the automation-hub convention) and friends.

Workflow inputs are applied last by the composite action: any input left
empty falls through to the resolved config value.

Stdlib only — this module is imported by the composite action on a bare
runner before any package install.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, NamedTuple

# Section key inside every config document. A document that has no such
# key is treated as the section itself, so a dedicated file can be flat.
SECTION = "marketplace_kit"

# Repo-level config, in discovery order. First existing file wins. The
# hub-conventional path comes first (automation-hub moved its universal
# config there); the legacy root path stays as a fallback for repos that
# haven't migrated.
REPO_CONFIG_CANDIDATES: tuple[str, ...] = (
    ".github/workflow-configs/bos-universal-config.json",
    ".github/bos-universal-config.json",
    "bos-universal-config.json",
    "marketplace-kit.json",
    ".marketplace-kit.json",
)

# Conventional org/hub-level config. Optional; auto-discovered.
GLOBAL_CONFIG_PATH = ".github/marketplace-kit-global-config.json"

MARKETPLACE_CONFIG_FILE = "marketplace-kit-marketplace-config.json"

POLICY_VALUES = ("fail", "warn", "skip")
SOURCE_VALUES = ("local", "inherit", "either")
PROVIDER_VALUES = ("auto", "none", "github-models", "external")
PROFILE_VALUES = ("baseline", "strict")

# Marketplace slug of the companion kit that owns live security posture.
CODE_SCANNING_KIT = "blackoutsecure/bos-code-scanning-kit"

# Rules this kit would otherwise duplicate from the code-scanning kit's
# posture audit. Left of the arrow is ours, right is theirs.
CODE_SCANNING_KIT_RULES: dict[str, str] = {
    "require_ghas_code_scanning": "PS001",
    "require_ghas_secret_scanning": "PS002",
    "require_dependabot_alerts": "PS003",
    "require_security_devops": "PS013",
}

# Every rule that only exists to assert security posture. Switched off
# as a group by `enable_security_scan: false`.
SECURITY_SCAN_RULES: tuple[str, ...] = (
    "require_security",
    "require_codeql",
    "require_ghas_code_scanning",
    "require_ghas_secret_scanning",
    "require_dependabot_alerts",
    "require_security_devops",
    "require_scorecard",
)

# The `strict` profile's recommendation: promote the controls that are
# free on public repositories and cheap to satisfy from `warn` to `fail`.
# Kept as an opt-in overlay so the default posture never breaks a build
# on upgrade.
STRICT_PROFILE: dict[str, Any] = {
    "require_security": "fail",
    "require_code_of_conduct": "fail",
    "require_contributing": "fail",
    "require_dependabot": "fail",
    "require_codeql": "fail",
    "require_editorconfig": "fail",
    "require_gitattributes": "fail",
    "require_gitignore": "fail",
    "require_markdownlint": "warn",
    "require_yamllint": "warn",
    "require_ghas_code_scanning": "fail",
    "require_ghas_secret_scanning": "fail",
    "require_dependabot_alerts": "fail",
    "require_scorecard": "warn",
    "require_repo_description": "fail",
    "require_repo_topics": "fail",
    "require_repo_homepage": "warn",
}


class ConfigError(Exception):
    """Raised when a config document is malformed or holds a bad value."""


class Option(NamedTuple):
    key: str        # config key / action input name
    env: str        # environment variable consumed by run.sh
    kind: str       # policy | source | bool | int | path | text | list
    default: Any    # tier-0 runtime default


def _policy(key: str, env: str) -> Option:
    return Option(key, env, "policy", "skip")


def _source(key: str, env: str) -> Option:
    return Option(key, env, "source", "")


# Every configurable option, in job-summary order. This table is the
# single source of truth shared by the CLI, the composite action, and
# the tests.
OPTIONS: tuple[Option, ...] = (
    Option("action_yml_path", "ACTION_YML_PATH", "path", "action.yml"),
    Option("fail_on_warning", "FAIL_ON_WARN", "bool", False),
    Option("skip_checks", "SKIP_CHECKS", "list", ()),
    Option("workflow_dir", "WORKFLOW_DIR", "path", ".github/workflows"),

    Option("check_org_health", "CHECK_ORG_HEALTH", "bool", True),
    Option("org_health_repo", "ORG_HEALTH_REPO_IN", "text", ""),
    Option("community_health_source", "CH_SOURCE_DEFAULT", "source", "either"),

    _policy("require_security", "REQ_SECURITY"),
    _policy("require_code_of_conduct", "REQ_CODE_OF_CONDUCT"),
    _policy("require_contributing", "REQ_CONTRIBUTING"),
    _policy("require_support", "REQ_SUPPORT"),
    _policy("require_issue_templates", "REQ_ISSUE_TEMPLATES"),
    _policy("require_pr_template", "REQ_PR_TEMPLATE"),
    _policy("require_funding", "REQ_FUNDING"),

    _source("security_source", "SRC_SECURITY"),
    _source("code_of_conduct_source", "SRC_CODE_OF_CONDUCT"),
    _source("contributing_source", "SRC_CONTRIBUTING"),
    _source("support_source", "SRC_SUPPORT"),
    _source("issue_templates_source", "SRC_ISSUE_TEMPLATES"),
    _source("pr_template_source", "SRC_PR_TEMPLATE"),
    _source("funding_source", "SRC_FUNDING"),

    _policy("require_dependabot", "REQ_DEPENDABOT"),
    _policy("require_codeql", "REQ_CODEQL"),
    _policy("require_editorconfig", "REQ_EDITORCONFIG"),
    _policy("require_gitattributes", "REQ_GITATTRIBUTES"),
    _policy("require_gitignore", "REQ_GITIGNORE"),
    _policy("require_markdownlint", "REQ_MARKDOWNLINT"),
    _policy("require_yamllint", "REQ_YAMLLINT"),

    _policy("require_ghas_code_scanning", "REQ_GHAS_CODE_SCANNING"),
    _policy("require_ghas_secret_scanning", "REQ_GHAS_SECRET_SCANNING"),
    _policy("require_dependabot_alerts", "REQ_DEPENDABOT_ALERTS"),
    _policy("require_security_devops", "REQ_SECURITY_DEVOPS"),
    _policy("require_scorecard", "REQ_SCORECARD"),

    _policy("require_repo_description", "REQ_REPO_DESCRIPTION"),
    _policy("require_repo_homepage", "REQ_REPO_HOMEPAGE"),
    _policy("require_repo_topics", "REQ_REPO_TOPICS"),
    Option("repo_description_max_length", "REPO_DESC_MAX_LEN", "int", 350),
    Option("repo_description_min_length", "REPO_DESC_MIN_LEN", "int", 30),

    Option("auto_generate_missing", "AUTO_GENERATE_MISSING", "bool", False),

    Option("enable_ai_findings_summary", "ENABLE_AI_FINDINGS_SUMMARY", "bool", False),
    Option("ai_findings_summary_provider", "AI_PROVIDER", "provider", "auto"),
    Option("ai_model", "AI_MODEL", "text", ""),
    Option("local_heuristic_fallback", "AI_LOCAL_FALLBACK", "bool", True),

    Option("profile", "MK_PROFILE", "profile", "baseline"),
    Option("enable_security_scan", "ENABLE_SECURITY_SCAN", "bool", True),
    Option("defer_to_code_scanning_kit", "DEFER_TO_CODE_SCANNING_KIT", "tristate", "auto"),
)

OPTIONS_BY_KEY: dict[str, Option] = {o.key: o for o in OPTIONS}

# Meta keys that steer the cascade rather than configure a check.
META_KEYS = frozenset({
    "use_marketplace_config",
    "use_marketplace_skip_checks",
})


# Options where an explicitly-supplied empty string is meaningful rather
# than "unset": `workflow_dir: ''` means "skip workflow linting". These
# use the `auto` sentinel to mean "fall through to config".
ALLOW_EMPTY_OVERRIDE = frozenset({"workflow_dir"})


class Resolved(NamedTuple):
    values: dict[str, Any]
    tiers: list[str]           # human-readable description of each applied tier
    use_marketplace: bool
    suppressed: dict[str, str] = {}  # option -> why it was forced to `skip`


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path}: invalid JSON: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read: {exc}") from exc
    if not isinstance(doc, dict):
        raise ConfigError(f"{path}: top-level value must be a JSON object")
    return doc


def extract_section(doc: dict, *, origin: str) -> dict:
    """Return the ``marketplace_kit`` section, or the doc itself if absent."""
    if SECTION in doc:
        section = doc[SECTION]
        if not isinstance(section, dict):
            raise ConfigError(f"{origin}: `{SECTION}` must be a JSON object")
        return section
    # A flat document is only treated as the section when it holds no
    # other known top-level section (e.g. `marketplace`, `action_test`).
    return {k: v for k, v in doc.items() if k in OPTIONS_BY_KEY or k in META_KEYS}


def load_marketplace_config() -> dict:
    """Tier 1: the recommended defaults shipped with the kit."""
    path = Path(__file__).resolve().parent / "data" / MARKETPLACE_CONFIG_FILE
    return extract_section(_read_json(path), origin=str(path))


def discover_repo_config(root: Path, *, path: str | None = None) -> Path | None:
    if path:
        candidate = root / path
        if not candidate.is_file():
            raise ConfigError(f"config_path {path!r} was not found")
        return candidate
    for candidate_name in REPO_CONFIG_CANDIDATES:
        candidate = root / candidate_name
        if candidate.is_file():
            return candidate
    return None


def discover_global_config(root: Path, *, path: str | None = None) -> Path | None:
    candidate = root / (path or GLOBAL_CONFIG_PATH)
    return candidate if candidate.is_file() else None


# ---------------------------------------------------------------------------
# Validation / coercion
# ---------------------------------------------------------------------------

def _coerce_bool(key: str, value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ConfigError(f"`{key}` must be a boolean (got: {value!r})")


def _coerce_int(key: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError(f"`{key}` must be a non-negative integer (got: {value!r})")
    try:
        number = int(value)
    except ValueError as exc:
        raise ConfigError(
            f"`{key}` must be a non-negative integer (got: {value!r})"
        ) from exc
    if number < 0:
        raise ConfigError(f"`{key}` must be >= 0 (got: {number})")
    return number


def _coerce_enum(key: str, value: Any, allowed: Iterable[str], *,
                 allow_empty: bool) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"`{key}` must be a string (got: {value!r})")
    text = value.strip()
    if not text and allow_empty:
        return ""
    if text not in allowed:
        raise ConfigError(
            f"`{key}` must be one of {', '.join(allowed)} (got: {value!r})"
        )
    return text


def _coerce_path(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"`{key}` must be a string (got: {value!r})")
    text = value.strip()
    if not text:
        return ""
    if text.startswith("/") or ".." in Path(text).parts:
        raise ConfigError(
            f"`{key}` must be a repo-relative path without `..` (got: {value!r})"
        )
    return text


def _coerce_text(key: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ConfigError(f"`{key}` must be a string (got: {value!r})")
    if any(ch in value for ch in "\r\n"):
        raise ConfigError(f"`{key}` must be a single line")
    return value.strip()


def _coerce_list(key: str, value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        items = [p.strip() for p in value.replace("\n", ",").split(",")]
    elif isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if not isinstance(item, str):
                raise ConfigError(f"`{key}` entries must be strings (got: {item!r})")
            items.append(item.strip())
    else:
        raise ConfigError(f"`{key}` must be an array or comma-separated string")
    return tuple(dict.fromkeys(i for i in items if i))


_COERCERS: dict[str, Callable[[str, Any], Any]] = {
    "bool": _coerce_bool,
    "int": _coerce_int,
    "path": _coerce_path,
    "text": _coerce_text,
    "list": _coerce_list,
    "policy": lambda k, v: _coerce_enum(k, v, POLICY_VALUES, allow_empty=False),
    "source": lambda k, v: _coerce_enum(k, v, SOURCE_VALUES, allow_empty=True),
    "provider": lambda k, v: _coerce_enum(k, v, PROVIDER_VALUES, allow_empty=False),
    "profile": lambda k, v: _coerce_enum(k, v, PROFILE_VALUES, allow_empty=False),
    "tristate": lambda k, v: _coerce_enum(
        k, "true" if v is True else "false" if v is False else v,
        ("auto", "true", "false"), allow_empty=False),
}


def coerce(key: str, value: Any) -> Any:
    """Validate and normalise ``value`` for the option named ``key``."""
    option = OPTIONS_BY_KEY.get(key)
    if option is None:
        raise ConfigError(f"unknown option `{key}`")
    return _COERCERS[option.kind](key, value)


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def merge_tier(values: dict[str, Any], section: dict, *, origin: str) -> None:
    """Apply one config tier onto ``values`` in place.

    Unknown keys are ignored so newer kit versions can extend the schema
    without breaking older callers. ``skip_checks`` appends by default;
    set ``use_marketplace_skip_checks: false`` in the tier to replace.
    """
    append_skips = section.get("use_marketplace_skip_checks", True)
    if not isinstance(append_skips, bool):
        raise ConfigError(f"{origin}: `use_marketplace_skip_checks` must be a boolean")

    for key, raw in section.items():
        # `$`-prefixed keys are editor conventions such as `$schema`.
        if key in META_KEYS or key.startswith("$"):
            continue
        if key not in OPTIONS_BY_KEY:
            continue
        try:
            value = coerce(key, raw)
        except ConfigError as exc:
            raise ConfigError(f"{origin}: {exc}") from exc
        if key == "skip_checks" and append_skips:
            value = tuple(dict.fromkeys((*values.get("skip_checks", ()), *value)))
        values[key] = value


def _marketplace_enabled(sections: Iterable[tuple[str, dict]]) -> bool:
    """Last tier that sets ``use_marketplace_config`` wins."""
    enabled = True
    for origin, section in sections:
        if "use_marketplace_config" in section:
            flag = section["use_marketplace_config"]
            if not isinstance(flag, bool):
                raise ConfigError(
                    f"{origin}: `use_marketplace_config` must be a boolean"
                )
            enabled = flag
    return enabled


def resolve(
    root: Path | str = ".",
    *,
    overrides: dict[str, Any] | None = None,
    global_config_path: str | None = None,
    use_global_config: str = "auto",
    repo_config_path: str | None = None,
    use_marketplace_config: str = "auto",
) -> Resolved:
    """Merge every tier and return the effective configuration.

    ``use_global_config`` is ``auto`` (load when present), ``true``
    (require the file) or ``false`` (never load it). The same tri-state
    applies to ``use_marketplace_config``, where ``auto`` defers to the
    config files (which themselves default to enabled).
    """
    root = Path(root)
    for name, tri in (("use_global_config", use_global_config),
                      ("use_marketplace_config", use_marketplace_config)):
        if tri not in ("auto", "true", "false"):
            raise ConfigError(f"`{name}` must be auto, true, or false (got: {tri!r})")

    values: dict[str, Any] = {
        o.key: (tuple(o.default) if o.kind == "list" else o.default)
        for o in OPTIONS
    }
    tiers = ["runtime defaults"]

    sections: list[tuple[str, dict]] = []

    global_path = None
    if use_global_config != "false":
        global_path = discover_global_config(root, path=global_config_path)
        if global_path is None and use_global_config == "true":
            raise ConfigError(
                "use_global_config is 'true' but "
                f"{global_config_path or GLOBAL_CONFIG_PATH} was not found"
            )
    if global_path is not None:
        sections.append((
            str(global_path),
            extract_section(_read_json(global_path), origin=str(global_path)),
        ))

    repo_path = discover_repo_config(root, path=repo_config_path)
    if repo_path is not None:
        sections.append((
            str(repo_path),
            extract_section(_read_json(repo_path), origin=str(repo_path)),
        ))

    if use_marketplace_config == "auto":
        use_marketplace = _marketplace_enabled(sections)
    else:
        use_marketplace = use_marketplace_config == "true"
    if use_marketplace:
        merge_tier(values, load_marketplace_config(),
                   origin="marketplace config")
        tiers.append("marketplace config (built-in)")
    else:
        tiers.append("marketplace config (disabled)")

    # The profile overlay sits between the marketplace tier and the
    # user tiers so a global or repo config can still relax a single
    # rule without abandoning the whole profile.
    profile = _resolve_scalar("profile", sections, overrides,
                              default=values["profile"])
    if profile == "strict":
        merge_tier(values, dict(STRICT_PROFILE), origin="strict profile")
        tiers.append("strict profile")
    values["profile"] = profile

    for origin, section in sections:
        merge_tier(values, section, origin=origin)
        tiers.append(origin)

    if overrides:
        applied = {}
        for key, raw in overrides.items():
            if key not in OPTIONS_BY_KEY or raw is None:
                continue
            if raw == "" and key not in ALLOW_EMPTY_OVERRIDE:
                continue
            applied[key] = coerce(key, raw)
        if applied:
            values.update(applied)
            tiers.append(f"workflow inputs ({', '.join(sorted(applied))})")

    suppressed = _apply_suppressions(values, root)
    return Resolved(values=values, tiers=tiers, use_marketplace=use_marketplace,
                    suppressed=suppressed)


def _resolve_scalar(
    key: str,
    sections: Iterable[tuple[str, dict]],
    overrides: dict[str, Any] | None,
    *,
    default: Any,
) -> Any:
    """Peek at one option ahead of the main merge. Last tier wins."""
    value = default
    for origin, section in sections:
        if key in section:
            try:
                value = coerce(key, section[key])
            except ConfigError as exc:
                raise ConfigError(f"{origin}: {exc}") from exc
    raw = (overrides or {}).get(key)
    if raw not in (None, ""):
        value = coerce(key, raw)
    return value


def uses_code_scanning_kit(root: Path) -> bool:
    """True when any workflow in ``root`` calls the code-scanning kit."""
    workflows = root / ".github" / "workflows"
    if not workflows.is_dir():
        return False
    for path in sorted(workflows.glob("*.y*ml")):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if CODE_SCANNING_KIT in text:
            return True
    return False


def _apply_suppressions(values: dict[str, Any], root: Path) -> dict[str, str]:
    """Force rules to `skip` that another tool owns or that were opted out.

    Returns ``{option: reason}`` so the job summary can explain why a
    rule did not run instead of silently dropping it.
    """
    suppressed: dict[str, str] = {}

    if not values["enable_security_scan"]:
        for key in SECURITY_SCAN_RULES:
            if values[key] != "skip":
                suppressed[key] = "enable_security_scan is false"

    defer = values["defer_to_code_scanning_kit"]
    if defer == "auto":
        defer = "true" if uses_code_scanning_kit(root) else "false"
    if defer == "true":
        for key, their_rule in CODE_SCANNING_KIT_RULES.items():
            if values[key] != "skip":
                suppressed[key] = (
                    f"owned by {CODE_SCANNING_KIT} ({their_rule})"
                )

    for key in suppressed:
        values[key] = "skip"
    return suppressed


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render(key: str, value: Any) -> str:
    """Render a resolved value as the string form run.sh expects."""
    option = OPTIONS_BY_KEY[key]
    if option.kind == "bool":
        return "true" if value else "false"
    if option.kind == "list":
        return ",".join(value)
    return str(value)


def as_env(values: dict[str, Any]) -> dict[str, str]:
    return {o.env: render(o.key, values[o.key]) for o in OPTIONS}


# ---------------------------------------------------------------------------
# Composite-action entry point: `python3 -m marketplace_kit.config`
#
# Reads workflow overrides from `MK_IN_<KEY>` env vars, resolves the
# cascade, and appends the run.sh-facing variables to `$GITHUB_ENV`.
# ---------------------------------------------------------------------------

_ENV_PREFIX = "MK_IN_"


def _overrides_from_env(environ: dict[str, str]) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for option in OPTIONS:
        raw = environ.get(_ENV_PREFIX + option.key.upper())
        if raw is None:
            continue
        raw = raw.strip()
        # `auto` is the sentinel for "fall through to the config cascade".
        if raw == "auto":
            continue
        if raw or option.key in ALLOW_EMPTY_OVERRIDE:
            overrides[option.key] = raw
    return overrides


def _write_github_env(env: dict[str, str], target: Path) -> None:
    with target.open("a", encoding="utf-8") as handle:
        for name, value in env.items():
            handle.write(f"{name}={value}\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    root = Path(os.environ.get("MK_CONFIG_ROOT", "."))
    try:
        resolved = resolve(
            root,
            overrides=_overrides_from_env(dict(os.environ)),
            global_config_path=os.environ.get("MK_GLOBAL_CONFIG_PATH") or None,
            use_global_config=os.environ.get("MK_USE_GLOBAL_CONFIG") or "auto",
            repo_config_path=os.environ.get("MK_CONFIG_PATH") or None,
            use_marketplace_config=os.environ.get("MK_USE_MARKETPLACE_CONFIG") or "auto",
        )
    except ConfigError as exc:
        sys.stderr.write(f"::error::marketplace-kit config: {exc}\n")
        return 2

    env = as_env(resolved.values)
    print("Resolved marketplace-kit configuration")
    for tier in resolved.tiers:
        print(f"  tier: {tier}")
    for key, reason in sorted(resolved.suppressed.items()):
        print(f"  suppressed: {key} -> skip ({reason})")
        print(f"::notice::marketplace-kit: {key} skipped — {reason}")
    for option in OPTIONS:
        print(f"  {option.key:<28} {env[option.env]}")

    if "--dry-run" not in argv:
        github_env = os.environ.get("GITHUB_ENV")
        if not github_env:
            sys.stderr.write("::error::GITHUB_ENV is not set\n")
            return 2
        _write_github_env(env, Path(github_env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
