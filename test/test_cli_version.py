"""Tests for the CLI's `version` subcommand and module-level metadata."""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout

import pytest

import marketplace_kit
from marketplace_kit.cli import main


def test_version_command_prints_kit_name_and_semver() -> None:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["version"])
    assert rc == 0
    out = buf.getvalue().strip()
    # "bos-marketplace-kit X.Y.Z[-suffix]"
    assert out.startswith("bos-marketplace-kit ")
    # SemVer-ish check (allow optional pre-release / build metadata).
    m = re.match(
        r"^bos-marketplace-kit \d+\.\d+\.\d+(?:[-+][\w.-]+)?$", out
    )
    assert m, f"unexpected version line: {out!r}"


def test_package_exposes_dunder_version() -> None:
    assert isinstance(marketplace_kit.__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+", marketplace_kit.__version__)


def test_version_flag_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    """`marketplace-kit --version` is handled by argparse and exits."""
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert marketplace_kit.__version__ in captured.out
