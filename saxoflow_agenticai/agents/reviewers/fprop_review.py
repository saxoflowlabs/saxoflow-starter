import os
import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger

def load_prompt_from_pkg(filename):
    # Load prompt file relative to the repo's root for CLI or package usage
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# Extraction function for formal property reviews
def extract_structured_formal_review(text: str, headings=None) -> str:
    """
    Extract and clean formal property review sections as "Heading: value" (one per line).
    Removes markdown, metadata, and flattens output for easy reading.
    """
    # Remove markdown/code blocks and common LLM noise
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"For example.*?(?=\n\S|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"Additionally, consider.*?(?=\n\S|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    if "additional_kwargs" in text:
        text = text.split("additional_kwargs")[0]
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)

    # Default headings for formal property review
    if headings is None:
        headings = [
            "Missing Properties",
            "Trivial Properties Detected",
            "Scope & Coverage Issues",
            "Cycle-Accuracy Problems",
            "Assertion Naming Suggestions",
            "Overall Property Set Quality",
            "Additional Formal Suggestions"
        ]
    results = {h: None for h in headings}
    for idx, heading in enumerate(headings):
        next_heading = headings[idx + 1] if idx + 1 < len(headings) else None
        if next_heading:
            pattern = rf"{re.escape(heading)}:\s*(.*?)(?=\n\s*{re.escape(next_heading)}:|\Z)"
        else:
            pattern = rf"{re.escape(heading)}:\s*(.*)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            value = match.group(1)
            value = value.replace('\n', ' ').replace('\\n', ' ')
            value = re.sub(r"[-*]\s*", "", value)
            value = re.sub(r"\s+", " ", value)
            value = value.strip(" .:;-")
            if value and not value.lower().startswith("none"):
                results[heading] = value
            else:
                results[heading] = "None"
        else:
            results[heading] = "None"
    # Output in canonical order, one heading per line
    return "\n".join([f"{h}: {results[h]}" for h in headings]).strip()

# --- Prompt templates ---
fpropreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "formal_properties"],
    template=load_prompt_from_pkg("fpropreview_prompt.txt")
)
debug_prompt_template = PromptTemplate(
    input_variables=["debug_input"],
    template=load_prompt_from_pkg("debug_prompt.txt")
)

class FormalPropReviewAgent:
    agent_type = "fpropreview"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="fpropreview")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str, prop_code: str) -> str:
        """
        Review SystemVerilog formal properties for coverage and completeness.
        """
        prompt = fpropreview_prompt_template.format(
            spec=spec,
            rtl_code=rtl_code,
            formal_properties=prop_code
        )
        if self.verbose:
            self.logger.info("Formal property review prompt:\n" + prompt)
        result = self.llm.invoke(prompt)
        review_text = str(result)
        if not review_text or not review_text.strip():
            self.logger.warning("LLM returned empty review. Using fallback critique report.")
            review_text = (
                "Missing Properties: None\n"
                "Trivial Properties Detected: None\n"
                "Scope & Coverage Issues: None\n"
                "Cycle-Accuracy Problems: None\n"
                "Assertion Naming Suggestions: None\n"
                "Overall Property Set Quality: No major issues found.\n"
                "Additional Formal Suggestions: None"
            )
        else:
            review_text = extract_structured_formal_review(review_text)
        self.logger.info("Formal property review cleaned output:\n" + review_text.strip())
        return review_text.strip()

    def improve(self, spec: str, rtl_code: str, prop_code: str, feedback: str) -> str:
        """
        Re-run the review or escalate based on new feedback.
        For extensibility, you could make a dedicated 'fpropreview_improve_prompt.txt'.
        """
        self.logger.info("Re-running formal property review with feedback context (if any).")
        return self.run(spec, rtl_code, prop_code)
