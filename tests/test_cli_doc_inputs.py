"""Tests for the CLI's `doc-inputs` subcommand."""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from marketplace_kit.cli import main


MANIFEST_WITH_IO = """\
name: Test Action
description: A test action with inputs and outputs.
runs:
  using: composite
  steps:
    - shell: bash
      run: echo hi

inputs:
  message:
    description: The message to echo.
    required: true
  retries:
    description: How many times to retry.
    required: false
    default: '3'
  silent:
    description: Run quietly.
    required: false
    default: 'false'

outputs:
  result:
    description: The outcome of the run.
  duration_ms:
    description: How long the action took, in ms.
"""


def _run(args: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(args)
    return rc, buf.getvalue()


def test_doc_inputs_emits_both_tables(tmp_path: Path) -> None:
    manifest = tmp_path / "action.yml"
    manifest.write_text(MANIFEST_WITH_IO, encoding="utf-8")
    rc, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    assert rc == 0
    assert "### Inputs" in out
    assert "### Outputs" in out


def test_doc_inputs_table_columns(tmp_path: Path) -> None:
    manifest = tmp_path / "action.yml"
    manifest.write_text(MANIFEST_WITH_IO, encoding="utf-8")
    _, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    # Header row + separator are present.
    assert "| Name | Required | Default | Description |" in out
    assert "|------|----------|---------|-------------|" in out
    # Each input appears as its own row.
    assert "`message`" in out
    assert "`retries`" in out
    assert "`silent`" in out
    # Required column populated correctly.
    assert "yes" in out  # message is required
    assert "no" in out   # retries / silent are not


def test_doc_inputs_default_value_rendered_in_backticks(tmp_path: Path) -> None:
    manifest = tmp_path / "action.yml"
    manifest.write_text(MANIFEST_WITH_IO, encoding="utf-8")
    _, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    # Defaults wrapped in backticks.
    assert "`3`" in out
    assert "`false`" in out


def test_doc_inputs_outputs_row_per_output(tmp_path: Path) -> None:
    manifest = tmp_path / "action.yml"
    manifest.write_text(MANIFEST_WITH_IO, encoding="utf-8")
    _, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    assert "`result`" in out
    assert "`duration_ms`" in out


def test_doc_inputs_manifest_without_io_emits_minimal_output(tmp_path: Path) -> None:
    manifest = tmp_path / "action.yml"
    manifest.write_text(
        "name: Bare\n"
        "description: Bare.\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - shell: bash\n"
        "      run: 'true'\n",
        encoding="utf-8",
    )
    rc, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    assert rc == 0
    # Neither inputs nor outputs section should appear.
    assert "### Inputs" not in out
    assert "### Outputs" not in out
    # But the generator preamble should always print.
    assert "doc-inputs" in out


def test_doc_inputs_missing_file_exits_two(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["doc-inputs", "--action-yml", str(tmp_path / "nope.yml")])
    assert exc.value.code == 2


def test_doc_inputs_description_pipe_is_escaped(tmp_path: Path) -> None:
    """A `|` in the description must not break the markdown table."""
    manifest = tmp_path / "action.yml"
    manifest.write_text(
        "name: Test\n"
        "description: With pipe.\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n"
        "    - shell: bash\n"
        "      run: 'true'\n"
        "inputs:\n"
        "  thing:\n"
        "    description: 'one | two | three'\n"
        "    required: false\n",
        encoding="utf-8",
    )
    _, out = _run(["doc-inputs", "--action-yml", str(manifest)])
    # The pipe in the desc should be escaped (\|).
    assert "one \\| two \\| three" in out
