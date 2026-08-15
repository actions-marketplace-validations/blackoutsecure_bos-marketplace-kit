"""Tests for the layered JSON configuration cascade.

Covers the four tiers (runtime defaults -> built-in marketplace config
-> optional global config -> optional repo config), the workflow-input
override layer, and the validation rules that keep a malformed config
from reaching `run.sh`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketplace_kit import config


def _write(root: Path, relpath: str, payload: dict) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tier 1 — built-in marketplace config
# ---------------------------------------------------------------------------

def test_marketplace_config_covers_every_option() -> None:
    section = config.load_marketplace_config()
    missing = [o.key for o in config.OPTIONS if o.key not in section]
    assert not missing, f"marketplace-config.json is missing: {missing}"


def test_marketplace_config_values_all_validate() -> None:
    for key, value in config.load_marketplace_config().items():
        config.coerce(key, value)


def test_defaults_come_from_marketplace_config(tmp_path: Path) -> None:
    values = config.resolve(tmp_path).values
    assert values["require_security"] == "warn"
    assert values["require_scorecard"] == "skip"
    assert values["repo_description_max_length"] == 350
    assert values["workflow_dir"] == ".github/workflows"


def test_marketplace_config_can_be_disabled_by_repo_config(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"use_marketplace_config": False}})
    resolved = config.resolve(tmp_path)
    assert resolved.use_marketplace is False
    # Falls back to the conservative runtime defaults.
    assert resolved.values["require_security"] == "skip"
    assert resolved.values["require_dependabot"] == "skip"


def test_marketplace_config_can_be_forced_on(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"use_marketplace_config": False}})
    resolved = config.resolve(tmp_path, use_marketplace_config="true")
    assert resolved.use_marketplace is True
    assert resolved.values["require_security"] == "warn"


# ---------------------------------------------------------------------------
# Tier 2/3 — global + repo configs
# ---------------------------------------------------------------------------

def test_global_config_is_auto_discovered(tmp_path: Path) -> None:
    _write(tmp_path, config.GLOBAL_CONFIG_PATH,
           {"marketplace_kit": {"require_scorecard": "warn"}})
    resolved = config.resolve(tmp_path)
    assert resolved.values["require_scorecard"] == "warn"
    assert any(config.GLOBAL_CONFIG_PATH in t for t in resolved.tiers)


def test_repo_config_overrides_global(tmp_path: Path) -> None:
    _write(tmp_path, config.GLOBAL_CONFIG_PATH,
           {"marketplace_kit": {"require_security": "fail",
                                "require_codeql": "fail"}})
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_security": "skip"}})
    values = config.resolve(tmp_path).values
    assert values["require_security"] == "skip"
    assert values["require_codeql"] == "fail"


def test_global_config_can_be_disabled(tmp_path: Path) -> None:
    _write(tmp_path, config.GLOBAL_CONFIG_PATH,
           {"marketplace_kit": {"require_scorecard": "fail"}})
    values = config.resolve(tmp_path, use_global_config="false").values
    assert values["require_scorecard"] == "skip"


def test_required_global_config_missing_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError):
        config.resolve(tmp_path, use_global_config="true")


def test_repo_config_discovery_order(tmp_path: Path) -> None:
    _write(tmp_path, "marketplace-kit.json",
           {"marketplace_kit": {"require_yamllint": "fail"}})
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_yamllint": "warn"}})
    values = config.resolve(tmp_path).values
    assert values["require_yamllint"] == "warn"


def test_hub_conventional_path_is_preferred_over_legacy(tmp_path: Path) -> None:
    """Hub kickers pass `.github/bos-universal-config.json` explicitly."""
    _write(tmp_path, ".github/workflow-configs/bos-universal-config.json",
           {"marketplace_kit": {"require_yamllint": "fail"}})
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_yamllint": "warn"}})
    resolved = config.resolve(tmp_path)
    assert resolved.values["require_yamllint"] == "warn"
    assert any(tier.endswith(".github/bos-universal-config.json")
               for tier in resolved.tiers)


def test_legacy_path_still_works_alone(tmp_path: Path) -> None:
    _write(tmp_path, ".github/workflow-configs/bos-universal-config.json",
           {"marketplace_kit": {"require_yamllint": "fail"}})
    assert config.resolve(tmp_path).values["require_yamllint"] == "fail"


def test_explicit_config_path_must_exist(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError):
        config.resolve(tmp_path, repo_config_path="nope.json")


def test_document_without_section_is_treated_as_the_section(tmp_path: Path) -> None:
    _write(tmp_path, "marketplace-kit.json", {"require_support": "fail"})
    assert config.resolve(tmp_path).values["require_support"] == "fail"


def test_foreign_sections_are_ignored(tmp_path: Path) -> None:
    """A universal config with only other tools' sections changes nothing."""
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace": {"enabled": True},
            "managed_file_sync": {"services": ["common"]}})
    values = config.resolve(tmp_path).values
    assert values["require_security"] == "warn"


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_from_the_future": "fail",
                                "require_support": "warn"}})
    assert config.resolve(tmp_path).values["require_support"] == "warn"


# ---------------------------------------------------------------------------
# skip_checks merge semantics
# ---------------------------------------------------------------------------

def test_skip_checks_append_across_tiers(tmp_path: Path) -> None:
    _write(tmp_path, config.GLOBAL_CONFIG_PATH,
           {"marketplace_kit": {"skip_checks": ["OP003"]}})
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"skip_checks": ["SC002", "OP003"]}})
    assert config.resolve(tmp_path).values["skip_checks"] == ("OP003", "SC002")


def test_skip_checks_can_replace_instead_of_append(tmp_path: Path) -> None:
    _write(tmp_path, config.GLOBAL_CONFIG_PATH,
           {"marketplace_kit": {"skip_checks": ["OP003"]}})
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"use_marketplace_skip_checks": False,
                                "skip_checks": ["SC002"]}})
    assert config.resolve(tmp_path).values["skip_checks"] == ("SC002",)


def test_skip_checks_accepts_a_comma_separated_string(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"skip_checks": "OP003, SC002"}})
    assert config.resolve(tmp_path).values["skip_checks"] == ("OP003", "SC002")


# ---------------------------------------------------------------------------
# Tier 4 — workflow inputs
# ---------------------------------------------------------------------------

def test_workflow_inputs_win(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_security": "skip"}})
    values = config.resolve(
        tmp_path, overrides={"require_security": "fail"}).values
    assert values["require_security"] == "fail"


def test_empty_workflow_inputs_fall_through(tmp_path: Path) -> None:
    values = config.resolve(
        tmp_path, overrides={"require_security": "", "fail_on_warning": None}).values
    assert values["require_security"] == "warn"
    assert values["fail_on_warning"] is False


def test_empty_workflow_dir_is_an_explicit_skip(tmp_path: Path) -> None:
    values = config.resolve(tmp_path, overrides={"workflow_dir": ""}).values
    assert values["workflow_dir"] == ""


def test_auto_sentinel_is_not_an_override() -> None:
    overrides = config._overrides_from_env({
        "MK_IN_WORKFLOW_DIR": "auto",
        "MK_IN_REQUIRE_SECURITY": "fail",
        "MK_IN_REQUIRE_CODEQL": "",
    })
    assert overrides == {"require_security": "fail"}


def test_env_overrides_include_explicit_empty_workflow_dir() -> None:
    overrides = config._overrides_from_env({"MK_IN_WORKFLOW_DIR": ""})
    assert overrides == {"workflow_dir": ""}


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("key,value", [
    ("require_security", "maybe"),
    ("require_security", True),
    ("fail_on_warning", "yes"),
    ("repo_description_max_length", -1),
    ("repo_description_max_length", "abc"),
    ("community_health_source", "elsewhere"),
    ("action_yml_path", "/etc/passwd"),
    ("action_yml_path", "../outside/action.yml"),
    ("org_health_repo", "acme/.github\nrm -rf /"),
    ("skip_checks", {"OP003": True}),
])
def test_invalid_values_are_rejected(key: str, value: object) -> None:
    with pytest.raises(config.ConfigError):
        config.coerce(key, value)


def test_bad_json_is_reported_with_the_path(tmp_path: Path) -> None:
    path = tmp_path / ".github" / "bos-universal-config.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(config.ConfigError) as exc:
        config.resolve(tmp_path)
    assert "bos-universal-config.json" in str(exc.value)


def test_non_object_section_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": ["nope"]})
    with pytest.raises(config.ConfigError):
        config.resolve(tmp_path)


def test_invalid_tristate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(config.ConfigError):
        config.resolve(tmp_path, use_global_config="yes")


# ---------------------------------------------------------------------------
# Env rendering — the contract with run.sh
# ---------------------------------------------------------------------------

def test_env_names_are_unique() -> None:
    envs = [o.env for o in config.OPTIONS]
    assert len(envs) == len(set(envs))


def test_as_env_renders_shell_friendly_scalars(tmp_path: Path) -> None:
    env = config.as_env(config.resolve(tmp_path).values)
    assert env["FAIL_ON_WARN"] == "false"
    assert env["CHECK_ORG_HEALTH"] == "true"
    assert env["REPO_DESC_MAX_LEN"] == "350"
    assert env["SKIP_CHECKS"] == ""
    assert all(isinstance(v, str) for v in env.values())


def test_main_appends_to_github_env(tmp_path: Path, monkeypatch) -> None:
    github_env = tmp_path / "github.env"
    monkeypatch.setenv("MK_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(github_env))
    monkeypatch.setenv("MK_IN_REQUIRE_SECURITY", "fail")
    assert config.main([]) == 0
    written = dict(
        line.split("=", 1)
        for line in github_env.read_text(encoding="utf-8").splitlines()
    )
    assert written["REQ_SECURITY"] == "fail"
    assert written["REQ_CODE_OF_CONDUCT"] == "warn"


def test_main_reports_config_errors_as_exit_2(tmp_path: Path, monkeypatch) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_security": "sometimes"}})
    monkeypatch.setenv("MK_CONFIG_ROOT", str(tmp_path))
    monkeypatch.setenv("GITHUB_ENV", str(tmp_path / "github.env"))
    assert config.main([]) == 2


# ---------------------------------------------------------------------------
# Composite-action contract
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_check_composite_exposes_every_option_as_an_input() -> None:
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / ".github" / "actions" / "check" / "action.yml")
        .read_text(encoding="utf-8")
    )
    inputs = manifest["inputs"]
    for option in config.OPTIONS:
        assert option.key in inputs, f"check action.yml lacks input {option.key!r}"


def test_check_composite_passes_every_option_to_the_resolver() -> None:
    import yaml

    manifest = yaml.safe_load(
        (REPO_ROOT / ".github" / "actions" / "check" / "action.yml")
        .read_text(encoding="utf-8")
    )
    step = next(s for s in manifest["runs"]["steps"] if s.get("id") == "config")
    for option in config.OPTIONS:
        name = f"MK_IN_{option.key.upper()}"
        assert name in step["env"], f"config step lacks {name}"


def test_config_driven_inputs_use_the_sentinel_default() -> None:
    import yaml

    for relpath in ("action.yml", ".github/actions/check/action.yml"):
        manifest = yaml.safe_load(
            (REPO_ROOT / relpath).read_text(encoding="utf-8"))
        for option in config.OPTIONS:
            spec = manifest["inputs"].get(option.key)
            if spec is None:
                continue
            sentinel = "auto" if option.key in config.ALLOW_EMPTY_OVERRIDE else ""
            assert spec.get("default", "") == sentinel, (
                f"{relpath}: input {option.key!r} must default to "
                f"{sentinel!r} so the config cascade applies"
            )


# ---------------------------------------------------------------------------
# Profiles — the opt-in stronger recommendation
# ---------------------------------------------------------------------------

def test_baseline_is_the_default_profile(tmp_path: Path) -> None:
    values = config.resolve(tmp_path).values
    assert values["profile"] == "baseline"
    assert values["require_security"] == "warn"


def test_strict_profile_promotes_free_controls(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"profile": "strict"}})
    values = config.resolve(tmp_path).values
    assert values["require_security"] == "fail"
    assert values["require_codeql"] == "fail"
    assert values["require_ghas_secret_scanning"] == "fail"
    assert values["require_repo_topics"] == "fail"


def test_repo_config_can_relax_a_rule_on_top_of_strict(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"profile": "strict",
                                "require_codeql": "warn"}})
    values = config.resolve(tmp_path).values
    assert values["require_codeql"] == "warn"
    assert values["require_security"] == "fail"


def test_strict_profile_can_come_from_a_workflow_input(tmp_path: Path) -> None:
    values = config.resolve(tmp_path, overrides={"profile": "strict"}).values
    assert values["require_security"] == "fail"


def test_unknown_profile_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"profile": "paranoid"}})
    with pytest.raises(config.ConfigError):
        config.resolve(tmp_path)


# ---------------------------------------------------------------------------
# enable_security_scan
# ---------------------------------------------------------------------------

def test_security_scan_is_on_by_default(tmp_path: Path) -> None:
    resolved = config.resolve(tmp_path)
    assert resolved.values["enable_security_scan"] is True
    assert resolved.values["require_security"] == "warn"
    assert resolved.suppressed == {}


def test_disabling_the_security_scan_skips_the_whole_group(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"enable_security_scan": False}})
    resolved = config.resolve(tmp_path)
    for key in config.SECURITY_SCAN_RULES:
        assert resolved.values[key] == "skip", key
    assert "require_security" in resolved.suppressed


def test_disabling_the_security_scan_leaves_other_rules_alone(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"enable_security_scan": False}})
    values = config.resolve(tmp_path).values
    assert values["require_code_of_conduct"] == "warn"
    assert values["require_repo_description"] == "warn"


def test_security_scan_can_be_disabled_from_a_workflow_input(tmp_path: Path) -> None:
    values = config.resolve(
        tmp_path, overrides={"enable_security_scan": "false"}).values
    assert values["require_codeql"] == "skip"


# ---------------------------------------------------------------------------
# Deferral to bos-code-scanning-kit
# ---------------------------------------------------------------------------

def _workflow_calling_code_scanning_kit(root: Path) -> None:
    path = root / ".github" / "workflows" / "scan.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "jobs:\n  scan:\n    steps:\n"
        f"      - uses: {config.CODE_SCANNING_KIT}@v1\n",
        encoding="utf-8")


def test_auto_defers_when_the_code_scanning_kit_is_wired_up(tmp_path: Path) -> None:
    _workflow_calling_code_scanning_kit(tmp_path)
    resolved = config.resolve(tmp_path)
    for key in config.CODE_SCANNING_KIT_RULES:
        assert resolved.values[key] == "skip", key
    # Only rules that were actually enabled get a suppression reason.
    assert config.CODE_SCANNING_KIT_RULES["require_ghas_code_scanning"] in \
        resolved.suppressed["require_ghas_code_scanning"]
    assert "require_security_devops" not in resolved.suppressed


def test_auto_does_not_defer_without_the_code_scanning_kit(tmp_path: Path) -> None:
    resolved = config.resolve(tmp_path)
    assert resolved.values["require_ghas_code_scanning"] == "warn"
    assert resolved.suppressed == {}


def test_deferral_can_be_forced_on(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"defer_to_code_scanning_kit": True}})
    values = config.resolve(tmp_path).values
    assert values["require_ghas_secret_scanning"] == "skip"


def test_deferral_can_be_forced_off(tmp_path: Path) -> None:
    _workflow_calling_code_scanning_kit(tmp_path)
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"defer_to_code_scanning_kit": "false"}})
    resolved = config.resolve(tmp_path)
    assert resolved.values["require_ghas_code_scanning"] == "warn"
    assert resolved.suppressed == {}


def test_deferral_leaves_marketplace_only_rules_alone(tmp_path: Path) -> None:
    """The kits are complementary: MP/OP/CH/LT/RM stay with this kit."""
    _workflow_calling_code_scanning_kit(tmp_path)
    values = config.resolve(tmp_path).values
    assert values["require_security"] == "warn"
    assert values["require_code_of_conduct"] == "warn"
    assert values["require_repo_description"] == "warn"


def test_deferral_does_not_claim_scorecard(tmp_path: Path) -> None:
    """SR001 has no code-scanning-kit equivalent, so it is never deferred."""
    assert "require_scorecard" not in config.CODE_SCANNING_KIT_RULES


def test_uses_code_scanning_kit_detects_only_real_calls(tmp_path: Path) -> None:
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs: {}\n", encoding="utf-8")
    assert config.uses_code_scanning_kit(tmp_path) is False
    _workflow_calling_code_scanning_kit(tmp_path)
    assert config.uses_code_scanning_kit(tmp_path) is True


# ---------------------------------------------------------------------------
# Job-summary provenance
# ---------------------------------------------------------------------------

def test_provenance_env_reports_identity_and_cascade(tmp_path: Path) -> None:
    _write(tmp_path, ".github/bos-universal-config.json",
           {"marketplace_kit": {"require_yamllint": "fail"}})
    env = config.provenance_env(config.resolve(tmp_path))
    assert env["MK_KIT_NAME"] == "bos-marketplace-kit"
    assert env["MK_KIT_VERSION"]
    assert env["MK_KIT_METADATA_SOURCE"] in {"distribution", "bundled"}
    assert env["MK_CONFIG_SOURCE"].endswith(".github/bos-universal-config.json")
    assert "marketplace config" in env["MK_CONFIG_TIERS"]


def test_provenance_env_values_are_single_line(tmp_path: Path) -> None:
    """$GITHUB_ENV is appended without heredoc quoting."""
    _workflow_calling_code_scanning_kit(tmp_path)
    env = config.provenance_env(config.resolve(tmp_path))
    assert env["MK_CONFIG_SUPPRESSED"], "deferral should be reported"
    for value in env.values():
        assert "\n" not in value
