#!/usr/bin/env python3
"""Render the README's action input/output tables from `action.yml`.

The tables live between generated markers so the README never drifts
from the manifest:

    <!-- BEGIN GENERATED: action-inputs -->
    ...
    <!-- END GENERATED: action-inputs -->

Usage:

    python3 scripts/render_readme_inputs.py           # print to stdout
    python3 scripts/render_readme_inputs.py --write   # update README.md
    python3 scripts/render_readme_inputs.py --check   # CI drift gate

Exit codes: ``0`` in sync, ``1`` when ``--check`` finds drift, ``2`` on
a usage or parse error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
ACTION_YML = REPO_ROOT / "action.yml"
README = REPO_ROOT / "README.md"

INPUTS_MARKER = "action-inputs"
OUTPUTS_MARKER = "action-outputs"


def _begin(marker: str) -> str:
    return f"<!-- BEGIN GENERATED: {marker} -->"


def _end(marker: str) -> str:
    return f"<!-- END GENERATED: {marker} -->"


def _cell(text: str) -> str:
    """Flatten a YAML folded scalar into one markdown table cell."""
    return " ".join(str(text or "").split()).replace("|", "\\|")


def _default_cell(value: object) -> str:
    if value is None or value == "":
        return "(config)"
    return f"`{_cell(str(value))}`"


def render_inputs(manifest: dict) -> str:
    rows = ["| Input | Default | Description |", "|-------|---------|-------------|"]
    for name, spec in (manifest.get("inputs") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        rows.append(
            f"| `{name}` | {_default_cell(spec.get('default'))} "
            f"| {_cell(spec.get('description'))} |"
        )
    return "\n".join(rows)


def render_outputs(manifest: dict) -> str:
    rows = ["| Output | Description |", "|--------|-------------|"]
    for name, spec in (manifest.get("outputs") or {}).items():
        spec = spec if isinstance(spec, dict) else {}
        rows.append(f"| `{name}` | {_cell(spec.get('description'))} |")
    return "\n".join(rows)


def replace_block(text: str, marker: str, body: str) -> str:
    begin, end = _begin(marker), _end(marker)
    start = text.find(begin)
    stop = text.find(end)
    if start == -1 or stop == -1 or stop < start:
        raise SystemExit(
            f"error: README.md is missing the {marker!r} generated markers"
        )
    return text[:start] + f"{begin}\n\n{body}\n\n" + text[stop:]


def build(manifest: dict, readme: str) -> str:
    readme = replace_block(readme, INPUTS_MARKER, render_inputs(manifest))
    return replace_block(readme, OUTPUTS_MARKER, render_outputs(manifest))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--write", action="store_true",
                       help="Rewrite README.md in place.")
    group.add_argument("--check", action="store_true",
                       help="Exit 1 if README.md is out of date.")
    args = parser.parse_args(argv)

    manifest = yaml.safe_load(ACTION_YML.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        sys.stderr.write(f"error: {ACTION_YML} did not parse as a mapping\n")
        return 2

    current = README.read_text(encoding="utf-8")
    updated = build(manifest, current)

    if args.check:
        if current != updated:
            sys.stderr.write(
                "error: README action tables are stale. Run "
                "`python3 scripts/render_readme_inputs.py --write`.\n"
            )
            return 1
        print("README action tables are up to date.")
        return 0

    if args.write:
        if current == updated:
            print("README action tables already up to date.")
            return 0
        README.write_text(updated, encoding="utf-8")
        print(f"Updated {README.relative_to(REPO_ROOT)}.")
        return 0

    print(render_inputs(manifest))
    print()
    print(render_outputs(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
