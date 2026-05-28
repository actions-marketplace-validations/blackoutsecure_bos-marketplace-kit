"""Tests for the SC001 scanner — composite-action shell-injection guard.

Regression coverage for the false-positive bug where the previous
awk-based detector latched on the first ``run:`` line and never
exited that state, so SAFE ``${{ inputs.* }}`` references inside
the ``env:`` blocks of LATER steps were flagged as violations.

The Python helper at ``.github/actions/check/scan_sc001.py`` tracks
the indentation of each ``run:`` mapping key and only scans lines
that are structurally inside its body.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCANNER_PATH = REPO_ROOT / ".github" / "actions" / "check" / "scan_sc001.py"


def _load_scanner():
    spec = importlib.util.spec_from_file_location("scan_sc001", SCANNER_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["scan_sc001"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scanner():
    return _load_scanner()


# `${{` is constructed at runtime to keep the GitHub Actions template
# engine from treating these test strings as templated expressions
# when this file is read by tools that walk source trees (the same
# defensive trick used by scan_sc001.py itself).
_OPEN = "$" + "{{"


def _composite(body: str) -> str:
    """Wrap a step body in a minimal composite action skeleton."""
    return (
        "name: test\n"
        "description: test\n"
        "runs:\n"
        "  using: composite\n"
        "  steps:\n" + body
    )


def test_unsafe_run_inputs_flagged(scanner) -> None:
    """An expression-form `inputs.*` reference inside a `run:` body
    is the canonical SC001 violation — must be flagged."""
    src = _composite(
        "    - shell: bash\n"
        "      run: |\n"
        f"        echo \"hi {_OPEN} inputs.user_name }}}}\"\n"
    )
    assert scanner.file_has_unsafe_run_interp(src) is True


def test_unsafe_run_github_event_flagged(scanner) -> None:
    """Same rule for `github.event.*` — also attacker-influenceable."""
    src = _composite(
        "    - shell: bash\n"
        "      run: |\n"
        f"        echo \"{_OPEN} github.event.issue.title }}}}\"\n"
    )
    assert scanner.file_has_unsafe_run_interp(src) is True


def test_safe_env_only_not_flagged(scanner) -> None:
    """REGRESSION: the previous awk detector flagged this because it
    never exited the `inrun` state. The `env:` block belongs to the
    same step as the (clean) `run:` body, but its `inputs.*` use is
    the SAFE plumbing pattern."""
    src = _composite(
        "    - shell: bash\n"
        "      env:\n"
        f"        USER_NAME: {_OPEN} inputs.user_name }}}}\n"
        "      run: |\n"
        '        echo "hi ${USER_NAME}"\n'
    )
    assert scanner.file_has_unsafe_run_interp(src) is False


def test_safe_env_in_later_step_not_flagged(scanner) -> None:
    """REGRESSION: this is the exact shape that tripped the old
    detector — a clean first step (with `run:`) followed by a SAFE
    second step whose `env:` block references inputs. The old code
    kept `inrun=1` across the step boundary and matched the second
    step's `env:` line."""
    src = _composite(
        "    - shell: bash\n"
        "      run: |\n"
        '        echo "first step has no inputs"\n'
        "    - shell: bash\n"
        "      env:\n"
        f"        TOKEN: {_OPEN} inputs.token }}}}\n"
        "      run: |\n"
        '        curl -H "Authorization: Bearer ${TOKEN}" https://example/\n'
    )
    assert scanner.file_has_unsafe_run_interp(src) is False


def test_multiple_steps_one_unsafe_flagged(scanner) -> None:
    """A clean first step followed by an UNSAFE second step still
    fires — proves the new detector reactivates `inrun` per `run:`."""
    src = _composite(
        "    - shell: bash\n"
        "      env:\n"
        f"        SAFE: {_OPEN} inputs.x }}}}\n"
        "      run: |\n"
        '        echo "${SAFE}"\n'
        "    - shell: bash\n"
        "      run: |\n"
        f"        echo \"oops {_OPEN} inputs.y }}}}\"\n"
    )
    assert scanner.file_has_unsafe_run_interp(src) is True


def test_non_composite_action_skipped(scanner) -> None:
    """Files without `using: composite` aren't composite actions and
    are out of scope for this rule (Docker / node actions execute in
    a sandbox where templating semantics differ)."""
    src = (
        "name: docker-action\n"
        "description: test\n"
        "runs:\n"
        "  using: docker\n"
        "  image: alpine\n"
        "  args:\n"
        f"    - {_OPEN} inputs.cmd }}}}\n"
    )
    assert scanner.file_has_unsafe_run_interp(src) is False


def test_inline_run_unsafe_flagged(scanner) -> None:
    """Some composite actions use the inline form `run: echo ...`
    instead of `run: |` — the inline body must still be scanned."""
    src = _composite(
        "    - shell: bash\n"
        f"      run: echo \"{_OPEN} inputs.x }}}}\"\n"
    )
    assert scanner.file_has_unsafe_run_interp(src) is True


def test_real_dist_check_action_clean(scanner) -> None:
    """Smoke test against the kit's own dist-check action — which
    uses ONLY the safe `env:` plumbing pattern. The previous awk
    detector flagged it; the new detector must not."""
    target = REPO_ROOT / ".github" / "actions" / "dist-check" / "action.yml"
    if not target.exists():  # pragma: no cover - skip on stripped checkouts
        pytest.skip(f"{target} not present in this checkout")
    assert scanner.file_has_unsafe_run_interp(target.read_text(encoding="utf-8")) is False


def test_real_check_action_clean(scanner) -> None:
    """Smoke test against the kit's own check action — same shape as
    dist-check, also flagged by the old detector."""
    target = REPO_ROOT / ".github" / "actions" / "check" / "action.yml"
    if not target.exists():  # pragma: no cover
        pytest.skip(f"{target} not present in this checkout")
    assert scanner.file_has_unsafe_run_interp(target.read_text(encoding="utf-8")) is False
