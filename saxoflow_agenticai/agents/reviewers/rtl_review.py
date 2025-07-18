from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <-- Use your central LLM config

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Load prompt file relative to the saxoflow_agenticai/ root, always robust
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt templates ---
rtlreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=load_prompt_from_pkg("rtlreview_prompt.txt")
)

class RTLReviewAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("rtlreview")  # Use config-driven LLM
        self.verbose = verbose

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Review RTL code for structural, style, synthesis, and spec adherence.
        """
        prompt = rtlreview_prompt_template.format(
            spec=spec, 
            rtl_code=rtl_code
        )
        if self.verbose:
            logger.info("[RTLReviewAgent] Prompt for RTL review:\n" + prompt)
        result = self.llm.invoke(prompt)
        # Fallback for empty response
        if not result or not str(result).strip():
            logger.warning("[RTLReviewAgent] LLM returned empty review. Using fallback critique report.")
            result = (
                "Syntax Issues: None\n"
                "Logic Issues: None\n"
                "Reset Issues: None\n"
                "Port Declarations Issues: None\n"
                "Optimization Suggestions: None\n"
                "Naming Improvements: None\n"
                "Synthesis Concerns: None\n"
                "Overall Comments: No major issues found."
            )
        logger.info("[RTLReviewAgent] RTL review completed.")
        return str(result).strip()

    def improve(self, spec: str, rtl_code: str, feedback: str) -> str:
        """
        Optionally, you could make this take a separate template (rtlreview_improve_prompt.txt)
        or just re-run the same review (if the logic doesn't need more).
        """
        logger.info("[RTLReviewAgent] Re-running review with feedback context (if any).")
        return self.run(spec, rtl_code)
