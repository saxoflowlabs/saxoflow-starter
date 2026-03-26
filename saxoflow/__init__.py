"""
SaxoFlow: RTL Design and Verification CLI Core

Provides simulation, synthesis, formal verification, and project management.
"""

from __future__ import annotations

from typing import Any

__version__ = "1"
__author__ = "SaxoFlow Labs"
__license__ = "Apache-2.0"

__all__ = ["cli"]


def __getattr__(name: str) -> Any:
	"""Lazily expose ``cli`` without importing ``saxoflow.cli`` at package import time.

	This avoids ``runpy`` warnings when users execute ``python -m saxoflow.cli``
	(module should not already be in ``sys.modules`` before execution).
	"""
	if name == "cli":
		from .cli import cli as _cli

		return _cli
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

