"""
Lightweight, import-safe package init.

Avoid importing heavy submodules at import time; tests load `cli.py` by path
after importing the package to resolve the directory.
"""

from __future__ import annotations

# Optional: expose a version if available, but don't crash if metadata missing.
try:
    from importlib.metadata import version, PackageNotFoundError  # Python 3.8+
    try:
        __version__ = version("saxoflow_agenticai")
    except PackageNotFoundError:
        __version__ = "0.0.0"
except Exception:
    __version__ = "0.0.0"

__all__ = ["__version__"]
