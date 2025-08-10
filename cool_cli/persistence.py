# cool_cli/persistence.py
"""
Persistence helpers for sessions and attachments.

Overview
--------
This module centralizes save/load operations for the interactive session, and
provides simple helpers to attach files, clear history, and set a global
system prompt.

Behavior is intentionally defensive:
- All public functions catch exceptions and return a user-facing Rich ``Text``
  message instead of raising (the CLI should not crash on I/O issues).
- File bytes are not persisted in session JSON; we only store attachment names,
  matching the original behavior.

Notes
-----
- Global state (``conversation_history``, ``attachments``, ``system_prompt``,
  ``config``) is sourced from :mod:`cool_cli.state` to keep parity with the
  rest of the app. We import the module (not the names) to ensure that writes
  mutate the canonical state shared across the application.
  # TODO(decide-future): Consider injecting state or adding a thin repository
  # object for easier testing and reduced global coupling.

Python: 3.9+
"""

from __future__ import annotations

import json
import os
from typing import Final, List  # noqa: F401  # kept for documentation/reference in type hints
# from typing import Dict  # UNUSED: kept for potential future metadata extensions.  # noqa: F401

from rich.text import Text

from . import state as _state

__all__ = [
    "attach_file",
    "save_session",
    "load_session",
    "clear_history",
    "set_system_prompt",
]

_DEFAULT_SESSION_FILENAME: Final[str] = "session.json"


# =============================================================================
# Public API
# =============================================================================

def attach_file(path: str) -> Text:
    """Attach a file by path; store name + raw bytes in memory.

    Parameters
    ----------
    path : str
        File system path to the file to attach.

    Returns
    -------
    rich.text.Text
        Cyan success message on success; bold red error message on failure.

    Notes
    -----
    - This stores the file contents in memory; large files may increase memory
      usage. The persisted session only records names (no bytes).
    """
    if not path:
        return Text("Attach command requires a file path.", style="bold red")
    if not os.path.isfile(path):
        return Text(f"File not found: {path}", style="bold red")
    try:
        with open(path, "rb") as f:
            content = f.read()
        _state.attachments.append({"name": os.path.basename(path), "content": content})
        return Text(f"Attached {os.path.basename(path)}", style="cyan")
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to attach file: {exc}", style="bold red")


def save_session(filename: str) -> Text:
    """Serialize conversation and metadata to JSON (no file bytes).

    Parameters
    ----------
    filename : str
        Destination JSON file path. If falsey (e.g., empty string), defaults to
        ``"session.json"`` to preserve original behavior.

    Returns
    -------
    rich.text.Text
        Cyan success message on success; bold red error message on failure.

    Format
    ------
    The saved JSON includes:
      - ``conversation_history`` (verbatim list of turns)
      - ``attachments`` (list of objects with only ``name``)
      - ``system_prompt`` (string)
      - ``config`` (dict)
    """
    out_path = filename or _DEFAULT_SESSION_FILENAME
    data = {
        "conversation_history": _state.conversation_history,
        "attachments": [{"name": att["name"]} for att in _state.attachments],
        "system_prompt": _state.system_prompt,
        "config": _state.config,
    }
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        return Text(f"Session saved to {out_path}", style="cyan")
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to save session: {exc}", style="bold red")


def load_session(filename: str) -> Text:
    """Load session JSON; reset globals; store attachment names only.

    Parameters
    ----------
    filename : str
        Source JSON file path.

    Returns
    -------
    rich.text.Text
        Cyan success message on success; bold red error message on failure.

    Behavior
    --------
    - Clears and repopulates ``conversation_history`` and ``attachments``.
    - File bytes are *not* loaded; we only track attachment names.
    - Merges loaded config keys into the current ``config`` dict.
    """
    if not filename:
        return Text("Load command requires a filename.", style="bold red")
    if not os.path.isfile(filename):
        return Text(f"Session file not found: {filename}", style="bold red")

    try:
        with open(filename, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        # Keep list identities stable by mutating in-place (slice assignment).
        _state.conversation_history[:] = data.get("conversation_history", [])
        _state.attachments[:] = [
            {"name": a.get("name", "unknown"), "content": b""}
            for a in data.get("attachments", [])
        ]
        # Update the system prompt in the shared state module.
        _state.system_prompt = data.get("system_prompt", "")

        # Update config keys rather than replacing the dict, preserving defaults.
        _state.config.update(data.get("config", {}))

        return Text(f"Session loaded from {filename}", style="cyan")
    except Exception as exc:  # noqa: BLE001
        return Text(f"Failed to load session: {exc}", style="bold red")


def clear_history() -> Text:
    """Clear conversation history and attachments (in memory).

    Returns
    -------
    rich.text.Text
        A confirmation message.
    """
    _state.conversation_history.clear()
    _state.attachments.clear()
    return Text("Conversation history and attachments cleared.", style="light cyan")


def set_system_prompt(prompt: str) -> Text:
    """Set or clear the global system prompt.

    Parameters
    ----------
    prompt : str
        New system prompt. Leading/trailing whitespace is stripped. An empty
        prompt clears the value.

    Returns
    -------
    rich.text.Text
        Cyan message when set; yellow message when cleared.

    Notes
    -----
    - We assign directly to ``state.system_prompt`` to ensure global visibility
      across the app. If callers imported the name directly (``from state import
      system_prompt``), they should reference the module/object rather than rebinding
      for consistency.  # TODO: Audit imports to prefer ``import state`` style.
    """
    _state.system_prompt = (prompt or "").strip()
    return Text(
        "System prompt set." if _state.system_prompt else "System prompt cleared.",
        style="cyan" if _state.system_prompt else "yellow",
    )

