# cool_cli/state.py
"""
Global runtime state for the SaxoFlow Cool CLI.

This module provides the *single source of truth* for shared, mutable runtime
objects used by the CLI:

- `console` / `runner`: process-wide singletons used by interactive flows.
- `conversation_history`: ordered list of user/assistant turns.
- `attachments`: transient file blobs (name + bytes) attached during a session.
- `system_prompt`: optional system instruction string.
- `config`: mutable runtime configuration (copy of defaults).

Why a dedicated module?
-----------------------
Keeping these globals in one small module makes them easy to:
- monkeypatch in unit tests,
- inspect/debug in REPL,
- and reset deterministically between test runs.

Behavioral guarantees (preserved)
---------------------------------
- Importing this module initializes state to defaults.
- Callers are allowed to mutate the exported lists/dicts in-place (preserved
  behavior from the original codebase).
- Utility helpers are provided for tests, but **they do not change** default
  behavior unless explicitly called.

Python: 3.9+ compatible.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from click.testing import CliRunner
from rich.console import Console

from .constants import DEFAULT_CONFIG

__all__ = [
    # Singletons / state
    "console",
    "runner",
    "conversation_history",
    "attachments",
    "system_prompt",
    "config",
    # Utilities
    "reset_state",
    "get_state_snapshot",
    # Type hints (exported for test/type consumers)
    "HistoryTurn",
    "Attachment",
]


# =============================================================================
# Type definitions (3.9+)
# =============================================================================

class HistoryTurn(TypedDict, total=False):
    """One turn in the conversation history.

    Attributes
    ----------
    user : str
        The user's input text for the turn.
    assistant : Any
        The assistant response. May be `str`, `rich.text.Text`,
        `rich.markdown.Markdown`, or another Rich renderable.
    panel : str
        Panel kind hint used by the TUI (e.g., "ai", "output", "agent").
        Not enforced here for flexibility.
    """


class Attachment(TypedDict):
    """One attached file (name + raw bytes)."""

    name: str
    content: bytes


# =============================================================================
# Console shim to ensure options.soft_wrap exists across Rich versions
# =============================================================================

class _SoftWrapConsole(Console):
    """Console that guarantees `options.soft_wrap` is present.

    Some Rich versions expose `soft_wrap` on Console but not on Console.options.
    Tests expect `console.options.soft_wrap` to exist; this shim preserves normal
    behavior and injects the attribute if Rich doesn't provide it.
    """

    @property
    def options(self):  # type: ignore[override]
        opts = super().options
        # If the Rich version already provides it, use as-is.
        if hasattr(opts, "soft_wrap"):
            return opts

        # Lightweight proxy that forwards attributes, adding `soft_wrap`.
        class _OptsProxy:
            __slots__ = ("_opts", "soft_wrap")

            def __init__(self, _opts, soft_wrap):
                self._opts = _opts
                self.soft_wrap = soft_wrap

            def __getattr__(self, name):
                return getattr(self._opts, name)

        # Prefer Console.soft_wrap if present; otherwise use True (we construct with soft_wrap=True).
        soft_wrap_val = getattr(self, "soft_wrap", True)
        return _OptsProxy(opts, soft_wrap_val)


# =============================================================================
# Global singletons (kept to match existing behavior)
# =============================================================================

runner: CliRunner = CliRunner()
console: Console = _SoftWrapConsole(soft_wrap=True)

# Session state
conversation_history: List[HistoryTurn] = []
attachments: List[Attachment] = []
system_prompt: str = ""

# Config (copy to avoid accidental mutation of the constant object)
config: Dict[str, Any] = dict(DEFAULT_CONFIG)


# =============================================================================
# Utilities (handy in tests; no-op unless explicitly called)
# =============================================================================

def reset_state(
    *,
    keep_console: bool = True,
    keep_runner: bool = True,
    override_config: Optional[Dict[str, Any]] = None,
) -> None:
    """Reset in-memory session state to defaults.

    This helper is primarily for tests. It clears the conversation history and
    attachments, resets the system prompt, and restores the runtime config to
    defaults (optionally overridden).

    Parameters
    ----------
    keep_console : bool, default True
        If False, recreate the global `console` instance.
    keep_runner : bool, default True
        If False, recreate the global `runner` instance.
    override_config : dict[str, Any] | None
        Optional mapping to merge on top of the default config.

    Notes
    -----
    - This does **not** write to disk or touch external resources.
    - Safe to call multiple times.
    """
    global console, runner, system_prompt, config

    if not keep_console:
        console = _SoftWrapConsole(soft_wrap=True)
    if not keep_runner:
        runner = CliRunner()

    # Preserve list identities for modules that hold references.
    conversation_history.clear()
    attachments.clear()
    system_prompt = ""

    # Start from defaults, then apply overrides if provided.
    config = dict(DEFAULT_CONFIG)
    if override_config:
        # Merge shallowly to preserve default keys unless explicitly overridden.
        config.update(override_config)


def get_state_snapshot() -> Dict[str, Any]:
    """Return a shallow snapshot of the current runtime state.

    Useful in tests for quick assertions without mutating the originals.

    Returns
    -------
    dict[str, Any]
        A dictionary containing lightweight copies of current globals. The
        `console` and `runner` singletons are returned by reference (do not
        mutate them here).
    """
    return {
        "console": console,
        "runner": runner,
        "conversation_history": list(conversation_history),
        "attachments": list(attachments),
        "system_prompt": system_prompt,
        "config": dict(config),
    }
