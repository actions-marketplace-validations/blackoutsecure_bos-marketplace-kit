"""Extract branding.icon and branding.color from an action.yml.

Called by the `branding-preview` composite. Emits shell-safe
ICON=... and COLOR=... lines on stdout (values quoted via
shlex.quote) that the calling shell `eval`s.
"""

from __future__ import annotations

import re
import shlex
import sys


def _fallback(path: str) -> tuple[str, str]:
    with open(path, encoding="utf-8") as f:
        src = f.read()
    m = re.search(r"(?m)^branding:\s*\n((?:[ \t]+.+\n?)+)", src)
    if not m:
        return "", ""
    block = m.group(1)
    ic = re.search(r"(?m)^\s+icon:\s*['\"]?([^'\"\n]+)['\"]?\s*$", block)
    cc = re.search(r"(?m)^\s+color:\s*['\"]?([^'\"\n]+)['\"]?\s*$", block)
    return (ic.group(1).strip() if ic else ""), (cc.group(1).strip() if cc else "")


def main() -> int:
    path = sys.argv[1]
    try:
        import yaml  # noqa: WPS433

        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        branding = doc.get("branding") or {}
        icon = (branding.get("icon") or "").strip() if isinstance(branding, dict) else ""
        color = (branding.get("color") or "").strip() if isinstance(branding, dict) else ""
    except Exception:
        icon, color = _fallback(path)

    print(f"ICON={shlex.quote(icon)}")
    print(f"COLOR={shlex.quote(color)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

