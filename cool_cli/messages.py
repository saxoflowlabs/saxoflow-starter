"""
ASCII-only, colorized message helpers for SaxoFlow.

Goals
-----
- Eliminate ambiguous-width glyphs (emoji, smart quotes, em dashes, etc.).
- Keep borders intact by ensuring all content is single-width ASCII.
- Provide consistent level prefixes and styles (SUCCESS, WARNING, ERROR, ...).
- Return Rich `Text` (for console/panels) or plain strings (for click/print).

Usage
-----
from cool_cli import messages as msg

console.print(msg.success("Installed Yosys"))
print(msg.s_warning("Virtualenv not found"))
"""

from __future__ import annotations

from typing import Final
import re

from rich.text import Text

__all__ = [
    "ascii_sanitize",
    "info",
    "success",
    "warning",
    "error",
    "tip",
    "note",
    "s_info",
    "s_success",
    "s_warning",
    "s_error",
    "s_tip",
    "s_note",
]

# Strip ANSI / escape codes (safety when content comes from shell tools)
_ANSI_RE: Final[re.Pattern[str]] = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

# Map common non-ASCII glyphs to safe ASCII; everything else becomes a space
_TRANSLATE: Final[dict[int, str]] = str.maketrans(
    {
        "•": "*",
        "—": "-",
        "–": "-",
        "…": "...",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "→": "->",
        "←": "<-",
        "↔": "<->",
        "↳": "->",
        "➜": "->",
        # frequently seen emoji/icons — drop or translate to ASCII hints
        "✅": "",
        "❌": "",
        "⚠": "",
        "📂": "",
        "👉": "->",
        "🌀": "",
    }
)


def ascii_sanitize(text: str) -> str:
    """Return an ASCII-only, markup-safe, single-width string.

    - Strips ANSI escape sequences.
    - Replaces tabs with 4 spaces and CR with LF.
    - Translates common non-ASCII punctuation/icons to ASCII.
    - Replaces any other non-ASCII or control characters (except newline) with a space.
    """
    if not text:
        return text
    out = _ANSI_RE.sub("", text)
    out = out.replace("\r", "\n").expandtabs(4)
    out = out.translate(_TRANSLATE)
    # keep newline; replace other non-ASCII/controls with a space
    return "".join(ch if (ch == "\n" or 32 <= ord(ch) < 127) else " " for ch in out)


# ---------- Rich Text API: for console.print / inside panels ----------


def _mk_text(prefix: str, msg: str, style: str) -> Text:
    """Build a Rich Text object with safe wrapping."""
    return Text(
        f"{prefix} {ascii_sanitize(msg)}",
        style=style,
        no_wrap=False,          # allow wrapping
        overflow="fold",        # break long tokens (URLs/paths)
    )


def info(msg: str) -> Text:
    return _mk_text("INFO:", msg, "bold cyan")


def success(msg: str) -> Text:
    return _mk_text("SUCCESS:", msg, "bold green")


def warning(msg: str) -> Text:
    return _mk_text("WARNING:", msg, "bold yellow")


def error(msg: str) -> Text:
    return _mk_text("ERROR:", msg, "bold red")


def tip(msg: str) -> Text:
    return _mk_text("TIP:", msg, "blue")


def note(msg: str) -> Text:
    return _mk_text("NOTE:", msg, "white")


# ---------- Plain-string API: for print()/click.secho paths ----------


def _mk_str(prefix: str, msg: str) -> str:
    """Build a sanitized plain string (no Rich dependency at callsite)."""
    return f"{prefix} {ascii_sanitize(msg)}"


def s_info(msg: str) -> str:
    return _mk_str("INFO:", msg)


def s_success(msg: str) -> str:
    return _mk_str("SUCCESS:", msg)


def s_warning(msg: str) -> str:
    return _mk_str("WARNING:", msg)


def s_error(msg: str) -> str:
    return _mk_str("ERROR:", msg)


def s_tip(msg: str) -> str:
    return _mk_str("TIP:", msg)


def s_note(msg: str) -> str:
    return _mk_str("NOTE:", msg)
