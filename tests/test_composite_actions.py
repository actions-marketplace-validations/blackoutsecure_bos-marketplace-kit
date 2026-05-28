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


def test_branch_protection_does_not_preflight_for_gh() -> None:
    """Regression test for workflow run 26483123210 (Jun 2026):
    the branch-protection composite previously asserted that the
    ``gh`` CLI was on PATH but actually talked to api.github.com via
    ``curl`` -- the ``gh`` preflight was vestigial. That dead check
    rejected lean self-hosted runner images that don't preinstall
    the ``gh`` CLI (the docker-github-runner image is intentionally
    minimal: ``curl`` + ``jq`` + ``git`` + ``python3`` + ``bash``
    only, no ``gh``). Don't reintroduce the preflight without also
    adding a real ``gh`` invocation or a graceful install/skip.
    """
    path = COMPOSITES_DIR / "branch-protection" / "action.yml"
    text = path.read_text(encoding="utf-8")
    assert "command -v gh" not in text, (
        f"{path}: vestigial `command -v gh` preflight detected. "
        "The composite uses `curl` directly for every GitHub API "
        "request -- adding a `gh` preflight rejects lean self-hosted "
        "runner images that lack the `gh` CLI for no real reason."
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


def test_check_actionlint_download_is_arch_aware() -> None:
    """Regression test for workflow run 26553990574 (Jun 2026):
    the check composite's actionlint installer previously hard-coded
    ``linux_amd64`` in the download URL. On ARM self-hosted runners
    (e.g. a Raspberry Pi or any ``ubuntu-*-arm`` runner) this
    silently downloaded the x86_64 tarball, passed SHA verification
    (we were checking the amd64 SHA against the amd64 tarball), then
    died at exec time with::

        actionlint: cannot execute binary file: Exec format error

    The fix is to detect the runner architecture with ``uname -m``
    and pick the matching actionlint release asset
    (``linux_amd64``/``linux_arm64``/``linux_armv6``/``linux_386``).
    Don't reintroduce the amd64-only hard-code.
    """
    path = COMPOSITES_DIR / "check" / "action.yml"
    text = path.read_text(encoding="utf-8")
    # Must perform some form of arch detection.
    assert "uname -m" in text, (
        f"{path}: actionlint installer must detect runner arch via "
        "`uname -m` before building the download URL. The previous "
        "amd64-only hard-code broke every non-x86_64 self-hosted runner."
    )
    # The URL must NOT hard-code linux_amd64 as the only choice.
    # We allow the literal ``linux_amd64`` to appear inside a `case`
    # arm or a comment, so check specifically for the old URL shape.
    assert "_linux_amd64.tar.gz" not in text, (
        f"{path}: actionlint download URL still contains the literal "
        "`_linux_amd64.tar.gz`. Use a per-arch asset name selected from "
        "`uname -m` instead."
    )


def test_lint_markdownlint_installs_outside_repo_root() -> None:
    """Regression test for workflow run 26553990574 (Jun 2026):
    the lint composite previously ran ``npm install
    markdownlint-cli2`` from the current working directory (the repo
    root). That created ``./node_modules/`` populated with every
    transitive dependency's ``README.md``, and the next step's
    default ``**/*.md`` glob then swept all of them up -- producing
    a 1562-finding report where every line lived in ``node_modules/``
    and masking any real findings in the user's tree.

    The fix is to install into ``RUNNER_TEMP`` with ``npm install
    --prefix "${MD_TMP}"`` and invoke the binary as
    ``"${MD_TMP}/node_modules/.bin/markdownlint-cli2"``. Don't
    reintroduce the cwd install.
    """
    path = COMPOSITES_DIR / "lint" / "action.yml"
    text = path.read_text(encoding="utf-8")
    # The npm install line must scope its install dir via --prefix
    # (any value -- the important thing is that it isn't cwd).
    assert "npm install" in text, f"{path}: lint composite no longer invokes npm install"
    # Look at every line that contains an npm install invocation.
    npm_install_lines = [
        line for line in text.splitlines()
        if "npm install" in line and not line.lstrip().startswith("#")
    ]
    assert npm_install_lines, f"{path}: no non-comment `npm install` line found"
    for line in npm_install_lines:
        assert "--prefix" in line or "\\" in line, (
            f"{path}: bare `npm install` from cwd detected: {line!r}. "
            "This installs dependencies into ./node_modules/ in the repo "
            "root, polluting the working tree and causing default `**/*.md` "
            "globs to scoop up hundreds of dependency README files."
        )
    # Defense in depth: the install dir name from the fix should appear.
    assert "marketplace-kit-markdownlint" in text, (
        f"{path}: expected the markdownlint install to land in "
        "`${RUNNER_TEMP}/marketplace-kit-markdownlint/`. If you renamed "
        "the scratch dir, update this assertion too."
    )


def test_lint_yamllint_has_pip_missing_fallback() -> None:
    """Regression test for workflow run 26553990574 (Jun 2026):
    the lint composite previously ran ``python3 -m pip install
    yamllint==...`` unconditionally. Lean self-hosted runner images
    (e.g. our docker-github-runner) ship ``python3`` without ``pip``
    to keep the image small, so this aborted the job with::

        /usr/bin/python3: No module named pip
        Error: Process completed with exit code 1.

    The fix is to probe for an already-installed yamllint binary
    first, then try pip if available, then apt-get install
    python3-pip + retry, then apt-get install yamllint as a final
    fallback, and finally skip-with-warning if every path fails.
    Don't reintroduce the bare ``python3 -m pip install`` that
    crashes on lean runners.
    """
    path = COMPOSITES_DIR / "lint" / "action.yml"
    text = path.read_text(encoding="utf-8")
    # The yamllint block must probe pip's presence before invoking it.
    assert "python3 -m pip --version" in text, (
        f"{path}: yamllint install must probe `python3 -m pip --version` "
        "before invoking pip. Lean runner images ship python3 without pip; "
        "the bare invocation aborts the job under `set -euo pipefail`."
    )
    # And must check for an existing binary first (cheapest path).
    assert "command -v yamllint" in text, (
        f"{path}: yamllint install path must first check `command -v yamllint` "
        "to avoid re-installing on runners that already ship it."
    )
    # And must have the skip-with-warning escape hatch.
    assert "yamllint | ⊘ skipped (install failed)" in text, (
        f"{path}: yamllint install path must emit a visible skip row "
        "(`yamllint | ⊘ skipped (install failed)`) when every install "
        "fallback fails, so the job summary makes the skip discoverable."
    )
