"""Tests for the Marketplace auto-publish relevance-scoring gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketplace_kit import config, relevance


def _write(root: Path, relpath: str, payload: dict) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Deterministic scoring
# ---------------------------------------------------------------------------

def test_action_yml_change_scores_highest() -> None:
    score, breakdown = relevance.score_changed_files(["action.yml"])
    assert score == 40
    assert breakdown[0].pattern == "action.yml"


def test_test_only_change_scores_low_even_with_many_files() -> None:
    files = [f"test/test_case_{i}.py" for i in range(50)]
    score, _ = relevance.score_changed_files(files)
    assert score == 3


def test_score_is_the_max_not_the_sum() -> None:
    score, _ = relevance.score_changed_files(["action.yml", "README.md", "test/test_x.py"])
    assert score == 40  # not 40 + 15 + 3


def test_unmatched_path_gets_the_low_default_weight() -> None:
    score, breakdown = relevance.score_changed_files(["some/random/file.xyz"])
    assert score == relevance._DEFAULT_OTHER_WEIGHT
    assert breakdown[0].pattern is None


def test_no_changed_files_scores_zero() -> None:
    score, breakdown = relevance.score_changed_files([])
    assert score == 0
    assert breakdown == []


def test_test_files_are_not_misclassified_as_generic_python_source() -> None:
    """`test/foo.py` must hit `test/**` (weight 3), not the generic `*.py` (25).

    Regression guard: `fnmatch` treats `*` as matching `/` too, so pattern
    order in the weight table matters — this would silently regress to 25
    if the generic extension globs were ever moved before path-prefix ones.
    """
    score, breakdown = relevance.score_changed_files(["test/foo.py"])
    assert score == 3
    assert breakdown[0].pattern == "test/**"


def test_docker_action_repo_type_weighs_dockerfile_like_action_yml() -> None:
    score, breakdown = relevance.score_changed_files(
        ["Dockerfile"], repo_type="docker-action"
    )
    assert score == 40
    assert breakdown[0].pattern == "Dockerfile"


def test_dockerfile_is_not_special_for_the_default_profile() -> None:
    score, breakdown = relevance.score_changed_files(["Dockerfile"], repo_type="composite-action")
    assert breakdown[0].pattern is None  # falls through to the "other" default


def test_library_repo_type_weighs_any_python_module_highly() -> None:
    score, _ = relevance.score_changed_files(["mypkg/core.py"], repo_type="library")
    assert score == 35


def test_weight_overrides_win_over_the_profile_default() -> None:
    score, breakdown = relevance.score_changed_files(
        ["README.md"], weight_overrides={"README.md": 99}
    )
    assert score == 99
    assert breakdown[0].weight == 99


def test_unknown_repo_type_is_rejected() -> None:
    with pytest.raises(ValueError):
        relevance.score_changed_files(["x"], repo_type="not-a-real-type")


# ---------------------------------------------------------------------------
# Persisted state
# ---------------------------------------------------------------------------

def test_state_round_trips_through_disk(tmp_path: Path) -> None:
    path = tmp_path / "score.json"
    state = relevance.ScoreState(running_total=42)
    state.record(sha="abc123", at="2026-01-01T00:00:00Z", diff_score=42, source="local", published=False)
    state.save(path)

    loaded = relevance.ScoreState.load(path)
    assert loaded.running_total == 42
    assert loaded.history[-1]["sha"] == "abc123"


def test_missing_state_file_loads_as_zero(tmp_path: Path) -> None:
    state = relevance.ScoreState.load(tmp_path / "does-not-exist.json")
    assert state.running_total == 0
    assert state.history == []


def test_corrupt_state_file_loads_as_zero_instead_of_raising(tmp_path: Path) -> None:
    path = tmp_path / "score.json"
    path.write_text("not json", encoding="utf-8")
    state = relevance.ScoreState.load(path)
    assert state.running_total == 0


def test_history_is_capped_at_twenty_entries(tmp_path: Path) -> None:
    state = relevance.ScoreState()
    for i in range(30):
        state.record(sha=str(i), at="", diff_score=1, source="local", published=False)
    path = tmp_path / "score.json"
    state.save(path)
    assert len(relevance.ScoreState.load(path).history) == 20


# ---------------------------------------------------------------------------
# Config accessor
# ---------------------------------------------------------------------------

def test_auto_publish_defaults_are_conservative(tmp_path: Path) -> None:
    settings = config.auto_publish_settings(tmp_path)
    assert settings.enabled is False
    assert settings.ai_enabled is True
    assert settings.force_manual_approval is False
    assert 1 <= settings.threshold <= 100


def test_repo_config_overrides_auto_publish_defaults(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/bos-universal-config.json",
        {"marketplace_kit": {"auto_publish": {
            "enabled": True,
            "threshold": 80,
            "repo_type": "docker-action",
            "force_manual_approval": True,
        }}},
    )
    settings = config.auto_publish_settings(tmp_path)
    assert settings.enabled is True
    assert settings.threshold == 80
    assert settings.repo_type == "docker-action"
    assert settings.force_manual_approval is True


def test_invalid_repo_type_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/bos-universal-config.json",
        {"marketplace_kit": {"auto_publish": {"repo_type": "not-a-type"}}},
    )
    with pytest.raises(config.ConfigError):
        config.auto_publish_settings(tmp_path)


def test_invalid_threshold_is_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".github/bos-universal-config.json",
        {"marketplace_kit": {"auto_publish": {"threshold": 500}}},
    )
    with pytest.raises(config.ConfigError):
        config.auto_publish_settings(tmp_path)
