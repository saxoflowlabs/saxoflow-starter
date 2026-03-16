# cool_cli/constants.py
"""
Shared constants and defaults for the SaxoFlow Cool CLI (Python 3.9+).

This module centralizes command names, editor sets, and default runtime config
so behavior remains consistent across the application.

Public API
----------
- SHELL_COMMANDS: Mapping of alias ➜ underlying command list.
- BLOCKING_EDITORS: Terminal editors that block the TUI.
- NONBLOCKING_EDITORS: GUI/daemon editors that do not block the TUI.
- AGENTIC_COMMANDS: Commands routed to the Agentic AI CLI.
- DEFAULT_CONFIG: Template configuration values (copy before mutating).
- CUSTOM_PROMPT_HTML: Prompt markup for prompt_toolkit.
- new_default_config(): Return a deep-copied DEFAULT_CONFIG for safe mutation.

Notes
-----
- Keep `DEFAULT_CONFIG` immutable by convention: callers should copy it before
  mutating (see `new_default_config()`).
- All constants are typed for clarity and linting. Behavior is unchanged.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Dict, Final, List, Tuple

__all__ = [
    "SHELL_COMMANDS",
    "BLOCKING_EDITORS",
    "NONBLOCKING_EDITORS",
    "AGENTIC_COMMANDS",
    "DEFAULT_CONFIG",
    "CUSTOM_PROMPT_HTML",
    "new_default_config",
]

# Type aliases for readability.
CommandList = List[str]


# ---------------------------------------------------------------------------
# Shell aliases supported in the CLI.
# These are rendered as simple, safe command lists (no shell=True usage).
# ---------------------------------------------------------------------------
SHELL_COMMANDS: Final[Dict[str, CommandList]] = {
    "ls": ["ls"],
    "ll": ["ls", "-la"],
    "pwd": ["pwd"],
    "whoami": ["whoami"],
    "date": ["date"],
    # NOTE(unused-idea): Add more safe aliases as needed.
    # "df": ["df", "-h"],
    # "du": ["du", "-h"],
}

# ---------------------------------------------------------------------------
# Editors: blocking (terminal) vs. non-blocking (GUI/daemonized) sets.
# Blocking editors are treated specially by the shell to suspend/resume the TUI.
# ---------------------------------------------------------------------------
BLOCKING_EDITORS: Final[Tuple[str, ...]] = ("nano", "vim", "vi", "micro")
NONBLOCKING_EDITORS: Final[Tuple[str, ...]] = ("code", "subl", "gedit")

# ---------------------------------------------------------------------------
# Agentic subcommands routed to saxoflow_agenticai.
# Order is meaningful for display; keep it stable.
# ---------------------------------------------------------------------------
AGENTIC_COMMANDS: Final[Tuple[str, ...]] = (
    "rtlgen",
    "tbgen",
    "fpropgen",
    "report",
    "rtlreview",
    "tbreview",
    "fpropreview",
    "debug",
    "sim",
    "fullpipeline",
    # NOTE(unused-idea): Consider exposing additional verbs when stable.
    # "analyze",
    # "optimize",
)

# ---------------------------------------------------------------------------
# Default runtime config (expand as needed).
# IMPORTANT: Treat as a template; copy it before mutating at runtime.
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Final[Dict[str, object]] = {
    "model": "placeholder",
    "temperature": 0.7,
    "top_k": 1,
    "top_p": 1.0,
    # TODO(decide-future): Add fields like "provider", "timeout_s" when wired.
}

# Prompt (HTML) used by prompt_toolkit.
CUSTOM_PROMPT_HTML: Final[str] = (
    "<ansibrightwhite>✦</ansibrightwhite> "
    "<ansicyan><b>saxoflow</b></ansicyan> "
    "<ansibrightwhite>⮞</ansibrightwhite> "
)


def new_default_config() -> Dict[str, object]:
    """Return a deep copy of :data:`DEFAULT_CONFIG` for safe mutation.

    Returns
    -------
    Dict[str, object]
        A deep-copied dictionary that callers may freely mutate.

    Rationale
    ---------
    Many call-sites want a mutable configuration derived from the defaults.
    Returning a copy avoids accidental in-place changes to module-level state.
    """
    # Defensive copy ensures module-level defaults remain immutable by convention.
    return deepcopy(DEFAULT_CONFIG)
