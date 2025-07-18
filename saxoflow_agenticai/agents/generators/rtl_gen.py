from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
import logging
import os

from saxoflow_agenticai.core.llm_factory import get_llm_from_config

logger = logging.getLogger("saxoflow_agenticai")

def load_prompt_from_pkg(filename):
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

rtlgen_prompt_template = PromptTemplate(
    input_variables=["spec"],
    template=load_prompt_from_pkg("rtlgen_prompt.txt"),
    template_format="jinja2"  # <-- Add this!
)

rtlgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_rtl_code", "review"],
    template=load_prompt_from_pkg("rtlgen_improve_prompt.txt"),
    template_format="jinja2"  # <-- Add this!
)

class RTLGenAgent:
    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        # Pick LLM from config if not supplied
        self.llm = llm or get_llm_from_config("rtlgen")
        self.verbose = verbose

    def run(self, spec: str) -> str:
        prompt = rtlgen_prompt_template.format(spec=spec)
        if self.verbose:
            logger.info("[RTLGenAgent] Prompt for RTL generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[RTLGenAgent] RTL code generated:\n" + str(result))
        return str(result).strip()

    def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
        prompt = rtlgen_improve_prompt_template.format(
            spec=spec,
            prev_rtl_code=prev_rtl_code,
            review=review
        )
        if self.verbose:
            logger.info("[RTLGenAgent] Prompt for RTL improvement:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            logger.info("[RTLGenAgent] Improved RTL code generated:\n" + str(result))
        return str(result).strip()

# ---- LangChain Tool registration ----
def _rtlgen_tool_func(spec: str) -> str:
    agent = RTLGenAgent()
    return agent.run(spec)

def _rtlgen_improve_tool_func(spec: str, prev_rtl_code: str, review: str) -> str:
    agent = RTLGenAgent()
    return agent.improve(spec, prev_rtl_code, review)

rtlgen_tool = Tool(
    name="RTLGen",
    func=_rtlgen_tool_func,
    description="Generate RTL code from a specification."
)

rtlgen_improve_tool = Tool(
    name="RTLGenImprove",
    func=_rtlgen_improve_tool_func,
    description="Improve RTL code based on review feedback."
)
