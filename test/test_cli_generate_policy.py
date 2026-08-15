"""Tests for the CLI's `generate-policy` subcommand."""

from __future__ import annotations

import io
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


def test_code_scan_workflow_not_in_install_all() -> None:
    """`code-scan-workflow` MUST be opt-in.

    `install --all` already scaffolds `codeql-workflow` (standalone
    CodeQL). Adding `code-scan-workflow` to the bulk set would
    silently install two overlapping CodeQL paths on every fresh
    bootstrap. Treat it like `scorecard-workflow` / `security-devops-
    workflow` \u2014 explicit opt-in by name.
    """
    from marketplace_kit.cli import INSTALL_ALL_KINDS

    assert "code-scan-workflow" not in INSTALL_ALL_KINDS


def test_code_scan_workflow_template_shape(tmp_path: Path) -> None:
    """The rendered template must call the hub reusable and parse as YAML."""
    import yaml

    rc, out, err = _run(
        [
            "generate-policy", "code-scan-workflow",
            "--owner", "acme",
            "--repo", "widget",
            "--project-name", "Widget",
            "--stdout",
        ]
    )
    assert rc == 0, err

    # Hub reusable is the source of truth for SHA pins; the caller
    # must invoke it by canonical path.
    assert (
        "blackoutsecure/bos-automation-hub/.github/workflows/"
        "security-scan.yml" in out
    ), "rendered template does not reference the hub reusable"

    # Placeholder substitution still applied to the header comment.
    assert "acme" in out
    assert "Widget" in out
    assert "{{owner}}" not in out
    assert "{{project_name}}" not in out

    # YAML parses; declares the expected job + permissions surface.
    doc = yaml.safe_load(out)
    assert isinstance(doc, dict)
    assert "scan" in doc["jobs"]
    assert "preflight" in doc["jobs"]
    # The CodeQL-language input must be a JSON-array STRING (parsed by
    # the reusable via fromJSON), not a YAML list \u2014 see template header.
    cq_langs = doc["jobs"]["scan"]["with"]["codeql_languages"]
    assert isinstance(cq_langs, str), (
        f"codeql_languages must be a string, got {type(cq_langs).__name__}"
    )


def test_mutual_exclusion_warning_on_generate_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scaffolding `code-scan-workflow` next to an existing codeql.yml warns."""
    monkeypatch.chdir(tmp_path)

    # Pre-create the standalone CodeQL workflow at its canonical path.
    codeql_path = tmp_path / ".github" / "workflows" / "codeql.yml"
    codeql_path.parent.mkdir(parents=True)
    codeql_path.write_text("name: codeql\n", encoding="utf-8")

    rc, _, err = _run([
        "generate-policy", "code-scan-workflow",
        "--owner", "acme",
        "--output", str(tmp_path / "out.yml"),
    ])
    assert rc == 0, err
    assert "warning" in err.lower()
    assert "codeql-workflow" in err
    assert "code-scan-workflow" in err


def test_mutual_exclusion_warning_symmetric(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scaffolding `codeql-workflow` next to an existing bos-launchpad-code-scan.yml warns."""
    monkeypatch.chdir(tmp_path)

    scan_path = tmp_path / ".github" / "workflows" / "bos-launchpad-code-scan.yml"
    scan_path.parent.mkdir(parents=True)
    scan_path.write_text("name: security-scan\n", encoding="utf-8")

    rc, _, err = _run([
        "generate-policy", "codeql-workflow",
        "--owner", "acme",
        "--output", str(tmp_path / "out.yml"),
    ])
    assert rc == 0, err
    assert "warning" in err.lower()
    assert "code-scan-workflow" in err


def test_no_mutual_exclusion_warning_when_sibling_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No warning fires when neither sibling exists \u2014 clean install case."""
    monkeypatch.chdir(tmp_path)

    rc, _, err = _run([
        "generate-policy", "code-scan-workflow",
        "--owner", "acme",
        "--output", str(tmp_path / "out.yml"),
    ])
    assert rc == 0, err
    assert "warning" not in err.lower()


@pytest.mark.parametrize("kind", [
    "codeql-workflow",
    "scorecard-workflow",
    "security-devops-workflow",
    "code-scan-workflow",
])
def test_generated_workflows_honour_default_runner(kind: str) -> None:
    """Generated workflows must resolve the org runner, not pin ubuntu."""
    rc, out, err = _run(["generate-policy", kind, "--owner", "acme", "--stdout"])
    assert rc == 0, err
    assert "vars.DEFAULT_RUNNER" in out
    assert "'ubuntu-latest'" in out, "fallback label must remain"
    assert "runs-on: ubuntu-latest" not in out
