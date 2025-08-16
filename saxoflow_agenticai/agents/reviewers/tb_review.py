# saxoflow_agenticai/agents/reviewers/tb_review.py
"""
Testbench review agent.

This module provides a `TBReviewAgent` that renders a Jinja2 prompt and calls
an LLM to produce a structured critique of a Verilog-2001 testbench. The raw
output is normalized into a canonical, sectioned report.

Public API (kept stable)
------------------------
- class TBReviewAgent
    - run(spec: str, rtl_code: str, top_module_name: str, testbench_code: str) -> str
    - improve(spec: str, rtl_code: str, top_module_name: str, testbench_code: str, feedback: str) -> str
- Functions
    - extract_structured_review(text: str) -> str

Notes
-----
- We keep `PromptTemplate(template_format="jinja2")` and `.invoke(prompt)`.
- Output format remains "Heading: value" lines separated by blank lines.
- The `top_module_name` parameter is accepted for compatibility but unused.
- New: we *prepend* testbench guidelines and constructs policy (if present)
  before the base prompt so models (including smaller ones) have consistent,
  tool-aware constraints (Icarus/Verilator/Yosys/OpenROAD). Missing files
  are tolerated (warning only).

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

__all__ = ["TBReviewAgent", "extract_structured_review"]

logger = get_logger(__name__)


# -----------------------
# Prompt file management
# -----------------------

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_PROMPT_TB_REVIEW = "tbreview_prompt.txt"

# Optional prepended guidance files (mirrors TBGenAgent).
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

    Missing files are tolerated; a warning is logged and an empty string returned.

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
        logger.warning("[TBReviewAgent] Optional %s file not found: %s", label, path)
    except OSError as exc:  # pragma: no cover - filesystem issues
        logger.warning("[TBReviewAgent] Failed reading %s (%s): %s", label, path, exc)
    return ""


def _build_tb_review_prompt(base_template: str) -> str:
    """
    Prepend TB guidelines and constructs policy (if present) to the review prompt.

    Parameters
    ----------
    base_template : str
        The original tbreview prompt text (Jinja).

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

    sections.append(base_template)
    return "\n\n".join(sections)


# ---------------------------
# LLM-output cleaning helpers
# ---------------------------

# Compile once for performance and clarity.
_RE_FENCED_BLOCK = re.compile(r"```.*?```", flags=re.DOTALL)
_RE_META = re.compile(
    r"AIMessage\(content=|additional_kwargs=.*|\bresponse_metadata=.*|usage_metadata=.*|id='[^']+'"
)
_RE_HERE_IS = re.compile(
    r"Here is the feedback on the testbench code:|"
    r"Here is the output feedback for the provided testbench:|"
    r"Here is the output feedback:",
    flags=re.IGNORECASE,
)
_RE_NEWLINES = re.compile(r"\r\n?")  # \r\n or \r -> \n
_RE_BOLD = re.compile(r"\*\*")
_RE_HEADING_SEP = re.compile(r"[\s\-*]+\s*")  # collapse bullets/dashes


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
    if isinstance(result, dict) and "content" in result:
        return str(result["content"])
    if hasattr(result, "content"):
        return str(getattr(result, "content"))
    return str(result)


# Canonical headings for TB review (order preserved in output).
_TB_HEADINGS: List[str] = [
    "Instantiation Issues",
    "Signal Declaration Issues",
    "Stimulus Issues",
    "Coverage Gaps",
    "Randomization Usage",
    "Corner Case Suggestions",
    "Output Checking Suggestions",
    "Waveform/Monitoring Suggestions",
    "Standards Compliance Issues",
    "Overall Comments",
]


def extract_structured_review(text: str) -> str:
    """
    Normalize an LLM testbench review into labeled sections.

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

    # Remove artifacts and normalize whitespace.
    text = _RE_FENCED_BLOCK.sub("", text)
    text = _RE_META.sub("", text)
    text = _RE_HERE_IS.sub("", text)
    text = _RE_NEWLINES.sub("\n", text)
    text = _RE_BOLD.sub("", text)

    # Build a heading-capture pattern: "(Heading A|Heading B|...):"
    heading_pattern = r"(?P<heading>" + "|".join(re.escape(h) for h in _TB_HEADINGS) + r")\s*:\s*\n?"
    splits = [(m.group("heading"), m.start()) for m in re.finditer(heading_pattern, text, re.IGNORECASE)]
    sections: Dict[str, str] = {}

    # Append sentinel for end-of-string iteration.
    splits.append(("__END__", len(text)))

    for i in range(len(splits) - 1):
        heading, start = splits[i]
        end = splits[i + 1][1]

        # Compute the content start offset just after the heading match in this slice.
        local = re.search(heading_pattern, text[start:], re.IGNORECASE)
        content_start = start + local.end() if local else start  # pragma: no cover (defensive)

        content = text[content_start:end].strip()

        # Flatten lines and collapse bullets/dashes.
        content = content.replace("\\n", " ").replace("\n", " ")
        content = _RE_HEADING_SEP.sub(" ", content)
        content = re.sub(r"\s+", " ", content).strip(" .:;-")

        if not content or content.lower() in {"none", "-", "--"}:
            content = "None"

        sections[heading] = content

    # Emit all canonical headings in order; default missing to 'None'.
    lines = [f"{h}: {sections.get(h, 'None')}" for h in _TB_HEADINGS]
    return "\n\n".join(lines)


# -----------------------
# PromptTemplate instance
# -----------------------

_tbreview_prompt_template = PromptTemplate(
    input_variables=["testbench_code", "spec", "rtl_code"],
    template=_build_tb_review_prompt(_load_prompt_from_pkg(_PROMPT_TB_REVIEW)),
    template_format="jinja2",
)


# -------------
# Agent class
# -------------

class TBReviewAgent:
    """Review a Verilog-2001 testbench and return a structured critique."""

    agent_type = "tbreview"

    def __init__(self, llm: Optional[BaseLanguageModel] = None, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        llm : Optional[BaseLanguageModel]
            Pre-constructed LangChain model. If None, resolve from configuration
            via `ModelSelector.get_model(agent_type="tbreview")`.
        verbose : bool, default False
            If True, log rendered prompt and raw model output.
        """
        self.llm = llm or ModelSelector.get_model(agent_type="tbreview")
        self.verbose = bool(verbose)
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str, top_module_name: str, testbench_code: str) -> str:  # noqa: ARG002
        """
        Execute a testbench review and return a normalized report.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code under test (context for the review).
        top_module_name : str
            Top-level module name (unused; kept for interface compatibility).
        testbench_code : str
            The testbench code to review.

        Returns
        -------
        str
            Structured review with canonical headings.
        """
        # NOTE: `top_module_name` is intentionally unused in the current prompt.
        prompt = _tbreview_prompt_template.format(
            testbench_code=testbench_code,
            spec=spec,
            rtl_code=rtl_code,
        )

        if self.verbose:
            self.logger.info("Rendered prompt for TB review:\n%s", prompt)

        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - provider/network error
            raise RuntimeError(f"LLM invocation failed in TBReviewAgent: {exc}") from exc

        if self.verbose:
            self.logger.info("Raw LLM review output:\n%s", repr(result))

        review_text = _extract_review_content(result)
        if not review_text or not review_text.strip():
            # Keep the original fallback text (headings differ slightly from canonical set).
            self.logger.warning("LLM returned empty review. Using fallback critique report.")
            review_text = (
                "Instantiation Issues: None\n"
                "Stimulus Issues: None\n"
                "Coverage Gaps: None\n"
                "Randomization Usage: None\n"
                "Corner Case Suggestions: None\n"
                "Assertions & Checking Suggestions: None\n"
                "Monitoring & Debug Suggestions: None\n"
                "Overall Comments: No major issues found."
            )
            cleaned = review_text.strip()
        else:
            cleaned = extract_structured_review(review_text).strip()

        self.logger.info("Cleaned TB review output:\n%s", cleaned)
        return cleaned

    def improve(
        self,
        spec: str,
        rtl_code: str,
        top_module_name: str,  # noqa: ARG002
        testbench_code: str,
        feedback: str,  # noqa: ARG002
    ) -> str:
        """
        Re-run the review. Current implementation ignores `feedback`.

        Parameters
        ----------
        spec : str
            Natural-language design specification.
        rtl_code : str
            RTL code under test (context for the review).
        top_module_name : str
            Top-level module name (unused; kept for interface compatibility).
        testbench_code : str
            The testbench code to review.
        feedback : str
            Reviewer or debug feedback (unused).

        Returns
        -------
        str
            Structured review identical in format to `run(...)`.

        Notes
        -----
        - Kept for API compatibility with other agents' `.improve(...)` methods.
        - If you later want to incorporate `feedback`, add a second template and
          keep this original path commented for reference.
        """
        self.logger.info("Re-running testbench review with feedback context (ignored).")
        return self.run(spec, rtl_code, top_module_name, testbench_code)
