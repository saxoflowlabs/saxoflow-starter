# cool_cli/banner.py
"""
Gradient banner rendering utilities for SaxoFlow.

Public API
----------
- interpolate_color(stops, t): RGB interpolation across color stops.
- print_banner(console, compact=False): Render the SAXOFLOW banner with a
  left-to-right blue→cyan→white gradient using Rich.

Design notes
------------
- The module validates inputs (color stops and ASCII art) and guards the
  render path with exceptions translated into a safe fallback, so a CLI
  session will not crash on banner rendering errors.
- Internal helpers are small and testable. Public function signatures
  are preserved for backward compatibility.

Python 3.9+ compatible.
"""

from __future__ import annotations

from typing import Iterable, List, Sequence, Tuple

from rich.console import Console
from rich.text import Text

# Type aliases for readability (3.9+ compatible).
RGB = Tuple[int, int, int]
RGBStops = Sequence[RGB]

__all__ = ["interpolate_color", "print_banner"]

# =============================================================================
# Gradient presets
# =============================================================================

# Default, smooth gradient: Deep blue → Blue → Cyan → Light-cyan → White.
_COLOR_STOPS_DEFAULT: RGBStops = (
    (0, 60, 180),     # Deep blue
    (0, 120, 255),    # Blue
    (0, 200, 255),    # Cyan-ish
    (0, 255, 255),    # Cyan
    (120, 255, 255),  # Light cyan
    (220, 255, 255),  # Near white
    (255, 255, 255),  # White
)

# NOTE: Alternative stops kept for future experimentation with a cooler tone.
# Keeping it commented (unused) per requirement to not delete unused ideas.
# _COLOR_STOPS_COOLER: RGBStops = (
#     (0, 40, 120),
#     (0, 100, 210),
#     (0, 170, 230),
#     (80, 230, 255),
#     (220, 255, 255),
#     (255, 255, 255),
# )  # TODO(decide-future): Compare visual contrast vs default.


# =============================================================================
# ASCII art (immutable source; functions return copies)
# =============================================================================

_ASCII_COMPACT: Tuple[str, ...] = (
    "███  ███  █   █  ███  ███  █    ███  █   █",
    "█    █ █   █ █   █ █  █    █    █ █  █ █ █",
    "███  ███    █    ███  ███  █    ███  █ █ █",
    "  █  █ █   █ █   █ █  █    █    █ █  █ █ █",
    "███  █ █  █   █  █ █  █    ███  ███   █ █ ",
)

_ASCII_FULL: Tuple[str, ...] = (
    "███████╗ █████╗ ██╗   ██╗ ██████╗  ██████╗ ██╗      ██████╗ ██╗    ██╗",
    "██╔════╝██╔══██╗ ██║ ██╔╝██╔═══██╗██╔════╝ ██║     ██╔═══██╗██║    ██║",
    "███████╗███████║  ████╔╝ ██║   ██║██████╗  ██║     ██║   ██║██║ █╗ ██║",
    "╚════██║██╔══██║ ██╔═██╗ ██║   ██║██╔═══╝  ██║     ██║   ██║██║███╗██║",
    "███████║██║  ██║██║   ██╗╚██████╔╝██║      ███████╗╚██████╔╝╚███╔███╔╝",
    "╚══════╝╚═╝  ╚═╝╚═╝   ╚═╝ ╚═════╝ ╚═╝      ╚══════╝ ╚═════╝  ╚══╝╚══╝ ",
    "",
)


# =============================================================================
# Internal helpers
# =============================================================================

def _clamp01(x: float) -> float:
    """Clamp a float into [0, 1]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _validate_color_stops(stops: RGBStops) -> None:
    """Validate color stops for interpolation.

    Args:
        stops: Sequence of (R, G, B) tuples.

    Raises:
        ValueError: If stops are fewer than 2 or any component is out of 0..255.
    """
    if stops is None or len(stops) < 2:
        raise ValueError("color stops must contain at least two (R,G,B) tuples.")
    for idx, (r, g, b) in enumerate(stops):
        if not (0 <= r <= 255 and 0 <= g <= 255 and 0 <= b <= 255):
            raise ValueError(f"color component out of range at index {idx}: {(r, g, b)}")


def _select_ascii_art(compact: bool) -> List[str]:
    """Return the ASCII art lines for the banner according to the layout.

    Note:
        Returns a new list to avoid accidental mutation of module-level tuples.
    """
    return list(_ASCII_COMPACT if compact else _ASCII_FULL)


def _build_gradient_text(ascii_art: Iterable[str], color_stops: RGBStops) -> Text:
    """Build a Rich Text object with a left→right gradient applied per row.

    Args:
        ascii_art: Iterable of banner lines.
        color_stops: Sequence of RGB color stops.

    Returns:
        Rich `Text` object with styles applied.

    Raises:
        ValueError: If ascii_art is empty or color_stops are invalid.
    """
    _validate_color_stops(color_stops)

    lines = [line for line in ascii_art]
    if not any(line.strip() for line in lines):
        raise ValueError("ascii_art is empty or whitespace-only.")

    gradient_text = Text()
    # Compute width over non-blank lines to get a consistent gradient scale.
    visible_lines = [line for line in lines if line.strip()]
    if not visible_lines:
        # Safety: should be unreachable due to check above.
        raise ValueError("no visible lines found in ascii_art.")  # TODO: confirm invariant.

    max_width = max(len(line) for line in visible_lines)

    for line in lines:
        for col_idx, char in enumerate(line):
            if char == " ":
                gradient_text.append(char)
                continue
            # Normalize column index across the visible width into [0,1].
            t = _clamp01(col_idx / max(1, max_width - 1))
            r, g, b = interpolate_color(color_stops, t)
            gradient_text.append(char, style=f"bold rgb({r},{g},{b})")
        gradient_text.append("\n")
    return gradient_text


# =============================================================================
# Public API
# =============================================================================

def interpolate_color(stops: RGBStops, t: float) -> RGB:
    """Interpolate between a list of RGB color stops.

    Parameters
    ----------
    stops : Sequence[Tuple[int, int, int]]
        A sequence of RGB tuples with values 0..255. Must contain ≥ 2 stops.
    t : float
        Interpolation parameter in [0, 1]. Values outside the range are
        clamped.

    Returns
    -------
    Tuple[int, int, int]
        The interpolated RGB value.

    Notes
    -----
    - Uses piecewise linear interpolation between adjacent stops.
    - The first matching segment is used; edge values (0 and 1) snap to
      the first and last stop, respectively.
    """
    _validate_color_stops(stops)
    t = _clamp01(float(t))

    if t <= 0.0:
        return stops[0]
    if t >= 1.0:
        return stops[-1]

    seg = 1.0 / (len(stops) - 1)
    idx = int(t / seg)
    if idx >= len(stops) - 1:
        # Numerical safety at t ~ 1.0 after float ops.
        return stops[-1]

    local_t = (t - seg * idx) / seg
    c1 = stops[idx]
    c2 = stops[idx + 1]

    r = int(c1[0] + (c2[0] - c1[0]) * local_t)
    g = int(c1[1] + (c2[1] - c1[1]) * local_t)
    b = int(c1[2] + (c2[2] - c1[2]) * local_t)
    return r, g, b


def print_banner(console: Console, compact: bool = False) -> None:
    """Print the SAXOFLOW banner with a smooth blue→cyan→white gradient.

    This is a guarded render function: on any internal error it falls back
    to a plain bold white banner so the CLI remains usable.

    Args:
        console: A `rich.console.Console` instance to print to.
        compact: If True, use a compact banner layout.

    Examples
    --------
    >>> from rich.console import Console
    >>> print_banner(Console(), compact=True)
    """
    try:
        ascii_art = _select_ascii_art(compact=compact)
        text = _build_gradient_text(ascii_art, _COLOR_STOPS_DEFAULT)
        console.print(text)
    except Exception as exc:  # noqa: BLE001
        # Safe fallback: print unstyled ASCII art; log-friendly message inline.
        # TODO(decide-future): route this to a logger once logging is centralized.
        fallback = Text()
        for line in _select_ascii_art(compact=compact):
            fallback.append(line + "\n", style="bold white")
        fallback.append(f"\n[warning] Banner rendered without gradient: {exc}[/warning]\n")
        console.print(fallback)
