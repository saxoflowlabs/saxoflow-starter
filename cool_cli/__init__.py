# cool_cli/__init__.py
"""
Minimal init to avoid import-time cycles.

Do NOT import app/bootstrap/commands/shell here.
Keep side effects out of package import.
"""

__version__ = "0.1.0"
__all__: list[str] = ["__version__"]
