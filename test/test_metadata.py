"""Tests for package-metadata separation.

Identity must never come from the policy cascade, and must survive a
missing distribution (the composite action runs `src/` off a runner
without installing the package).
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

from marketplace_kit import metadata

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def test_bundled_fallback_matches_pyproject() -> None:
    project = _pyproject()["project"]
    assert metadata._FALLBACK["version"] == project["version"]
    assert metadata._FALLBACK["name"] == project["name"]
    assert metadata._FALLBACK["license"] == project["license"]


def test_load_returns_every_field() -> None:
    meta = metadata.load()
    for field in ("name", "version", "author", "license", "homepage"):
        assert getattr(meta, field), f"{field} is empty"
    assert meta.source in ("distribution", "bundled")


def test_license_is_an_identifier_not_the_licence_text() -> None:
    assert "\n" not in metadata.load().license
    assert len(metadata.load().license) <= 64


def test_falls_back_when_the_distribution_is_missing(monkeypatch) -> None:
    from importlib import metadata as importlib_metadata

    def boom(_name):
        raise importlib_metadata.PackageNotFoundError

    monkeypatch.setattr(importlib_metadata, "metadata", boom)
    meta = metadata.load()
    assert meta.source == "bundled"
    assert meta.version == metadata._FALLBACK["version"]


def test_metadata_is_independent_of_config(tmp_path, monkeypatch) -> None:
    """A broken repo config must not affect package identity."""
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "bos-universal-config.json").write_text(
        "{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert metadata.load().name == metadata.DISTRIBUTION


def test_as_rows_is_display_ready() -> None:
    rows = metadata.load().as_rows()
    assert [label for label, _ in rows][0] == "name"
    assert all(isinstance(v, str) and v for _, v in rows)


def test_version_helper_matches_load() -> None:
    assert metadata.version() == metadata.load().version


def test_package_dunder_version_uses_metadata() -> None:
    import marketplace_kit

    assert marketplace_kit.__version__ == metadata.version()
