# saxoflow_agenticai/agents/reviewers/debug_agent.py
"""
Debug agent.

Analyzes RTL, testbench, and simulation logs to produce a structured debug
report and recommends which agent(s) should attempt an automatic fix.

Public API (kept stable)
------------------------
- class DebugAgent
    - run(rtl_code, tb_code, sim_stdout="", sim_stderr="", sim_error_message="")
      -> tuple[str, list[str]]
    - improve(...) -> tuple[str, list[str]]  # proxies to run(...)
- function
    - extract_structured_debug_report(text: str, headings: list[str] | None) -> str

Notes
-----
- We keep LangChain `PromptTemplate(template_format="jinja2")`.
- LLM is invoked with `.invoke(prompt)`, preserving existing behavior.
- Output remains a tuple of (cleaned_report, suggested_agents).

Python: 3.9+
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = ["DebugAgent", "extract_structured_debug_report"]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_DEBUG = "debug_prompt.txt"


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
    if not path.exists():  # pragma: no cover - defensive
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


# ---------------------------
# LLM-output cleaning helpers
# ---------------------------

# Compile once for performance and clarity.
_RE_FENCED_BLOCK = re.compile(r"```.*?```", flags=re.DOTALL)
_RE_FOR_EXAMPLE = re.compile(
    r"For example.*?(?=\n\S|$)", flags=re.DOTALL | re.IGNORECASE
)
_RE_ADDITIONALLY = re.compile(
    r"Additionally, consider.*?(?=\n\S|$)", flags=re.DOTALL | re.IGNORECASE
)
_RE_CONTENT_PREFIX = re.compile(r"^content=['\"]?", flags=re.IGNORECASE)
_RE_BOLD = re.compile(r"\*\*")
_RE_MULTI_NL = re.compile(r"\n+")
_RE_BULLET_PREFIX = re.compile(r"^\s*[-*]\s*", flags=re.MULTILINE)

# Keep the canonical headings in the order we want to emit them.
_DEBUG_HEADINGS: List[str] = [
    "Problems identified",
    "Explanation",
    "Suggested Fixes",
    "Suggested Agent for Correction",
]


def extract_structured_debug_report(
    text: str, headings: Optional[List[str]] = None
) -> str:
    """
    Normalize a debug report into labeled sections.

    The function removes markdown/metadata noise, flattens whitespace, and emits
    "Heading: value" lines in a canonical order separated by blank lines.

    Parameters
    ----------
    text : str
        Raw LLM debug content (arbitrary formatting).
    headings : list[str] | None
        Custom headings to extract. If None, default canonical headings apply.

    Returns
    -------
    str
        Structured debug report with canonical headings and cleaned content.
    """
    text = str(text or "")

    # Remove markdown/code/metadata and normalize whitespace.
    text = _RE_FENCED_BLOCK.sub("", text)
    text = _RE_FOR_EXAMPLE.sub("", text)
    text = _RE_ADDITIONALLY.sub("", text)
    text = _RE_CONTENT_PREFIX.sub("", text.strip())
    text = _RE_BOLD.sub("", text)

    # Truncate at "additional_kwargs" if present (matches existing behavior).
    if "additional_kwargs" in text:
        text = text.split("additional_kwargs", 1)[0]

    text = text.replace("\r", "\n")
    text = _RE_MULTI_NL.sub("\n", text)
    text = _RE_BULLET_PREFIX.sub("", text)

    # Canonical ordering for output.
    if headings is None:
        headings = list(_DEBUG_HEADINGS)

    results = {h: "None" for h in headings}

    for idx, heading in enumerate(headings):
        next_heading = headings[idx + 1] if idx + 1 < len(headings) else None
        if next_heading:
            pattern = (
                rf"{re.escape(heading)}:\s*((?:.|\n)*?)"
                rf"(?=\n\s*{re.escape(next_heading)}:|\Z)"
            )
        else:
            pattern = rf"{re.escape(heading)}:\s*((?:.|\n)*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1)
            # Flatten whitespace and remove lightweight bullet artifacts.
            value = value.replace("\n", " ").replace("\\n", " ")
            value = re.sub(r"[-*]\s*", "", value)
            value = re.sub(r"\s+", " ", value).strip(" .:;-")
            if value and value.lower() != "none":
                results[heading] = value

    # Double newline between sections for readability.
    return "\n\n".join(f"{h}: {results[h]}" for h in headings)


# -----------------------
# PromptTemplate instance
# -----------------------

debug_prompt_template = PromptTemplate(
    input_variables=[
        "rtl_code",
        "tb_code",
        "sim_stdout",
        "sim_stderr",
        "sim_error_message",
    ],
    template=_load_prompt_from_pkg(_PROMPT_DEBUG),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class DebugAgent:
    """Produce a structured debug report and suggest corrective agents."""

    agent_type = "debug"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, it is resolved from
            configuration via `ModelSelector.get_model(agent_type="debug")`.
        verbose : bool, default False
            If True, log rendered prompt and cleaned output.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="debug")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    # --- internals ---

    @staticmethod
    def _extract_agents_from_debug(debug_report: str) -> List[str]:
        """
        Parse which agent(s) the LLM recommends for correction.

        Parameters
        ----------
        debug_report : str
            Clean (or raw) debug report text.

        Returns
        -------
        list[str]
            Agent class names such as ["RTLGenAgent", "TBGenAgent"] or ["UserAction"].

        Notes
        -----
        - Keeps original behavior: if the heading isn't found, defaults to
          both RTLGenAgent and TBGenAgent.
        """
        m = re.search(
            r"Suggested Agent for Correction:\s*([^\n]+)",
            debug_report,
            flags=re.IGNORECASE,
        )
        if m:
            return [a.strip() for a in m.group(1).split(",")]
        # Fallback mirrors original: be permissive and suggest both.
        return ["RTLGenAgent", "TBGenAgent"]

    # --- public API (kept stable) ---

    def run(
        self,
        rtl_code: str,
        tb_code: str,
        sim_stdout: str = "",
        sim_stderr: str = "",
        sim_error_message: str = "",
    ) -> Tuple[str, List[str]]:
        """
        Analyze RTL, testbench, and simulation logs; return a structured report.

        Parameters
        ----------
        rtl_code : str
            RTL (Verilog/SystemVerilog) code content.
        tb_code : str
            Testbench (SystemVerilog) code content.
        sim_stdout : str, default ""
            Simulator standard output.
        sim_stderr : str, default ""
            Simulator standard error.
        sim_error_message : str, default ""
            High-level error message if present.

        Returns
        -------
        tuple[str, list[str]]
            (cleaned_debug_report, suggested_agent_names)
        """
        prompt = debug_prompt_template.format(
            rtl_code=rtl_code,
            tb_code=tb_code,
            sim_stdout=sim_stdout or "",
            sim_stderr=sim_stderr or "",
            sim_error_message=sim_error_message or "",
        )

        if self.verbose:
            self.logger.info("Debug prompt:\n%s", prompt)

        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - provider/network error
            raise RuntimeError(f"LLM invocation failed in DebugAgent: {exc}") from exc

        if not result or not str(result).strip():
            self.logger.warning("LLM returned empty debug output. Using fallback.")
            result = (
                "No explicit debugging suggestions found. "
                "Ensure your input includes code, testbench, or error logs for best results.\n"
                "Suggested Agent for Correction: UserAction"
            )

        debug_output_raw = str(result).strip()
        debug_output_clean = extract_structured_debug_report(debug_output_raw)
        agent_list = self._extract_agents_from_debug(debug_output_raw)

        self.logger.info("Debugging output generated.")
        self.logger.info("Debug Report (CLEANED):\n%s", debug_output_clean)

        return debug_output_clean, agent_list

    def improve(  # noqa: D401 - short docstring; interface parity across agents
        self,
        rtl_code: str,
        tb_code: str,
        sim_stdout: str = "",
        sim_stderr: str = "",
        sim_error_message: str = "",
        feedback: str = "",  # noqa: ARG002 - intentionally unused to preserve behavior
    ) -> Tuple[str, List[str]]:
        """Re-run the debug flow. `feedback` is accepted for parity but unused."""
        self.logger.info("Re-running debug with feedback context (ignored).")
        # TODO: If you later want to incorporate `feedback`, add a second prompt and
        # keep this path as the fallback to preserve backward compatibility.
        return self.run(rtl_code, tb_code, sim_stdout, sim_stderr, sim_error_message)
