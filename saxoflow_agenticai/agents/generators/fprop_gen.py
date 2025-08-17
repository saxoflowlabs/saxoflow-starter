# saxoflow_agenticai/agents/generators/fprop_gen.py
"""
Formal property (SVA) generator agent.

This module provides a `FormalPropGenAgent` that renders prompts and calls an LLM
to produce SystemVerilog Assertions (SVAs). It mirrors the patterns used in
RTLGen/TBGen for consistency and maintainability.

Public API (kept stable)
------------------------
- class FormalPropGenAgent
    - run(spec: str, rtl_code: str) -> str
    - improve(spec: str, rtl_code: str, prev_fprops: str, review: str) -> str
- Tools (LangChain)
    - fpropgen_tool (name="FormalPropGen")
    - fpropgen_improve_tool (name="FormalPropGenImprove")

Notes
-----
- We keep `PromptTemplate(template_format="jinja2")` to match current prompts.
- We keep direct `.invoke(prompt)` and return `str(result).strip()` to preserve
  exact output behavior (no extra normalization that could change content).

Python: 3.9+
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = [
    "FormalPropGenAgent",
    "fpropgen_tool",
    "fpropgen_improve_tool",
]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_FPROP = "fpropgen_prompt.txt"
_PROMPT_FPROP_IMPROVE = "fpropgen_improve_prompt.txt"


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


# -----------------------
# PromptTemplate instances
# -----------------------

# Keep LangChain PromptTemplate with jinja2 format to preserve existing behavior.
_fpropgen_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=_load_prompt_from_pkg(_PROMPT_FPROP),
    template_format="jinja2",
)

_fpropgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "prev_fprops", "review"],
    template=_load_prompt_from_pkg(_PROMPT_FPROP_IMPROVE),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class FormalPropGenAgent:
    """Generate and iteratively improve SystemVerilog assertions (SVAs)."""

    agent_type = "fpropgen"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="fpropgen")`.
        verbose : bool, default False
            If True, surface prompt and raw result via logger.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="fpropgen")
        self.verbose = bool(verbose)
        # Use the class name as the logger name for consistent color-coding.
        self.logger = get_logger(self.__class__.__name__)

    # --- public API (kept stable) ---

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Generate SystemVerilog formal properties (SVAs) for the given RTL code.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            The RTL Verilog/SystemVerilog code for which SVAs are generated.

        Returns
        -------
        str
            The SVA text returned by the LLM (stringified and stripped).
        """
        prompt = _fpropgen_prompt_template.format(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            self.logger.info("Prompt for SVA generation:\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("SVAs generated (raw):\n%s", raw)

        # Preserve exact behavior: do not alter the text beyond .strip().
        return str(raw).strip()

    def improve(self, spec: str, rtl_code: str, prev_fprops: str, review: str) -> str:
        """
        Use review feedback and previous properties to improve the formal properties.

        Parameters
        ----------
        spec : str
            Original natural-language design specification.
        rtl_code : str
            The RTL code (context for property refinement).
        prev_fprops : str
            The previous/former SVA set to refine.
        review : str
            Review feedback text to apply.

        Returns
        -------
        str
            The improved SVA text returned by the LLM (stringified and stripped).
        """
        prompt = _fpropgen_improve_prompt_template.format(
            spec=spec, rtl_code=rtl_code, prev_fprops=prev_fprops, review=review
        )
        if self.verbose:
            self.logger.info("Prompt for improved SVA:\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("Improved SVAs generated (raw):\n%s", raw)

        # Preserve exact behavior: do not alter the text beyond .strip().
        return str(raw).strip()

    # --- internals ---

    def _invoke_llm(self, prompt: str) -> str:
        """
        Invoke the configured LLM and coerce result into a plain string when possible.

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
        except Exception as exc:  # pragma: no cover - provider/network failure
            # TODO: adopt retry/backoff at call sites if needed (LCEL Runnable.retry)
            raise RuntimeError(f"LLM invocation failed in FormalPropGenAgent: {exc}") from exc

        # Typical chat models return AIMessage(content=...), others return strings.
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

def _fpropgen_tool_func(spec: str, rtl_code: str) -> str:
    """Tool wrapper: Create a fresh agent and run once."""
    agent = FormalPropGenAgent()
    return agent.run(spec, rtl_code)


def _fpropgen_improve_tool_func(spec: str, rtl_code: str, prev_fprops: str, review: str) -> str:
    """Tool wrapper: Create a fresh agent and improve once."""
    agent = FormalPropGenAgent()
    return agent.improve(spec, rtl_code, prev_fprops, review)


fpropgen_tool = Tool(
    name="FormalPropGen",
    func=_fpropgen_tool_func,
    description="Generate SystemVerilog assertions (SVA) for a design spec and RTL code.",
)

fpropgen_improve_tool = Tool(
    name="FormalPropGenImprove",
    func=_fpropgen_improve_tool_func,
    description="Improve formal properties based on prior SVAs and review feedback.",
)

