import os
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger

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
    agent_type = "fpropgen"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="fpropgen")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Generate SystemVerilog formal properties (SVAs) for the given RTL code and design spec.
        """
        prompt = fpropgen_prompt_template.format(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            self.logger.info("Prompt for SVA generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("SVAs generated:\n" + str(result))
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
            self.logger.info("Prompt for improved SVA:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Improved SVAs generated:\n" + str(result))
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
