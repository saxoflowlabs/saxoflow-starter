from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <-- Add this import

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    # Always load prompt relative to saxoflow_agenticai/ root
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt templates (with Jinja2 support) ---
fpropgen_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=load_prompt_from_pkg("fpropgen_prompt.txt"),
    template_format="jinja2"
)

fpropgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "prev_fprops", "review"],
    template=load_prompt_from_pkg("fpropgen_improve_prompt.txt"),
    template_format="jinja2"
)

class FormalPropGenAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or get_llm_from_config("fpropgen")  # <-- config-driven
        self.verbose = verbose

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Generate SystemVerilog formal properties (SVAs) for the given RTL code and design spec.
        """
        prompt = fpropgen_prompt_template.format(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            logger.info("[FormalPropGenAgent] Prompt for SVA generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[FormalPropGenAgent] SVAs generated:\n" + str(result))
        return str(result).strip()

    def improve(self, spec: str, rtl_code: str, prev_fprops: str, review: str) -> str:
        """
        Use review feedback and previous properties to improve the formal properties.
        Uses fpropgen_improve_prompt.txt as template.
        """
        prompt = fpropgen_improve_prompt_template.format(
            spec=spec,
            rtl_code=rtl_code,
            prev_fprops=prev_fprops,
            review=review
        )
        if self.verbose:
            logger.info("[FormalPropGenAgent] Prompt for improved SVA:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[FormalPropGenAgent] Improved SVAs generated:\n" + str(result))
        return str(result).strip()

# --- Usage as LangChain Tool (optional) ---

fpropgen_tool = Tool(
    name="FormalPropGen",
    func=lambda spec, rtl_code: FormalPropGenAgent().run(spec, rtl_code),
    description="Generate SystemVerilog assertions (SVA) for a design spec and RTL code."
)

fpropgen_improve_tool = Tool(
    name="FormalPropGenImprove",
    func=lambda spec, rtl_code, prev_fprops, review: FormalPropGenAgent().improve(spec, rtl_code, prev_fprops, review),
    description="Improve formal properties based on prior SVAs and review feedback."
)
