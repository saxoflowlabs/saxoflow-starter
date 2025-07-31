import os
import re
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

def _extract_report_content(result: object) -> str:
    """
    Cleanly extract the report content from the LLM output,
    handling AIMessage, dict, or string.
    """
    # 1. AIMessage (e.g., LangChain, Fireworks, OpenAI) with .content attribute
    if hasattr(result, "content"):
        text = result.content
    # 2. dict-style LLM result with 'content' key
    elif isinstance(result, dict) and 'content' in result:
        text = result['content']
    else:
        text = str(result)

    # Remove markdown code fences and extraneous ``` markers
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"```(\w+)?", "", text)
    # Optionally, strip leading/trailing whitespace and repeated blank lines
    text = text.strip()
    text = re.sub(r"\n\s*\n", "\n\n", text)  # condense multiple blank lines
    # Remove any extra LLM meta text
    text = re.sub(r"(AIMessage|content=|additional_kwargs=|response_metadata=|usage_metadata=).*", "", text)
    return text.strip()

# --- Prompt template: expects ALL phase outputs as named fields ---
report_prompt_template = PromptTemplate(
    input_variables=[
        "specification",
        "rtl_code",
        "rtl_review_report",
        "testbench_code",
        "testbench_review_report",
        "formal_properties",
        "formal_property_review_report",
        "simulation_status",
        "simulation_stdout",
        "simulation_stderr",
        "simulation_error_message",
        "debug_report"
    ],
    template=load_prompt_from_pkg("report_prompt.txt"),
    template_format="jinja2"
)


class ReportAgent:
    agent_type = "report"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="report")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, phase_outputs: dict) -> str:
        """
        Summarize the outputs of all agents/phases for reporting.
        Expects phase_outputs as a dict with all named artifacts.
        """
        # Make sure all required keys are present (use '' for missing keys)
        prompt_vars = {k: phase_outputs.get(k, "") for k in report_prompt_template.input_variables}
        prompt = report_prompt_template.format(**prompt_vars)
        if self.verbose:
            self.logger.info("Prompt for summary report:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Raw pipeline report output:\n" + repr(result))
        clean_report = _extract_report_content(result)
        if not clean_report or not clean_report.strip():
            self.logger.warning("LLM returned empty report. Using fallback summary.")
            clean_report = "No report generated. Please check pipeline phase outputs."
        self.logger.info("Cleaned pipeline summary report:\n" + clean_report)
        return clean_report

# --- Usage as LangChain Tool (optional) ---
report_tool = Tool(
    name="PipelineReport",
    func=lambda phase_outputs: ReportAgent().run(phase_outputs),
    description="Summarize outputs of all phases for a pipeline report."
)
