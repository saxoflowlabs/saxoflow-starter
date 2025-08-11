# cool_cli/agentic.py
"""
Agentic command execution and AI buddy orchestration.

Responsibilities
----------------
- Quick agentic actions via the `saxoflow_agenticai` Click CLI runner
  (subset: rtlgen/tbgen/fpropgen/report).
- Orchestrate the AI buddy flow (review path, action-token path, chat).

Behavior (preserved)
--------------------
- `run_quick_action()` uses the shared Click runner to invoke the agentic CLI
  for a small, whitelisted set of commands and returns the raw textual output.
- `ai_buddy_interactive()`:
  1) If the buddy requests a file to review, we prompt the user to paste code
     or a path, read it, and retry the review.
  2) If the buddy produces a review result, we return it as a white `Text`.
  3) If the buddy emits an action token, we ask for confirmation; on "yes"
     we invoke the agentic CLI and return its output, otherwise we return
     a yellow "cancelled" `Text`.
  4) Otherwise we return the model's chat message as a white `Text`.

Design notes
------------
- All risky operations (I/O, CLI invocation) are guarded. Any exception is
  converted into a user-friendly `Text` so the TUI does not crash.
- Public signatures and return types are unchanged to avoid breaking callers.
- Python 3.9+ compatible.

Unused / deferred
-----------------
- Support for additional agentic commands is intentionally commented out to
  avoid changing behavior now; see `QUICK_ACTIONS_ALLOWLIST`.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union, TypedDict, Literal

from builtins import open as _builtins_open  # expose rebindable open for tests

from rich.markdown import Markdown
from rich.text import Text

from saxoflow_agenticai.cli import cli as agent_cli

from .ai_buddy import ask_ai_buddy
from .state import console, runner

__all__ = ["run_quick_action", "ai_buddy_interactive"]

# Make `open` a module attribute so tests can monkeypatch it.
open = _builtins_open  # noqa: A001


# ---------------------------------------------------------------------------
# Typed protocol for AI buddy responses (for maintainability/readability)
# ---------------------------------------------------------------------------

BuddyType = Literal["need_file", "review_result", "action", "chat"]


class _BaseBuddyResult(TypedDict, total=False):
    """Common keys that may appear in AI buddy results."""

    type: BuddyType
    message: str


class _NeedFileResult(_BaseBuddyResult):
    type: Literal["need_file"]


class _ReviewResult(_BaseBuddyResult):
    type: Literal["review_result"]


class _ActionResult(_BaseBuddyResult):
    type: Literal["action"]
    action: str


class _ChatResult(_BaseBuddyResult):
    type: Literal["chat"]


BuddyResult = Union[_NeedFileResult, _ReviewResult, _ActionResult, _ChatResult]


# ---------------------------------------------------------------------------
# Constants / Configuration
# ---------------------------------------------------------------------------

# Keep the allowlist tight to preserve current UX. Extend carefully.
QUICK_ACTIONS_ALLOWLIST = {"rtlgen", "tbgen", "fpropgen", "report"}

# NOTE (kept for future reference; not active to avoid behavior drift):
# QUICK_ACTIONS_ALLOWLIST |= {"debug", "fullpipeline"}  # TODO: evaluate later.


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_quick_action(instruction: str) -> Optional[str]:
    """Run a subset of agentic instructions via the shared Click runner.

    Parameters
    ----------
    instruction : str
        One of {"rtlgen", "tbgen", "fpropgen", "report"} (case-sensitive).

    Returns
    -------
    Optional[str]
        The raw CLI output (stdout/stderr combined by Click) or None if
        the instruction is not in the quick-action allowlist.

    Notes
    -----
    - Behavior matches the original implementation: we do not raise on
      CLI failures here; callers can display the plain textual output.
    - Runner exceptions are handled internally and converted to strings.
    """
    cmd = (instruction or "").strip()
    if cmd in QUICK_ACTIONS_ALLOWLIST:
        return _invoke_agent_cli_safely([cmd])
    return None


def ai_buddy_interactive(
    user_input: str,
    history: List[Dict[str, Any]],
    file_to_review: Optional[str] = None,
) -> Union[Text, Markdown]:
    """Handle NL input with the AI buddy: review, action-token, or chat.

    Parameters
    ----------
    user_input : str
        The end-user message to send to the AI buddy.
    history : list[dict[str, Any]]
        Recent conversation turns (as used by `ask_ai_buddy`).
    file_to_review : str, optional
        Optional code/path for review actions (if already provided by caller).

    Returns
    -------
    Text | Markdown
        Rich renderable with the final message to display.

    Flow (preserved)
    ----------------
    - Need file → prompt user → read code/path → retry review.
    - Review result → return as white `Text`.
    - Action token → ask for confirmation → invoke CLI on "yes" → return output.
    - Default chat → return as white `Text`.
    """
    # Defensive: rely on the existing contract but guard for partial dicts.
    result: BuddyResult = ask_ai_buddy(  # type: ignore[assignment]
        user_input, history, file_to_review=file_to_review
    )

    # 1) Needs file for review
    if result.get("type") == "need_file":
        console.print(Text(result.get("message", ""), style="yellow"))
        # NOTE: Keep interactive prompt behavior unchanged.
        file_or_code = input("Paste code or provide file path: ").strip()

        try:
            code = _read_code_from_disk_or_text(file_or_code)
        except OSError as exc:
            # Preserve TUI; return an error as Text rather than raising.
            return Text(f"Failed to read file: {exc}", style="red")

        # Retry review with the collected code contents
        retried: BuddyResult = ask_ai_buddy(  # type: ignore[assignment]
            user_input, history, file_to_review=code
        )
        if retried.get("type") == "review_result":
            return Text(retried.get("message", ""), style="white")
        # Fixed message per test contract: unexpected type on retry.
        return Text("Unexpected response.", style="red")

    # 2) Review result
    if result.get("type") == "review_result":
        return Text(result.get("message", ""), style="white")

    # 3) Action trigger (explicit token)
    if result.get("type") == "action":
        action_name = result.get("action", "").strip()
        if not action_name:
            # TODO: clarify if empty action tokens can be produced by the model.
            return Text("Received an empty action token.", style="red")

        console.print(Text(result.get("message", ""), style="cyan"))
        # Keep the exact confirmation prompt/flow.
        confirm = input(f"Ready to run '{action_name}'? (yes/no): ").strip().lower()
        if confirm in {"yes", "y"}:
            output = _invoke_agent_cli_safely([action_name]) or "[⚠] No output."
            return Text(output, style="white")
        return Text("Action cancelled.", style="yellow")

    # 4) Standard chat (default)
    return Text(result.get("message", ""), style="white")


# ---------------------------------------------------------------------------
# Internal helpers (module-private)
# ---------------------------------------------------------------------------

def _read_code_from_disk_or_text(maybe_path: str) -> str:
    """Return code contents either from a file path or from raw text.

    Parameters
    ----------
    maybe_path : str
        A string that may be a file path or literal code.

    Returns
    -------
    str
        The code payload to feed into the review step.

    Raises
    ------
    OSError
        If the path exists but cannot be read.

    Notes
    -----
    - Treat nonexistent paths as inline code (original behavior).
    - Only regular files are read; directories/globs are ignored by design.
      # TODO(decide-future): consider supporting multiple files or patterns.
    """
    if os.path.isfile(maybe_path):
        with open(maybe_path, "r", encoding="utf-8") as fh:
            return fh.read()
    return maybe_path


def _invoke_agent_cli_safely(args: List[str]) -> str:
    """Invoke the agentic Click CLI via the shared runner with guardrails.

    Parameters
    ----------
    args : list[str]
        Arguments to pass to the Click CLI entrypoint.

    Returns
    -------
    str
        Combined output from the Click invocation. Returns an empty string
        if invocation produced no output (behavior preserved).

    Notes
    -----
    - This wrapper ensures exceptions from Click do not crash the TUI.
    - Any exception is converted to a printable string for display.
    """
    try:
        result_obj = runner.invoke(agent_cli, args)
        return result_obj.output or ""
    except Exception as exc:  # Broad guard to keep UI resilient.
        # TODO(telemetry): consider logging exc for diagnostics.
        return f"[agentic error] {exc}"
