"""Deterministic relevance scoring for the Marketplace auto-publish gate.

Decides whether a set of changed files is significant enough to trigger an
automatic release, and tracks a running score across commits that don't
individually cross the threshold (so three small-but-real fixes in a row
still eventually trigger a release, instead of resetting to zero every push).

Two independent signals feed the final decision:

1. **Deterministic, path-based scoring** (this module) — always available,
   no network, no config beyond the weight table. Every changed path is
   matched against an ordered set of categories; the highest-weighted
   category match wins for that path, and a repo's score for one diff is
   the highest weight among its changed files (not a sum — one meaningful
   file is enough to flag a diff as relevant; a pile of trivial ones should
   not out-vote it).
2. **AI refinement** (`ai.score_relevance`) — optional, opportunistic,
   never required. When reachable, its score is preferred; the
   deterministic score is always the fallback and is always reported
   alongside it for transparency.

The running total persists in a small JSON state file committed back to the
repo (mirrors the `tracked-release.json` pattern already used by
`bos-upstream-watcher`), and resets to zero the moment a release is
triggered from it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

DEFAULT_STATE_PATH = ".github/marketplace-relevance-score.json"
DEFAULT_THRESHOLD = 65
MAX_SCORE = 100

REPO_TYPES = ("auto", "composite-action", "docker-action", "library")

# Ordered highest-weight-first; the first pattern a path matches wins.
# Each repo type overrides only the patterns that differ from the baseline
# composite-action profile below.
# Ordered highest-priority-first; the first pattern a path matches wins.
# More specific path prefixes (tests, CI metadata) are listed BEFORE the
# generic extension globs they'd otherwise also match — `fnmatch` treats
# `*` as matching `/` too, so `test/foo.py` would incorrectly hit `*.py`
# first if the generic globs came first.
_BASELINE_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("action.yml", 40),
    ("action.yaml", 40),
    ("run.sh", 35),
    ("lib.sh", 35),
    ("helper.py", 35),
    ("src/**", 35),
    ("pyproject.toml", 20),
    ("package.json", 20),
    ("package-lock.json", 20),
    ("requirements*.txt", 20),
    ("go.mod", 20),
    ("go.sum", 20),
    ("README.md", 15),
    ("README.*", 15),
    ("LICENSE", 5),
    ("NOTICE", 5),
    ("test/**", 3),
    ("tests/**", 3),
    ("test_*.py", 3),
    ("*_test.py", 3),
    (".github/workflows/**", 1),
    (".github/dependabot.yml", 1),
    (".editorconfig", 1),
    (".gitattributes", 1),
    (".gitignore", 1),
    (".markdownlint.json", 1),
    (".shellcheckrc", 1),
    (".yamllint.yml", 1),
    # Generic ecosystem extensions last: specific paths above must get a
    # chance to match first, since these would otherwise match everything.
    ("*.py", 25),
    ("*.sh", 25),
    ("*.js", 25),
    ("*.ts", 25),
    ("*.go", 25),
)

_DOCKER_ACTION_OVERRIDES: tuple[tuple[str, int], ...] = (
    ("Dockerfile", 40),
    ("Dockerfile.*", 40),
    ("entrypoint.sh", 35),
    ("docker-entrypoint.sh", 35),
)

_LIBRARY_OVERRIDES: tuple[tuple[str, int], ...] = (
    # A library has no single manifest entrypoint; any top-level source
    # module is as significant as `action.yml` would be for an action.
    ("*.py", 35),
    ("*.js", 35),
    ("*.ts", 35),
    ("*.go", 35),
)

_DEFAULT_OTHER_WEIGHT = 2


def weights_for_repo_type(repo_type: str, overrides: dict[str, int] | None = None) -> dict[str, int]:
    """Build the ordered pattern -> weight table for one repo type."""
    if repo_type not in REPO_TYPES:
        raise ValueError(f"unknown repo_type '{repo_type}': expected one of {REPO_TYPES}")
    table = dict(_BASELINE_WEIGHTS)
    if repo_type == "docker-action":
        table.update(_DOCKER_ACTION_OVERRIDES)
    elif repo_type == "library":
        table.update(_LIBRARY_OVERRIDES)
    if overrides:
        table.update(overrides)
    return table


@dataclass(frozen=True)
class FileScore:
    path: str
    weight: int
    pattern: str | None  # None when the "other" fallback weight applied


def score_changed_files(
    changed_files: Iterable[str],
    *,
    repo_type: str = "auto",
    weight_overrides: dict[str, int] | None = None,
) -> tuple[int, list[FileScore]]:
    """Deterministic 0-100 score for one diff, plus a per-file breakdown.

    The diff's score is the single highest-weighted match across its
    changed files — a diff touching `action.yml` alongside a hundred test
    files is exactly as relevant as one touching only `action.yml`.
    """
    resolved_type = "composite-action" if repo_type == "auto" else repo_type
    table = weights_for_repo_type(resolved_type, weight_overrides)

    breakdown: list[FileScore] = []
    for path in changed_files:
        matched_pattern: str | None = None
        matched_weight = _DEFAULT_OTHER_WEIGHT
        for pattern, weight in table.items():
            if fnmatch(path, pattern):
                matched_pattern = pattern
                matched_weight = weight
                break
        breakdown.append(FileScore(path=path, weight=matched_weight, pattern=matched_pattern))

    score = max((entry.weight for entry in breakdown), default=0)
    return min(score, MAX_SCORE), breakdown


@dataclass
class ScoreState:
    """Persisted running total between publishes."""

    running_total: int = 0
    last_reset_sha: str = ""
    last_reset_at: str = ""
    history: list[dict[str, Any]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.history is None:
            self.history = []

    @classmethod
    def load(cls, path: Path) -> ScoreState:
        if not path.is_file():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        return cls(
            running_total=int(data.get("running_total", 0) or 0),
            last_reset_sha=str(data.get("last_reset_sha") or ""),
            last_reset_at=str(data.get("last_reset_at") or ""),
            history=list(data.get("history") or [])[-20:],
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "running_total": self.running_total,
                    "last_reset_sha": self.last_reset_sha,
                    "last_reset_at": self.last_reset_at,
                    "history": self.history[-20:],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def record(self, *, sha: str, at: str, diff_score: int, source: str, published: bool) -> None:
        self.history.append(
            {
                "sha": sha,
                "at": at,
                "diff_score": diff_score,
                "source": source,
                "running_total": self.running_total,
                "published": published,
            }
        )
