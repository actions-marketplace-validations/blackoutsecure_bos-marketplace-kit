"""Structural + shell sanity tests for every composite action shipped
by the kit.

These tests enumerate every `action.yml` under ``.github/actions/``
plus the root composite, and assert:

* The YAML parses.
* It declares ``runs.using: composite``.
* Every ``inputs.<name>`` is a mapping with a ``description``.
* Every ``outputs.<name>`` is a mapping with a ``description``.
* Every ``run: |`` body whose ``shell`` is bash passes ``bash -n``.
* Every such body passes ``shellcheck -S error`` when shellcheck is
  installed (skipped otherwise so CI without shellcheck still passes).

Together with `test_workflows_structure.py` this is the kit's smoke
test for "did I break a composite by accident".
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSITES_DIR = REPO_ROOT / ".github" / "actions"
ROOT_ACTION = REPO_ROOT / "action.yml"


def _discover() -> list[Path]:
    """Every action.yml in the repo (composites + root)."""
    paths: list[Path] = []
    if ROOT_ACTION.is_file():
        paths.append(ROOT_ACTION)
    for f in sorted(COMPOSITES_DIR.glob("*/action.yml")):
        paths.append(f)
    return paths


COMPOSITE_FILES = _discover()


def _id(p: Path) -> str:
    """Pytest test ID = parent dir name (or repo-root for the root action)."""
    if p == ROOT_ACTION:
        return "<root>"
    return p.parent.name


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_action_yaml_parses(action_path: Path) -> None:
    yaml.safe_load(action_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_action_has_required_top_level_keys(action_path: Path) -> None:
    d = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    for k in ("name", "description", "runs"):
        assert k in d, f"{action_path}: missing top-level key {k!r}"


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_action_runs_is_composite(action_path: Path) -> None:
    d = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    assert d["runs"].get("using") == "composite"


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_every_input_has_description(action_path: Path) -> None:
    d = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    inputs = d.get("inputs") or {}
    for name, spec in inputs.items():
        assert isinstance(spec, dict), f"{action_path}: input {name!r} is not a mapping"
        desc = spec.get("description")
        assert desc and str(desc).strip(), (
            f"{action_path}: input {name!r} has no description"
        )


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_every_output_has_description(action_path: Path) -> None:
    d = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    outputs = d.get("outputs") or {}
    for name, spec in outputs.items():
        assert isinstance(spec, dict), f"{action_path}: output {name!r} is not a mapping"
        desc = spec.get("description")
        assert desc and str(desc).strip(), (
            f"{action_path}: output {name!r} has no description"
        )


def _bash_steps(action_path: Path) -> list[tuple[int, str]]:
    """Return [(index, run-body)] for every bash step in this action."""
    d = yaml.safe_load(action_path.read_text(encoding="utf-8"))
    out: list[tuple[int, str]] = []
    for i, step in enumerate(d["runs"].get("steps", []) or []):
        if not isinstance(step, dict):
            continue
        if step.get("shell") != "bash":
            continue
        body = step.get("run")
        if isinstance(body, str) and body.strip():
            out.append((i, body))
    return out


@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_bash_steps_parse_via_bash_n(action_path: Path) -> None:
    """Every bash step must compile under ``bash -n``."""
    steps = _bash_steps(action_path)
    if not steps:
        pytest.skip(f"{action_path}: no bash steps")
    for idx, body in steps:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{idx}.sh", delete=False
        ) as tmp:
            tmp.write("#!/usr/bin/env bash\nset -euo pipefail\n")
            tmp.write(body)
            tmp_path = tmp.name
        result = subprocess.run(
            ["bash", "-n", tmp_path], capture_output=True, text=True
        )
        Path(tmp_path).unlink(missing_ok=True)
        assert result.returncode == 0, (
            f"{action_path}#step{idx}: bash -n failed:\n{result.stderr}"
        )


@pytest.mark.skipif(
    shutil.which("shellcheck") is None,
    reason="shellcheck not installed",
)
@pytest.mark.parametrize("action_path", COMPOSITE_FILES, ids=[_id(p) for p in COMPOSITE_FILES])
def test_bash_steps_clean_under_shellcheck_errors(action_path: Path) -> None:
    """Every bash step must be clean under ``shellcheck -S error``."""
    steps = _bash_steps(action_path)
    if not steps:
        pytest.skip(f"{action_path}: no bash steps")
    for idx, body in steps:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f"_{idx}.sh", delete=False
        ) as tmp:
            tmp.write("#!/usr/bin/env bash\nset -euo pipefail\n")
            tmp.write(body)
            tmp_path = tmp.name
        result = subprocess.run(
            ["shellcheck", "-x", "-S", "error", "--shell=bash", tmp_path],
            capture_output=True, text=True,
        )
        Path(tmp_path).unlink(missing_ok=True)
        assert result.returncode == 0, (
            f"{action_path}#step{idx}: shellcheck error:\n{result.stdout}"
        )


def test_at_least_one_composite_was_discovered() -> None:
    """Guard against the directory-walk regressing to zero results."""
    # 6 originals + 2 added in the recent feat commit + root manifest.
    assert len(COMPOSITE_FILES) >= 5, (
        f"only discovered {len(COMPOSITE_FILES)} composite manifests; "
        "this suggests the discovery logic regressed."
    )


def test_root_action_wires_every_input_to_a_composite() -> None:
    """The root `action.yml` is a thin router: every input it declares
    should appear in at least one ``with:`` block in its steps."""
    d = yaml.safe_load(ROOT_ACTION.read_text(encoding="utf-8"))
    declared = set((d.get("inputs") or {}).keys())
    # Collect all input names referenced in the steps' `with:` blocks.
    body = ROOT_ACTION.read_text(encoding="utf-8")
    # Cheap textual sweep — every `inputs.<name>` reference counts.
    referenced = {
        name for name in declared
        if f"inputs.{name}" in body or f"inputs[ '{name}'" in body
    }
    missing = declared - referenced
    assert not missing, (
        f"root action.yml declares {sorted(missing)} but never references them"
    )
