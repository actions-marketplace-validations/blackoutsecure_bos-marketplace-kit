"""Tests for the CLI's `generate-policy` subcommand."""

from __future__ import annotations

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from marketplace_kit.cli import POLICY_KINDS, main


def _run(args: list[str]) -> tuple[int, str, str]:
    """Invoke the CLI and capture stdout, stderr, and exit code."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = main(args)
    return rc, out.getvalue(), err.getvalue()


def test_generate_policy_list() -> None:
    rc, out, _ = _run(["generate-policy", "list"])
    assert rc == 0
    for kind in POLICY_KINDS:
        assert kind in out


@pytest.mark.parametrize("kind", sorted(POLICY_KINDS))
def test_generate_policy_stdout_renders_each_kind(kind: str) -> None:
    rc, out, err = _run(
        [
            "generate-policy", kind,
            "--owner", "acme",
            "--repo", "widget",
            "--email", "sec@acme.example",
            "--project-name", "widget",
            "--stdout",
        ]
    )
    assert rc == 0, err
    # Each template should produce non-empty output...
    assert out.strip(), f"empty output for kind {kind!r}"
    # ...and substitute placeholders. (Not every template uses every
    # placeholder, so just check at least one substitution happened
    # and no raw `{{owner}}` etc. leak through.)
    assert "{{owner}}" not in out
    assert "{{repo_name}}" not in out
    assert "{{contact_email}}" not in out
    assert "{{project_name}}" not in out


def test_generate_policy_unknown_kind_exits_nonzero() -> None:
    rc, _, err = _run(["generate-policy", "no-such-thing"])
    assert rc != 0
    assert "no-such-thing" in err


def test_generate_policy_writes_file(tmp_path: Path) -> None:
    out_path = tmp_path / "SECURITY.md"
    rc, _, err = _run(
        [
            "generate-policy", "security",
            "--owner", "blackoutsecure",
            "--repo", "bos-marketplace-kit",
            "--email", "security@blackoutsecure.com",
            "--output", str(out_path),
        ]
    )
    assert rc == 0, err
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "blackoutsecure" in text
    assert "{{" not in text


def test_generate_policy_refuses_overwrite_without_force(tmp_path: Path) -> None:
    out_path = tmp_path / "SECURITY.md"
    out_path.write_text("pre-existing\n", encoding="utf-8")
    rc, _, err = _run(
        [
            "generate-policy", "security",
            "--output", str(out_path),
        ]
    )
    assert rc != 0
    assert "exists" in err
    # File untouched.
    assert out_path.read_text(encoding="utf-8") == "pre-existing\n"


def test_generate_policy_force_overwrites(tmp_path: Path) -> None:
    out_path = tmp_path / "SECURITY.md"
    out_path.write_text("pre-existing\n", encoding="utf-8")
    rc, _, _ = _run(
        [
            "generate-policy", "security",
            "--output", str(out_path),
            "--force",
        ]
    )
    assert rc == 0
    text = out_path.read_text(encoding="utf-8")
    assert "pre-existing" not in text
    assert "Security Policy" in text or "SECURITY" in text.upper()


def test_generate_policy_default_repo_is_cwd_basename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When --repo isn't given, the CWD basename should be substituted."""
    target = tmp_path / "my-cool-action"
    target.mkdir()
    monkeypatch.chdir(target)
    rc, out, _ = _run(["generate-policy", "security", "--owner", "acme", "--stdout"])
    assert rc == 0
    assert "my-cool-action" in out


def test_action_yml_template_self_validates(tmp_path: Path) -> None:
    """The scaffolded `action.yml` MUST pass every kit check cleanly.

    Otherwise scaffolding a fresh manifest would fail the kit's own
    pre-publish gate — including MP010 (description <= 125 chars).
    """
    import yaml

    from marketplace_kit.cli import _run_checks

    out_path = tmp_path / "action.yml"
    rc, _, err = _run(
        [
            "generate-policy", "action-yml",
            "--owner", "acme",
            "--repo", "widget",
            "--project-name", "Widget",
            "--output", str(out_path),
        ]
    )
    assert rc == 0, err
    assert out_path.exists()

    manifest = yaml.safe_load(out_path.read_text(encoding="utf-8"))
    assert isinstance(manifest, dict)

    # The rendered template must pass every check.
    results = _run_checks(manifest)
    fails = [r for r in results if r.status == "fail"]
    assert not fails, (
        "scaffolded action.yml failed kit checks:\n"
        + "\n".join(f"  {r.rule_id}: {r.message}" for r in fails)
    )

    # Sanity: MP010 specifically must report a pass (not skip), i.e.
    # the template includes a non-empty description under the limit.
    mp010 = [r for r in results if r.rule_id == "MP010"]
    assert mp010, "MP010 did not fire on the scaffolded template"
    assert mp010[0].status == "pass", (
        f"MP010 expected pass, got {mp010[0].status}: {mp010[0].message}"
    )


def test_action_yml_not_in_install_all(tmp_path: Path) -> None:
    """`install --all` must NOT scaffold action.yml.

    Overwriting a real Marketplace manifest with a template would be
    destructive; the kind is opt-in only.
    """
    from marketplace_kit.cli import INSTALL_ALL_KINDS

    assert "action-yml" not in INSTALL_ALL_KINDS
