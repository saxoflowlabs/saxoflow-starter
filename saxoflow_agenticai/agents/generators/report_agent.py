# saxoflow_agenticai/agents/generators/report_agent.py
"""
Pipeline report generator agent.

This module provides a `ReportAgent` that renders a Jinja2 prompt and calls an
LLM to produce a human-readable summary of all pipeline phases. It mirrors the
patterns used in RTL/TB/Formal agents for consistency and maintainability.

Public API (kept stable)
------------------------
- class ReportAgent
    - run(phase_outputs: dict) -> str
- Tools (LangChain)
    - report_tool (name="PipelineReport")

Notes
-----
- We keep `PromptTemplate(template_format="jinja2")` to match current prompts.
- We keep direct `.invoke(prompt)` and return a cleaned string summary,
  preserving current behavior.

Python: 3.9+
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional

from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = ["ReportAgent", "report_tool"]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_REPORT = "report_prompt.txt"


def _load_prompt_from_pkg(filename: str) -> str:
    """
    Load a prompt text file shipped with the package.

    Parameters
    ----------
    filename : str
        Name of the file under `<repo>/saxoflow_agenticai/prompts/`.

    Returns
    -------
    str
        File contents as UTF-8 text.

    Raises
    ------
    FileNotFoundError
        If the prompt file cannot be found.
    OSError
        If reading the file fails.
    """
    path = _PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------
# LLM-output cleaning helpers
# ---------------------------

# Compiled regexes for performance and clarity.
_RE_FENCED_BLOCK = re.compile(r"```.*?```", flags=re.DOTALL)
_RE_CODE_FENCE_OPEN = re.compile(r"```(\w+)?")
_RE_MULTI_BLANKS = re.compile(r"\n\s*\n")
# NOTE: Keep this behavior identical to the original:
# remove common metadata tokens from the same line forward.
_RE_META_LINE = re.compile(
    r"(AIMessage|content=|additional_kwargs=|response_metadata=|usage_metadata=).*"
)


def _extract_report_content(result: object) -> str:
    """
    Cleanly extract the report content from the LLM output.

    This matches original behavior:
    - Prefer `.content` (AIMessage-like)
    - Fallback to dict["content"], else `str(result)`
    - Remove triple-fenced code blocks and code-fence openers
    - Trim, condense blank lines
    - Drop common metadata fragments appearing inline

    Parameters
    ----------
    result : object
        Raw LLM result object.

    Returns
    -------
    str
        Cleaned report text.
    """
    # 1) AIMessage or AIMessage-like (LangChain) with .content attribute.
    if hasattr(result, "content"):
        text = getattr(result, "content")
    # 2) dict-style result with 'content' key.
    elif isinstance(result, dict) and "content" in result:
        text = result["content"]
    else:
        text = str(result)

    # Remove fenced code blocks and any lingering code-fence openers.
    text = _RE_FENCED_BLOCK.sub("", text)
    text = _RE_CODE_FENCE_OPEN.sub("", text)

    # Normalize whitespace and condense multiple blank lines.
    text = text.strip()
    text = _RE_MULTI_BLANKS.sub("\n\n", text)

    # Remove inline metadata fragments (kept identical to previous behavior).
    text = _RE_META_LINE.sub("", text)
    return text.strip()


# -----------------------
# PromptTemplate instance
# -----------------------

# Keep LangChain PromptTemplate with jinja2 support to preserve behavior.
_report_prompt_template = PromptTemplate(
    input_variables=[
        "specification",
        "rtl_code",
        "rtl_review_report",
        "testbench_code",
        "testbench_review_report",
        "formal_properties",
        "formal_property_review_report",
        "simulation_status",
        "simulation_stdout",
        "simulation_stderr",
        "simulation_error_message",
        "debug_report",
    ],
    template=_load_prompt_from_pkg(_PROMPT_REPORT),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class ReportAgent:
    """Summarize outputs of all pipeline phases into a cohesive report."""

    agent_type = "report"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="report")`.
        verbose : bool, default False
            If True, surface prompt and raw result via logger.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="report")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, phase_outputs: Dict[str, str]) -> str:
        """
        Summarize the outputs of all agents/phases for reporting.

        Parameters
        ----------
        phase_outputs : Dict[str, str]
            A mapping containing all expected artifacts. Missing keys are
            replaced by empty strings to preserve current behavior.

        Returns
        -------
        str
            Clean, human-readable pipeline report text.
        """
        # Ensure all required keys exist. Missing keys default to empty strings.
        prompt_vars = {k: phase_outputs.get(k, "") for k in _report_prompt_template.input_variables}

        prompt = _report_prompt_template.format(**prompt_vars)
        if self.verbose:
            self.logger.info("Prompt for summary report:\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            # Use repr for visibility of escape sequences if present.
            self.logger.info("Raw pipeline report output:\n%s", repr(raw))

        clean_report = _extract_report_content(raw)
        if not clean_report:
            self.logger.warning("LLM returned empty report. Using fallback summary.")
            clean_report = "No report generated. Please check pipeline phase outputs."

        self.logger.info("Cleaned pipeline summary report:\n%s", clean_report)
        return clean_report

    # --- internals ---

    def _invoke_llm(self, prompt: str) -> str:
        """
        Invoke the configured LLM and coerce result into a plain string.

        Returns
        -------
        str
            Best-effort text extraction from typical LangChain return types.

        Raises
        ------
        RuntimeError
            If the underlying LLM invocation fails (network/provider error).
        """
        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - network/provider failure
            # TODO: consider retries/backoff upstream via LCEL Runnable.retry
            raise RuntimeError(f"LLM invocation failed in ReportAgent: {exc}") from exc

        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text
        return str(result)


# ---------------------------------------
# LangChain Tool registration (public API)
# ---------------------------------------

def _report_tool_func(phase_outputs: Dict[str, str]) -> str:
    """Tool wrapper: create a fresh agent and run once."""
    agent = ReportAgent()
    return agent.run(phase_outputs)


report_tool = Tool(
    name="PipelineReport",
    func=_report_tool_func,
    description="Summarize outputs of all phases for a pipeline report.",
)

