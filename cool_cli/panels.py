# cool_cli/panels.py
"""
Rich panel builders for SaxoFlow's interactive CLI.

Public API
----------
- welcome_panel(text, panel_width=None) -> Panel
- user_input_panel(message, width=None) -> Panel
- output_panel(renderable, border_style="white", icon=None, width=None) -> Panel
- error_panel(message, width=None) -> Panel
- ai_panel(renderable, width=None) -> Panel
- agent_panel(renderable, border_style="magenta", icon=None, width=None) -> Panel

Design notes
------------
- Functions are defensive and will not crash on common input issues; they coerce
  strings to `Text` and ensure wrapping so long lines don't break the layout.
- Width calculation uses a safe default derived from the terminal size with
  sensible bounds to avoid overly narrow/wide panels.
- Unused parameters from the original code are **kept** (e.g., `icon`,
  `border_style` in `output_panel`) per requirement. Where a parameter is not
  used, it's documented inline with a TODO.

Python 3.9+ compatible.
"""

from __future__ import annotations

from typing import Final, Optional, Union

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

__all__ = [
    "welcome_panel",
    "user_input_panel",
    "output_panel",
    "error_panel",
    "ai_panel",
    "agent_panel",
]

# =============================================================================
# Configuration
# =============================================================================

_DEFAULT_MIN_WIDTH: Final[int] = 80
_DEFAULT_WIDTH_SCALE: Final[float] = 0.8


# =============================================================================
# Internal helpers
# =============================================================================

def _default_panel_width(scale: float = _DEFAULT_WIDTH_SCALE) -> int:
    """Compute a reasonable panel width based on terminal size.

    Parameters
    ----------
    scale : float
        Fraction of the terminal width to use. Defaults to 0.8 (80%).

    Returns
    -------
    int
        A width in characters, with a lower bound to reduce cramping.
    """
    try:
        term_width = Console().width
    except Exception:
        # Fallback if Rich can't get terminal width for any reason.
        term_width = _DEFAULT_MIN_WIDTH * 2
    width = int(term_width * scale)
    return max(_DEFAULT_MIN_WIDTH, width)


def _coerce_text(
    renderable: Union[str, Text],
    *,
    style: Optional[str] = None,
    no_wrap: bool = False,
    overflow: str = "fold",
) -> Text:
    """Return a `Text` object with consistent wrapping rules.

    - Strings are converted to `Text` with the given style.
    - Existing `Text` objects have `no_wrap` and `overflow` normalized.

    Parameters
    ----------
    renderable : str | Text
        The content to render.
    style : str, optional
        Rich style applied when `renderable` is a string.
    no_wrap : bool
        Whether to disable wrapping. We default to False so long lines wrap.
    overflow : str
        How to wrap/clip long content. We use "fold" to break anywhere.

    Returns
    -------
    Text
        A `rich.text.Text` instance ready for use inside a `Panel`.
    """
    if isinstance(renderable, Text):
        renderable.no_wrap = no_wrap
        renderable.overflow = overflow
        return renderable
    if isinstance(renderable, str):
        return Text(renderable, style=style, no_wrap=no_wrap, overflow=overflow)
    # Be forgiving: coerce unknown renderables via repr to avoid crashes.
    # TODO(decide-future): consider supporting more Rich types directly.
    return Text(repr(renderable), style=style, no_wrap=no_wrap, overflow=overflow)


# =============================================================================
# Public panel builders
# =============================================================================

def welcome_panel(welcome_text: str, panel_width: Optional[int] = None) -> Panel:
    """Render a welcome message panel (styled as coming from SaxoFlow).

    Parameters
    ----------
    welcome_text : str
        Body text to show in the panel.
    panel_width : int, optional
        Explicit width override. If omitted, uses a default derived from
        terminal width.

    Returns
    -------
    Panel
        A Rich panel with cyan border and left-aligned "saxoflow" title.
    """
    width = panel_width if panel_width is not None else _default_panel_width()
    body = _coerce_text(welcome_text, style="bold white", no_wrap=False)
    return Panel(
        body,
        border_style="cyan",
        title="saxoflow",
        title_align="left",
        padding=(0, 1),
        width=width,
        expand=False,
    )


def user_input_panel(message: str, width: Optional[int] = None) -> Panel:
    """Create a panel representing the user's input.

    Parameters
    ----------
    message : str
        The user's message text.
    width : int, optional
        Panel width. Defaults to a safe width based on terminal size.

    Returns
    -------
    Panel
        A cyan-bordered panel labeled "user".
    """
    w = width if width is not None else _default_panel_width()
    txt = _coerce_text(message, style="bold white", no_wrap=False, overflow="fold")
    return Panel(
        txt,
        border_style="cyan",
        title="user",
        title_align="left",
        padding=(0, 1),
        expand=False,
        width=w,
    )


def output_panel(
    renderable: Union[str, Text],
    border_style: str = "white",  # kept for signature compatibility
    icon: Optional[str] = None,   # kept for signature compatibility
    width: Optional[int] = None,
) -> Panel:
    """Wrap generic output in a panel.

    Parameters
    ----------
    renderable : str | Text
        Content to display.
    border_style : str
        **Unused (kept for compatibility).** Current behavior always uses
        `"orange1"` to match the original implementation.
        # TODO(decide-future): honor this parameter once downstream callers
        # expect customizable borders.
    icon : str, optional
        **Unused (kept for compatibility).** Reserved for future decorations.
    width : int, optional
        Panel width; calculated by default.

    Returns
    -------
    Panel
        An `"orange1"` bordered panel titled "saxoflow".
    """
    _ = (border_style, icon)  # silence linters; kept for signature compatibility
    w = width if width is not None else _default_panel_width()
    txt = _coerce_text(renderable, no_wrap=False, overflow="fold")
    return Panel(
        txt,
        border_style="orange1",  # preserving original behavior
        title="saxoflow",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=w,
    )


def error_panel(message: str, width: Optional[int] = None) -> Panel:
    """Create an error panel with red border and yellow text.

    Parameters
    ----------
    message : str
        Human-readable error message.
    width : int, optional
        Panel width; calculated by default.

    Returns
    -------
    Panel
        A red-bordered panel labeled "error".
    """
    w = width if width is not None else _default_panel_width()
    txt = _coerce_text(f"Error: {message}", style="yellow", no_wrap=False)
    return Panel(
        txt,
        border_style="red",
        title="error",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=w,
    )


def ai_panel(renderable: Union[str, Text], width: Optional[int] = None) -> Panel:
    """Create a panel for assistant/AI output.

    Parameters
    ----------
    renderable : str | Text
        The assistant-rendered content.
    width : int, optional
        Panel width; calculated by default.

    Returns
    -------
    Panel
        A bold cyan-bordered panel labeled "saxoflow_AI".
    """
    w = width if width is not None else _default_panel_width()
    txt = _coerce_text(renderable, style="white", no_wrap=False, overflow="fold")
    return Panel(
        txt,
        border_style="bold cyan",
        title="saxoflow_AI",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=w,
    )


def agent_panel(
    renderable: Union[str, Text],
    border_style: str = "magenta",
    icon: Optional[str] = None,  # kept for compatibility
    width: Optional[int] = None,
) -> Panel:
    """Create a panel for agentic pipeline output.

    Parameters
    ----------
    renderable : str | Text
        The agent's output content.
    border_style : str
        Border color/style for the panel. Defaults to `"magenta"`.
    icon : str, optional
        **Unused (kept for compatibility).** Reserved for future decorations.
    width : int, optional
        Panel width; calculated by default.

    Returns
    -------
    Panel
        A panel titled "saxoflow_agent" with the configured border.
    """
    _ = icon  # silence linters; kept for signature compatibility
    w = width if width is not None else _default_panel_width()
    txt = _coerce_text(renderable, no_wrap=False, overflow="fold")
    return Panel(
        txt,
        border_style=border_style,
        title="saxoflow_agent",
        title_align="left",
        padding=(1, 2),
        expand=False,
        width=w,
    )
