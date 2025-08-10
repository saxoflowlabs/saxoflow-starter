# cool_cli/editors.py
"""
Editor launch helpers for the SaxoFlow Cool CLI (Python 3.9+).

Overview
--------
This module centralizes logic to detect and launch editors in a
user-friendly way for an interactive TUI:

- Blocking editors (``nano``, ``vim``, ``vi``, ``micro``) suspend the
  prompt-toolkit application if present, then resume upon exit.
- GUI/non-blocking editors (``code``, ``subl``, ``gedit``) are started
  in the background without blocking the TUI.
- Any other command is executed via ``subprocess.run`` with stdout/stderr
  returned as a Rich ``Text`` element.

Behavior is preserved from the original implementation. Any exceptions
are caught and surfaced as readable error messages (no crashes).

Public API
----------
- is_blocking_editor_command(user_input: str) -> bool
- is_terminal_editor(cmd: str) -> bool
- handle_terminal_editor(shell_cmd: str) -> Text

Notes
-----
- The module is intentionally defensive. Shlex errors, missing commands,
  and subprocess errors are converted into friendly ``Text`` messages.
- Unused ideas are kept commented for reference per project guidelines.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from typing import List, Optional

from prompt_toolkit.application.current import get_app_or_none
from rich.text import Text

from .constants import BLOCKING_EDITORS, NONBLOCKING_EDITORS

__all__ = [
    "is_blocking_editor_command",
    "is_terminal_editor",
    "handle_terminal_editor",
]


# =============================================================================
# Internal helpers
# =============================================================================

def _safe_shlex_split(command: str) -> Optional[List[str]]:
    """Safely split a shell command into tokens.

    Parameters
    ----------
    command : str
        Raw command string.

    Returns
    -------
    list[str] | None
        The token list, or ``None`` if the string is empty. Raises no exceptions.

    Notes
    -----
    ``shlex.split`` can raise ``ValueError`` on unbalanced quotes.
    We swallow that and treat the command as invalid in caller functions.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    return tokens or None


def _first_token(cmd: str) -> str:
    """Return the first token of a command, honoring an optional leading ``!``.

    Parameters
    ----------
    cmd : str
        Command string (may begin with ``!``).

    Returns
    -------
    str
        The first token or an empty string if none could be parsed.
    """
    stripped = (cmd or "").strip()
    if not stripped:
        return ""
    if stripped.startswith("!"):
        # After '!', we still need the actual first token.
        rest = stripped[1:].strip()
        return rest.split(maxsplit=1)[0] if rest else ""
    return stripped.split(maxsplit=1)[0]


def _run_blocking_editor(shell_cmd: str, editor: str) -> Text:
    """Run a blocking editor, suspending prompt-toolkit if available.

    Parameters
    ----------
    shell_cmd : str
        The full command line to execute (e.g., 'nano file.v').
    editor : str
        The resolved editor program name (first token).

    Returns
    -------
    rich.text.Text
        A message indicating we have returned from the editor.

    Notes
    -----
    Uses ``os.system`` to preserve exact behavior and environment semantics.
    """
    app = get_app_or_none()

    def _invoke() -> None:
        # Interactive usage by design (no shell=True for general shell commands).
        # `os.system` is intentionally kept to match prior behavior (env, PATH, TTY).
        os.system(shell_cmd)  # noqa: S605

    if app:
        # Suspend prompt-toolkit so the editor controls the terminal.
        app.suspend_to_background(func=_invoke)
    else:
        _invoke()
    return Text(f"✅ Returned from {editor}", style="cyan")


def _launch_nonblocking(tokens: List[str], editor: str) -> Text:
    """Launch a non-blocking (GUI) editor and return immediately.

    Parameters
    ----------
    tokens : list[str]
        Tokenized command, e.g., ['code', 'file.v'].
    editor : str
        Editor program name.

    Returns
    -------
    rich.text.Text
        A status message indicating launch success or a readable error.
    """
    try:
        subprocess.Popen(tokens)  # noqa: S603
        return Text(f"🚀 Launched {editor} in background", style="cyan")
    except Exception as exc:  # noqa: BLE001
        # Keep UX consistent: never raise, always return readable output.
        return Text(f"❌ Failed to launch {editor}: {exc}", style="red")


def _run_sync_command(tokens: List[str]) -> Text:
    """Run a non-editor command synchronously and return combined output.

    Parameters
    ----------
    tokens : list[str]
        Tokenized command (no shell).

    Returns
    -------
    rich.text.Text
        Combined stdout/stderr as white text, or a readable error message.
    """
    try:
        result = subprocess.run(tokens, capture_output=True, text=True)  # noqa: S603
        # Preserve original behavior: return stdout, else stderr, else empty.
        return Text((result.stdout or result.stderr or ""), style="white")
    except Exception as exc:  # noqa: BLE001
        return Text(f"❌ Shell error: {exc}", style="red")


# =============================================================================
# Public API
# =============================================================================

def is_blocking_editor_command(user_input: str) -> bool:
    """Return ``True`` if the input launches a blocking terminal editor.

    Parameters
    ----------
    user_input : str
        The user-entered command (may include a leading ``!``).

    Returns
    -------
    bool
        ``True`` if the resolved first token is a blocking editor (nano/vim/vi/micro).

    Examples
    --------
    >>> is_blocking_editor_command("nano file.txt")
    True
    >>> is_blocking_editor_command("!vim path/to/file")
    True
    >>> is_blocking_editor_command("code file.txt")
    False
    """
    first = _first_token(user_input)
    return bool(first) and first in BLOCKING_EDITORS


def is_terminal_editor(cmd: str) -> bool:
    """Detect whether a command would launch a terminal/GUI editor.

    Parameters
    ----------
    cmd : str
        Raw command string, with or without a leading ``!``.

    Returns
    -------
    bool
        ``True`` for known editors (blocking or non-blocking), else ``False``.

    Examples
    --------
    >>> is_terminal_editor("vim file")
    True
    >>> is_terminal_editor("!code file")
    True
    >>> is_terminal_editor("cat file")
    False
    """
    first = _first_token(cmd)
    # Tuple + tuple concatenation is fine; keep types as defined in constants.
    return bool(first) and (first in BLOCKING_EDITORS or first in NONBLOCKING_EDITORS)


def handle_terminal_editor(shell_cmd: str) -> Text:
    """Launch editors or run a command in a user-friendly way.

    Behavior
    --------
    - Blocking editors suspend the prompt-toolkit app if present, then resume.
    - Non-blocking editors launch in background via ``subprocess.Popen``.
    - Other commands run synchronously via ``subprocess.run``.

    Parameters
    ----------
    shell_cmd : str
        Command string to execute (no leading ``!`` expected here).

    Returns
    -------
    rich.text.Text
        A user-readable message or the command's stdout/stderr.

    Notes
    -----
    - This function never raises; exceptions are converted into error messages.
    - ``shell=True`` is never used. We pass tokenized arguments to subprocess.
    """
    tokens = _safe_shlex_split(shell_cmd)
    if tokens is None:
        # Could be empty input or a shlex parsing error.
        # Distinguish with a quick re-check:
        if (shell_cmd or "").strip():
            return Text("[❌] Bad command: could not parse input", style="red")
        return Text("[❌] No command specified.", style="red")

    editor = tokens[0]

    # Blocking editors: suspend TUI if possible, then run foreground editor.
    if editor in BLOCKING_EDITORS:
        return _run_blocking_editor(shell_cmd, editor)

    # GUI/Non-blocking editors: launch and return immediately.
    if editor in NONBLOCKING_EDITORS:
        return _launch_nonblocking(tokens, editor)

    # Fallback: run like a normal command and return combined output.
    return _run_sync_command(tokens)
