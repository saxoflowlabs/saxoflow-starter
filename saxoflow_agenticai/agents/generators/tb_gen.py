# saxoflow_agenticai/agents/generators/tb_gen.py
"""
Verilog-2001 Testbench generator agent.

This module provides a `TBGenAgent` that renders prompts and calls an LLM to
produce a Verilog-2001 testbench, plus robust post-processing to extract clean
code from markdown-ish model outputs.

Public API (kept stable)
------------------------
- class TBGenAgent
    - run(spec: str, rtl_code: str, top_module_name: str) -> str
    - improve(
          spec: str,
          prev_tb_code: str,
          review: str,
          rtl_code: str,
          top_module_name: str,
      ) -> str
- Tools (LangChain)
    - tbgen_tool (name="TBGen")
    - tbgen_improve_tool (name="TBGenImprove")

Notes
-----
- We keep `PromptTemplate(template_format="jinja2")` to match current prompts.
- We keep direct `.invoke(prompt)` and string coercion, preserving behavior.
- Prompt discovery stays package-local: `<repo>/saxoflow_agenticai/prompts/...`.
- New: we *prepend* TB guidelines/constructs (if present) to the prompt text so
  smaller/older models also adhere to house rules and tool constraints
  (Icarus/Verilator, etc.). Missing guidance files are tolerated and only warn.

Python: 3.9+
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = [
    "TBGenAgent",
    "extract_verilog_tb_code",
    "tbgen_tool",
    "tbgen_improve_tool",
]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_TB = "tbgen_prompt.txt"
_PROMPT_TB_IMPROVE = "tbgen_improve_prompt.txt"

# New, optional, prepended guidance for testbench generation.
_TB_GUIDELINES_FILE = "tb_guidelines.txt"
_TB_CONSTRUCTS_FILE = "tb_constructs.txt"


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


def _maybe_read_guidance(filename: str, label: str) -> str:
    """
    Best-effort read for optional guidance files.

    Missing files are tolerated to preserve backward compatibility; a warning
    is logged and an empty string is returned.

    Parameters
    ----------
    filename : str
        File name under the prompts directory.
    label : str
        Human-friendly label used in warnings.

    Returns
    -------
    str
        File contents or empty string if not found/readable.
    """
    path = _PROMPTS_DIR / filename
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
        logger.warning("[TBGenAgent] Optional %s file not found: %s", label, path)
    except OSError as exc:  # pragma: no cover - filesystem issues
        logger.warning("[TBGenAgent] Failed reading %s (%s): %s", label, path, exc)
    return ""


def _build_tb_prompt(base_template: str) -> str:
    """
    Inject TB guidelines and constructs policy (if present) before the
    base Jinja template to give the model strong, consistent context.

    The added blocks are delimited with explicit markers so downstream
    debugging is easy.

    Parameters
    ----------
    base_template : str
        The original tbgen prompt text (Jinja).

    Returns
    -------
    str
        Composite prompt: guidance + base template.
    """
    guidelines = _maybe_read_guidance(_TB_GUIDELINES_FILE, "TB guidelines")
    constructs = _maybe_read_guidance(_TB_CONSTRUCTS_FILE, "TB constructs (policy)")

    sections = []

    if guidelines.strip():
        sections.append(
            "[TESTBENCH GUIDELINES (OPEN-SOURCE FLOW)]\n"
            "<<BEGIN_TB_GUIDELINES>>\n"
            f"{guidelines.strip()}\n"
            "<<END_TB_GUIDELINES>>"
        )
    if constructs.strip():
        sections.append(
            "[TESTBENCH CONSTRUCTS POLICY]\n"
            "<<BEGIN_TB_CONSTRUCTS>>\n"
            f"{constructs.strip()}\n"
            "<<END_TB_CONSTRUCTS>>"
        )

    # Always append the original template last.
    sections.append(base_template)
    return "\n\n".join(sections)


# -----------------------------------
# Testbench extraction from LLM output
# -----------------------------------

# Compile once for performance and readability.
_RE_CODE_FENCE = re.compile(
    r"```(?:verilog|systemverilog|\w+)?", re.IGNORECASE
)  # ``` or ```verilog...
_RE_SINGLE_BACKTICK_START = re.compile(r"^`+", re.MULTILINE)
_RE_SINGLE_BACKTICK_END = re.compile(r"`+$", re.MULTILINE)
_RE_SMART_QUOTES = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})
_RE_CONTENT_PREFIX = re.compile(r"^content=['\"]?", re.IGNORECASE)
_RE_HERE_IS = re.compile(r"^Here[^\n]*\n", re.IGNORECASE)
_RE_MODULE_BLOCKS = re.compile(r"(module[\s\S]+?endmodule)", re.IGNORECASE)
_RE_ESCAPED_NL = re.compile(r"\\n")


def extract_verilog_tb_code(llm_output: str) -> str:
    """
    Extract only the Verilog testbench code from LLM output.

    Heuristics
    ----------
    1) Strip markdown code fences/backticks and language hints.
    2) Normalize “smart” quotes.
    3) Remove API wrapper prefixes like `content="..."` and "Here is ..." lines.
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
        Cleaned Verilog testbench code.

    Notes
    -----
    - We never strip quotes *inside* the code; we only trim at boundaries.
    """
    text = str(llm_output or "")

    # 1) Remove triple backtick fences and language hints.
    code = _RE_CODE_FENCE.sub("", text).replace("```", "")

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

# Compose the final template with prepended guidance (if available).
_tbgen_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "top_module_name"],
    template=_build_tb_prompt(_load_prompt_from_pkg(_PROMPT_TB)),
    template_format="jinja2",
)

_tbgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_tb_code", "review", "rtl_code", "top_module_name"],
    template=_build_tb_prompt(_load_prompt_from_pkg(_PROMPT_TB_IMPROVE)),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class TBGenAgent:
    """Generate and iteratively improve a Verilog-2001 testbench for a given RTL."""

    agent_type = "tbgen"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="tbgen")`.
        verbose : bool, default False
            If True, surface prompt and raw result via logger.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="tbgen")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    # --- public API (kept stable) ---

    def run(self, spec: str, rtl_code: str, top_module_name: str) -> str:
        """
        Generate a Verilog-2001 testbench for the given RTL code using the spec.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            The RTL Verilog code under test.
        top_module_name : str
            Top-level module name (used in the testbench).

        Returns
        -------
        str
        """
        prompt = _tbgen_prompt_template.format(
            spec=spec, rtl_code=rtl_code, top_module_name=top_module_name
        )
        if self.verbose:
            self.logger.info("Prompt for testbench generation:\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("Testbench generated (raw):\n%s", raw)

        tb_code = extract_verilog_tb_code(raw)

        # Legacy newline fix (kept for exact behavior): if only \\n present, unescape.
        if "\\n" in tb_code and "\n" not in tb_code:
            tb_code = tb_code.replace("\\n", "\n")

        if self.verbose:
            self.logger.info("Testbench after extraction:\n%s", tb_code)
        return tb_code

    def improve(
        self,
        spec: str,
        prev_tb_code: str,
        review: str,
        rtl_code: str,
        top_module_name: str,
    ) -> str:
        """
        Improve a previously generated testbench using review feedback.

        Parameters
        ----------
        spec : str
            Original natural-language design specification.
        prev_tb_code : str
            The current/previous testbench to refine.
        review : str
            Review feedback text.
        rtl_code : str
            RTL code (may be needed for context during improvement).
        top_module_name : str
            Top-level module name.

        Returns
        -------
        str
        """
        prompt = _tbgen_improve_prompt_template.format(
            spec=spec,
            prev_tb_code=prev_tb_code,
            review=review,
            rtl_code=rtl_code,
            top_module_name=top_module_name,
        )
        if self.verbose:
            self.logger.info("Prompt for improved testbench:\n%s", prompt)

        raw = self._invoke_llm(prompt)
        if self.verbose:
            self.logger.info("Improved testbench generated (raw):\n%s", raw)

        tb_code = extract_verilog_tb_code(raw)

        # Legacy newline fix (kept for exact behavior): if only \\n present, unescape.
        if "\\n" in tb_code and "\n" not in tb_code:
            tb_code = tb_code.replace("\\n", "\n")

        if self.verbose:
            self.logger.info("Improved testbench after extraction:\n%s", tb_code)
        return tb_code

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
        except Exception as exc:  # pragma: no cover - provider/network failure
            # TODO: adopt retry/backoff at call sites if needed (LCEL Runnable.retry)
            raise RuntimeError(f"LLM invocation failed in TBGenAgent: {exc}") from exc

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

tbgen_tool = Tool(
    name="TBGen",
    func=lambda spec, rtl_code, top_module_name: TBGenAgent().run(
        spec, rtl_code, top_module_name
    ),
    description="Generate a Verilog-2001 testbench from a spec and RTL code.",
)

tbgen_improve_tool = Tool(
    name="TBGenImprove",
    func=lambda spec, prev_tb_code, review, rtl_code, top_module_name: TBGenAgent().improve(  # noqa: E501
        spec, prev_tb_code, review, rtl_code, top_module_name
    ),
    description="Improve a testbench using review feedback, original spec, and RTL code.",
)

