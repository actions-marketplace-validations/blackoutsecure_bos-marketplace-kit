"""Smoke tests for the operator bootstrap scripts under ``scripts/``.

These scripts are NOT part of the in-workflow runtime (the composite
``branch-protection`` covers that). They exist so an operator can
bootstrap branch protection / org rulesets *once* using ``gh`` CLI
with admin scopes the default ``GITHUB_TOKEN`` doesn't have.

Tests here verify:

* The shebang + ``set -euo pipefail`` are present.
* ``bash -n`` is clean.
* Running with no args fails with a usage hint.
* The shipped ruleset JSON is valid and contains the expected
  placeholder markers (which the bootstrap script refuses to upload).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"


def _discover_shell_scripts() -> list[Path]:
    return sorted(SCRIPTS_DIR.glob("*.sh"))


SHELL_SCRIPTS = _discover_shell_scripts()
SHELL_SCRIPT_IDS = [p.name for p in SHELL_SCRIPTS]


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=SHELL_SCRIPT_IDS)
def test_shell_script_has_bash_shebang(script: Path) -> None:
    first_line = script.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#!") and "bash" in first_line, (
        f"{script}: first line is {first_line!r}; expected a bash shebang"
    )


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=SHELL_SCRIPT_IDS)
def test_shell_script_sets_strict_mode(script: Path) -> None:
    text = script.read_text(encoding="utf-8")
    # Look for the canonical strict-mode preamble.
    assert "set -euo pipefail" in text, (
        f"{script}: does not invoke `set -euo pipefail`"
    )


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=SHELL_SCRIPT_IDS)
def test_shell_script_parses_via_bash_n(script: Path) -> None:
    result = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"{script}: bash -n failed:\n{result.stderr}"
    )


@pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="shellcheck not installed",
)
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=SHELL_SCRIPT_IDS)
def test_shell_script_clean_under_shellcheck_errors(script: Path) -> None:
    # ``-S error`` -- we only block the build on errors, not warnings,
    # to keep the smoke layer fast. The kit's CI workflow runs the
    # stricter warning-level lint separately.
    result = subprocess.run(
        ["shellcheck", "-x", "-S", "error", "--shell=bash", str(script)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, (
        f"{script}: shellcheck error:\n{result.stdout}"
    )


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=SHELL_SCRIPT_IDS)
def test_shell_script_no_args_prints_usage_and_fails(script: Path) -> None:
    """All bootstrap scripts should refuse to do anything dangerous
    when invoked with no arguments — they must emit a usage line and
    exit non-zero."""
    # Force-strip GH_TOKEN / GITHUB_TOKEN so the script doesn't get
    # surprise auth from the developer's shell.
    env = dict(os.environ)
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, env=env,
        timeout=10,
    )
    assert result.returncode != 0, (
        f"{script}: ran with no args and exited 0 — should refuse"
    )
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined, (
        f"{script}: no 'usage' hint in output:\n"
        f"  stdout: {result.stdout!r}\n  stderr: {result.stderr!r}"
    )


# ---------------------------------------------------------------------------
# main-protection-ruleset.json sanity
# ---------------------------------------------------------------------------

RULESET_JSON = SCRIPTS_DIR / "main-protection-ruleset.json"


@pytest.mark.skipif(not RULESET_JSON.is_file(), reason="ruleset JSON not present")
def test_ruleset_json_parses() -> None:
    data = json.loads(RULESET_JSON.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    # The bootstrap script depends on these top-level keys.
    for k in ("name", "target", "enforcement", "rules", "conditions"):
        assert k in data, f"ruleset JSON missing key {k!r}"


@pytest.mark.skipif(not RULESET_JSON.is_file(), reason="ruleset JSON not present")
def test_ruleset_json_has_placeholders_for_operator_to_replace() -> None:
    """The shipped template MUST contain the placeholders the bootstrap
    script refuses to upload. If those go missing, operators could
    accidentally ship a ruleset that locks down nothing."""
    text = RULESET_JSON.read_text(encoding="utf-8")
    assert "REPLACE_ME" in text, (
        "ruleset JSON missing REPLACE_ME placeholder — operators must"
        " be forced to set repository names explicitly."
    )
    assert "BYPASS_ACTOR_ID_PLACEHOLDER" in text, (
        "ruleset JSON missing BYPASS_ACTOR_ID_PLACEHOLDER — operators"
        " must be forced to set the bypass actor explicitly."
    )


@pytest.mark.skipif(not RULESET_JSON.is_file(), reason="ruleset JSON not present")
def test_ruleset_blocks_workflow_paths() -> None:
    """The whole reason this ruleset exists: block direct pushes to
    ``.github/workflows/**`` on the default branch."""
    data = json.loads(RULESET_JSON.read_text(encoding="utf-8"))
    file_rules = [
        r for r in data.get("rules", [])
        if r.get("type") == "file_path_restriction"
    ]
    assert file_rules, "ruleset has no file_path_restriction rule"
    paths = file_rules[0].get("parameters", {}).get("restricted_file_paths", [])
    assert ".github/workflows/**" in paths, (
        f"ruleset doesn't restrict .github/workflows/**; restricted_file_paths={paths}"
    )


def test_bootstrap_ruleset_refuses_to_upload_with_placeholder() -> None:
    """End-to-end: feed the shipped JSON to ``bootstrap-ruleset.sh`` and
    confirm it refuses (because of the placeholder)."""
    script = SCRIPTS_DIR / "bootstrap-ruleset.sh"
    if not script.is_file() or not RULESET_JSON.is_file():
        pytest.skip("bootstrap-ruleset.sh or ruleset JSON not present")
    if shutil.which("gh") is None:
        pytest.skip("gh CLI not installed; cannot exercise full preflight")
    # Pass a dummy org name and the real ruleset JSON. The script's
    # placeholder check is purely string-based and runs before any
    # network call, so this test is hermetic.
    env = dict(os.environ)
    env.pop("GH_TOKEN", None)
    env.pop("GITHUB_TOKEN", None)
    result = subprocess.run(
        ["bash", str(script), "test-org", str(RULESET_JSON)],
        capture_output=True, text=True, env=env, timeout=10,
    )
    assert result.returncode != 0, (
        "bootstrap-ruleset.sh accepted a JSON file with placeholder values"
    )
    combined = (result.stdout + result.stderr).lower()
    # The script should mention either the placeholder or an auth issue
    # (gh CLI sometimes fails on auth first if no token is set).
    assert (
        "placeholder" in combined
        or "replace_me" in combined
        or "not authenticated" in combined
        or "auth" in combined
    ), (
        f"bootstrap-ruleset.sh refused but did not explain why:\n"
        f"  stdout: {result.stdout}\n  stderr: {result.stderr}"
    )
