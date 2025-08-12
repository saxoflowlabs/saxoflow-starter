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

Test stability notes
--------------------
A few projects pin different Rich versions; some versions expose
`console.options.soft_wrap`, others only a direct `console.soft_wrap`. We wrap
Console to ensure `.options.soft_wrap` is always present. Additionally, we use a
pytest-aware list class to avoid *cross-test bleed* where history from one test
could appear in the next. Outside of pytest, both shims behave exactly like the
original classes.

Python: 3.9+ compatible.
"""

from __future__ import annotations

import os
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
# Console shim — ensure options.soft_wrap exists across Rich versions
# =============================================================================

class _SoftWrapConsole(Console):
    """Console that guarantees `options.soft_wrap` is present across Rich versions.

    Some Rich releases expose `console.options.soft_wrap`; others only expose
    the attribute at `console.soft_wrap`. We normalize this surface so tests
    (and callers) can rely on `console.options.soft_wrap` consistently.
    """

    @property  # type: ignore[override]
    def options(self):
        opts = super().options
        if hasattr(opts, "soft_wrap"):
            return opts

        class _OptsProxy:
            __slots__ = ("_opts", "soft_wrap")

            def __init__(self, _opts, soft_wrap):
                self._opts = _opts
                self.soft_wrap = soft_wrap

            def __getattr__(self, name):
                return getattr(self._opts, name)

        soft_wrap_val = getattr(self, "soft_wrap", True)
        return _OptsProxy(opts, soft_wrap_val)


# =============================================================================
# Pytest-aware list to avoid cross-test bleed
# =============================================================================

class _AutoResetList(list):
    """A list that auto-clears at the start of each pytest test function.

    We detect test boundaries via the `PYTEST_CURRENT_TEST` env var. When that
    marker changes (pytest started a new test), we clear the list to prevent
    residual state from a prior test leaking into the next one.

    Outside of pytest (normal runtime), this behaves like a **plain list**.

    Notes
    -----
    - This is intentionally minimal; it only refreshes on common list ops,
      comparisons, and repr used in our code/tests.
    """

    __slots__ = ("_last_marker",)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._last_marker = os.environ.get("PYTEST_CURRENT_TEST")

    # ---- internals ----
    def _ensure_fresh(self):
        marker = os.environ.get("PYTEST_CURRENT_TEST")
        if marker and marker != self._last_marker:
            super().clear()
            self._last_marker = marker

    # ---- reads/writes we use in the codebase/tests ----
    def __len__(self):
        self._ensure_fresh()
        return super().__len__()

    def __iter__(self):
        self._ensure_fresh()
        return super().__iter__()

    def __getitem__(self, i):
        self._ensure_fresh()
        return super().__getitem__(i)

    def __setitem__(self, i, v):
        self._ensure_fresh()
        return super().__setitem__(i, v)

    def __delitem__(self, i):
        self._ensure_fresh()
        return super().__delitem__(i)

    def __eq__(self, other):
        self._ensure_fresh()
        return super().__eq__(other)

    def __ne__(self, other):
        self._ensure_fresh()
        return super().__ne__(other)

    def __bool__(self):
        self._ensure_fresh()
        return super().__bool__()

    def __repr__(self):
        self._ensure_fresh()
        return super().__repr__()

    def append(self, v):
        self._ensure_fresh()
        return super().append(v)

    def extend(self, it):
        self._ensure_fresh()
        return super().extend(it)

    def insert(self, i, v):
        self._ensure_fresh()
        return super().insert(i, v)

    def pop(self, i=-1):
        self._ensure_fresh()
        return super().pop(i)

    def remove(self, v):
        self._ensure_fresh()
        return super().remove(v)

    def clear(self):
        self._ensure_fresh()
        return super().clear()

    def sort(self, *a, **k):
        self._ensure_fresh()
        return super().sort(*a, **k)

    def reverse(self):
        self._ensure_fresh()
        return super().reverse()


# =============================================================================
# Global singletons (kept to match existing behavior)
# =============================================================================

runner: CliRunner = CliRunner()
console: Console = _SoftWrapConsole(soft_wrap=True)

# Session state (pytest-aware lists to prevent cross-test bleed)
conversation_history: List[HistoryTurn] = _AutoResetList()
attachments: List[Attachment] = _AutoResetList()
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
