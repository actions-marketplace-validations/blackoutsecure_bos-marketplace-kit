"""Tests for the CLI's check subcommand."""

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


def write(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "action.yml"
    p.write_text(content, encoding="utf-8")
    return p


def test_check_passes_on_valid_manifest(tmp_path: Path) -> None:
    p = write(tmp_path, VALID_MANIFEST)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["check", "--action-yml", str(p)])
    assert rc == 0
    out = buf.getvalue()
    assert "MP001" in out and "PASS" in out


def test_check_fails_on_missing_description(tmp_path: Path) -> None:
    p = write(tmp_path, VALID_MANIFEST.replace("description: A test action.\n", ""))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["check", "--action-yml", str(p)])
    assert rc == 1
    assert "MP003" in buf.getvalue()


def test_check_fails_on_invalid_branding_color(tmp_path: Path) -> None:
    p = write(tmp_path, VALID_MANIFEST.replace("color: green", "color: chartreuse"))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["check", "--action-yml", str(p)])
    assert rc == 1
    assert "MP006" in buf.getvalue()


def test_check_fails_on_long_description(tmp_path: Path) -> None:
    long_desc = "X" * 200
    p = write(tmp_path, VALID_MANIFEST.replace("A test action.", long_desc))
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["check", "--action-yml", str(p)])
    assert rc == 1  # MP010 is fatal
    out = buf.getvalue()
    assert "MP010" in out
    assert "FAIL" in out


def test_check_fail_on_warning_promotes(tmp_path: Path) -> None:
    # Drop `author:` to trigger OP003 (warn). With --fail-on-warning,
    # the otherwise-clean manifest should exit non-zero.
    manifest = "\n".join(
        line for line in VALID_MANIFEST.splitlines() if not line.startswith("author:")
    ) + "\n"
    p = write(tmp_path, manifest)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["check", "--action-yml", str(p), "--fail-on-warning"])
    assert rc == 1
    assert "OP003" in buf.getvalue()


def test_check_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["check", "--action-yml", str(tmp_path / "nope.yml")])
    assert exc.value.code == 2
