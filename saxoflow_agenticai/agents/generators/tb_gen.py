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


def extract_verilog_tb_code(llm_output: str) -> str:
    """
    Extract only the Verilog/SystemVerilog testbench code from LLM output.
    Handles code blocks, content wrappers, markdown artifacts, smart quotes, and
    extracts module...endmodule if present.
    Converts any escaped newlines (\\n or \n) to actual newlines.
    Never strips quotes inside code, only at the very start/end.
    """
    # 1. Remove triple backtick code fences and any 'verilog' or 'systemverilog' language hints
    code = re.sub(r"```(?:verilog|systemverilog)?", "", llm_output, flags=re.IGNORECASE).replace("```", "")

    # 2. Remove single backticks at line start/end (common markdown junk)
    code = re.sub(r"^`+", "", code, flags=re.MULTILINE)
    code = re.sub(r"`+$", "", code, flags=re.MULTILINE)

    # 3. Remove smart quotes (from copy-paste or markdown processors)
    code = code.replace('“', '"').replace('”', '"').replace("‘", "'").replace("’", "'")

    # 4. Remove "content=" (from LLM API outputs) and "Here is..." lines
    code = re.sub(r"^content=['\"]?", "", code.strip(), flags=re.IGNORECASE)
    code = re.sub(r"^Here[^\n]*\n", "", code)

    # 5. Extract from first 'module' to matching 'endmodule'
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
            # 7. Final fallback: remove leading/trailing backticks, quotes
            code = code.strip().strip("`").strip("'\"")

    # 8. Replace escaped newlines with real linebreaks (handles both \\n and \n)
    code = code.replace("\\n", "\n").replace('\n', '\n')
    return code


# --- Prompt templates (Jinja2 support) ---
tbgen_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code", "top_module_name"],
    template=load_prompt_from_pkg("tbgen_prompt.txt"),
    template_format="jinja2"
)

tbgen_improve_prompt_template = PromptTemplate(
    input_variables=["spec", "prev_tb_code", "review", "rtl_code", "top_module_name"],
    template=load_prompt_from_pkg("tbgen_improve_prompt.txt"),
    template_format="jinja2"
)


class TBGenAgent:
    agent_type = "tbgen"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="tbgen")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str, top_module_name: str) -> str:
        """
        Generate a SystemVerilog testbench for the given RTL code, using the design spec.
        """
        prompt = tbgen_prompt_template.format(spec=spec, rtl_code=rtl_code, top_module_name=top_module_name)
        if self.verbose:
            self.logger.info("Prompt for testbench generation:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Testbench generated (raw):\n" + str(result))
        tb_code = extract_verilog_tb_code(str(result))
        # Fix for escaped newlines:
        if "\\n" in tb_code and not "\n" in tb_code:
            tb_code = tb_code.replace("\\n", "\n")
        if self.verbose:
            self.logger.info("Testbench after extraction:\n" + tb_code)
        return tb_code

    def improve(self, spec: str, prev_tb_code: str, review: str, rtl_code: str, top_module_name: str) -> str:
        """
        Use review feedback to improve the testbench code.
        """
        prompt = tbgen_improve_prompt_template.format(
            spec=spec,
            prev_tb_code=prev_tb_code,
            review=review,
            rtl_code=rtl_code,
            top_module_name=top_module_name
        )
        if self.verbose:
            self.logger.info("Prompt for improved testbench:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Improved testbench generated (raw):\n" + str(result))
        tb_code = extract_verilog_tb_code(str(result))
        # Fix for escaped newlines:
        if "\\n" in tb_code and not "\n" in tb_code:
            tb_code = tb_code.replace("\\n", "\n")
        if self.verbose:
            self.logger.info("Improved testbench after extraction:\n" + tb_code)
        return tb_code


# ---- Usage as a LangChain Tool (Optional) ----

tbgen_tool = Tool(
    name="TBGen",
    func=lambda spec, rtl_code, top_module_name: TBGenAgent().run(spec, rtl_code, top_module_name),
    description="Generate a SystemVerilog testbench from a spec and RTL code."
)

tbgen_improve_tool = Tool(
    name="TBGenImprove",
    func=lambda spec, prev_tb_code, review, rtl_code, top_module_name: TBGenAgent().improve(spec, prev_tb_code, review, rtl_code, top_module_name),
    description="Improve a testbench using review feedback, original spec, and RTL code."
)
