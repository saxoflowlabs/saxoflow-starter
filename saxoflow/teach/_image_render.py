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
# Match the TUI panel width (~170 cols); 160 leaves room for panel borders.
_CHAFA_WIDTH = 160
# Max height in terminal rows.  Taller = more pixel rows = finer detail.
_CHAFA_HEIGHT = 48


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

    Tries progressively simpler chafa invocations to maximise the chance of
    getting *some* output when running inside a Rich panel (piped stdout,
    no TTY).

    Attempt order
    -------------
    1. Auto-detect mode — let chafa pick sixel/truecolor/ANSI based on TERM.
       ``TERM=xterm-256color`` is injected when not already set.
    2. Forced ``--format ansi`` — bypasses terminal detection entirely and
       always produces ANSI-escape colour output; safe for any pipe consumer.
    3. Forced ``--format symbols`` — lowest common denominator; always
       produces ASCII/Unicode block output even in a bare dumb terminal.

    UnicodeDecodeError prevention
    ------------------------------
    ``encoding="utf-8"`` with ``errors="replace"`` is mandatory.  The
    default ``text=True`` uses ``locale.getpreferredencoding()`` which may be
    ``ASCII`` on minimal Linux systems, causing a silent UnicodeDecodeError
    for braille characters (U+2800+) that collapses back to placeholder.
    """
    suffix = f".{image_ext}" if image_ext else ".png"
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        # Propagate TERM so chafa can detect terminal capabilities.
        # Force xterm-256color when unset (bare shells, venvs, CI).
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")
        env.setdefault("COLORTERM", "truecolor")  # hint: 24-bit colour available

        # --- Attempt 1: auto-detect (best quality) ---
        art = _run_chafa(
            chafa_path,
            ["--symbols", "braille+border+vhalf+hhalf+edge+detail",
             "--size", f"{width}x{height}"],
            tmp_path, env, fig_num,
        )
        if art:
            return art

        # --- Attempt 2: force ANSI colour output (always works when piped) ---
        logger.debug("chafa attempt 1 gave empty output; retrying with --format ansi")
        art = _run_chafa(
            chafa_path,
            ["--format", "ansi",
             "--symbols", "braille+border+vhalf+hhalf+edge+detail",
             "--size", f"{width}x{height}"],
            tmp_path, env, fig_num,
        )
        if art:
            return art

        # --- Attempt 3: symbols-only (dumb-terminal safe fallback) ---
        logger.debug("chafa attempt 2 gave empty output; retrying with --format symbols")
        art = _run_chafa(
            chafa_path,
            ["--format", "symbols", "--size", f"{width}x{height}"],
            tmp_path, env, fig_num,
        )
        if art:
            return art

        logger.debug("All chafa attempts produced empty output for figure %d", fig_num)

    except Exception as exc:
        logger.debug("chafa rendering failed for figure %d: %s", fig_num, exc)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return _placeholder(fig_num)


def _run_chafa(
    chafa_path: str,
    extra_args: list,
    tmp_path: str,
    env: dict,
    fig_num: int,
) -> Optional[str]:
    """Run chafa with *extra_args* and return the art string, or ``None``.

    Returns ``None`` when chafa exits non-zero OR produces empty stdout.
    """
    cmd = [chafa_path] + extra_args + [tmp_path]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            art = result.stdout.rstrip("\n")
            label = f"  Figure {fig_num}"
            return f"{art}\n{label}"

        logger.debug(
            "chafa cmd=%r rc=%d stdout_len=%d stderr=%r",
            cmd,
            result.returncode,
            len(result.stdout),
            result.stderr[:200],
        )
    except subprocess.TimeoutExpired:
        logger.debug("chafa timed out (cmd=%r fig=%d)", cmd, fig_num)
    except Exception as exc:
        logger.debug("chafa subprocess error (cmd=%r fig=%d): %s", cmd, fig_num, exc)
    return None


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
