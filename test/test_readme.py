"""Documentation and lint gates that run inside the normal pytest job.

CI for this repo is driven by hub-managed workflow kickers, so the
drift gates live here rather than as extra workflow steps: the generated
README tables must match `action.yml`, and the Python sources must be
ruff-clean when ruff is available.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
ACTION_YML = REPO_ROOT / "action.yml"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import render_readme_inputs as renderer  # noqa: E402


def test_generated_tables_are_in_sync() -> None:
    manifest = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    current = README.read_text(encoding="utf-8")
    assert renderer.build(manifest, current) == current, (
        "README action tables are stale — run "
        "`python3 scripts/render_readme_inputs.py --write`"
    )


def test_every_action_input_appears_in_the_generated_table() -> None:
    manifest = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    table = renderer.render_inputs(manifest)
    for name in manifest["inputs"]:
        assert f"`{name}`" in table


def test_readme_has_the_generated_markers() -> None:
    text = README.read_text(encoding="utf-8")
    for marker in (renderer.INPUTS_MARKER, renderer.OUTPUTS_MARKER):
        assert renderer._begin(marker) in text
        assert renderer._end(marker) in text


def _sections(text: str) -> list[str]:
    """Top-level headings, ignoring anything inside a fenced block."""
    open_fence = ""
    found = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            token = stripped[:3]
            run = len(stripped) - len(stripped.lstrip(token[0]))
            if not open_fence:
                open_fence = token[0] * run
            elif stripped == open_fence or (
                stripped.startswith(open_fence[0]) and run >= len(open_fence)
                and set(stripped) == {open_fence[0]}
            ):
                open_fence = ""
            continue
        if not open_fence and line.startswith("## "):
            found.append(line[3:].strip())
    return found


def test_readme_section_order_matches_the_kit_layout() -> None:
    expected = [
        "✨ Features",
        "📖 Table of Contents",
        "📋 Prerequisites",
        "🚀 Quick start",
        "⚙️ Action inputs",
        "📤 Action outputs",
        "🧰 What's in the box",
        "🏗️ Configuration inheritance and layering",
        "📦 Package metadata",
        "✅ Check rule catalogue",
        "🚢 Publishing to Marketplace",
        "🧪 Examples",
        "💻 Local usage (CLI)",
        "⚠️ Runtime and repository notes",
        "🔐 Security",
        "🏷️ Versioning",
        "🤝 Contributing",
        "📜 License",
    ]
    assert _sections(README.read_text(encoding="utf-8")) == expected


def test_table_of_contents_lists_every_section() -> None:
    text = README.read_text(encoding="utf-8")
    toc = text.split("## 📖 Table of Contents", 1)[1].split("## 📋", 1)[0]
    for title in _sections(text):
        assert f"[{title}]" in toc, f"Table of Contents is missing {title!r}"


def test_readme_size_stays_within_op005_bounds() -> None:
    size = README.stat().st_size
    assert 512 < size < 128 * 1024, f"README is {size} bytes"


@pytest.mark.skipif(shutil.which("ruff") is None, reason="ruff not installed")
def test_python_sources_are_ruff_clean() -> None:
    result = subprocess.run(
        ["ruff", "check", "src", "test", "scripts"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout or result.stderr
