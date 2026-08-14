"""Tests for the CLI's `name-check` subcommand.

Network calls are mocked so tests are hermetic and fast.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from marketplace_kit import cli
from marketplace_kit.cli import main


def _run(*args: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(list(args))
    return rc, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Slug normalisation
# ---------------------------------------------------------------------------

class TestSlugify:
    """Exercise the private _slugify helper directly."""

    def test_lowercases(self) -> None:
        assert cli._slugify("My Action") == "my-action"

    def test_collapses_separators(self) -> None:
        assert cli._slugify("Foo  Bar___Baz") == "foo-bar-baz"

    def test_strips_punctuation(self) -> None:
        assert cli._slugify("Foo Bar!?") == "foo-bar"

    def test_strips_leading_trailing_dashes(self) -> None:
        assert cli._slugify("---Foo---") == "foo"

    def test_returns_empty_for_pure_punct(self) -> None:
        assert cli._slugify("!!!") == ""


# ---------------------------------------------------------------------------
# name-check command (HTTP mocked)
# ---------------------------------------------------------------------------

class TestNameCheckCommand:
    def test_empty_slug_exits_two(self) -> None:
        rc, _, err = _run("name-check", "!!!")
        assert rc == 2
        assert "empty slug" in err

    def test_reports_collision_when_marketplace_page_returns_200(self) -> None:
        with patch.object(cli, "_http_status", return_value=200):
            rc, out, _ = _run("name-check", "Foo Action")
        assert rc == 1  # collision is fatal by default
        assert "foo-action" in out
        assert "200" in out or "in use" in out.lower() or "taken" in out.lower()

    def test_reports_available_when_404(self) -> None:
        with patch.object(cli, "_http_status", return_value=404):
            rc, out, _ = _run("name-check", "Unique Action")
        assert rc == 0
        assert "unique-action" in out

    def test_no_fail_flag_returns_zero_on_collision(self) -> None:
        with patch.object(cli, "_http_status", return_value=200):
            rc, _, _ = _run("name-check", "Foo Action", "--no-fail")
        assert rc == 0

    def test_network_error_does_not_explode(self) -> None:
        # urlopen returning None signals "couldn't reach marketplace".
        # The CLI should surface the situation without crashing.
        with patch.object(cli, "_http_status", return_value=None):
            rc, out, _ = _run("name-check", "Some Action")
        # Exit code policy: undecidable → warn but still 0.
        assert rc == 0
        assert "some-action" in out

    def test_reserved_name_is_flagged(self) -> None:
        # A reserved Marketplace path slug (e.g. "marketplace") should
        # be flagged even before checking the HTTP status.
        with patch.object(cli, "_http_status", return_value=404):
            rc, out, _ = _run("name-check", "Marketplace")
        # Reserved slugs are non-zero by default.
        assert rc == 1
        # And the output should call this out explicitly.
        assert "reserved" in out.lower() or "marketplace" in out
