# saxoflow/teach/_image_render.py
"""
Image notice utilities for the SaxoFlow tutoring TUI.

Instead of attempting to render images as low-resolution terminal art,
this module emits a clean notice that tells the student a figure is
available and how to open it at full resolution via 'fig N'.

Python: 3.9+
"""

from __future__ import annotations

__all__ = ["render_image_from_bytes"]


def render_image_from_bytes(
    image_bytes: bytes,
    image_ext: str = "png",
    fig_num: int = 1,
    **_kwargs,
) -> str:
    """Return a plain-text notice telling the student to use 'fig N' to view.

    Inline terminal rendering (chafa) has been removed in favour of the
    full-resolution 'fig N' command which opens the image in the system
    viewer.  This function is kept so call-sites require no changes.

    Returns
    -------
    str
        Plain text — no Rich markup, no ANSI escape codes.
    """
    return _notice(fig_num, image_ext)


def _notice(fig_num: int, image_ext: str = "png") -> str:
    """Return a one-line notice with the open-in-viewer instruction."""
    ext = image_ext.upper() if image_ext else "IMG"
    inner = f"Figure {fig_num} ({ext}) — type 'fig {fig_num}' to open in system image viewer"
    border = "\u2500" * (len(inner) + 4)
    return (
        f"  \u250c{border}\u2510\n"
        f"  \u2502  {inner}  \u2502\n"
        f"  \u2514{border}\u2518"
    )
