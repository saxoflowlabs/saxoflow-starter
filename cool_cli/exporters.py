# cool_cli/exporters.py
"""
Export helpers (Markdown) and simple session statistics.

Overview
--------
This module provides two public utilities:

- :func:`export_markdown` — Write the current conversation history to a
  Markdown file (safe, never raises; returns a Rich ``Text`` status).
- :func:`get_stats` — Compute a rough word/token-ish count for the session.

Behavior (preserved)
--------------------
- The default export filename is ``"conversation.md"`` when an empty/falsey
  filename is passed.
- Any exception during export is caught and converted to a red, human-readable
  ``Text`` message (the CLI should not crash).
- Assistant content that is a ``rich.text.Text`` emits its ``.plain`` text,
  and a ``rich.markdown.Markdown`` emits its source markdown; otherwise we
  fall back to ``str(value)``.

Notes
-----
- We rely on global state from :mod:`cool_cli.state` (``conversation_history``,
  ``system_prompt``). This keeps parity with the rest of the CLI codebase.
  # TODO(decide-future): Refactor to inject state explicitly for testability.

Python: 3.9+
"""

from __future__ import annotations

from builtins import open as _builtin_open  # allow test monkeypatching via module symbol
from typing import Any, Final

from rich.markdown import Markdown
from rich.text import Text

from .state import conversation_history, system_prompt

__all__ = ["export_markdown", "get_stats"]

# Expose a module-level `open` for tests to monkeypatch.
# Use it in the code below instead of the built-in directly.
open = _builtin_open  # type: ignore[assignment]  # noqa: A001

# Default export target when caller passes a falsey filename.
_DEFAULT_EXPORT_FILENAME: Final[str] = "conversation.md"


# =============================================================================
# Internal helpers
# =============================================================================

def _assistant_to_str(msg: Any) -> str:
    """Normalize assistant content to a plain string.

    - ``Text`` → ``.plain`` (avoid Rich markup).
    - ``Markdown`` → source markdown string; different Rich versions store this
      under different attributes (``text``, ``markdown``, ``source``, ``_markdown``).
      We try them in a sensible order and also peek into ``__dict__``.
    - Fallback → ``str(msg)``.
    """
    if isinstance(msg, Text):
        return msg.plain

    if isinstance(msg, Markdown):
        # Try common/public attributes first
        for attr in ("text", "markdown", "source", "_markdown"):
            val = getattr(msg, attr, None)
            if isinstance(val, str) and val:
                return val
        # Some Rich versions stash the raw value only in __dict__
        data = getattr(msg, "__dict__", {}) or {}
        for attr in ("text", "markdown", "source", "_markdown"):
            val = data.get(attr)
            if isinstance(val, str) and val:
                return val
        # Final fallback
        return str(msg)

    return str(msg)


# =============================================================================
# Public API
# =============================================================================

def export_markdown(filename: str) -> Text:
    """Export the conversation history into a simple Markdown transcript.

    Parameters
    ----------
    filename : str
        Output file path. If falsey (e.g., empty string), defaults to
        ``"conversation.md"`` to preserve original behavior.

    Returns
    -------
    rich.text.Text
        A cyan success message on success; a red error message otherwise.
    """
    out_path = filename or _DEFAULT_EXPORT_FILENAME
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            if system_prompt:
                fh.write(f"## System Prompt\n\n{system_prompt}\n\n")
            for turn in conversation_history:
                fh.write(f"### User\n\n{turn.get('user', '')}\n\n")
                assistant_str = _assistant_to_str(turn.get("assistant", ""))
                fh.write(f"### Assistant\n\n{assistant_str}\n\n")
        return Text(f"Conversation exported to {out_path}", style="cyan")
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to export conversation: {exc}", style="red")


def get_stats() -> Text:
    """Compute a rough token-ish count (by whitespace) for the session."""
    total_tokens = 0
    for turn in conversation_history:
        total_tokens += len(str(turn.get("user", "")).split())
        total_tokens += len(_assistant_to_str(turn.get("assistant", "")).split())
    return Text(
        f"Approx token count: {total_tokens} (ignoring attachments)",
        style="light cyan",
    )
