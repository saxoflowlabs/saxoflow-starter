# saxoflow_agenticai/agents/generators/rtl_gen.py
"""
RTL generator agent.

This module provides an `RTLGenAgent` that renders prompts and calls an LLM to
produce Verilog, plus robust post-processing to extract clean RTL from
markdown-ish model outputs.

Public API (kept stable)
------------------------
- class RTLGenAgent
    - run(spec: str) -> str
    - improve(spec: str, prev_rtl_code: str, review: str) -> str
- Tools (LangChain)
    - rtlgen_tool (name="RTLGen")
    - rtlgen_improve_tool (name="RTLGenImprove")

Notes
-----
- We keep `PromptTemplate(template_format="jinja2")` to match current prompts.
- We keep direct `.invoke(prompt)` and convert to string, preserving behavior.
- Prompt discovery stays package-local (`<repo>/saxoflow_agenticai/prompts/...`).
- In addition to the base prompts, we *optionally* prepend:
    - prompts/verilog_guidelines.txt
    - prompts/verilog_constructs.txt
  If either file is missing, we log a warning and proceed without it.

Python: 3.9+
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = [
    "RTLGenAgent",
    "extract_verilog_code",
    "rtlgen_tool",
    "rtlgen_improve_tool",
]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"

# Base prompt files (existing)
_PROMPT_RTL = "rtlgen_prompt.txt"
_PROMPT_RTL_IMPROVE = "rtlgen_improve_prompt.txt"

# New additive guideline files (optional but recommended)
# NOTE: use ".txt" extension to be explicit and easy to manage.
_PROMPT_GUIDELINES = "verilog_guidelines.txt"
_PROMPT_CONSTRUCTS = "verilog_constructs.txt"


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


def _load_optional_prompt(filename: str) -> str:
    """
    Load an optional prompt file. If missing, return empty string and warn.

    Parameters
    ----------
    filename : str
        File name relative to the prompts directory.

    Returns
    -------
    str
        File contents or empty string if not present.
    """
    path = _PROMPTS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "[RTLGenAgent] Optional prompt not found: %s (continuing without it)",
            path,
        )
        return ""
    except OSError as exc:
        logger.warning(
            "[RTLGenAgent] Failed reading optional prompt %s: %s (continuing without it)",
            path,
            exc,
        )
        return ""


# Preload guideline/constructs text once (empty if missing).
# These are concatenated *before* the base prompt body to give the LLM more context.
_GUIDELINES_TXT = _load_optional_prompt(_PROMPT_GUIDELINES)
_CONSTRUCTS_TXT = _load_optional_prompt(_PROMPT_CONSTRUCTS)


def _compose_with_guidelines(body: str) -> str:
    """
    Compose the final prompt string by prepending guidelines/constructs
    (when available) before the original base prompt body.

    Parameters
    ----------
    body : str
        The rendered base prompt (from rtlgen_prompt.txt or rtlgen_improve_prompt.txt).

    Returns
    -------
    str
        Concatenated prompt string.
    """
    sections = []
    if _GUIDELINES_TXT.strip():
        sections.append(_GUIDELINES_TXT.strip())
    if _CONSTRUCTS_TXT.strip():
        sections.append(_CONSTRUCTS_TXT.strip())
    sections.append(body.strip())
    return "\n\n" + ("\n\n".join(sections)).strip() + "\n"


# -----------------------------------
# Verilog extraction from LLM outputs
# -----------------------------------

# Compile once for performance and readability.
_RE_CODE_FENCE = re.compile(r"```(?:\w+)?", re.IGNORECASE)  # ``` or ```verilog
_RE_SINGLE_BACKTICK_START = re.compile(r"^`+", re.MULTILINE)
_RE_SINGLE_BACKTICK_END = re.compile(r"`+$", re.MULTILINE)
_RE_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_RE_CONTENT_PREFIX = re.compile(r"^content=['\"]?", re.IGNORECASE)
_RE_HERE_IS = re.compile(r"^Here[^\n]*\n", re.IGNORECASE)
_RE_MODULE_BLOCKS = re.compile(r"(module[\s\S]+?endmodule)", re.IGNORECASE)
_RE_ESCAPED_NL = re.compile(r"\\n")


def extract_verilog_code(llm_output: str) -> str:
    """
    Extract Verilog code from LLM output as robustly as possible.

    Heuristics
    ----------
    1) Strip markdown code fences/backticks and language hints.
    2) Normalize “smart” quotes.
    3) Remove API wrapper prefixes like `content="..."`
    4) Prefer text between 'module' and matching 'endmodule' (supports multi-modules).
    5) Fallback to first line starting with 'module' or the full text.
    6) Convert escaped newlines (``\\n``) to real newlines.

    Parameters
    ----------
    llm_output : str
        Raw output from the LLM.

    Returns
    -------
    str
        Cleaned Verilog code.
    """
    text = str(llm_output or "")

    # 1) Remove triple backtick fences and language hints.
    code = _RE_CODE_FENCE.sub("", text)

    # Also remove any remaining plain fences.
    code = code.replace("```", "")

    # 2) Remove stray single backticks at line boundaries.
    code = _RE_SINGLE_BACKTICK_START.sub("", code)
    code = _RE_SINGLE_BACKTICK_END.sub("", code)

    # 3) Normalize smart quotes.
    code = code.translate(_RE_SMART_QUOTES)

    # 4) Remove wrapper prefixes and “Here is …” style lines.
    code = _RE_CONTENT_PREFIX.sub("", code.strip())
    code = _RE_HERE_IS.sub("", code)

    # 5) Extract modules if present.
    modules = _RE_MODULE_BLOCKS.findall(code)
    if modules:
        code = "\n\n".join(m.strip() for m in modules)
    else:
        # Fallback: start from the first line beginning with 'module'.
        lines = code.strip().splitlines()
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith("module"):
                cleaned = "\n".join(lines[idx:]).strip().rstrip("`'\"")
                code = cleaned
                break
        else:
            # Final fallback: return everything stripped of leading/trailing ticks/quotes.
            code = code.strip().strip("`'\"")

    # 6) Convert escaped newlines to real ones.
    code = _RE_ESCAPED_NL.sub("\n", code)
    return code


# -----------------------
# PromptTemplate instances
# -----------------------

# We keep LangChain PromptTemplate with jinja2 format to preserve existing behavior.
_rtlgen_prompt_template = PromptTemplate(
    input_variables=["spec"],
    template=_load_prompt_from_pkg(_PROMPT_RTL),
    template_format="jinja2",
)

_rtlgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_rtl_code", "review"],
    template=_load_prompt_from_pkg(_PROMPT_RTL_IMPROVE),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class RTLGenAgent:
    """Generate and iteratively improve Verilog RTL from a textual spec."""

    agent_type = "rtlgen"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="rtlgen")`.
        verbose : bool, default False
            If True, surface prompt and raw result via logger.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="rtlgen")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    # --- public API (kept stable) ---

    def run(self, spec: str) -> str:
        """
        Generate RTL from the given specification.

        Parameters
        ----------
        spec : str
            Natural-language design specification.

        Returns
        -------
        str
            Extracted Verilog RTL.
        """
        base_prompt = _rtlgen_prompt_template.format(spec=spec)
        prompt = _compose_with_guidelines(base_prompt)

        if self.verbose:
            self.logger.info("Prompt for RTL generation (with guidelines):\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("RTL code generated (raw):\n%s", raw)

        verilog_code = extract_verilog_code(raw)

        # Historical guard: if only escaped newlines present, fix them.
        if "\\n" in verilog_code and "\n" not in verilog_code:
            verilog_code = verilog_code.replace("\\n", "\n")

        if self.verbose:
            self.logger.info("RTL code after extraction:\n%s", verilog_code)
        return verilog_code

    def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
        """
        Improve previously generated RTL using review feedback.

        Parameters
        ----------
        spec : str
            Original natural-language design specification.
        prev_rtl_code : str
            The current/previous RTL version to refine.
        review : str
            Review feedback text.

        Returns
        -------
        str
            Improved Verilog RTL.
        """
        base_prompt = _rtlgen_improve_prompt_template.format(
            spec=spec, prev_rtl_code=prev_rtl_code, review=review
        )
        prompt = _compose_with_guidelines(base_prompt)

        if self.verbose:
            self.logger.info("Prompt for RTL improvement (with guidelines):\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("Improved RTL code generated (raw):\n%s", raw)

        verilog_code = extract_verilog_code(raw)
        if self.verbose:
            self.logger.info("Improved RTL code after extraction:\n%s", verilog_code)
        return verilog_code

    # --- internals ---

    def _invoke_llm(self, prompt: str) -> str:
        """
        Invoke the configured LLM and coerce result into a plain string.

        Returns
        -------
        str
            Best-effort text extraction from typical LangChain return types.
        """
        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - provider/network failure
            # TODO: adopt retry/backoff at call sites if needed (LCEL Runnable.retry)
            raise RuntimeError(f"LLM invocation failed in RTLGenAgent: {exc}") from exc

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

def _rtlgen_tool_func(spec: str) -> str:
    """Tool wrapper: Create a fresh agent and run once."""
    agent = RTLGenAgent()
    return agent.run(spec)


def _rtlgen_improve_tool_func(spec: str, prev_rtl_code: str, review: str) -> str:
    """Tool wrapper: Create a fresh agent and improve once."""
    agent = RTLGenAgent()
    return agent.improve(spec, prev_rtl_code, review)


rtlgen_tool = Tool(
    name="RTLGen",
    func=_rtlgen_tool_func,
    description="Generate RTL code from a specification.",
)

rtlgen_improve_tool = Tool(
    name="RTLGenImprove",
    func=_rtlgen_improve_tool_func,
    description="Improve RTL code based on review feedback.",
)


# -----------------------------------------------------------------------------
# Optional/unused enhancements (kept as comments for future evolution)
# -----------------------------------------------------------------------------

# from langchain_core.runnables import Runnable  # noqa: E402
# from langchain_core.output_parsers import StrOutputParser  # noqa: E402
#
# def _build_chain(llm: BaseLanguageModel) -> Runnable:
#     """
#     Example LCEL chain:
#     PromptTemplate -> LLM -> StrOutputParser -> extract_verilog_code
#     Not used today; kept as a reference if you want retries/streaming later.
#     """
#     prompt = _rtlgen_prompt_template
#     return prompt | llm | StrOutputParser()
#
# class RTLGenAgentLCEL(RTLGenAgent):
#     """
#     Variant that uses an LCEL Runnable for generation and improvement flows.
#     Not used in production yet, kept for experimentation.
#     """
#     def run(self, spec: str) -> str:
#         chain = _rtlgen_prompt_template | self.llm  # | StrOutputParser()
#         raw = chain.invoke({"spec": spec})
#         return extract_verilog_code(str(raw))
#
#     def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
#         chain = _rtlgen_improve_prompt_template | self.llm  # | StrOutputParser()
#         raw = chain.invoke(
#             {"spec": spec, "prev_rtl_code": prev_rtl_code, "review": review}
#         )
#         return extract_verilog_code(str(raw))
#
# # Streaming example (kept commented):
# # for chunk in self.llm.stream(prompt): ...
#
# # BaseAgent example (kept commented to avoid behavior changes):
# # from saxoflow_agenticai.core.base_agent import BaseAgent
# #
# # class RTLGenAgentBA(BaseAgent):
# #     def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False):
# #         super().__init__(template_name=_PROMPT_RTL, llm=llm, verbose=verbose)
# #         self.agent_type = "rtlgen"
# #
# #     def run(self, spec: str) -> str:
# #         prompt = self.render_prompt({"spec": spec}, template_name=_PROMPT_RTL)
# #         raw = self.query_model(prompt)
# #         return extract_verilog_code(raw)
# #
# #     def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
# #         prompt = self.render_prompt(
# #             {"spec": spec, "prev_rtl_code": prev_rtl_code, "review": review},
# #             template_name=_PROMPT_RTL_IMPROVE,
# #         )
# #         raw = self.query_model(prompt)
# #         return extract_verilog_code(raw)
