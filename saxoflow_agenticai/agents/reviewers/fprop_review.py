# saxoflow_agenticai/agents/reviewers/fprop_review.py
"""
Formal property (SVA) review agent.

This module provides a `FormalPropReviewAgent` that renders a Jinja2 prompt and
calls an LLM to produce a structured critique of SystemVerilog formal properties.
The raw output is normalized into canonical headings.

Public API (kept stable)
------------------------
- class FormalPropReviewAgent
    - run(spec: str, rtl_code: str, prop_code: str) -> str
    - improve(spec: str, rtl_code: str, prop_code: str, feedback: str) -> str
- function
    - extract_structured_formal_review(text: str, headings: list[str] | None) -> str

Notes
-----
- We intentionally keep `str(result)` (instead of `.content`) to preserve the
  project’s current behavior and cleaning rules.
- Jinja2 prompt templates are used via LangChain’s `PromptTemplate`.

Python: 3.9+
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = ["FormalPropReviewAgent", "extract_structured_formal_review"]

logger = get_logger(__name__)

# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_FPROP_REVIEW = "fpropreview_prompt.txt"
# _PROMPT_DEBUG = "debug_prompt.txt"  # Unused in current agent; see commented section below.


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


# --------------------------------
# LLM-output cleaning (compiled RX)
# --------------------------------

_RE_FENCED_BLOCK = re.compile(r"```.*?```", flags=re.DOTALL)
_RE_FOR_EXAMPLE = re.compile(r"For example.*?(?=\n\S|$)", flags=re.DOTALL | re.IGNORECASE)
_RE_ADDITIONALLY = re.compile(
    r"Additionally, consider.*?(?=\n\S|$)", flags=re.DOTALL | re.IGNORECASE
)
_RE_MULTI_NL = re.compile(r"\n+")
_RE_BULLET_PREFIX = re.compile(r"^\s*[-*]\s*", flags=re.MULTILINE)


def extract_structured_formal_review(text: str, headings: Optional[List[str]] = None) -> str:
    """
    Normalize a formal property review into labeled sections.

    Heuristics
    ----------
    - Remove fenced code blocks and common LLM noise (example/aside sections).
    - Normalize newlines, strip bullet prefixes, flatten whitespace.
    - Extract canonical headings and return "Heading: value" per line.
    - Missing or empty sections are filled with "None".

    Parameters
    ----------
    text : str
        Raw LLM review content (arbitrary formatting).
    headings : list[str] | None
        Headings to extract. If None, a default canonical list is used.

    Returns
    -------
    str
        Structured review with canonical headings and cleaned content.
    """
    text = str(text or "")

    # Remove markdown/code blocks and common boilerplate.
    text = _RE_FENCED_BLOCK.sub("", text)
    text = _RE_FOR_EXAMPLE.sub("", text)
    text = _RE_ADDITIONALLY.sub("", text)

    # Truncate at "additional_kwargs" if present (matches existing behavior).
    if "additional_kwargs" in text:
        text = text.split("additional_kwargs", 1)[0]

    # Normalize newlines and remove bullet prefixes.
    text = _RE_MULTI_NL.sub("\n", text)
    text = _RE_BULLET_PREFIX.sub("", text)

    # Default headings for formal property review.
    if headings is None:
        headings = [
            "Missing Properties",
            "Trivial Properties Detected",
            "Scope & Coverage Issues",
            "Cycle-Accuracy Problems",
            "Assertion Naming Suggestions",
            "Overall Property Set Quality",
            "Additional Formal Suggestions",
        ]

    results: Dict[str, str] = {h: "None" for h in headings}

    for idx, heading in enumerate(headings):
        next_heading = headings[idx + 1] if idx + 1 < len(headings) else None
        if next_heading:
            pattern = rf"{re.escape(heading)}:\s*(.*?)(?=\n\s*{re.escape(next_heading)}:|\Z)"
        else:
            pattern = rf"{re.escape(heading)}:\s*(.*)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if not match:
            # Heading is missing -> leave "None"
            continue

        value = match.group(1)
        # Flatten whitespace and remove lightweight bullet artifacts within the captured value.
        value = value.replace("\n", " ").replace("\\n", " ")
        value = re.sub(r"[-*]\s*", "", value)
        value = re.sub(r"\s+", " ", value).strip(" .:;-")

        if value and not value.lower().startswith("none"):
            results[heading] = value
        else:
            results[heading] = "None"

    # Emit in canonical order, one per line.
    return "\n".join(f"{h}: {results[h]}" for h in headings).strip()


# -----------------------
# PromptTemplate instances
# -----------------------

# Keep Jinja2 support for consistency with other agents.
fpropreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "formal_properties"],
    template=_load_prompt_from_pkg(_PROMPT_FPROP_REVIEW),
    template_format="jinja2",
)

# --- Unused prompt kept for reference / future evolution. ---
# debug_prompt_template = PromptTemplate(
#     input_variables=["debug_input"],
#     template=_load_prompt_from_pkg(_PROMPT_DEBUG),
#     template_format="jinja2",
# )
# Rationale: this agent does not use the debug prompt today. Keeping it commented
# avoids dead-code/flake8 issues while documenting the intended future path.


# -------------
# Agent class
# -------------

class FormalPropReviewAgent:
    """Review SystemVerilog formal properties and return a structured critique."""

    agent_type = "fpropreview"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, it is resolved from
            configuration via `ModelSelector.get_model(agent_type="fpropreview")`.
        verbose : bool, default False
            If True, log rendered prompt and cleaned output.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="fpropreview")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    # --- public API (kept stable) ---

    def run(self, spec: str, rtl_code: str, prop_code: str) -> str:
        """
        Review SystemVerilog formal properties for coverage and completeness.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code that the formal properties target.
        prop_code : str
            SystemVerilog assertions (SVAs) to be reviewed.

        Returns
        -------
        str
            Structured review text with canonical headings, each on its own line.
        """
        prompt = fpropreview_prompt_template.format(
            spec=spec, rtl_code=rtl_code, formal_properties=prop_code
        )
        if self.verbose:
            self.logger.info("Formal property review prompt:\n%s", prompt)

        try:
            # Preserve existing behavior: stringify the full result (not .content).
            result = self.llm.invoke(prompt)
            review_text = str(result)
        except Exception as exc:  # pragma: no cover - provider/network error
            raise RuntimeError(f"LLM invocation failed in FormalPropReviewAgent: {exc}") from exc

        if not review_text or not review_text.strip():
            self.logger.warning(
                "LLM returned empty review. Using fallback critique report."
            )
            review_text = (
                "Missing Properties: None\n"
                "Trivial Properties Detected: None\n"
                "Scope & Coverage Issues: None\n"
                "Cycle-Accuracy Problems: None\n"
                "Assertion Naming Suggestions: None\n"
                "Overall Property Set Quality: No major issues found.\n"
                "Additional Formal Suggestions: None"
            )
            cleaned = review_text.strip()
        else:
            cleaned = extract_structured_formal_review(review_text)

        self.logger.info("Formal property review cleaned output:\n%s", cleaned)
        return cleaned

    def improve(self, spec: str, rtl_code: str, prop_code: str, feedback: str) -> str:
        """
        Re-run the review with the same inputs.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code that the formal properties target.
        prop_code : str
            SystemVerilog assertions (SVAs) to be reviewed.
        feedback : str
            Reviewer/debug feedback (unused; kept for interface compatibility).

        Returns
        -------
        str
            Structured review identical in format to `run(...)`.

        Notes
        -----
        - Currently we ignore `feedback` to preserve behavior.
        - If you later want `feedback`-aware refinement, introduce a dedicated
          `fpropreview_improve_prompt.txt` and keep this path as the fallback.
        """
        self.logger.info(
            "Re-running formal property review with feedback context (ignored)."
        )
        return self.run(spec, rtl_code, prop_code)
