"""
SaxoFlow: RTL Design and Verification CLI Core

Provides simulation, synthesis, formal verification, and project management.
"""

__version__ = "1"
__author__ = "SaxoFlow Labs"
__license__ = "Apache-2.0"

__all__ = ["cli"]


def __getattr__(name):
    """Lazily expose the Click CLI without importing it for every submodule."""
    if name == "cli":
        from .cli import cli  # noqa: PLC0415

        return cli
    raise AttributeError(f"module 'saxoflow' has no attribute {name!r}")
