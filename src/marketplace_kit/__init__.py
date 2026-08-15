"""BOS Marketplace Kit — local CLI companion to the GitHub Actions."""

from .metadata import load as load_metadata
from .metadata import version as _version

__version__ = _version()

__all__ = ["__version__", "load_metadata"]
