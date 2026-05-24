"""Extract Marketplace-relevant metadata from an action.yml.

Called by the `check` composite. Emits a series of KEY=VALUE lines on
stdout that the calling shell `eval`s.
"""

from __future__ import annotations

import re
import sys


def _scalar(v: object) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v).strip()


def _fallback_parse(path: str) -> dict:
    """Minimal regex parser used when PyYAML is unavailable.

    Captures only the keys this check inspects. Sufficient for
    detecting empty/missing values; not a YAML implementation.
    """
    doc: dict[str, object] = {}
    cur_section: dict | None = None
    cur_key: str | None = None

    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            top = re.match(r"^([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
            if top:
                cur_key = top.group(1)
                val = top.group(2).strip().strip("'\"")
                if val:
                    doc[cur_key] = val
                    cur_section = None
                else:
                    doc[cur_key] = {}
                    cur_section = doc[cur_key]  # type: ignore[assignment]
                continue
            sub = re.match(r"^\s+([a-zA-Z_][a-zA-Z0-9_-]*):\s*(.*)$", line)
            if sub and isinstance(cur_section, dict):
                cur_section[sub.group(1)] = sub.group(2).strip().strip("'\"")
    return doc


def main() -> int:
    path = sys.argv[1]
    try:
        import yaml  # noqa: WPS433

        with open(path, encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
    except ImportError:
        doc = _fallback_parse(path)
    except Exception as exc:
        sys.stderr.write(f"warn: YAML parse failed ({exc}); falling back to regex parse\n")
        doc = _fallback_parse(path)

    name = _scalar(doc.get("name"))
    desc = _scalar(doc.get("description"))
    runs = doc.get("runs") or {}
    runs_using = _scalar(runs.get("using")) if isinstance(runs, dict) else ""
    branding = doc.get("branding") or {}
    icon = _scalar(branding.get("icon")) if isinstance(branding, dict) else ""
    color = _scalar(branding.get("color")) if isinstance(branding, dict) else ""

    print(f"NAME={name}")
    print(f"DESC_LEN={len(desc)}")
    print(f"RUNS_USING={runs_using}")
    print(f"BRANDING_ICON={icon}")
    print(f"BRANDING_COLOR={color}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
