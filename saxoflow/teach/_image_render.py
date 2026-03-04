# saxoflow/teach/_image_render.py
"""
Image rendering utilities for the SaxoFlow tutoring TUI.

Strategy
--------
1. Attempt ``chafa`` (Unicode/Braille art renderer) — best terminal-compatible
   option; works in any standard xterm-compatible terminal.
   - If the terminal reports sixel / truecolor support, chafa auto-promotes to
     that format and the rendering looks sharp.
   - On plain xterm/VS Code terminals, chafa falls back to its braille+block
     symbol mode which is significantly better than the legacy ``symbols``
     forced mode.
2. Graceful fallback — if ``chafa`` is not on PATH, emit a dim placeholder
   message so the student knows a figure exists at this point in the document.

``chafa`` install: ``sudo apt install chafa`` (Ubuntu/Debian)

Why the original ``--format=symbols`` looked garbled
------------------------------------------------------
Forcing ``--format=symbols`` locks chafa into its coarsest rendering mode:
only basic Unicode box-drawing characters with no colour depth.  Passing
``--stretch`` on top of that additionally warps the aspect ratio.  Removing
both lets chafa auto-detect the best available format (sixel > 256-colour
ANSI > braille symbols) and renders images dramatically better.

Python: 3.9+
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import os
from typing import Optional

__all__ = ["render_image_from_bytes"]

logger = logging.getLogger("saxoflow.teach.image_render")

# Width (in terminal columns) for chafa output.
_CHAFA_WIDTH = 72
# Max height in terminal rows (prevents screen flood on tall images).
_CHAFA_HEIGHT = 36


def render_image_from_bytes(
    image_bytes: bytes,
    image_ext: str = "png",
    fig_num: int = 1,
    width: int = _CHAFA_WIDTH,
    height: int = _CHAFA_HEIGHT,
) -> str:
    """Render *image_bytes* as a plain Unicode string suitable for terminal display.

    Uses ``chafa`` when available; falls back to a labelled placeholder.
    The returned string contains **no Rich markup** — callers are responsible
    for wrapping in ``rich.text.Text`` or escaping as needed.

    Parameters
    ----------
    image_bytes:
        Raw bytes of the image (PNG, JPEG, etc.).
    image_ext:
        File extension hinting at the format (used to name the temp file).
    fig_num:
        Figure number shown in the fallback placeholder label.
    width:
        Target width in terminal columns for chafa output.
    height:
        Maximum height in terminal rows; prevents very tall images flooding
        the screen.

    Returns
    -------
    str
        Either the chafa Unicode art string **or** a plain-text placeholder.
        Never raises; all errors are logged at DEBUG level and fall back to
        the placeholder.
    """
    if not image_bytes:
        return _placeholder(fig_num)

    chafa_path = shutil.which("chafa")
    if chafa_path:
        logger.debug("chafa found at: %s", chafa_path)
        return _render_with_chafa(image_bytes, image_ext, fig_num, width, height, chafa_path)

    logger.debug(
        "chafa not found on PATH. PATH=%s",
        os.environ.get("PATH", "(not set)"),
    )
    return _placeholder(fig_num)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _render_with_chafa(
    image_bytes: bytes,
    image_ext: str,
    fig_num: int,
    width: int,
    height: int,
    chafa_path: str,
) -> str:
    """Write *image_bytes* to a temp file and invoke chafa on it.

    chafa format auto-detection order (when no ``--format`` is forced):
      sixel (best) → truecolor ANSI → 256-colour ANSI → braille symbols

    Explicitly adding ``--symbols=braille+border+vhalf+hhalf+edge`` gives
    chafa's symbols-mode a much finer pixel grid (braille: 2×4 = 8× the
    resolution of plain block characters) when the terminal cannot do sixel.
    """
    suffix = f".{image_ext}" if image_ext else ".png"
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        # Pass TERM through so chafa can probe the real terminal's capabilities.
        # If TERM is not set (e.g. in a bare CI shell), default to xterm-256color
        # which gives chafa enough info to produce ANSI colour output.
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")

        result = subprocess.run(
            [
                chafa_path,
                # No --format flag — let chafa auto-pick the best available
                # format for the current terminal (sixel > ansi > symbols).
                "--symbols", "braille+border+vhalf+hhalf+edge+detail",
                "--size", f"{width}x{height}",  # cap both axes; preserve AR
                tmp_path,
            ],
            capture_output=True,
            # CRITICAL: force UTF-8 regardless of the system locale.
            # The default (text=True with no encoding) uses locale.getpreferredencoding()
            # which may be ASCII on minimal Linux systems, causing UnicodeDecodeError
            # for braille characters (U+2800+) — that exception is silently caught and
            # falls back to _placeholder even though chafa actually succeeded.
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=15,
        )

        if result.returncode == 0 and result.stdout:
            art = result.stdout.rstrip("\n")
            label = f"  Figure {fig_num}"
            return f"{art}\n{label}"

        logger.debug(
            "chafa returned code %d stderr=%r stdout_empty=%s",
            result.returncode,
            result.stderr[:200],
            not result.stdout,
        )

    except subprocess.TimeoutExpired:
        logger.debug("chafa timed out rendering figure %d", fig_num)
    except Exception as exc:
        logger.debug("chafa rendering failed for figure %d: %s", fig_num, exc)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    # chafa was available but failed — still show placeholder
    return _placeholder(fig_num)


def _placeholder(fig_num: int) -> str:
    """Return a plain-text placeholder for an unrenderable image."""
    inner_width = 60
    pad_label = f"Figure {fig_num} — image not rendered in terminal."
    pad_chafa = "Run: saxoflow install --single chafa"
    pad1 = " " * max(0, inner_width - len(pad_label))
    pad2 = " " * max(0, inner_width - len(pad_chafa))
    border = "\u2500" * (inner_width + 2)
    lines = [
        f"  \u256f{border}\u256e",
        f"  \u2502  {pad_label}{pad1}  \u2502",
        f"  \u2502  {pad_chafa}{pad2}  \u2502",
        f"  \u2570{border}\u256f",
    ]
    return "\n".join(lines)
