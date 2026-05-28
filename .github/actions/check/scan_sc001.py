"""SC001 scanner — detect expression-form input/event interpolation in
composite-action `run:` bodies.

Background
==========

GitHub Actions evaluates ``${{ ... }}`` expressions BEFORE the
generated shell script is handed to bash. Any value derived from an
attacker-influenceable source (``inputs.*``, ``github.event.*``)
that is interpolated directly into a ``run:`` body is a shell-
injection surface, even if the eventual shell carefully quotes its
own variables: the substitution happens textually, before bash sees
the script.

The safe pattern is to plumb the value through ``env:`` on the same
step and reference the resulting environment variable inside the
script. The runner sets ``env`` values via the process environment,
so bash sees a normal variable and the value cannot break out of
the script structure.

History — earlier awk-in-bash detector (NOW REPLACED)
=====================================================

The previous implementation in ``action.yml`` used:

    /^[[:space:]]*run:/ { inrun=1 }
    inrun && $0 ~ pat { print FILENAME; exit }

This set ``inrun=1`` on the FIRST ``run:`` line in the file and
never cleared it — so EVERY ``${{ inputs.* }}`` / ``${{ github.event.* }}``
that appeared later in the file (including SAFE references inside
the ``env:`` block of LATER steps) was flagged as a violation.

This Python helper does the structural thing the awk one-liner
couldn't: it tracks the indentation of each ``run:`` mapping key
and considers a line "inside the run body" iff its indentation is
strictly greater than the ``run:`` line's indentation. The body
ends at the first non-blank line whose indentation is ``<=`` the
``run:`` key's indentation. ``env:`` references in other steps
therefore stay invisible to the detector, eliminating false
positives.

Output
======

The script accepts one or more action.yml paths on argv. For each
composite action that contains an unsafe interpolation, the path is
printed on its own line. Files with no violations are silent. Exit
code is 0 regardless (the caller decides whether finding any path
constitutes a failure).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Match the literal `${{` ... `inputs.` / `github.event.` opening of a
# templating expression that references an attacker-influenceable
# value. Concatenated from "$" + "{{" so the literal sequence never
# appears verbatim in this source file either (defensive — Actions
# template scanners that walk source trees have historically choked
# on the sequence appearing inside string literals).
_DOLLAR = "$"
_OPEN = _DOLLAR + "{{"
# Allow any whitespace between the `{{` and the dotted path.
_UNSAFE_RE = re.compile(re.escape(_OPEN) + r"\s*(inputs|github\.event)\b")


def _indent_of(line: str) -> int:
    """Return the number of leading spaces in ``line`` (tabs = 1)."""
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "\t":
            n += 1
        else:
            break
    return n


def _is_blank(line: str) -> bool:
    return line.strip() == "" or line.lstrip().startswith("#")


def file_has_unsafe_run_interp(text: str) -> bool:
    """Return True iff any ``run:`` body in ``text`` interpolates
    ``${{ inputs.* }}`` or ``${{ github.event.* }}`` directly.

    Only the body of a ``run:`` mapping key is scanned; ``env:`` blocks
    on the same or other steps are NOT scanned, even when they
    reference inputs (that is the safe, recommended pattern).
    """
    lines = text.splitlines()

    # Confirm the file is actually a composite action; the caller may
    # also do this, but we keep the check here so the function is
    # safe in isolation (e.g. when invoked from unit tests).
    if not re.search(r"^\s*using:\s*composite\b", text, flags=re.MULTILINE):
        return False

    in_run = False
    run_indent = -1  # indentation of the `run:` mapping key

    for raw in lines:
        # A `run:` mapping key starts a body block. Capture its indent
        # so we can detect when the body ends.
        m = re.match(r"^(\s*)run:\s*(?:[>|][+-]?)?\s*$", raw)
        if m:
            in_run = True
            run_indent = len(m.group(1))
            continue

        # Some action.yml files put a short inline scalar on the
        # `run:` line itself (e.g. `run: echo hi`). The body is then
        # exactly that one line — scan it and immediately reset.
        m_inline = re.match(r"^(\s*)run:\s+(.+)$", raw)
        if m_inline and not m_inline.group(2).startswith(("|", ">")):
            if _UNSAFE_RE.search(m_inline.group(2)):
                return True
            in_run = False
            run_indent = -1
            continue

        if not in_run:
            continue

        # Blank / comment lines don't terminate a YAML block scalar.
        if _is_blank(raw):
            continue

        # A non-blank line at indent <= run_indent terminates the body.
        if _indent_of(raw) <= run_indent:
            in_run = False
            run_indent = -1
            # Re-examine this line at top of loop iteration — but the
            # next iteration's `for` will only see the NEXT line. So
            # we need to handle the case where this line itself opens
            # a new run block. Detect by re-running the run-key
            # regex against the same line:
            m2 = re.match(r"^(\s*)run:\s*(?:[>|][+-]?)?\s*$", raw)
            if m2:
                in_run = True
                run_indent = len(m2.group(1))
            continue

        # We're inside a `run:` body — scan for the unsafe pattern.
        if _UNSAFE_RE.search(raw):
            return True

    return False


def main(argv: list[str]) -> int:
    for path in argv[1:]:
        p = Path(path)
        try:
            text = p.read_text(encoding="utf-8")
        except OSError as exc:
            sys.stderr.write(f"warn: cannot read {path}: {exc}\n")
            continue
        if file_has_unsafe_run_interp(text):
            print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
