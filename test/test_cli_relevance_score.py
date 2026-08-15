"""CLI smoke tests for `marketplace-kit relevance-score`."""

from __future__ import annotations

import json
from pathlib import Path

from marketplace_kit.cli import main


def _run(args: list[str]) -> tuple[int, str, str]:
    import contextlib
    import io

    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = main(args)
    return rc, out.getvalue(), err.getvalue()


def test_relevance_score_with_explicit_files_and_dry_run(tmp_path: Path) -> None:
    rc, out, _ = _run([
        "relevance-score", "--root", str(tmp_path),
        "--files", "action.yml\nREADME.md",
        "--dry-run", "--json",
    ])
    assert rc == 0
    result = json.loads(out)
    assert result["deterministic_score"] == 40
    assert result["should_publish"] is False
    assert not (tmp_path / ".github/marketplace-relevance-score.json").exists()


def test_relevance_score_persists_state_across_runs(tmp_path: Path) -> None:
    rc, out, _ = _run([
        "relevance-score", "--root", str(tmp_path),
        "--files", "README.md", "--json",
    ])
    assert rc == 0
    first = json.loads(out)
    assert first["running_total"] == 15
    state_path = tmp_path / ".github/marketplace-relevance-score.json"
    assert state_path.exists()

    rc, out, _ = _run([
        "relevance-score", "--root", str(tmp_path),
        "--files", "README.md", "--json",
    ])
    second = json.loads(out)
    assert second["running_total"] == 30


def test_relevance_score_reset_zeroes_the_running_total(tmp_path: Path) -> None:
    _run(["relevance-score", "--root", str(tmp_path), "--files", "action.yml", "--json"])
    rc, out, _ = _run(["relevance-score", "--root", str(tmp_path), "--reset", "--head", "deadbeef"])
    assert rc == 0
    assert json.loads(out)["running_total"] == 0

    rc, out, _ = _run([
        "relevance-score", "--root", str(tmp_path), "--files", "README.md", "--json",
    ])
    assert json.loads(out)["running_total"] == 15
