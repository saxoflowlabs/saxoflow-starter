"""
SaxoFlow: RTL Design and Verification CLI Core

Provides simulation, synthesis, formal verification, and project management.
"""

__version__ = "0.2.0"  # bump version
__author__ = "SaxoFlow Labs"
__license__ = "MIT"

from .cli import cli

__all__ = ["cli"]


# Clean module structure: avoid circular imports at __init__ level
