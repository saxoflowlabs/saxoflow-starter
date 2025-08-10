# cool_cli/ai_buddy.py
"""
AI Buddy utilities for SaxoFlow.

This module exposes:
- ACTION_KEYWORDS: Canonical mapping from user intents to internal actions.
- detect_action(): Keyword-based intent detector.
- ask_ai_buddy(): High-level chat/review orchestrator that either chats with an LLM,
  triggers review agents, or returns an action token for downstream tools.

Behavior-preserving notes:
- Return shapes match the original code:
  * {"type": "need_file", "message": ...}
  * {"type": "review_result", "action": <str>, "message": <str>}
  * {"type": "action", "action": <str>, "message": <str>}
  * {"type": "chat", "message": <str>}
- On exceptions, a structured error is returned instead of allowing crashes:
  * {"type": "error", "message": <str>}

Python 3.9+ compatible.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple, Literal, TypedDict

from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.agent_manager import AgentManager

__all__ = [
    "MAX_HISTORY_TURNS",
    "ACTION_KEYWORDS",
    "detect_action",
    "ask_ai_buddy",
]


# =============================================================================
# Constants & Configuration
# =============================================================================

MAX_HISTORY_TURNS: int = 5

# Canonical mapping from user-visible keywords to internal actions.
# NOTE: Keep additions conservative to minimize false positives in detect_action().
ACTION_KEYWORDS: Dict[str, str] = {
    # Generation
    "generate rtl": "rtlgen",
    "rtlgen": "rtlgen",
    "generate testbench": "tbgen",
    "tbgen": "tbgen",
    "formal property": "fpropgen",
    "generate formal": "fpropgen",
    "sva": "fpropgen",
    # Simulation, Synthesis, etc.
    "simulate": "sim",
    "simulation": "sim",
    "synth": "synth",
    "synthesis": "synth",
    "debug": "debug",
    "report": "report",
    "pipeline": "fullpipeline",
    # Review
    "review rtl": "rtlreview",
    "check rtl": "rtlreview",
    "review testbench": "tbreview",
    "check testbench": "tbreview",
    "review formal": "fpropreview",
    "review property": "fpropreview",
    "check formal": "fpropreview",
    # NOTE: Add new keywords cautiously to avoid false positives in detect_action().
}

# -----------------------------------------------------------------------------
# (Unused but kept for future reference)
# A scored/regex-based detector could replace simple "contains" matching if
# false positives/negatives become an issue.
# from re import compile as re_compile
# ACTION_TOKEN_RE = re_compile(r"__ACTION:(?P<name>[a-z_]+)__")
# TODO(decide-future): switch to regex-based token detection when needed.
# -----------------------------------------------------------------------------


# =============================================================================
# Typed payloads (maintainability/readability; runtime behavior unchanged)
# =============================================================================

BuddyType = Literal["need_file", "review_result", "action", "chat", "error"]


class BuddyBase(TypedDict, total=False):
    """Common typed keys for buddy responses."""
    type: BuddyType
    message: str


class NeedFile(BuddyBase):
    type: Literal["need_file"]


class ReviewResult(BuddyBase):
    type: Literal["review_result"]
    action: str


class ActionTrigger(BuddyBase):
    type: Literal["action"]
    action: str


class ChatResult(BuddyBase):
    type: Literal["chat"]


class ErrorResult(BuddyBase):
    type: Literal["error"]


BuddyResult = Dict[str, Any]  # Keep runtime shape flexible for full compatibility.


# =============================================================================
# Custom Exceptions
# =============================================================================

class AskAIBuddyError(Exception):
    """Base exception for ask_ai_buddy orchestration errors."""


class AgentExecutionError(AskAIBuddyError):
    """Raised when an underlying agent fails to execute."""


class LLMInvocationError(AskAIBuddyError):
    """Raised when the selected LLM cannot be invoked or returns an invalid result."""


# =============================================================================
# Internal helpers (module-private)
# =============================================================================

def _safe_lower(s: Optional[str]) -> str:
    """Return a lowercased string, gracefully handling None."""
    return (s or "").lower()


def _format_chat_history(
    history: Iterable[Dict[str, str]],
    limit: int = MAX_HISTORY_TURNS,
) -> str:
    """Format recent conversation turns for inclusion in the prompt.

    Args:
        history: Iterable of turn dicts with keys 'user' and optional 'assistant'.
        limit: Max number of recent turns to include.

    Returns:
        str: Alternating 'User:' and 'Assistant:' lines for the prompt.
    """
    lines: List[str] = []
    recent = list(history)[-limit:] if history else []
    for turn in recent:
        # Defensive: missing keys default to empty strings.
        user_msg = turn.get("user", "")
        asst_msg = turn.get("assistant", "")
        lines.append(f"User: {user_msg}\nAssistant: {asst_msg}")
    return "\n".join(lines)


def _build_system_suffix(action: Optional[str]) -> str:
    """Build the instruction suffix guiding the model on how to respond.

    If an actionable design step is requested, instruct the model to emit the
    explicit action token after confirming prerequisites.
    """
    # NOTE: The "{action}" token is intentionally literal in the instruction text
    # so the model can replace it with the resolved action name at inference time.
    if action:
        return (
            "Assistant: (Your answer should be factual and cite sources or link resources "
            "if possible. If the user asks for a design action (like generate RTL), first "
            "guide them through prerequisites. After the user confirms they are ready, "
            "respond ONLY with the string '__ACTION:{action}__' to trigger the tool.)"
        )
    return (
        "Assistant: (Your answer should be factual and cite sources or link resources "
        "if possible.)"
    )


def _invoke_llm(
    agent_type: str,
    provider: Optional[str],
    model_name: Optional[str],
    prompt: str,
) -> str:
    """Invoke the selected LLM and return text content.

    Args:
        agent_type: Logical agent type for model selection (e.g., 'buddy').
        provider: Optional provider override.
        model_name: Optional model name override.
        prompt: Full prompt to send.

    Returns:
        str: Model response text.

    Raises:
        LLMInvocationError: If model selection or invocation fails, or content is empty.
    """
    try:
        llm = ModelSelector.get_model(
            agent_type=agent_type,
            provider=provider,
            model_name=model_name,
        )
    except Exception as exc:  # noqa: BLE001
        raise LLMInvocationError(f"Model selection failed: {exc}") from exc

    try:
        response = llm.invoke(prompt)
    except Exception as exc:  # noqa: BLE001
        raise LLMInvocationError(f"Model invocation failed: {exc}") from exc

    # Handle common SDK patterns (attribute or plain string)
    text = getattr(response, "content", None) or str(response)
    if not isinstance(text, str) or not text.strip():
        raise LLMInvocationError("Empty or invalid LLM response content.")
    return text


def _run_review_agent(action: str, file_to_review: str) -> str:
    """Execute a review agent for the given action.

    Args:
        action: One of {'rtlreview', 'tbreview', 'fpropreview'}.
        file_to_review: File path or code text to review.

    Returns:
        str: Review output string.

    Raises:
        AgentExecutionError: If the agent cannot be fetched or run.
    """
    try:
        review_agent = AgentManager.get_agent(action)
    except Exception as exc:  # noqa: BLE001
        raise AgentExecutionError(
            f"Failed to get review agent for '{action}': {exc}"
        ) from exc

    try:
        result = review_agent.run(file_to_review)
    except Exception as exc:  # noqa: BLE001
        raise AgentExecutionError(
            f"Review agent run failed for '{action}': {exc}"
        ) from exc

    # Normalize to string if agent returns a non-string payload.
    if not isinstance(result, str):
        # TODO(decide-future): Normalize structured payloads if agents
        # start returning dicts or richer objects.
        result = str(result)
    return result


# =============================================================================
# Public API
# =============================================================================

def detect_action(message: str) -> Tuple[Optional[str], Optional[str]]:
    """Detect an actionable keyword in the user message.

    Args:
        message: Arbitrary user input.

    Returns:
        Tuple[Optional[str], Optional[str]]: (action, matched_keyword).
        If nothing detected, returns (None, None).

    Notes:
        - The first matching keyword wins (simple contains-matching).
        - Consider moving to a scored matcher if false positives become an issue.
    """
    lowered = _safe_lower(message)
    for key, action in ACTION_KEYWORDS.items():
        if key in lowered:
            return action, key
    return None, None


def ask_ai_buddy(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    agent_type: str = "buddy",
    provider: Optional[str] = None,
    model: Optional[str] = None,
    file_to_review: Optional[str] = None,
) -> BuddyResult:
    """Main entry point for AI buddy interactions.

    Behaviors (preserved):
        - If the message implies a *review* action and `file_to_review` is provided,
          it runs the associated review agent and returns a 'review_result'.
        - If the message implies a *review* action but no file is provided,
          it returns 'need_file' with instructions.
        - Otherwise, it chats with the selected LLM. If the LLM returns the
          '__ACTION:<name>__' token, it returns a typed 'action' response.

    Args:
        message: User input string.
        history: Optional recent conversation turns to provide context. Each item
            should be a dict with keys 'user' and optional 'assistant'.
        agent_type: Logical agent type for model selection.
        provider: Optional provider override.
        model: Optional model name override.
        file_to_review: Code content or path required for review actions.

    Returns:
        dict: One of:
            {"type": "need_file", "message": <str>}
            {"type": "review_result", "action": <str>, "message": <str>}
            {"type": "action", "action": <str>, "message": <str>}
            {"type": "chat", "message": <str>}
            {"type": "error", "message": <str>}  # on handled exceptions

    Notes:
        - Python 3.9+ compatible (no structural pattern matching).
        - Exceptions are caught and converted to a stable error payload so callers
          don't crash the shell/CLI.
    """
    action, matched_keyword = detect_action(message)

    # -------------------------------------------------------------------------
    # Review path (direct)
    # -------------------------------------------------------------------------
    if action in {"rtlreview", "tbreview", "fpropreview"}:
        if not file_to_review:
            return {
                "type": "need_file",
                "message": (
                    f"Please provide the code/file to review for '{matched_keyword}'. "
                    "Paste the code or specify the path (e.g., 'review rtl mydesign.v')."
                ),
            }

        try:
            review_output = _run_review_agent(action, file_to_review)
        except AgentExecutionError as exc:
            return {"type": "error", "message": str(exc)}
        return {"type": "review_result", "action": action, "message": review_output}

    # -------------------------------------------------------------------------
    # Chat / Action token path
    # -------------------------------------------------------------------------
    # Build prompt (history + user + instruction suffix).
    history_text = _format_chat_history(history or [])
    suffix = _build_system_suffix(action)
    prompt_parts: List[str] = []
    if history_text:
        prompt_parts.append(history_text)
    prompt_parts.append(f"User: {message}")
    prompt_parts.append(suffix)
    prompt = "\n".join(prompt_parts)

    try:
        text = _invoke_llm(
            agent_type=agent_type,
            provider=provider,
            model_name=model,
            prompt=prompt,
        )
    except LLMInvocationError as exc:
        return {"type": "error", "message": str(exc)}

    # Preserve original behavior: detect explicit action token via simple contains.
    if action and f"__ACTION:{action}__" in text:
        return {"type": "action", "action": action, "message": text}

    # Default: normal chat.
    return {"type": "chat", "message": text}

