"""Tests for the CLI's `install` subcommand.

`install` is a thin wrapper over `generate-policy` that writes one or
every recommended policy file at its canonical repo-relative path.
The policy-template substitution itself is covered by
`test_cli_generate_policy.py`; here we focus on the install-specific
behaviour (write/skip/force/dry-run, --all, path resolution).
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from marketplace_kit.cli import INSTALL_ALL_KINDS, POLICY_KINDS, main


def _run(args: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(args)
    return rc, out.getvalue(), err.getvalue()


# --- happy paths -----------------------------------------------------------


def test_install_single_kind_writes_canonical_path(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "codeql-workflow",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    out_path = tmp_path / POLICY_KINDS["codeql-workflow"].default_out
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    # Template placeholders are substituted by _render_policy and the
    # canonical CodeQL workflow shape is intact.
    assert "{{owner}}" not in text
    assert "github/codeql-action" in text
    # Summary line is on stderr (we keep stdout reserved for piping).
    assert "install summary:" in err
    assert "1 written" in err


def test_install_all_writes_every_recommended_kind(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "--all",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    for kind in INSTALL_ALL_KINDS:
        out_path = tmp_path / POLICY_KINDS[kind].default_out
        assert out_path.exists(), f"{kind} not written"
    assert f"{len(INSTALL_ALL_KINDS)} written" in err
    assert "0 overwritten" in err
    assert "0 skipped" in err


def test_install_defaults_to_cwd_when_no_cwd_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    rc, _, err = _run(["install", "dependabot", "--owner", "acme"])
    assert rc == 0, err
    assert (tmp_path / ".github" / "dependabot.yml").exists()


# --- safety: refuse-if-exists ---------------------------------------------


def test_install_skips_existing_files_without_force(tmp_path: Path) -> None:
    target = tmp_path / POLICY_KINDS["dependabot"].default_out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "dependabot",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    # File untouched.
    assert target.read_text(encoding="utf-8") == "pre-existing\n"
    assert "[skip" in err
    assert "1 skipped" in err


def test_install_force_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / POLICY_KINDS["dependabot"].default_out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "dependabot",
        "--owner", "acme",
        "--cwd", str(tmp_path),
        "--force",
    ])
    assert rc == 0, err
    text = target.read_text(encoding="utf-8")
    assert "pre-existing" not in text
    assert "github-actions" in text  # canonical dependabot template content
    assert "[force" in err
    assert "1 overwritten" in err


def test_install_all_mixes_write_and_skip(tmp_path: Path) -> None:
    # Pre-populate one of the install-all kinds; the others should
    # still install cleanly, and the skipped one should not be touched.
    pre_kind = "security"
    pre_path = tmp_path / POLICY_KINDS[pre_kind].default_out
    pre_path.parent.mkdir(parents=True, exist_ok=True)
    pre_path.write_text("DO NOT TOUCH\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "--all",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    assert pre_path.read_text(encoding="utf-8") == "DO NOT TOUCH\n"
    expected_written = len(INSTALL_ALL_KINDS) - 1
    assert f"{expected_written} written" in err
    assert "1 skipped" in err


# --- dry-run --------------------------------------------------------------


def test_install_dry_run_writes_nothing(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "--all",
        "--owner", "acme",
        "--cwd", str(tmp_path),
        "--dry-run",
    ])
    assert rc == 0, err
    for kind in INSTALL_ALL_KINDS:
        out_path = tmp_path / POLICY_KINDS[kind].default_out
        assert not out_path.exists(), f"{kind} was written despite --dry-run"
    assert "would install summary:" in err
    assert "dry-run: no files modified." in err
    assert "[dry-write" in err


def test_install_dry_run_reports_force_on_existing(tmp_path: Path) -> None:
    target = tmp_path / POLICY_KINDS["dependabot"].default_out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("pre-existing\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "dependabot",
        "--owner", "acme",
        "--cwd", str(tmp_path),
        "--force",
        "--dry-run",
    ])
    assert rc == 0, err
    assert target.read_text(encoding="utf-8") == "pre-existing\n"
    assert "[dry-force" in err
    assert "1 overwritten" in err


# --- error paths -----------------------------------------------------------


def test_install_requires_kind_or_all() -> None:
    rc, _, err = _run(["install"])
    assert rc != 0
    assert "KIND is required" in err


def test_install_rejects_both_kind_and_all(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "dependabot", "--all",
        "--cwd", str(tmp_path),
    ])
    assert rc != 0
    assert "not both" in err


def test_install_rejects_unknown_kind(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "no-such-thing",
        "--cwd", str(tmp_path),
    ])
    assert rc != 0
    assert "no-such-thing" in err


def test_install_rejects_nonexistent_cwd(tmp_path: Path) -> None:
    rc, _, err = _run([
        "install", "dependabot",
        "--cwd", str(tmp_path / "does-not-exist"),
    ])
    assert rc != 0
    assert "not a directory" in err


# --- every recommended kind round-trips ------------------------------------


@pytest.mark.parametrize("kind", INSTALL_ALL_KINDS)
def test_install_each_recommended_kind_writes_clean_template(
    kind: str, tmp_path: Path,
) -> None:
    rc, _, err = _run([
        "install", kind,
        "--owner", "acme",
        "--repo", "widget",
        "--email", "sec@acme.example",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    out_path = tmp_path / POLICY_KINDS[kind].default_out
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    # Template placeholders are fully substituted. (We can't assert
    # the absence of any `{{` because GitHub Actions expression syntax
    # — `${{ matrix.language }}`, `${{ github.workflow }}`, etc. —
    # legitimately uses double braces in the CodeQL / yamllint
    # templates. Restrict the assertion to the kit's own placeholder
    # vocabulary.)
    for placeholder in ("{{owner}}", "{{repo_name}}",
                        "{{contact_email}}", "{{project_name}}"):
        assert placeholder not in text, (
            f"placeholder {placeholder} not substituted for kind {kind!r}"
        )


# --- mutual-exclusion (codeql-workflow vs code-scan-workflow) -------------


def test_install_code_scan_warns_when_codeql_present(tmp_path: Path) -> None:
    """`install code-scan-workflow` warns when codeql.yml already exists."""
    codeql_path = tmp_path / POLICY_KINDS["codeql-workflow"].default_out
    codeql_path.parent.mkdir(parents=True, exist_ok=True)
    codeql_path.write_text("name: codeql\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "code-scan-workflow",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    # New file landed at its canonical path.
    assert (tmp_path / POLICY_KINDS["code-scan-workflow"].default_out).exists()
    # Standalone codeql.yml is untouched.
    assert codeql_path.read_text(encoding="utf-8") == "name: codeql\n"
    # Warning surfaced naming both sides of the conflict.
    assert "warning" in err.lower()
    assert "codeql-workflow" in err
    assert "code-scan-workflow" in err


def test_install_codeql_warns_when_code_scan_present(tmp_path: Path) -> None:
    """Symmetric: `install codeql-workflow` warns when bos-launchpad-code-scan.yml exists."""
    scan_path = tmp_path / POLICY_KINDS["code-scan-workflow"].default_out
    scan_path.parent.mkdir(parents=True, exist_ok=True)
    scan_path.write_text("name: security-scan\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "codeql-workflow",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    assert "warning" in err.lower()
    assert "code-scan-workflow" in err


def test_install_no_warning_when_sibling_absent(tmp_path: Path) -> None:
    """No warning fires for the clean install case."""
    rc, _, err = _run([
        "install", "code-scan-workflow",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    assert "warning" not in err.lower()


def test_install_no_warning_on_skip(tmp_path: Path) -> None:
    """When the target already exists (skip), no overlap warning fires.

    The user has already seen the conflict at the original install
    time; surfacing it again on every re-run would be noisy.
    """
    # Both files pre-exist \u2014 we'd otherwise warn loudly.
    codeql_path = tmp_path / POLICY_KINDS["codeql-workflow"].default_out
    codeql_path.parent.mkdir(parents=True, exist_ok=True)
    codeql_path.write_text("name: codeql\n", encoding="utf-8")

    scan_path = tmp_path / POLICY_KINDS["code-scan-workflow"].default_out
    scan_path.write_text("name: security-scan\n", encoding="utf-8")

    rc, _, err = _run([
        "install", "code-scan-workflow",
        "--owner", "acme",
        "--cwd", str(tmp_path),
    ])
    assert rc == 0, err
    # Skipped (target exists, no --force), so no warning either.
    assert "[skip" in err
    assert "warning" not in err.lower()
