"""Package identity, deliberately independent of the policy cascade.

Configuration in [`config.py`](config.py) owns *policy* — what the kit
enforces. This module owns *identity* — what the kit is. The two never
share a resolution path, so package name, version, author, and homepage
stay available even when repository policy is absent, overridden, or
failed to load.

Values come from installed distribution metadata when the kit was
installed as a package, and fall back to the bundled constants when the
composite action runs the source tree straight off a runner without a
`pip install`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

DISTRIBUTION = "bos-marketplace-kit"

# Bundled fallbacks — used when no installed distribution is found (the
# composite action executes `src/` directly). Kept in lockstep with
# pyproject.toml by test_metadata.py.
_FALLBACK = {
    "name": DISTRIBUTION,
    "version": "0.2.0",
    "summary": "Local CLI for the BOS Marketplace Kit — validate, "
               "preview, and dry-run Marketplace Action releases without pushing.",
    "author": "Blackout Secure",
    "license": "Apache-2.0",
    "homepage": "https://github.com/blackoutsecure/bos-marketplace-kit",
}


class PackageMetadata(NamedTuple):
    name: str
    version: str
    summary: str
    author: str
    license: str
    homepage: str
    source: str  # "distribution" or "bundled"

    def as_rows(self) -> list[tuple[str, str]]:
        return [
            ("name", self.name),
            ("version", self.version),
            ("author", self.author),
            ("license", self.license),
            ("homepage", self.homepage),
            ("metadata source", self.source),
        ]


def _homepage_from(meta) -> str:
    """`Home-page` was dropped by modern build backends in favour of
    repeated `Project-URL: Label, URL` entries."""
    home = meta.get("Home-page")
    if home:
        return home
    for entry in meta.get_all("Project-URL") or ():
        label, _, url = entry.partition(",")
        if label.strip().lower() in ("homepage", "source", "repository"):
            return url.strip()
    return _FALLBACK["homepage"]


def _license_from(meta) -> str:
    """`License` may hold the entire licence text on older metadata."""
    value = (meta.get("License-Expression") or meta.get("License") or "").strip()
    if not value:
        return _FALLBACK["license"]
    first = value.splitlines()[0].strip()
    return first if 0 < len(first) <= 64 else _FALLBACK["license"]


def load() -> PackageMetadata:
    """Return package identity. Never raises, never consults config."""
    try:
        from importlib import metadata as importlib_metadata

        meta = importlib_metadata.metadata(DISTRIBUTION)
    except Exception:
        return PackageMetadata(source="bundled", **_FALLBACK)

    return PackageMetadata(
        name=meta.get("Name") or _FALLBACK["name"],
        version=meta.get("Version") or _FALLBACK["version"],
        summary=meta.get("Summary") or _FALLBACK["summary"],
        author=(meta.get("Author") or meta.get("Author-email")
                or _FALLBACK["author"]),
        license=_license_from(meta),
        homepage=_homepage_from(meta),
        source="distribution",
    )


def version() -> str:
    return load().version


_LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")
_LICENSE_PATTERNS = (
    (r"apache license(?:,? version)?\s*2(?:\.0)?", "Apache-2.0"),
    (r"mit license", "MIT"),
    (r"gnu general public license.*version\s*3", "GPL-3.0-only"),
    (r"gnu general public license.*version\s*2", "GPL-2.0-only"),
    (r"bsd 3-clause|redistribution and use.*three conditions", "BSD-3-Clause"),
    (r"bsd 2-clause|redistribution and use.*two conditions", "BSD-2-Clause"),
)


def read_repo_license(root: Path | str = ".") -> str:
    """Return a best-effort SPDX identifier from a repository license file."""
    root = Path(root)
    for filename in _LICENSE_FILES:
        path = root / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")[:12000]
        except OSError:
            continue
        spdx = re.search(r"SPDX-License-Identifier:\s*([^\s*]+)", text, re.IGNORECASE)
        if spdx:
            return spdx.group(1).strip()
        lowered = text.lower()
        for pattern, identifier in _LICENSE_PATTERNS:
            if re.search(pattern, lowered):
                return identifier
        return "unknown"
    return "unknown"
