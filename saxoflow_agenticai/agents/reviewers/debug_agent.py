from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <- Add this

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Loads prompts from the package's prompts/ directory, robust to CWD/package usage.
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt template loading ---
debug_prompt_template = PromptTemplate(
    input_variables=["debug_input"],
    template=load_prompt_from_pkg("debug_prompt.txt")
)

# (Optional) If you add a feedback-aware debug_improve_prompt.txt, do similar:
# debug_improve_prompt_template = PromptTemplate(
#     input_variables=["debug_input", "review"],
#     template=load_prompt_from_pkg("debug_improve_prompt.txt")
# )

class DebugAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("debug")  # <- Config-driven LLM
        self.verbose = verbose

    def run(self, debug_input: str) -> str:
        """
        Analyze debug input (code, log, error, or simulation output) and provide debugging advice.
        """
        prompt = debug_prompt_template.format(debug_input=debug_input)
        if self.verbose:
            logger.info("[DebugAgent] Debug prompt:\n" + prompt)
        result = self.llm.invoke(prompt)
        if not result or not str(result).strip():
            logger.warning("[DebugAgent] LLM returned empty debug output. Using fallback.")
            result = (
                "No explicit debugging suggestions found. "
                "Ensure your input includes code, testbench, or error logs for best results."
            )
        logger.info("[DebugAgent] Debugging output generated.")
        return str(result).strip()

    def improve(self, debug_input: str, feedback: str) -> str:
        """
        Use feedback to refine the debugging advice.
        (For now, re-run with just the debug_input. Add feedback prompt if desired.)
        """
        logger.info("[DebugAgent] Re-running debug with feedback context (if any).")
        # If you add a debug_improve_prompt.txt, you can do:
        # prompt = debug_improve_prompt_template.format(debug_input=debug_input, review=feedback)
        # result = self.llm.invoke(prompt)
        # ...etc.
        return self.run(debug_input)
