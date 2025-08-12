"""
Export helpers (Markdown) and simple session statistics.
"""
from __future__ import annotations

from builtins import open as _builtin_open  # allow test monkeypatching via module symbol
from typing import Any, Final

from rich.markdown import Markdown
from rich.text import Text

from .state import conversation_history, system_prompt

__all__ = ["export_markdown", "get_stats"]

# Expose a module-level `open` for tests to monkeypatch.
open = _builtin_open  # type: ignore[assignment]  # noqa: A001

_DEFAULT_EXPORT_FILENAME: Final[str] = "conversation.md"


# =============================================================================
# Internal helpers
# =============================================================================

def _assistant_to_str(msg: Any) -> str:
    """Normalize assistant content to a plain string.

    - ``Text`` → ``.plain`` to avoid Rich markup in the export.
    - ``Markdown`` → source markdown, checking several versions' attribute names.
    - Anything else → ``str(msg)``.
    """
    if isinstance(msg, Text):
        return msg.plain
    if isinstance(msg, Markdown):
            # Try multiple Rich versions' attribute names for the source text.
            for attr in ("text", "markdown", "source", "_markdown", "_text"):
                val = getattr(msg, attr, None)
                if isinstance(val, str):
                    return val
            # Final fallback: stringification
            return str(msg)
    return str(msg)


# =============================================================================
# Public API
# =============================================================================

def export_markdown(filename: str) -> Text:
    """Export the conversation history into a simple Markdown transcript."""
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
