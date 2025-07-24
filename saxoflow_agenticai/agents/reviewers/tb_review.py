import os
import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger  # Use colored logger

def load_prompt_from_pkg(filename):
    # Robustly load prompt file relative to project root
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

def _extract_review_content(result):
    if isinstance(result, dict) and 'content' in result:
        return result['content']
    return str(result)

def extract_structured_review(text: str) -> str:
    # Remove LLM metadata and code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"AIMessage\(content=|additional_kwargs=.*|\bresponse_metadata=.*|usage_metadata=.*|id='[^']+'", "", text)
    text = re.sub(r"Here is the feedback on the testbench code:|Here is the output feedback for the provided testbench:|Here is the output feedback:", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\*\*", "", text)  # Remove bold

    # List all canonical headings you care about:
    headings = [
        "Instantiation Issues",
        "Signal Declaration Issues",
        "Stimulus Issues",
        "Coverage Gaps",
        "Randomization Usage",
        "Corner Case Suggestions",
        "Output Checking Suggestions",
        "Waveform/Monitoring Suggestions",
        "Standards Compliance Issues",
        "Overall Comments"
    ]

    # Make a pattern that matches each heading followed by a colon
    pattern = r"(?P<heading>" + "|".join([re.escape(h) for h in headings]) + r")\s*:\s*\n?"
    splits = [(m.group('heading'), m.start()) for m in re.finditer(pattern, text, re.IGNORECASE)]
    sections = {}

    # Append a dummy split for the end of the text
    splits.append(("End", len(text)))
    for i in range(len(splits) - 1):
        heading = splits[i][0]
        start = splits[i][1]
        end = splits[i+1][1]
        # Move past the matched heading
        after_heading = re.search(pattern, text[start:], re.IGNORECASE)
        if after_heading:
            content_start = start + after_heading.end()
        else:
            content_start = start
        content = text[content_start:end].strip()
        # Remove all \n, flatten spaces
        content = content.replace("\\n", " ").replace("\n", " ")
        content = re.sub(r"[\s\-*]+\s*", " ", content)
        content = re.sub(r"\s+", " ", content).strip(" .:;-")
        if not content or content.lower() in ["none", "-", "--"]:
            content = "None"
        sections[heading] = content

    # Output each heading with its content, in canonical order, double newlines between
    lines = []
    for h in headings:
        lines.append(f"{h}: {sections.get(h, 'None')}")
    return "\n\n".join(lines)


# Load the prompt template from file at startup (recommended for production)
tbreview_prompt_template = PromptTemplate(
    input_variables=["testbench_code", "spec", "rtl_code"],
    template=load_prompt_from_pkg("tbreview_prompt.txt"),
    template_format="jinja2"
)

class TBReviewAgent:
    agent_type = "tbreview"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="tbreview")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str, top_module_name: str, testbench_code: str) -> str:
        """
        Full compatible signature: (spec, rtl_code, top_module_name, testbench_code)
        (top_module_name is ignored, kept for interface compatibility)
        """
        prompt = tbreview_prompt_template.format(
            testbench_code=testbench_code,
            spec=spec,
            rtl_code=rtl_code
        )
        if self.verbose:
            self.logger.info("Rendered prompt for TB review:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Raw LLM review output:\n" + repr(result))
        review_text = _extract_review_content(result)
        if not review_text or not review_text.strip():
            self.logger.warning("LLM returned empty review. Using fallback critique report.")
            review_text = (
                "Instantiation Issues: None\n"
                "Stimulus Issues: None\n"
                "Coverage Gaps: None\n"
                "Randomization Usage: None\n"
                "Corner Case Suggestions: None\n"
                "Assertions & Checking Suggestions: None\n"
                "Monitoring & Debug Suggestions: None\n"
                "Overall Comments: No major issues found."
            )
        else:
            review_text = extract_structured_review(review_text)
        self.logger.info("Cleaned TB review output:\n" + review_text.strip())
        return review_text.strip()

    def improve(self, spec: str, rtl_code: str, top_module_name: str, testbench_code: str, feedback: str) -> str:
        """
        Feedback-compatible improve interface. feedback is ignored, included for interface consistency.
        """
        self.logger.info("Re-running testbench review with feedback context (if any).")
        return self.run(spec, rtl_code, top_module_name, testbench_code)
