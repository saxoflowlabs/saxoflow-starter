from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <-- use your config LLM selector

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Always load prompt relative to saxoflow_agenticai/ root
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt templates ---
report_prompt_template = PromptTemplate(
    input_variables=["phases"],
    template=load_prompt_from_pkg("report_prompt.txt")
)

class ReportAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("report")
        self.verbose = verbose

    def run(self, phase_outputs: dict) -> str:
        """
        Summarize the outputs of all agents/phases for reporting.
        """
        prompt = report_prompt_template.format(phases=phase_outputs)
        if self.verbose:
            logger.info("[ReportAgent] Prompt for summary report:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[ReportAgent] Pipeline summary generated:\n" + str(result))
        return str(result).strip()

# --- Usage as LangChain Tool (optional) ---
report_tool = Tool(
    name="PipelineReport",
    func=lambda phase_outputs: ReportAgent().run(phase_outputs),
    description="Summarize outputs of all phases for a pipeline report."
)
