"""Extract Marketplace-relevant metadata from an action.yml.

Called by the `check` composite. Emits a series of shell-safe
`KEY=value` lines on stdout (values quoted via shlex.quote) that the
calling shell `eval`s.
"""

from __future__ import annotations

import re
import shlex
import sys


def _scalar(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def _fallback_parse(path: str) -> dict:
    """Minimal regex parser used when PyYAML is unavailable.

    Captures only the keys this check inspects. Sufficient for
    detecting empty/missing values; not a YAML implementation.

    Block scalars (`>`, `>-`, `|`, `|-`) ARE understood — without
    that, an action.yml whose top-level ``description: >-`` spans
    multiple lines would have ``>-`` captured as the literal value
    (DESC_LEN=2 instead of the real character count), spuriously
    tripping MP003 / OP003.
    """
    doc: dict[str, object] = {}
    cur_section: dict | None = None
    cur_key: str | None = None

    # Block-scalar accumulator state. When a ``key: >-`` (or `|`, etc.)
    # is seen at the top level, we collect subsequent indented lines
    # until the indentation drops back to column 0 (a new top-level
    # key) or EOF.
    block_target: tuple[str, str] | None = None  # (key, style)
    block_lines: list[str] = []

    def _flush_block() -> None:
        nonlocal block_target, block_lines
        if block_target is None:
            return
        key, style = block_target
        # Strip the common leading indentation so we keep relative
        # formatting (matches PyYAML's behaviour for plain block
        # scalars with no explicit indentation indicator).
        stripped = [ln.lstrip() for ln in block_lines]
        if style.startswith(">"):
            # Folded scalar: join non-empty lines with single spaces;
            # blank lines become a single newline (paragraph break).
            joined_parts: list[str] = []
            buf: list[str] = []
            for ln in stripped:
                if ln == "":
                    if buf:
                        joined_parts.append(" ".join(buf))
                        buf = []
                    joined_parts.append("")
                else:
                    buf.append(ln)
            if buf:
                joined_parts.append(" ".join(buf))
            value = "\n".join(joined_parts)
        else:  # literal `|`
            value = "\n".join(stripped)
        # Chomping indicators: `-` strips trailing newlines; `+`
        # keeps all (rare); default keeps one trailing newline.
        if style.endswith("-"):
            value = value.rstrip("\n")
        doc[key] = value
        block_target = None
        block_lines = []

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")

            # If we're inside a block scalar, decide whether this line
            # belongs to its body or terminates it.
            if block_target is not None:
                if line.strip() == "":
                    block_lines.append("")
                    continue
                # A line that starts at column 0 (no leading
                # whitespace) is a new top-level mapping key — flush
                # and fall through to normal processing.
                if not line.startswith((" ", "\t")):
                    _flush_block()
                else:
                    block_lines.append(line)
                    continue

            top = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
            if top:
                cur_key = top.group(1)
                rhs = top.group(2)
                # Detect block-scalar indicators on the right-hand
                # side. The full grammar allows an explicit
                # indentation indicator (``>2``, ``|4``) — we accept
                # but ignore that digit.
                m_block = re.match(r"^([>|])([0-9]*)([+-]?)\s*(?:#.*)?$", rhs)
                if m_block:
                    style = m_block.group(1) + (m_block.group(3) or "")
                    block_target = (cur_key, style)
                    block_lines = []
                    cur_section = None
                    continue
                val = rhs.strip().strip("'\"")
                if val:
                    doc[cur_key] = val
                    cur_section = None
                else:
                    doc[cur_key] = {}
                    cur_section = doc[cur_key]  # type: ignore[assignment]
                continue
            sub = re.match(r"^\s+([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
            if sub and isinstance(cur_section, dict):
                cur_section[sub.group(1)] = sub.group(2).strip().strip("'\"")
    # End of file — flush any open block scalar.
    _flush_block()
    return doc


def main() -> int:
    path = sys.argv[1]
    try:
        import yaml  # noqa: WPS433

        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except ImportError:
        doc = _fallback_parse(path)
    except Exception as exc:
        sys.stderr.write(f"warn: YAML parse failed ({exc}); falling back to regex parse\n")
        doc = _fallback_parse(path)

    name = _scalar(doc.get("name"))
    desc = _scalar(doc.get("description"))
    runs = doc.get("runs") or {}
    runs_using = _scalar(runs.get("using")) if isinstance(runs, dict) else ""
    branding = doc.get("branding") or {}
    icon = _scalar(branding.get("icon")) if isinstance(branding, dict) else ""
    color = _scalar(branding.get("color")) if isinstance(branding, dict) else ""

    # Emit shell-safe assignments. `shlex.quote` wraps values in
    # single quotes and escapes any internal single quotes, so the
    # caller's `eval` is safe against odd YAML content.
    out = [
        ("NAME", name),
        ("DESC_LEN", str(len(desc))),
        ("RUNS_USING", runs_using),
        ("BRANDING_ICON", icon),
        ("BRANDING_COLOR", color),
    ]
    for key, val in out:
        print(f"{key}={shlex.quote(val)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

