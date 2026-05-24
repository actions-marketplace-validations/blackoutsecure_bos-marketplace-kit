"""Shared pytest configuration for the BOS Marketplace Kit tests."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _import_from_path(module_name: str, file_path: Path):
    """Load a Python file as a module without installing it.

    Used to import the `_bp.py` helper that ships *inside* the
    branch-protection composite directory (not under src/), so the
    composite stays self-contained when consumers `uses:` it.
    """
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec is not None and spec.loader is not None, f"could not load {file_path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Eagerly import the bundled module under the alias used by tests.
_bp = _import_from_path("_bp", REPO_ROOT / ".github" / "actions" / "branch-protection" / "_bp.py")
sys.modules["bp_helper"] = _bp  # human-friendly alias for tests
