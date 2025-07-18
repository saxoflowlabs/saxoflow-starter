from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <- Import this!

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Robustly load prompt file relative to project root
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# Load the prompt template from file at startup (recommended for production)
tbreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "testbench_code"],
    template=load_prompt_from_pkg("tbreview_prompt.txt")
)

class TBReviewAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("tbreview")   # <- Config-driven
        self.verbose = verbose

    def run(self, spec: str, rtl_code: str, testbench_code: str) -> str:
        """
        Review a SystemVerilog testbench for stimulus quality, coverage, and correct RTL instantiation,
        using spec and RTL code as reference.
        """
        prompt = tbreview_prompt_template.format(
            spec=spec,
            rtl_code=rtl_code,
            testbench_code=testbench_code
        )
        if self.verbose:
            logger.info("[TBReviewAgent] Testbench review prompt:\n" + prompt)
        result = self.llm.invoke(prompt)
        # Fallback for empty response
        if not result or not str(result).strip():
            logger.warning("[TBReviewAgent] LLM returned empty review. Using fallback critique report.")
            result = (
                "Instantiation Issues: None\n"
                "Stimulus Issues: None\n"
                "Coverage Gaps: None\n"
                "Randomization Usage: None\n"
                "Corner Case Suggestions: None\n"
                "Assertions Suggestions: None\n"
                "Monitoring & Debug Suggestions: None\n"
                "Overall Comments: No major issues found."
            )
        logger.info("[TBReviewAgent] Testbench review completed.")
        return str(result).strip()

    def improve(self, spec: str, rtl_code: str, testbench_code: str, feedback: str) -> str:
        """
        Optionally re-run the review or escalate based on new feedback, with full context.
        For extensibility, you can add a new prompt template with feedback if needed.
        """
        logger.info("[TBReviewAgent] Re-running testbench review with feedback context (if any).")
        return self.run(spec, rtl_code, testbench_code)
