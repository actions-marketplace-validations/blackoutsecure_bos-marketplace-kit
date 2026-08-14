"""Tests for the CLI's `doctor` subcommand."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from marketplace_kit.cli import main


VALID_MANIFEST = """\
name: My Action
description: A test action.
author: Tester
branding:
  icon: check-circle
  color: green
runs:
  using: composite
  steps:
    - shell: bash
      run: echo hi
"""


def _populate_repo(root: Path, *, with_manifest: bool = True, **extra_files: str) -> None:
    """Lay down a minimal Marketplace-repo skeleton in ``root``."""
    if with_manifest:
        (root / "action.yml").write_text(VALID_MANIFEST, encoding="utf-8")
    (root / "README.md").write_text("# Test\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    for name, content in extra_files.items():
        (root / name).write_text(content, encoding="utf-8")


def _run_doctor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *args: str) -> tuple[int, str]:
    monkeypatch.chdir(tmp_path)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["doctor", *args])
    return rc, buf.getvalue()


def test_doctor_passes_with_full_community_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate_repo(
        tmp_path,
        **{
            "SECURITY.md": "Sec\n",
            "CODE_OF_CONDUCT.md": "Coc\n",
        },
    )
    rc, out = _run_doctor(tmp_path, monkeypatch)
    # No fails (warns are tolerated by default).
    assert rc == 0
    assert "MP001" in out and "PASS" in out
    # Community-health section recognises all required + optional files.
    assert "SECURITY.md present" in out
    assert "CODE_OF_CONDUCT.md present" in out


def test_doctor_warns_on_missing_security_md(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # No SECURITY.md, but otherwise OK.
    _populate_repo(tmp_path)
    rc, out = _run_doctor(tmp_path, monkeypatch)
    assert rc == 0  # warns don't fail by default
    assert "SECURITY.md missing" in out
    assert "WARN" in out


def test_doctor_fails_on_missing_license(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate_repo(tmp_path)
    (tmp_path / "LICENSE").unlink()
    rc, out = _run_doctor(tmp_path, monkeypatch)
    assert rc == 1
    assert "LICENSE missing" in out
    assert "FAIL" in out


def test_doctor_fails_on_missing_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate_repo(tmp_path, with_manifest=False)
    rc, out = _run_doctor(tmp_path, monkeypatch)
    assert rc == 1
    assert "action.yml" in out
    assert "not found" in out or "missing" in out.lower()


def test_doctor_fail_on_warning_promotes_warns_to_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate_repo(tmp_path)  # no SECURITY.md → warn
    rc, _ = _run_doctor(tmp_path, monkeypatch, "--fail-on-warning")
    assert rc == 1


def test_doctor_summary_line_is_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _populate_repo(tmp_path)
    _, out = _run_doctor(tmp_path, monkeypatch)
    assert "Summary:" in out
    # Summary should report counts of fails + warns.
    assert "fail" in out and "warn" in out
