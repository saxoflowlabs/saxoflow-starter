from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config  # <-- IMPORTANT

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt templates (Jinja2 support) ---
tbgen_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=load_prompt_from_pkg("tbgen_prompt.txt"),
    template_format="jinja2"
)

tbgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_tb_code", "review", "rtl_code"],
    template=load_prompt_from_pkg("tbgen_improve_prompt.txt"),
    template_format="jinja2"
)

class TBGenAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        # Use config-driven LLM (like RTLGenAgent)
        self.llm = llm or get_llm_from_config("tbgen")
        self.verbose = verbose

    def run(self, spec: str, rtl_code: str) -> str:
        """
        Generate a SystemVerilog testbench for the given RTL code, using the design spec.
        """
        prompt = tbgen_prompt_template.format(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            logger.info("[TBGenAgent] Prompt for testbench generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[TBGenAgent] Testbench generated:\n" + str(result))
        return str(result).strip()

    def improve(self, spec: str, prev_tb_code: str, review: str, rtl_code: str) -> str:
        """
        Use review feedback to improve the testbench code.
        """
        prompt = tbgen_improve_prompt_template.format(
            spec=spec,
            prev_tb_code=prev_tb_code,
            review=review,
            rtl_code=rtl_code
        )
        if self.verbose:
            logger.info("[TBGenAgent] Prompt for improved testbench:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[TBGenAgent] Improved testbench generated:\n" + str(result))
        return str(result).strip()

# ---- Usage as a LangChain Tool (Optional) ----

tbgen_tool = Tool(
    name="TBGen",
    func=lambda spec, rtl_code: TBGenAgent().run(spec, rtl_code),
    description="Generate a SystemVerilog testbench from a spec and RTL code."
)

tbgen_improve_tool = Tool(
    name="TBGenImprove",
    func=lambda spec, prev_tb_code, review, rtl_code: TBGenAgent().improve(spec, prev_tb_code, review, rtl_code),
    description="Improve a testbench using review feedback, original spec, and RTL code."
)
