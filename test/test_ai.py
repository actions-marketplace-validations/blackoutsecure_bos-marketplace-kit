"""Tests for the optional AI layer.

The contract under test is that AI is strictly opportunistic: no
provider, a disabled provider, or any provider failure must degrade to
deterministic local remediation rather than raising or blocking.

No test in this file performs a network call — the transport is always
stubbed.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from marketplace_kit import ai, summary

FINDINGS = [
    ai.Finding("MP010", "fail", "description is 130 chars"),
    ai.Finding("CH001", "warn", "CODE_OF_CONDUCT.md missing"),
    ai.Finding("MP001", "pass", "`name` present"),
]


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def test_no_credentials_means_no_provider() -> None:
    assert not ai.detect_provider("auto", environ={}).usable


def test_auto_prefers_github_models() -> None:
    provider = ai.detect_provider("auto", environ={
        "GITHUB_TOKEN": "t", "OPENAI_API_KEY": "k",
        "OPENAI_API_ENDPOINT": "https://example.invalid/v1",
    })
    assert provider.name == "github-models"
    assert provider.endpoint == ai.GITHUB_MODELS_ENDPOINT


def test_dedicated_models_token_wins_over_workflow_token() -> None:
    provider = ai.detect_provider("auto", environ={
        "GITHUB_TOKEN": "workflow", "GITHUB_MODELS_TOKEN": "dedicated"})
    assert provider.token == "dedicated"


def test_auto_falls_through_to_external() -> None:
    provider = ai.detect_provider("auto", environ={
        "OPENAI_API_KEY": "k", "OPENAI_API_ENDPOINT": "https://example.invalid/v1"})
    assert provider.name == "external"


def test_external_needs_both_key_and_endpoint() -> None:
    assert not ai.detect_provider(
        "external", environ={"OPENAI_API_KEY": "k"}).usable


def test_external_rejects_non_https_endpoint() -> None:
    assert not ai.detect_provider(
        "external",
        environ={"OPENAI_API_KEY": "k", "OPENAI_API_ENDPOINT": "http://example.invalid/v1"},
    ).usable


def test_none_never_resolves_a_provider() -> None:
    assert not ai.detect_provider(
        "none", environ={"GITHUB_TOKEN": "t"}).usable


def test_explicit_provider_does_not_fall_through() -> None:
    provider = ai.detect_provider("github-models", environ={
        "OPENAI_API_KEY": "k", "OPENAI_API_ENDPOINT": "https://example.invalid/v1"})
    assert not provider.usable


def test_unknown_provider_is_treated_as_auto() -> None:
    assert ai.detect_provider(
        "nonsense", environ={"GITHUB_TOKEN": "t"}).name == "github-models"


def test_model_override_beats_environment() -> None:
    provider = ai.detect_provider(
        "auto", model="acme/m1",
        environ={"GITHUB_TOKEN": "t", "GITHUB_MODELS_MODEL": "env/m"})
    assert provider.model == "acme/m1"


# ---------------------------------------------------------------------------
# Deterministic local remediation
# ---------------------------------------------------------------------------

def test_local_summary_only_covers_fail_and_warn() -> None:
    text = ai.local_summary(FINDINGS)
    assert "MP010" in text
    assert "CH001" in text
    assert "MP001" not in text


def test_local_summary_adds_family_guidance() -> None:
    text = ai.local_summary(FINDINGS)
    assert "`MP###`" in text
    assert "`CH###`" in text


def test_local_summary_when_clean() -> None:
    assert "No remediation needed" in ai.local_summary(
        [ai.Finding("MP001", "pass", "ok")])


def test_local_summary_truncates_long_reports() -> None:
    many = [ai.Finding(f"MP{i:03d}", "fail", "x") for i in range(40)]
    text = ai.local_summary(many)
    assert "further finding(s) omitted" in text


# ---------------------------------------------------------------------------
# summarize() — the opportunistic contract
# ---------------------------------------------------------------------------

def test_disabled_returns_local(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", _explode)
    result = ai.summarize(FINDINGS, enabled=False, environ={"GITHUB_TOKEN": "t"})
    assert result.provider == "local"
    assert "disabled" in result.fallback_reason


def test_no_provider_returns_local(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", _explode)
    result = ai.summarize(FINDINGS, environ={})
    assert result.provider == "local"
    assert "MP010" in result.text


def test_provider_error_returns_local(monkeypatch) -> None:
    def fail(*_a, **_k):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(ai, "_chat", fail)
    result = ai.summarize(FINDINGS, environ={"GITHUB_TOKEN": "t"})
    assert result.provider == "local"
    assert "unavailable" in result.fallback_reason
    assert "MP010" in result.text


def test_empty_model_response_returns_local(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", lambda *_a, **_k: "   ")
    result = ai.summarize(FINDINGS, environ={"GITHUB_TOKEN": "t"})
    assert result.provider == "local"


def test_successful_model_response_is_used(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", lambda *_a, **_k: "* fix MP010 first")
    result = ai.summarize(FINDINGS, environ={"GITHUB_TOKEN": "t"})
    assert result.provider == "github-models"
    assert result.fallback_reason == ""
    assert result.text == "* fix MP010 first"


def test_clean_report_never_calls_a_model(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", _explode)
    result = ai.summarize([ai.Finding("MP001", "pass", "ok")],
                          environ={"GITHUB_TOKEN": "t"})
    assert result.provider == "local"


def test_local_fallback_can_be_switched_off(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", _explode)
    result = ai.summarize(FINDINGS, enabled=False, local_fallback=False)
    assert result.text == ""


def test_only_findings_are_sent(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def capture(_provider, prompt, **_k):
        captured["prompt"] = prompt
        return "ok"

    monkeypatch.setattr(ai, "_chat", capture)
    ai.summarize(FINDINGS, environ={"GITHUB_TOKEN": "t"})
    assert captured["prompt"].startswith("Findings:")
    assert "MP001" not in captured["prompt"], "passing rows must not be sent"


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------

def test_chat_rejects_non_https_endpoints() -> None:
    provider = ai.Provider("external", "http://insecure.invalid/v1", "k", "m")
    with pytest.raises(ValueError):
        ai._chat(provider, "hi")


def test_chat_posts_bearer_token_and_parses_choice(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": "done"}}]}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.get_header("Authorization")
        captured["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    provider = ai.Provider("external", "https://api.invalid/v1", "sekret", "m1")
    assert ai._chat(provider, "hello", system="sys") == "done"
    assert captured["url"] == "https://api.invalid/v1/chat/completions"
    assert captured["auth"] == "Bearer sekret"
    assert captured["body"]["messages"][0]["content"] == "sys"


# ---------------------------------------------------------------------------
# Template tailoring
# ---------------------------------------------------------------------------

DRAFT = "# Security Policy\n\nReport issues to security@example.com.\n" * 3


def test_tailoring_is_off_by_default() -> None:
    assert ai.tailor_template(DRAFT, label="x", project_name="p").text == DRAFT


def test_tailoring_without_a_provider_returns_the_draft() -> None:
    result = ai.tailor_template(
        DRAFT, label="x", project_name="p", enabled=True, environ={})
    assert result.text == DRAFT
    assert result.provider == "local"


def test_tailoring_rejects_a_suspiciously_short_response(monkeypatch) -> None:
    monkeypatch.setattr(ai, "_chat", lambda *_a, **_k: "no")
    result = ai.tailor_template(DRAFT, label="x", project_name="p",
                                enabled=True, environ={"GITHUB_TOKEN": "t"})
    assert result.text == DRAFT
    assert "unusable" in result.fallback_reason


def test_tailoring_uses_a_good_response(monkeypatch) -> None:
    better = DRAFT.replace("example.com", "acme.test")
    monkeypatch.setattr(ai, "_chat", lambda *_a, **_k: better)
    result = ai.tailor_template(DRAFT, label="x", project_name="p",
                                enabled=True, environ={"GITHUB_TOKEN": "t"})
    assert result.text == better
    assert result.provider == "github-models"


# ---------------------------------------------------------------------------
# summary.py — the composite action's job-summary entry point
# ---------------------------------------------------------------------------

def test_parse_report_skips_malformed_rows() -> None:
    findings = summary.parse_report(
        "MP010|fail|too long\nnot-a-row\nCH001|warn|missing\n")
    assert [f.rule_id for f in findings] == ["MP010", "CH001"]


def test_summary_main_appends_to_step_summary(tmp_path, monkeypatch) -> None:
    target = tmp_path / "summary.md"
    monkeypatch.setenv("MK_REPORT", "MP010|fail|description too long")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    monkeypatch.setenv("ENABLE_AI_FINDINGS_SUMMARY", "false")
    monkeypatch.setenv("AI_LOCAL_FALLBACK", "true")
    assert summary.main() == 0
    text = target.read_text(encoding="utf-8")
    assert "Remediation summary" in text
    assert "MP010" in text


def test_summary_main_is_a_noop_without_a_report(tmp_path, monkeypatch) -> None:
    target = tmp_path / "summary.md"
    monkeypatch.setenv("MK_REPORT", "")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(target))
    assert summary.main() == 0
    assert not target.exists()


def test_summary_main_survives_a_broken_config(tmp_path, monkeypatch) -> None:
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "bos-universal-config.json").write_text(
        "{not json", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ENABLE_AI_FINDINGS_SUMMARY", raising=False)
    monkeypatch.setenv("MK_REPORT", "MP010|fail|description too long")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path / "s.md"))
    assert summary.main() == 0


def _explode(*_args, **_kwargs):
    raise AssertionError("a model must not be contacted here")
