"""Tests for the no-PyYAML fallback parser in extract_meta.py.

Background: on runners without PyYAML, ``extract_meta.py`` uses a
hand-rolled regex parser. The previous version did not understand
YAML block scalars (``>``, ``>-``, ``|``, ``|-``), so an action.yml
that opened ``description: >-`` was parsed with ``>-`` as the value
(DESC_LEN=2) and the check would erroneously emit
``MP003: description is 2 chars``.

These tests pin the fallback parser's block-scalar handling.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import io
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
EXTRACT_PATH = REPO_ROOT / ".github" / "actions" / "check" / "extract_meta.py"


def _load_module(yaml_present: bool):
    """Load extract_meta.py with optional control over PyYAML import.

    When ``yaml_present`` is False we install an import hook that
    raises ``ImportError`` for ``yaml``, forcing the fallback path.
    """
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if not yaml_present and name == "yaml":
            raise ImportError("yaml hidden for test")
        return real_import(name, globals, locals, fromlist, level)

    spec = importlib.util.spec_from_file_location("extract_meta_under_test", EXTRACT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extract_meta_under_test"] = mod
    if not yaml_present:
        builtins.__import__ = fake_import
    try:
        spec.loader.exec_module(mod)
    finally:
        builtins.__import__ = real_import
    return mod


@pytest.fixture
def fallback_module():
    """Load extract_meta.py with PyYAML hidden so the fallback runs."""
    mod = _load_module(yaml_present=False)
    yield mod
    sys.modules.pop("extract_meta_under_test", None)


def _write_action(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "action.yml"
    p.write_text(textwrap.dedent(body), encoding="utf-8")
    return p


def test_fallback_folded_dash_description(fallback_module, tmp_path: Path) -> None:
    """The kit's own action.yml shape — ``description: >-`` followed
    by indented lines — must be parsed as the folded text, not as
    the literal indicator ``>-``."""
    p = _write_action(
        tmp_path,
        """\
        name: my-action
        description: >-
          Pre-publish validator for GitHub Marketplace Actions. Lints
          metadata, branding, naming, and security defaults.
        runs:
          using: composite
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    desc = doc["description"]
    assert isinstance(desc, str)
    # The folded value joins the two body lines with a single space.
    # Allow for slight whitespace differences but ensure we did NOT
    # capture the literal ``>-`` indicator.
    assert desc.startswith("Pre-publish validator")
    assert ">-" not in desc
    # Sanity: real-world descriptions are at least 50 chars.
    assert len(desc) >= 50


def test_fallback_folded_plain(fallback_module, tmp_path: Path) -> None:
    """Folded ``>`` (no chomp indicator) also works."""
    p = _write_action(
        tmp_path,
        """\
        name: x
        description: >
          One line of text that
          wraps over two source lines.
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    assert "wraps over two source lines" in doc["description"]
    assert doc["description"].startswith("One line of text")


def test_fallback_literal_pipe(fallback_module, tmp_path: Path) -> None:
    """Literal ``|`` preserves newlines between source lines."""
    p = _write_action(
        tmp_path,
        """\
        name: x
        description: |
          line one
          line two
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    assert doc["description"].startswith("line one")
    assert "\n" in doc["description"]


def test_fallback_literal_strip(fallback_module, tmp_path: Path) -> None:
    """``|-`` strips trailing newlines."""
    p = _write_action(
        tmp_path,
        """\
        name: x
        description: |-
          only line
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    assert doc["description"] == "only line"


def test_fallback_block_scalar_terminates_on_top_level_key(
    fallback_module, tmp_path: Path
) -> None:
    """A block scalar's body must end when a new top-level key is
    seen at column 0 — otherwise we'd swallow ``runs:``, ``inputs:``,
    etc. into the description value."""
    p = _write_action(
        tmp_path,
        """\
        name: x
        description: >-
          first paragraph line
          second paragraph line
        runs:
          using: composite
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    assert "first paragraph line" in doc["description"]
    assert "using" not in doc["description"]
    assert isinstance(doc.get("runs"), dict)
    assert doc["runs"].get("using") == "composite"


def test_fallback_plain_scalar_still_works(fallback_module, tmp_path: Path) -> None:
    """Inline scalars without block indicators continue to round-trip."""
    p = _write_action(
        tmp_path,
        """\
        name: my-action
        description: a short single-line description
        runs:
          using: composite
        """,
    )
    doc = fallback_module._fallback_parse(str(p))
    assert doc["name"] == "my-action"
    assert doc["description"] == "a short single-line description"


def test_real_action_yml_desc_length_via_cli(tmp_path: Path) -> None:
    """End-to-end: run the script as a subprocess against the kit's
    OWN action.yml with PYTHONPATH manipulated so PyYAML is hidden,
    and assert DESC_LEN matches the real description length (not 2).

    Hides PyYAML by running with an empty ``sys.path`` prefix that
    doesn't contain site-packages — easier said than done, so we
    instead use a small shim: a wrapper python program that pops the
    ``yaml`` module from sys.modules and blocks its import via meta-
    path finder, then execs extract_meta.py.
    """
    action_yml = REPO_ROOT / "action.yml"
    if not action_yml.exists():  # pragma: no cover
        pytest.skip("kit action.yml not present in this checkout")

    shim = tmp_path / "run_without_yaml.py"
    shim.write_text(
        textwrap.dedent(
            f"""\
            import sys
            from importlib.abc import MetaPathFinder
            class BlockYaml(MetaPathFinder):
                def find_spec(self, name, path, target=None):
                    if name == "yaml":
                        raise ImportError("yaml hidden")
                    return None
            sys.meta_path.insert(0, BlockYaml())
            sys.modules.pop("yaml", None)
            sys.argv = [{str(EXTRACT_PATH)!r}, {str(action_yml)!r}]
            with open({str(EXTRACT_PATH)!r}, encoding="utf-8") as f:
                exec(compile(f.read(), {str(EXTRACT_PATH)!r}, "exec"), {{"__name__": "__main__"}})
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(shim)], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    desc_line = next(
        (ln for ln in result.stdout.splitlines() if ln.startswith("DESC_LEN=")),
        None,
    )
    assert desc_line is not None, result.stdout
    # shlex.quote wraps the integer in single quotes — strip them.
    desc_len = int(desc_line.split("=", 1)[1].strip().strip("'"))
    # The kit's real description is well above 50 chars; the bug
    # symptom was DESC_LEN=2 (the literal ``>-``).
    assert desc_len >= 50, f"DESC_LEN={desc_len} — block-scalar fallback regressed"
