"""Branch-protection payload + drift-detection helpers.

Pure-Python helpers extracted from the `branch-protection` composite
action so the same logic can be unit-tested, reused by the
`scripts/bootstrap-branch-protection.sh` operator script, and (later)
exposed via a CLI subcommand.

Two entrypoints:

  * Library  — import and call `build_payload(...)`, `compare(...)`,
               `parse_restrict_pushes(...)` directly.
  * CLI      — `python -m marketplace_kit._bp build|compare|parse-restrict`
               for shell-based callers that want a JSON-in / JSON-out
               contract without touching Python imports.

Both surfaces are kept tiny on purpose: this module owns *only* the
JSON shapes that GitHub's REST API expects on
`PUT /repos/{owner}/{repo}/branches/{branch}/protection` and its
`GET` response shape.

This module has NO third-party dependencies and works on Python 3.9+
(the floor for GitHub-hosted runners is older than that).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

def _coerce_bool(raw: str | bool | None, default: bool = False) -> bool:
    """Convert the YAML-string flavour of booleans the composite passes
    via env (``'true'`` / ``'false'`` / ``''``) into a real bool."""
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    s = str(raw).strip().lower()
    if s == "":
        return default
    return s == "true"


def _coerce_int(raw: str | int | None, default: int | None = None) -> int | None:
    if isinstance(raw, int):
        return raw
    if raw is None:
        return default
    s = str(raw).strip()
    if not s:
        return default
    try:
        return int(s)
    except ValueError:
        return default


def parse_status_checks(raw: str) -> list[dict[str, Any]]:
    """Parse a CSV/newline-separated list of status-check contexts into
    the shape the protection API expects (``[{context, app_id}]``).

    Empty / whitespace-only input → empty list.
    Order is preserved; duplicates are removed (first-wins)."""
    items: list[str] = []
    for chunk in (raw or "").replace("\n", ",").split(","):
        s = chunk.strip()
        if s and s not in items:
            items.append(s)
    return [{"context": c, "app_id": None} for c in items]


def parse_restrict_pushes(spec: str) -> dict[str, list[str]] | None:
    """Parse the kit's compact `bp_restrict_pushes` mini-DSL.

    Format: comma-separated entries. Prefixes:

        team:<slug>   — team push permission
        app:<slug>    — GitHub App push permission
        <login>       — user push permission (no prefix)

    Returns ``None`` for an all-whitespace / empty spec, which is what
    the REST API needs to disable restrictions (the API rejects an
    empty ``{}`` here)."""
    if spec is None:
        return None
    items = [x.strip() for x in str(spec).split(",")]
    items = [x for x in items if x]
    if not items:
        return None
    users: list[str] = []
    teams: list[str] = []
    apps: list[str] = []
    for it in items:
        if it.startswith("team:"):
            teams.append(it[5:])
        elif it.startswith("app:"):
            apps.append(it[4:])
        else:
            users.append(it)
    return {"users": users, "teams": teams, "apps": apps}


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------

def build_payload(env: dict[str, str] | None = None) -> dict[str, Any]:
    """Construct the JSON payload for ``PUT branches/{branch}/protection``
    from a dict of environment variables (kept dict-shaped so the
    composite can pass ``os.environ`` and tests can pass a literal).

    Recognised keys (all strings in YAML-truthy form):

        BP_REQUIRE_PR
        BP_REQUIRED_APPROVALS
        BP_DISMISS_STALE
        BP_REQUIRE_CODEOWNER
        BP_REQUIRE_LAST_PUSH_APPROVAL
        BP_STATUS_CHECKS                (CSV/newline)
        BP_STATUS_CHECKS_STRICT
        BP_REQUIRE_SIGNED
        BP_REQUIRE_LINEAR
        BP_REQUIRE_CONVO
        BP_NO_FORCE_PUSH                (semantic invert)
        BP_NO_DELETION                  (semantic invert)
        BP_LOCK_BRANCH
        BP_INCLUDE_ADMINS
        BP_RESTRICT_PUSHES              (CSV with prefixes)

    Returns the dict ready to be JSON-encoded.
    """
    e = dict(env) if env is not None else dict(os.environ)

    status_checks = parse_status_checks(e.get("BP_STATUS_CHECKS", ""))
    strict = _coerce_bool(e.get("BP_STATUS_CHECKS_STRICT"), True)
    require_pr = _coerce_bool(e.get("BP_REQUIRE_PR"), True)
    restrictions = parse_restrict_pushes(e.get("BP_RESTRICT_PUSHES", ""))

    payload: dict[str, Any] = {
        # API requires this key (even when null).
        "required_status_checks":
            {"strict": strict, "checks": status_checks}
            if (status_checks or strict) else None,
        "enforce_admins": _coerce_bool(e.get("BP_INCLUDE_ADMINS"), False),
        "required_pull_request_reviews":
            {
                "dismiss_stale_reviews":
                    _coerce_bool(e.get("BP_DISMISS_STALE"), True),
                "require_code_owner_reviews":
                    _coerce_bool(e.get("BP_REQUIRE_CODEOWNER"), True),
                "required_approving_review_count":
                    _coerce_int(e.get("BP_REQUIRED_APPROVALS"), 1),
                "require_last_push_approval":
                    _coerce_bool(e.get("BP_REQUIRE_LAST_PUSH_APPROVAL"), False),
            } if require_pr else None,
        "restrictions": restrictions,
        "required_linear_history": _coerce_bool(e.get("BP_REQUIRE_LINEAR"), True),
        # GitHub stores "allow_force_pushes" — we expose the inverse for
        # clarity (default "no force-pushes").
        "allow_force_pushes":
            not _coerce_bool(e.get("BP_NO_FORCE_PUSH"), True),
        "allow_deletions":
            not _coerce_bool(e.get("BP_NO_DELETION"), True),
        "required_conversation_resolution":
            _coerce_bool(e.get("BP_REQUIRE_CONVO"), True),
        "lock_branch": _coerce_bool(e.get("BP_LOCK_BRANCH"), False),
        "required_signatures": _coerce_bool(e.get("BP_REQUIRE_SIGNED"), False),
    }
    return payload


# ---------------------------------------------------------------------------
# Drift detector
# ---------------------------------------------------------------------------

def _nested_enabled(obj: Any) -> Any:
    """Many GET-branch-protection fields come back as {'enabled': bool}.
    Some come back as a bare bool. Normalise both shapes."""
    if isinstance(obj, dict) and "enabled" in obj:
        return bool(obj["enabled"])
    if isinstance(obj, bool):
        return obj
    return obj  # absent / other shape; caller decides


def compare(desired: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return a list of human-readable drift findings between the
    ``desired`` payload (as built by :func:`build_payload`) and the
    raw response from ``GET branches/{branch}/protection`` (which can
    be ``{}`` for an unprotected branch).

    Each finding is a single line of the form
    ``<dotted.key>: want=<X> got=<Y>``. An empty return value means
    "fully compliant"."""
    findings: list[str] = []

    # --- pull-request reviews ---------------------------------------------
    pr_des = desired.get("required_pull_request_reviews")
    pr_cur = current.get("required_pull_request_reviews")
    if pr_des is not None:
        for k in (
            "dismiss_stale_reviews",
            "require_code_owner_reviews",
            "required_approving_review_count",
            "require_last_push_approval",
        ):
            want = pr_des.get(k)
            got = (pr_cur or {}).get(k) if isinstance(pr_cur, dict) else None
            if want is not None and want != got:
                findings.append(
                    f"required_pull_request_reviews.{k}: want={want} got={got}"
                )
    elif pr_cur:
        findings.append(
            "required_pull_request_reviews: want=disabled got=enabled"
        )

    # --- status checks ----------------------------------------------------
    sc_des = desired.get("required_status_checks")
    if sc_des is not None:
        sc_cur = current.get("required_status_checks") or {}
        want_strict = sc_des.get("strict")
        got_strict = sc_cur.get("strict") if isinstance(sc_cur, dict) else None
        if want_strict is not None and want_strict != got_strict:
            findings.append(
                f"required_status_checks.strict: want={want_strict} got={got_strict}"
            )
        want_checks = sorted(c["context"] for c in sc_des.get("checks", []))
        got_raw = sc_cur.get("checks") if isinstance(sc_cur, dict) else []
        got_checks = sorted(
            [c["context"] if isinstance(c, dict) else c for c in (got_raw or [])]
        )
        if want_checks and want_checks != got_checks:
            findings.append(
                f"required_status_checks.checks: want={want_checks} got={got_checks}"
            )

    # --- top-level booleans (mixed shapes) --------------------------------
    bool_keys = (
        "required_linear_history",
        "lock_branch",
        "allow_force_pushes",
        "allow_deletions",
        "required_conversation_resolution",
        "required_signatures",
        "enforce_admins",
    )
    for k in bool_keys:
        if k not in desired:
            continue
        want = bool(desired[k])
        got_raw = current.get(k)
        got = _nested_enabled(got_raw)
        # Treat missing as False (GitHub omits keys that are off).
        if got is None or isinstance(got, dict):
            got = False
        if bool(got) != want:
            findings.append(f"{k}: want={want} got={got}")
    return findings


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
# Kept small: each sub-action reads env (or a file/stdin) and emits
# JSON to stdout. Designed for `python -m marketplace_kit._bp <cmd>`
# invocations from bash.

def _cmd_build(args: argparse.Namespace) -> int:
    payload = build_payload()
    json.dump(payload, sys.stdout, indent=2 if args.pretty else None)
    sys.stdout.write("\n")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    with open(args.desired, encoding="utf-8") as f:
        des = json.load(f)
    with open(args.current, encoding="utf-8") as f:
        cur = json.load(f)
    findings = compare(des, cur)
    if not findings:
        print("__COMPLIANT__")
    else:
        for line in findings:
            print(line)
    return 0


def _cmd_parse_restrict(args: argparse.Namespace) -> int:
    spec = args.spec if args.spec is not None else os.environ.get("BP_RESTRICT_PUSHES", "")
    out = parse_restrict_pushes(spec)
    json.dump(out, sys.stdout)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m marketplace_kit._bp",
        description=(
            "Branch-protection payload + drift helpers. Reads BP_* "
            "env vars; intended for shell callers."
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Emit desired-state JSON from BP_* env.")
    p_build.add_argument("--pretty", action="store_true", help="Indent the JSON.")
    p_build.set_defaults(func=_cmd_build)

    p_cmp = sub.add_parser("compare", help="Diff a desired JSON file against a current JSON file.")
    p_cmp.add_argument("--desired", required=True)
    p_cmp.add_argument("--current", required=True)
    p_cmp.set_defaults(func=_cmd_compare)

    p_rp = sub.add_parser("parse-restrict", help="Parse a bp_restrict_pushes spec to JSON.")
    p_rp.add_argument("--spec", default=None, help="Spec string (default: $BP_RESTRICT_PUSHES).")
    p_rp.set_defaults(func=_cmd_parse_restrict)

    ns = p.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
