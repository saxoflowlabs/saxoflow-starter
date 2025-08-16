# saxoflow_agenticai/agents/reviewers/rtl_review.py
"""
RTL review agent.

This module provides an `RTLReviewAgent` that renders a Jinja2 prompt and calls
an LLM to produce a structured critique of Verilog RTL. It then post-processes
the raw output into a normalized, sectioned report.

Enhancements in this version
----------------------------
- Prepend tool-aware Verilog guidelines and constructs policy to the prompt,
  pulled from `prompts/verilog_guidelines.txt` and `prompts/verilog_constructs.txt`.
  If those are missing, we fall back to `guidelines_core.txt` and
  `constructs_quick.txt`. This mirrors the RTLGenAgent behavior and keeps the
  review aligned with generation constraints.
- All currently used features and output shape remain unchanged.

Public API (kept stable)
------------------------
- class RTLReviewAgent
    - run(spec: str, rtl_code: str) -> str
    - improve(spec: str, rtl_code: str, feedback: str) -> str  # proxy to run(...)
- Functions
    - extract_structured_rtl_review(text: str) -> str

Python: 3.9+
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel

from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = [
    "RTLReviewAgent",
    "extract_structured_rtl_review",
]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_RTL_REVIEW = "rtlreview_prompt.txt"

# Preferred filenames with graceful fallbacks to preserve compatibility.
_GUIDELINES_CANDIDATES = ("verilog_guidelines.txt", "guidelines_core.txt")
_CONSTRUCTS_CANDIDATES = ("verilog_constructs.txt", "constructs_quick.txt")


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


def _load_first_existing(candidates: tuple) -> Optional[str]:
    """
    Return the contents of the first existing file from `candidates`
    located under the prompts directory, else None.

    Parameters
    ----------
    candidates : tuple
        Candidate filenames to try in order.

    Returns
    -------
    Optional[str]
        File contents or None if none exist.
    """
    for fname in candidates:
        p = _PROMPTS_DIR / fname
        if p.exists():
            return p.read_text(encoding="utf-8")
    return None


def _load_guidelines_bundle() -> str:
    """
    Compose a bundle string that prepends guidelines + constructs to the prompt.

    Returns
    -------
    str
        A guidelines block followed by a constructs block. Empty sections are
        omitted if files are missing. If neither file exists, returns an empty
        string to preserve backward compatibility.
    """
    guidelines = _load_first_existing(_GUIDELINES_CANDIDATES)
    constructs = _load_first_existing(_CONSTRUCTS_CANDIDATES)

    blocks: List[str] = []
    if guidelines:
        blocks.append(
            "[VERILOG GUIDELINES — PREPENDED]\n"
            + guidelines.strip()
        )
    if constructs:
        blocks.append(
            "[CONSTRUCTS POLICY — PREPENDED]\n"
            + constructs.strip()
        )

    # Join with a single blank line between sections, plus a trailing newline.
    return ("\n\n".join(blocks) + ("\n\n" if blocks else ""))


def _compose_review_prompt(spec: str, rtl_code: str) -> str:
    """
    Build the final prompt string by prepending the guidelines bundle and then
    appending the rendered review template.

    Parameters
    ----------
    spec : str
        Natural-language design specification.
    rtl_code : str
        RTL code to be reviewed.

    Returns
    -------
    str
        Fully composed prompt ready for model invocation.
    """
    guidelines_block = _load_guidelines_bundle()
    rendered = _rtlreview_prompt_template.format(spec=spec, rtl_code=rtl_code)
    return f"{guidelines_block}{rendered}"


# ---------------------------
# LLM-output cleaning helpers
# ---------------------------

# Compile once for performance and clarity.
_RE_FENCED_BLOCK = re.compile(r"```.*?```", flags=re.DOTALL)
_RE_META = re.compile(
    r"AIMessage\(content=|additional_kwargs=.*|\bresponse_metadata=.*|usage_metadata=.*|id='[^']+'"
)
_RE_HERE_IS = re.compile(
    r"Here is the review:|Here is the output feedback for the provided RTL:|Here is the output feedback:",
    flags=re.IGNORECASE,
)
_RE_BOLD = re.compile(r"\*\*")
_RE_NEWLINES = re.compile(r"\r\n?")

# Canonical headings for RTL review (order preserved in output).
_RTL_HEADINGS: List[str] = [
    "Syntax Issues",
    "Logic Issues",
    "Reset Issues",
    "Port Declaration Issues",
    "Optimization Suggestions",
    "Naming Improvements",
    "Synthesis Concerns",
    "Overall Comments",
]


def _extract_review_content(result: object) -> str:
    """
    Extract the textual review from various LLM return shapes.

    Parameters
    ----------
    result : object
        Raw LLM result (could be AIMessage-like, dict, or string).

    Returns
    -------
    str
        Review text as a string.
    """
    # 1) AIMessage-like object with .content
    if hasattr(result, "content"):
        return getattr(result, "content")

    # 2) dict-style payload with 'content'
    if isinstance(result, dict) and "content" in result:
        return str(result["content"])

    # 3) Fallback to stringification
    return str(result)


def extract_structured_rtl_review(text: str) -> str:
    """
    Normalize an LLM RTL review into labeled sections.

    Heuristics
    ----------
    - Remove fenced code blocks, obvious metadata, and boilerplate intros.
    - Normalize newlines and strip markdown bold markers.
    - Parse canonical headings and collect their associated content.
    - Fill missing headings with 'None'.
    - Output as "Heading: value", separated by blank lines.

    Parameters
    ----------
    text : str
        Raw LLM review content (arbitrary formatting).

    Returns
    -------
    str
        Structured review with canonical headings and cleaned content.
    """
    text = str(text or "")

    # Remove blocks and artifacts.
    text = _RE_FENCED_BLOCK.sub("", text)
    text = _RE_META.sub("", text)
    text = _RE_HERE_IS.sub("", text)
    text = _RE_NEWLINES.sub("\n", text)  # normalize CRLF/CR → \n
    text = _RE_BOLD.sub("", text)  # remove **bold**

    # Build a heading-capture pattern.
    pattern = r"(?P<heading>" + "|".join([re.escape(h) for h in _RTL_HEADINGS]) + r")\s*:\s*\n?"
    splits = [(m.group("heading"), m.start()) for m in re.finditer(pattern, text, re.IGNORECASE)]
    sections: Dict[str, str] = {}

    # Append sentinel for end-of-string iteration.
    splits.append(("__END__", len(text)))

    for i in range(len(splits) - 1):
        heading, start = splits[i]
        end = splits[i + 1][1]

        # Move past the current heading match within the local slice to find content start.
        local_match = re.search(pattern, text[start:], re.IGNORECASE)
        if local_match:
            content_start = start + local_match.end()
        else:  # pragma: no cover - defensive
            content_start = start

        content = text[content_start:end].strip()

        # Clean bullet clutter and flatten whitespace.
        content = content.replace("\\n", " ").replace("\n", " ")
        content = re.sub(r"[\s\-*]+\s*", " ", content)
        content = re.sub(r"\s+", " ", content).strip(" .:;-")

        if not content or content.lower() in {"none", "-", "--"}:
            content = "None"

        sections[heading] = content

    # Emit all canonical headings in order; default missing to 'None'.
    lines = [f"{h}: {sections.get(h, 'None')}" for h in _RTL_HEADINGS]
    return "\n\n".join(lines)


# -----------------------
# PromptTemplate instance
# -----------------------

_rtlreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=_load_prompt_from_pkg(_PROMPT_RTL_REVIEW),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class RTLReviewAgent:
    """Review RTL and return a structured critique across canonical sections."""

    agent_type = "rtlreview"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="rtlreview")`.
        verbose : bool, default False
            If True, log rendered prompt and raw model output.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="rtlreview")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Execute an RTL review and return a normalized report.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code to be reviewed.

        Returns
        -------
        str
            Structured review with canonical headings.
        """
        prompt = _compose_review_prompt(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            self.logger.info("Rendered prompt for RTL review:\n%s", prompt)

        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - provider/network error
            raise RuntimeError(f"LLM invocation failed in RTLReviewAgent: {exc}") from exc

        if self.verbose:
            self.logger.info("Raw LLM review output:\n%s", repr(result))

        review_text = _extract_review_content(result)
        if not review_text.strip():
            self.logger.warning("LLM returned empty review. Using fallback critique report.")
            review_text = (
                "Syntax Issues: None\n"
                "Logic Issues: None\n"
                "Reset Issues: None\n"
                "Port Declaration Issues: None\n"
                "Optimization Suggestions: None\n"
                "Naming Improvements: None\n"
                "Synthesis Concerns: None\n"
                "Overall Comments: No major issues found."
            )
        else:
            review_text = extract_structured_rtl_review(review_text)

        cleaned = review_text.strip()
        self.logger.info("Cleaned review output:\n%s", cleaned)
        return cleaned

    def improve(self, spec: str, rtl_code: str, feedback: str) -> str:
        """
        Re-run the review. Current implementation ignores `feedback` by design.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code to be reviewed.
        feedback : str
            Reviewer or debug feedback (unused).

        Returns
        -------
        str
            Structured review identical in format to `run(...)`.

        Notes
        -----
        - Kept for API compatibility with other agents' `.improve(...)`.
        - If you later want to thread `feedback` into the prompt, switch to a
          second template and keep the original path commented below.
        """
        self.logger.info("Re-running review with feedback context (ignored).")
        # TODO: Introduce a feedback-aware prompt:
        # feedback_prompt = _rtlreview_improve_prompt_template.format(
        #     spec=spec, rtl_code=rtl_code, feedback=feedback
        # )
        # result = self.llm.invoke(feedback_prompt)
        # return extract_structured_rtl_review(_extract_review_content(result))
        return self.run(spec, rtl_code)
