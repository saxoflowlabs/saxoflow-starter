import os
import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from langchain_core.tools import Tool
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger

def load_prompt_from_pkg(filename):
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()


def extract_verilog_code(llm_output: str) -> str:
    """
    Extracts Verilog code from LLM output as robustly as possible.
    - Strips all markdown code fences and stray backticks.
    - Prefers text between 'module' and matching 'endmodule'.
    - Returns clean Verilog code, free of artifacts.
    - Converts any escaped newlines (\\n or \n) to actual newlines.
    """
    # 1. Remove triple backtick code fences and any 'verilog' language hints
    code = re.sub(r"```(?:verilog)?", "", llm_output, flags=re.IGNORECASE).replace("```", "")

    # 2. Remove single backticks at line start/end (common markdown junk)
    code = re.sub(r"^`+", "", code, flags=re.MULTILINE)
    code = re.sub(r"`+$", "", code, flags=re.MULTILINE)

    # 3. Remove smart quotes (from copy-paste or markdown processors)
    code = code.replace('“', '"').replace('”', '"').replace("‘", "'").replace("’", "'")

    # 4. Remove "content=" (from LLM API outputs) and other wrappers
    code = re.sub(r"^content=['\"]?", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"^Here[^\n]*\n", "", code)  # Remove "Here is ..." lines

    # 5. Now extract from first 'module' to matching 'endmodule'
    modules = re.findall(r"(module[\s\S]+?endmodule)", code, re.IGNORECASE)
    if modules:
        code = "\n\n".join([m.strip() for m in modules])
    else:
        # 6. Fallback: find first line starting with module
        lines = code.strip().splitlines()
        for idx, line in enumerate(lines):
            if line.strip().lower().startswith('module'):
                cleaned = "\n".join(lines[idx:]).strip().rstrip("`")
                cleaned = cleaned.rstrip("'\"")
                code = cleaned
                break
        else:
            # 7. Final fallback: return everything, but remove leading/trailing backticks, quotes
            code = code.strip().strip("`").strip("'\"")

    # 8. Replace escaped newlines with real linebreaks (handles both \\n and \n)
    code = code.replace("\\n", "\n").replace('\n', '\n')
    return code


rtlgen_prompt_template = PromptTemplate(
    input_variables=["spec"],
    template=load_prompt_from_pkg("rtlgen_prompt.txt"),
    template_format="jinja2"
)

rtlgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_rtl_code", "review"],
    template=load_prompt_from_pkg("rtlgen_improve_prompt.txt"),
    template_format="jinja2"
)


class RTLGenAgent:
    agent_type = "rtlgen"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="rtlgen")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str) -> str:
        prompt = rtlgen_prompt_template.format(spec=spec)
        if self.verbose:
            self.logger.info("Prompt for RTL generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("RTL code generated (raw):\n" + str(result))
        verilog_code = extract_verilog_code(str(result))
        # Fix for escaped newlines:
        if "\\n" in verilog_code and not "\n" in verilog_code:
            verilog_code = verilog_code.replace("\\n", "\n")
        if self.verbose:
            self.logger.info("RTL code after extraction:\n" + verilog_code)
        return verilog_code

    def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
        prompt = rtlgen_improve_prompt_template.format(
            spec=spec,
            prev_rtl_code=prev_rtl_code,
            review=review
        )
        if self.verbose:
            self.logger.info("Prompt for RTL improvement:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Improved RTL code generated (raw):\n" + str(result))
        verilog_code = extract_verilog_code(str(result))
        if self.verbose:
            self.logger.info("Improved RTL code after extraction:\n" + verilog_code)
        return verilog_code


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
