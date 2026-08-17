"""Optional AI assistance with a deterministic local fallback.

Two rules govern everything here:

1. **Opportunistic.** A provider is used only when one is actually
   reachable. A missing token, a disabled provider, a network error, or
   a malformed response is never fatal — the caller silently gets the
   deterministic local result instead.
2. **Minimal data.** Only the finding rows selected for a summary are
   sent, never repository contents, secrets, or config.

Providers:

* `github-models` — `https://models.github.ai/inference`, authenticated
  with `GITHUB_MODELS_TOKEN` or the workflow `GITHUB_TOKEN`. Needs the
  `models: read` workflow permission.
* `external` — any OpenAI-compatible endpoint, via `OPENAI_API_KEY` and
  `OPENAI_API_ENDPOINT`.
* `none` — never call a model.
* `auto` (default) — try `github-models`, then `external`, then fall
  back to local remediation.

Stdlib only, so the composite action can run this straight off a runner.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Iterable
from typing import NamedTuple

PROVIDERS = ("auto", "none", "github-models", "external")

GITHUB_MODELS_ENDPOINT = "https://models.github.ai/inference"
DEFAULT_MODEL = "openai/gpt-4o-mini"
TASK_DEFAULT_MODELS = {
    "summary": "openai/gpt-4o-mini",
    "relevance": "openai/gpt-4o-mini",
    "metadata": "openai/gpt-4o-mini",
    "categories": "openai/gpt-4o-mini",
    "readme": "openai/gpt-4o-mini",
}

_TIMEOUT = 20
_MAX_FINDINGS = 25


class Provider(NamedTuple):
    name: str        # "github-models" | "external" | "none"
    endpoint: str
    token: str
    model: str

    @property
    def usable(self) -> bool:
        return bool(self.name != "none" and self.endpoint and self.token)


class Summary(NamedTuple):
    text: str
    provider: str      # provider that produced the text, or "local"
    fallback_reason: str  # why the model was not used; "" when it was


class Finding(NamedTuple):
    rule_id: str
    status: str
    message: str


class RelevanceScore(NamedTuple):
    score: int          # 0-100, or -1 when the model was not consulted
    source: str          # "ai" | "local" (deterministic only)
    reasoning: str        # short model explanation; "" for local
    fallback_reason: str  # why the model was not used; "" when it was


class LicenseInference(NamedTuple):
    identifier: str
    provider: str
    fallback_reason: str


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def _env(environ: dict[str, str] | None, key: str) -> str:
    source = os.environ if environ is None else environ
    return (source.get(key) or "").strip()


def _https_endpoint(value: str) -> str:
    """Normalize an endpoint and reject cleartext transport before requests."""
    endpoint = value.strip()
    return endpoint if endpoint.startswith("https://") else ""


def detect_provider(
    requested: str = "auto",
    *,
    model: str = "",
    task: str = "summary",
    environ: dict[str, str] | None = None,
) -> Provider:
    """Resolve the provider to use, without contacting it."""
    if requested not in PROVIDERS:
        requested = "auto"
    none = Provider("none", "", "", "")
    if requested == "none":
        return none

    def selected_model() -> str:
        explicit = model.strip()
        if explicit and explicit.lower() != "auto":
            return explicit
        task_key = "".join(
            character if character.isalnum() else "_" for character in task.upper()
        )
        return (
            _env(environ, f"GITHUB_MODELS_MODEL_{task_key}")
            or _env(environ, "GITHUB_MODELS_MODEL")
            or TASK_DEFAULT_MODELS.get(task, DEFAULT_MODEL)
        )

    def github_models() -> Provider | None:
        token = (_env(environ, "GITHUB_MODELS_TOKEN")
                 or _env(environ, "GITHUB_TOKEN"))
        if not token:
            return None
        return Provider(
            "github-models",
            _https_endpoint(_env(environ, "GITHUB_MODELS_ENDPOINT") or GITHUB_MODELS_ENDPOINT),
            token,
            selected_model(),
        )

    def external() -> Provider | None:
        token = _env(environ, "OPENAI_API_KEY")
        endpoint = _https_endpoint(_env(environ, "OPENAI_API_ENDPOINT"))
        if not (token and endpoint):
            return None
        return Provider(
            "external",
            endpoint,
            token,
            selected_model(),
        )

    if requested == "github-models":
        return github_models() or none
    if requested == "external":
        return external() or none
    return github_models() or external() or none


# ---------------------------------------------------------------------------
# Deterministic local remediation — always available
# ---------------------------------------------------------------------------

# Rule-family guidance. Keyed by the two-letter prefix so a new rule in
# an existing family gets sensible advice without a code change.
_FAMILY_ADVICE: dict[str, str] = {
    "MP": "Marketplace requirement. Fix `action.yml` before publishing — "
          "the listing will be rejected otherwise.",
    "OP": "Operational best practice. Not blocking, but Marketplace "
          "listings convert better with it fixed.",
    "SC": "Security hygiene. Treat as blocking: it affects everyone who "
          "consumes the action.",
    "CH": "Community-health file. Scaffold it with "
          "`marketplace-kit install --all`, or set the rule's "
          "`*_source` to `inherit` if your org `.github` repo owns it.",
    "DP": "Dependency policy. Scaffold with "
          "`marketplace-kit install dependabot`.",
    "CQ": "Code scanning. Scaffold with "
          "`marketplace-kit install codeql-workflow`.",
    "LT": "Lint configuration. Scaffold with `marketplace-kit install "
          "markdownlint` / `yamllint` / `shellcheckrc`.",
    "GH": "Repository setting, not a file. Enable it under "
          "Settings -> Code security.",
    "MS": "Opt-in Microsoft Security DevOps workflow. Scaffold with "
          "`marketplace-kit install security-devops-workflow`.",
    "SR": "Opt-in OpenSSF Scorecard workflow. Scaffold with "
          "`marketplace-kit install scorecard-workflow`.",
    "RM": "Repository `About` box. Fix in Settings, or automate it with "
          "the kit's `repo-metadata` composite on release.",
}

_GENERIC_ADVICE = ("See the check rule catalogue in the kit README for "
                   "the remediation steps.")


def local_summary(findings: Iterable[Finding]) -> str:
    """Deterministic remediation text. No network, no model, no config."""
    rows = [f for f in findings if f.status in ("fail", "warn")]
    if not rows:
        return "All checks passed. No remediation needed."

    lines = [
        f"{len(rows)} finding(s) need attention.",
        "",
    ]
    seen_families: set[str] = set()
    for finding in rows[:_MAX_FINDINGS]:
        lines.append(f"* **{finding.rule_id}** ({finding.status}) — {finding.message}")
        family = finding.rule_id[:2]
        if family not in seen_families:
            seen_families.add(family)
    lines.append("")
    lines.append("How to fix, by rule family:")
    for family in sorted(seen_families):
        lines.append(f"* `{family}###` — {_FAMILY_ADVICE.get(family, _GENERIC_ADVICE)}")
    if len(rows) > _MAX_FINDINGS:
        lines.append("")
        lines.append(f"({len(rows) - _MAX_FINDINGS} further finding(s) omitted.)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Model call
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a release engineer reviewing a GitHub Marketplace Action. "
    "Given a list of check findings, write a short markdown summary: at "
    "most six bullets, each naming the rule ID and the single most "
    "effective fix. Be specific and terse. Do not invent rules, do not "
    "restate the input verbatim, and do not add a preamble or heading."
)


def _chat(provider: Provider, prompt: str, *, system: str = "") -> str:
    url = provider.endpoint.rstrip("/") + "/chat/completions"
    if not url.startswith("https://"):
        raise ValueError("AI endpoint must be https")

    payload = json.dumps({
        "model": provider.model,
        "temperature": 0.1,
        "max_tokens": 500,
        "messages": [
            {"role": "system", "content": system or _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {provider.token}",
            "User-Agent": "bos-marketplace-kit",
        },
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
        body = json.loads(response.read().decode("utf-8"))
    return (body["choices"][0]["message"]["content"] or "").strip()


def _prompt(findings: Iterable[Finding]) -> str:
    rows = [f for f in findings if f.status in ("fail", "warn")][:_MAX_FINDINGS]
    body = "\n".join(f"{f.rule_id} {f.status}: {f.message}" for f in rows)
    return f"Findings:\n{body}"


def summarize(
    findings: Iterable[Finding],
    *,
    enabled: bool = True,
    requested_provider: str = "auto",
    model: str = "",
    local_fallback: bool = True,
    environ: dict[str, str] | None = None,
) -> Summary:
    """Summarize findings, preferring a model but never depending on one."""
    findings = list(findings)
    local = local_summary(findings) if local_fallback else ""

    if not enabled:
        return Summary(local, "local", "AI summary disabled by config")

    provider = detect_provider(
        requested_provider, model=model, task="summary", environ=environ
    )
    if not provider.usable:
        return Summary(local, "local", "no AI provider credentials detected")

    if not any(f.status in ("fail", "warn") for f in findings):
        return Summary(local, "local", "nothing to summarize")

    try:
        text = _chat(provider, _prompt(findings))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return Summary(local, "local", f"{provider.name} unavailable ({type(exc).__name__})")

    if not text.strip():
        return Summary(local, "local", f"{provider.name} returned an empty response")
    return Summary(text.strip(), provider.name, "")


# ---------------------------------------------------------------------------
# Marketplace license inference — only used when local detection is unknown
# ---------------------------------------------------------------------------

_LICENSE_SYSTEM_PROMPT = (
    "You identify SPDX license identifiers from license text. Respond with "
    "ONLY a JSON object with one key named identifier and an SPDX value or unknown. "
    "Never guess a license that is not supported by the supplied text."
)


def infer_license(
    license_text: str,
    *,
    enabled: bool = True,
    requested_provider: str = "auto",
    model: str = "",
    environ: dict[str, str] | None = None,
) -> LicenseInference:
    """Infer an SPDX identifier from bounded LICENSE text, never fatally."""
    if not enabled:
        return LicenseInference("unknown", "local", "AI license inference disabled")
    provider = detect_provider(
        requested_provider, model=model, task="metadata", environ=environ
    )
    if not provider.usable:
        return LicenseInference("unknown", "local", "no AI provider credentials detected")
    bounded_text = license_text[:12000]
    if not bounded_text.strip():
        return LicenseInference("unknown", "local", "license file is empty")
    try:
        parsed = json.loads(_chat(
            provider,
            "LICENSE text:\\n" + bounded_text,
            system=_LICENSE_SYSTEM_PROMPT,
        ))
        identifier = str(parsed["identifier"]).strip()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, KeyError, IndexError, TypeError,
            json.JSONDecodeError) as exc:
        return LicenseInference("unknown", "local", f"{provider.name} unavailable ({type(exc).__name__})")
    if not identifier or len(identifier) > 64 or any(char.isspace() for char in identifier):
        return LicenseInference("unknown", "local", f"{provider.name} returned an invalid identifier")
    return LicenseInference(identifier, provider.name, "")


# ---------------------------------------------------------------------------
# Marketplace-publish relevance scoring — used by the auto-publish gate
# ---------------------------------------------------------------------------

_RELEVANCE_SYSTEM_PROMPT = (
    "You are a release engineer deciding whether a set of changed files in a "
    "GitHub Marketplace Action repository is significant enough to warrant "
    "publishing a new release. Score how release-worthy the changes are on "
    "a 0-100 scale: 0 means purely cosmetic/no-op (typo fixes, comments, "
    "CI-only, test-only), 100 means a major functional change users of the "
    "action would need immediately (a new input, a behavior change, a "
    "security fix). Respond with ONLY a JSON object on one line: "
    '{"score": <integer 0-100>, "reasoning": "<one short sentence>"}. '
    "No markdown, no code fences, no other text."
)


def _relevance_prompt(changed_files: Iterable[str], deterministic_score: int) -> str:
    files = "\n".join(f"- {path}" for path in changed_files)
    return (
        f"Deterministic heuristic score (file-path based): {deterministic_score}/100.\n"
        f"Changed files:\n{files}\n\n"
        "Re-score 0-100 using the changed file paths as your only signal "
        "(you do not have the diff content)."
    )


def score_relevance(
    changed_files: Iterable[str],
    deterministic_score: int,
    *,
    enabled: bool = True,
    requested_provider: str = "auto",
    model: str = "",
    environ: dict[str, str] | None = None,
) -> RelevanceScore:
    """AI-refine a deterministic relevance score, never depending on a model.

    Mirrors :func:`summarize`'s opportunistic contract: a missing token,
    disabled provider, network error, or malformed response silently falls
    back to the deterministic score instead of failing the caller.
    """
    changed_files = list(changed_files)
    if not enabled:
        return RelevanceScore(-1, "local", "", "AI relevance scoring disabled by config")

    provider = detect_provider(
        requested_provider, model=model, task="relevance", environ=environ
    )
    if not provider.usable:
        return RelevanceScore(-1, "local", "", "no AI provider credentials detected")

    if not changed_files:
        return RelevanceScore(-1, "local", "", "no changed files to score")

    try:
        text = _chat(
            provider,
            _relevance_prompt(changed_files, deterministic_score),
            system=_RELEVANCE_SYSTEM_PROMPT,
        )
        parsed = json.loads(text)
        score = int(parsed["score"])
        reasoning = str(parsed.get("reasoning") or "").strip()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, KeyError, IndexError, TypeError,
            json.JSONDecodeError) as exc:
        return RelevanceScore(-1, "local", "", f"{provider.name} unavailable ({type(exc).__name__})")

    if not 0 <= score <= 100:
        return RelevanceScore(-1, "local", "", f"{provider.name} returned an out-of-range score")
    return RelevanceScore(score, provider.name, reasoning, "")


# ---------------------------------------------------------------------------
# Template tailoring — used by `generate-policy --ai` / `install --ai`
# ---------------------------------------------------------------------------

_TEMPLATE_SYSTEM_PROMPT = (
    "You are editing a repository's community-health file. Return the "
    "complete file content only — no code fences, no commentary. Keep "
    "the structure and headings of the draft, keep every placeholder "
    "value that is already filled in, and do not invent URLs, emails, "
    "or policies that were not in the draft."
)


def tailor_template(
    draft: str,
    *,
    label: str,
    project_name: str,
    enabled: bool = False,
    requested_provider: str = "auto",
    model: str = "",
    environ: dict[str, str] | None = None,
) -> Summary:
    """Rewrite a rendered policy template for this project.

    Returns the draft unchanged whenever a model is unavailable, so the
    caller can always write the result.
    """
    if not enabled:
        return Summary(draft, "local", "AI drafting disabled")

    provider = detect_provider(
        requested_provider, model=model, task="template", environ=environ
    )
    if not provider.usable:
        return Summary(draft, "local", "no AI provider credentials detected")

    prompt = (
        f"Project: {project_name}\nFile: {label}\n\n"
        f"Draft to adapt:\n{draft}"
    )
    try:
        text = _chat(provider, prompt, system=_TEMPLATE_SYSTEM_PROMPT)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
            OSError, ValueError, KeyError, IndexError, json.JSONDecodeError) as exc:
        return Summary(draft, "local", f"{provider.name} unavailable ({type(exc).__name__})")

    if not text or len(text) < len(draft) // 4:
        return Summary(draft, "local", f"{provider.name} returned an unusable draft")
    return Summary(text, provider.name, "")
