import os
import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger

def load_prompt_from_pkg(filename):
    # Loads prompts from the package's prompts/ directory, robust to CWD/package usage.
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

# --- Prompt template loading ---
debug_prompt_template = PromptTemplate(
    input_variables=[
        "rtl_code",
        "tb_code",
        "sim_stdout",
        "sim_stderr",
        "sim_error_message"
    ],
    template=load_prompt_from_pkg("debug_prompt.txt"),
    template_format="jinja2"
)

def extract_structured_debug_report(text: str, headings=None) -> str:
    """
    Extracts and cleans each section of the debug report,
    outputs each as 'Heading: value' separated by double newlines, always in canonical order.
    """
    import re

    # Remove markdown/code/metadata
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"For example.*?(?=\n\S|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"Additionally, consider.*?(?=\n\S|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"^content=['\"]?", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\*\*", "", text)  # Remove markdown bold
    if "additional_kwargs" in text:
        text = text.split("additional_kwargs")[0]
    text = text.replace('\r', '\n')
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)

    # Canonical order
    if headings is None:
        headings = [
            "Problems identified",
            "Explanation",
            "Suggested Fixes",
            "Suggested Agent for Correction"
        ]

    results = {h: "None" for h in headings}
    for idx, heading in enumerate(headings):
        # Find the start and end of each section
        next_heading = headings[idx + 1] if idx + 1 < len(headings) else None
        if next_heading:
            pattern = rf"{re.escape(heading)}:\s*((?:.|\n)*?)(?=\n\s*{re.escape(next_heading)}:|\Z)"
        else:
            pattern = rf"{re.escape(heading)}:\s*((?:.|\n)*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = match.group(1)
            # Clean: flatten multiple lines, bullets, extra whitespace
            value = value.replace('\n', ' ').replace('\\n', ' ')
            value = re.sub(r"[-*]\s*", "", value)
            value = re.sub(r"\s+", " ", value).strip(" .:;-")
            if value and value.lower() != "none":
                results[heading] = value
    # Output with double newlines for clarity
    return "\n\n".join([f"{h}: {results[h]}" for h in headings])


class DebugAgent:
    agent_type = "debug"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="debug")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def _extract_agents_from_debug(self, debug_report: str):
        """
        Parse the agent(s) the LLM recommends for correction.
        Returns a list of agent names (strings).
        """
        m = re.search(r"Suggested Agent for Correction:\s*([^\n]+)", debug_report)
        if m:
            # Split by comma for multiple agents, clean whitespace
            return [a.strip() for a in m.group(1).split(",")]
        # Default: fallback to both for safety (could also choose "UserAction" if no actionable feedback)
        return ["RTLGenAgent", "TBGenAgent"]

    def run(
        self,
        rtl_code: str,
        tb_code: str,
        sim_stdout: str = "",
        sim_stderr: str = "",
        sim_error_message: str = ""
    ):
        """
        Analyze RTL, testbench, and simulation log separately.
        Returns a cleaned debug report and the suggested agent(s) for correction as a list.
        """
        prompt = debug_prompt_template.format(
            rtl_code=rtl_code,
            tb_code=tb_code,
            sim_stdout=sim_stdout or "",
            sim_stderr=sim_stderr or "",
            sim_error_message=sim_error_message or ""
        )
        if self.verbose:
            self.logger.info("Debug prompt:\n" + prompt)
        result = self.llm.invoke(prompt)
        if not result or not str(result).strip():
            self.logger.warning("LLM returned empty debug output. Using fallback.")
            result = (
                "No explicit debugging suggestions found. "
                "Ensure your input includes code, testbench, or error logs for best results.\n"
                "Suggested Agent for Correction: UserAction"
            )
        debug_output_raw = str(result).strip()
        debug_output_clean = extract_structured_debug_report(debug_output_raw)
        self.logger.info("Debugging output generated.")
        agent_list = self._extract_agents_from_debug(debug_output_raw)
        self.logger.info("Debug Report (CLEANED):\n%s", debug_output_clean)

        return debug_output_clean, agent_list

    def improve(
        self,
        rtl_code: str,
        tb_code: str,
        sim_stdout: str = "",
        sim_stderr: str = "",
        sim_error_message: str = "",
        feedback: str = ""
    ):
        """
        Use feedback to refine the debugging advice.
        (For now, re-run with just the debug_input. Add feedback prompt if desired.)
        """
        self.logger.info("Re-running debug with feedback context (if any).")
        # For future: pass feedback to prompt if needed
        return self.run(rtl_code, tb_code, sim_stdout, sim_stderr, sim_error_message)
