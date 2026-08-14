#!/usr/bin/env python3
"""Job-summary entry point for the `check` composite's AI step.

Reads the `id|status|message` report emitted by `run.sh`, resolves the
AI configuration from the same cascade the checks used, and appends a
remediation section to `$GITHUB_STEP_SUMMARY`.

Always exits 0: a missing provider, a disabled summary, or a provider
error degrades to deterministic local remediation rather than turning a
passing build red.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from marketplace_kit import ai, config  # noqa: E402


def parse_report(text: str) -> list[ai.Finding]:
    findings: list[ai.Finding] = []
    for line in text.splitlines():
        parts = line.split("|", 2)
        if len(parts) != 3:
            continue
        rule_id, status, message = (p.strip() for p in parts)
        if rule_id and status:
            findings.append(ai.Finding(rule_id, status.lower(), message))
    return findings


def main() -> int:
    findings = parse_report(os.environ.get("MK_REPORT", ""))
    if not findings:
        return 0

    # The `config` step already resolved the cascade and exported it to
    # $GITHUB_ENV; re-resolve only when running outside that flow.
    if "ENABLE_AI_FINDINGS_SUMMARY" in os.environ:
        values = {
            "enable_ai_findings_summary":
                os.environ["ENABLE_AI_FINDINGS_SUMMARY"] == "true",
            "ai_findings_summary_provider": os.environ.get("AI_PROVIDER", "auto"),
            "ai_model": os.environ.get("AI_MODEL", ""),
            "local_heuristic_fallback":
                os.environ.get("AI_LOCAL_FALLBACK", "true") == "true",
        }
    else:
        try:
            values = config.resolve(os.environ.get("MK_CONFIG_ROOT", ".")).values
        except config.ConfigError:
            # The check step already reported the config error; fall back
            # to local remediation rather than duplicating it.
            values = {"enable_ai_findings_summary": False,
                      "ai_findings_summary_provider": "auto",
                      "ai_model": "",
                      "local_heuristic_fallback": True}

    summary = ai.summarize(
        findings,
        enabled=bool(values["enable_ai_findings_summary"]),
        requested_provider=str(values["ai_findings_summary_provider"]),
        model=str(values["ai_model"]),
        local_fallback=bool(values["local_heuristic_fallback"]),
    )

    if not summary.text:
        return 0

    block = [
        "",
        "### Remediation summary",
        "",
        summary.text,
        "",
        f"<sub>Source: `{summary.provider}`"
        + (f" — {summary.fallback_reason}" if summary.fallback_reason else "")
        + "</sub>",
        "",
    ]
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    text = "\n".join(block)
    if target:
        with open(target, "a", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
