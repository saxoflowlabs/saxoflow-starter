# saxoflow_agenticai/orchestrator/feedback_coordinator.py
"""
Feedback-driven improvement loop for SaxoFlow Agentic AI.

This module coordinates:
  1) An initial generation via a "generator" agent (e.g., RTLGenAgent)
  2) A review via a "feedback" agent (e.g., RTLReviewAgent / debug agent)
  3) Iterative improvements via the generator agent's `improve(...)` method

It also provides a robust "no action needed" detector for textual feedback.

Public API (kept stable)
------------------------
- class AgentFeedbackCoordinator
    - is_no_action_feedback(feedback: str) -> bool
    - iterate_improvements(agent, initial_spec, feedback_agent, max_iters=1, logger=None)
      -> Tuple[str, str]

Notes
-----
- The input/output behavior of `iterate_improvements` is preserved:
  returns (final_generated_output, last_feedback_string).
- Argument signatures for agents are wired as before (tbgen/rtlgen/fpropgen
  get their specific tuple layouts). If signatures change in the future, update
  `_build_review_args` / `_build_improve_args` in one place.

Python: 3.9+
"""

from __future__ import annotations

import io
import logging
import re
import sys
from contextlib import contextmanager
from typing import Any, List, Tuple


# -------------------------
# Regex compilation (global)
# -------------------------

# Compile once to avoid re-compilation on every call (minor perf gain in loops).
_NO_ISSUE_PATTERNS: List[re.Pattern] = [
    re.compile(
        r"\bno (major )?(issue|issues|problem|problems|concerns|errors|fixes|changes|action)(s)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bnothing to (fix|address|change|improve|add)\b", re.IGNORECASE),
    re.compile(r"\bnone found\b", re.IGNORECASE),
    re.compile(r"\ball good\b", re.IGNORECASE),
    re.compile(r"\bok\b", re.IGNORECASE),
    re.compile(r"\blooks good\b", re.IGNORECASE),
    re.compile(r"\bno feedback\b", re.IGNORECASE),
    re.compile(r"\bclean\b", re.IGNORECASE),
    re.compile(r"\bapproved\b", re.IGNORECASE),
    re.compile(r"\bpass(ed)?\b", re.IGNORECASE),
    re.compile(r"\bcorrect\b", re.IGNORECASE),
]

_LINE_OK = re.compile(
    r"(none|no issues?|ok|looks good|pass|clean|approved|correct)[ .:;,-]*$",
    re.IGNORECASE,
)
_LINE_SECTION_OK = re.compile(
    r"^[A-Za-z0-9 _-]+:\s*(none|ok|pass|clean|approved|correct)[ .:;,-]*$",
    re.IGNORECASE,
)

_SANITIZE_PUNCT = re.compile(r"[-*:_`']")
_COLLAPSE_WS = re.compile(r"\s+")


def _normalize_feedback(feedback: str) -> str:
    """
    Normalize review/debug text to improve detection robustness.

    Steps
    -----
    - lower() and strip()
    - replace certain punctuation with a space
    - collapse whitespace
    """
    text = (feedback or "").lower().strip()
    text = _SANITIZE_PUNCT.sub(" ", text)
    text = _COLLAPSE_WS.sub(" ", text)
    return text


def _all_lines_look_ok(text: str) -> bool:
    """
    Return True if all non-empty lines look like 'none/ok/approved/...'
    or 'Section: none/ok/approved/...'."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    return all(_LINE_OK.match(ln) or _LINE_SECTION_OK.match(ln) for ln in lines)


def _as_tuple(obj: Any) -> Tuple[Any, ...]:
    """Ensure value is a tuple; convenience for spec argument handling."""
    return obj if isinstance(obj, tuple) else (obj,)


def _has_agent_type(agent: Any, expected: str) -> bool:
    """Return True if agent.agent_type equals `expected` (defensively handles absence)."""
    return getattr(agent, "agent_type", None) == expected


def _build_review_args(
    agent: Any, spec_args: Tuple[Any, ...], generated: Any
) -> Tuple[Any, ...]:
    """
    Build args for feedback_agent.run(...) based on generator agent type.

    Mappings (kept as-is)
    ---------------------
    - tbgen reviewer expects: (spec, rtl_code, top_module_name, testbench_code)
    - rtlgen reviewer expects: (spec, rtl_code)
    - fpropgen reviewer expects: (spec, rtl_code, formal_properties)
    - default fallback: all original spec inputs + generated output as the last arg
    """
    if _has_agent_type(agent, "tbgen"):
        return (spec_args[0], spec_args[1], spec_args[2], generated)
    if _has_agent_type(agent, "rtlgen"):
        return (spec_args[0], generated)
    if _has_agent_type(agent, "fpropgen"):
        return (spec_args[0], spec_args[1], generated)
    return spec_args + (generated,)


def _build_improve_args(
    agent: Any, spec_args: Tuple[Any, ...], prev_output: Any, feedback: str
) -> Tuple[Any, ...]:
    """
    Build args for generator agent improve(...) based on agent type.

    Mappings (kept as-is)
    ---------------------
    - fpropgen.improve(spec, rtl_code, prev_formal_properties, feedback)
    - tbgen.improve(spec, prev_tb_code, feedback, rtl_code, top_module_name)
    - rtlgen.improve(spec, prev_rtl_code, review)
    - default fallback: all original spec inputs + previous output + feedback
    """
    if _has_agent_type(agent, "fpropgen"):
        return spec_args + (prev_output, feedback)
    if _has_agent_type(agent, "tbgen"):
        return (spec_args[0], prev_output, feedback, spec_args[1], spec_args[2])
    if _has_agent_type(agent, "rtlgen"):
        return (spec_args[0], prev_output, feedback)
    return spec_args + (prev_output, feedback)


@contextmanager
def _suppress_stdio(enabled: bool):
    """
    Temporarily suppress stdout/stderr when enabled.

    Used to keep agent/reviewer chatter off the terminal in quiet mode,
    without altering public APIs or agent implementations.
    """
    if not enabled:
        yield
        return
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        yield
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class AgentFeedbackCoordinator:
    """
    Coordinates generator/reviewer passes with an iterative improvement loop.

    Methods
    -------
    is_no_action_feedback(feedback: str) -> bool
    iterate_improvements(agent, initial_spec, feedback_agent, max_iters=1, logger=None)
    """

    @staticmethod
    def is_no_action_feedback(feedback: str) -> bool:
        """Return True if feedback means 'no action needed'."""
        text = (feedback or "").strip()
        if not text or len(text) < 12:
            return True

        norm = _normalize_feedback(text)
        for pat in _NO_ISSUE_PATTERNS:
            if pat.search(norm):
                return True

        if _all_lines_look_ok(text):
            return True

        return False

    @staticmethod
    def iterate_improvements(
        agent: Any,
        initial_spec: Any,
        feedback_agent: Any,
        max_iters: int = 1,
        logger: logging.Logger | None = None,
    ) -> Tuple[str, str]:
        """
        Run the (generate -> review -> improve) loop up to `max_iters` times.

        Returns
        -------
        Tuple[str, str]
            (final_generated_output, last_feedback_text)

        Notes
        -----
        - Quiet-by-default: stdout/stderr from agents are suppressed when the
          logger is not verbose (effective level >= WARNING). Public API is unchanged.
        """
        log = logger or logging.getLogger("saxoflow_agenticai")

        # Quiet mode if not verbose at the logger.
        quiet_stdio = log.getEffectiveLevel() >= logging.WARNING

        # Normalize to tuple for consistent handling.
        spec_args = _as_tuple(initial_spec)

        # Initial generation
        with _suppress_stdio(enabled=quiet_stdio):
            output = agent.run(*spec_args)
        prev_output = output
        last_feedback = ""

        # Improvement loop
        for i in range(max_iters):
            review_args = _build_review_args(agent, spec_args, prev_output)
            with _suppress_stdio(enabled=quiet_stdio):
                feedback = feedback_agent.run(*review_args)
            feedback = (feedback or "").strip()

            if not feedback:
                feedback = "No major issues found."
                log.warning(
                    "[AgentFeedbackCoordinator] Review/debug agent returned blank feedback. Using fallback."
                )

            last_feedback = feedback

            if AgentFeedbackCoordinator.is_no_action_feedback(feedback):
                log.info(
                    "[AgentFeedbackCoordinator] Exiting improvement loop at iteration %d "
                    "as review/debug reports no major issues.",
                    i + 1,
                )
                break

            log.info(
                "[AgentFeedbackCoordinator] Triggering improvement step at iteration %d.",
                i + 1,
            )

            improve_args = _build_improve_args(agent, spec_args, prev_output, feedback)
            try:
                with _suppress_stdio(enabled=quiet_stdio):
                    prev_output = agent.improve(*improve_args)
            except NotImplementedError as exc:
                log.warning(
                    "[AgentFeedbackCoordinator] 'improve' not implemented on %s: %s. "
                    "Stopping improvement loop.",
                    getattr(agent, "agent_type", type(agent).__name__),
                    exc,
                )
                break
            except Exception as exc:  # pragma: no cover - defensive
                log.error(
                    "[AgentFeedbackCoordinator] Error in improve(): %s. Stopping loop.",
                    exc,
                )
                break
        else:
            log.warning(
                "[AgentFeedbackCoordinator] Max iterations reached without review agent "
                "reporting 'no major issues'."
            )

        log.info(
            "[AgentFeedbackCoordinator] Improvement loop finished at iteration %d. Returning output.",
            (i + 1) if "i" in locals() else 0,  # keep exact message shape
        )

        return prev_output, last_feedback
