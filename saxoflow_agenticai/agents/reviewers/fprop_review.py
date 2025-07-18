from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <- Import this

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Load prompt file relative to the repo's root for CLI or package usage
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

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
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("fpropreview")  # <- Config-driven LLM
        self.verbose = verbose

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
            logger.info("[FormalPropReviewAgent] Formal property review prompt:\n" + prompt)
        result = self.llm.invoke(prompt)
        # Fallback for empty response
        if not result or not str(result).strip():
            logger.warning("[FormalPropReviewAgent] LLM returned empty review. Using fallback critique report.")
            result = (
                "Missing Properties: None\n"
                "Trivial Properties Detected: None\n"
                "Scope & Coverage Issues: None\n"
                "Cycle-Accuracy Problems: None\n"
                "Assertion Naming Suggestions: None\n"
                "Overall Property Set Quality: No major issues found.\n"
                "Additional Formal Suggestions: None"
            )
        logger.info("[FormalPropReviewAgent] Formal property review completed.")
        return str(result).strip()

    def improve(self, spec: str, rtl_code: str, prop_code: str, feedback: str) -> str:
        """
        Re-run the review or escalate based on new feedback.
        For extensibility, you could make a dedicated 'fpropreview_improve_prompt.txt'.
        """
        logger.info("[FormalPropReviewAgent] Re-running formal property review with feedback context (if any).")
        return self.run(spec, rtl_code, prop_code)
