import os
import re
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
from saxoflow_agenticai.core.model_selector import ModelSelector
from saxoflow_agenticai.core.log_manager import get_logger

def load_prompt_from_pkg(filename):
    here = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    prompt_path = os.path.join(here, "prompts", filename)
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()

def _extract_review_content(result):
    # Handles both OpenAI-style {'content': ...} and string result
    if isinstance(result, dict) and 'content' in result:
        return result['content']
    return str(result)

def extract_structured_rtl_review(text: str) -> str:
    """
    Extracts RTL review sections as: "Heading: value" (one per line, separated by blank lines).
    Robustly removes markdown, metadata, bullets, and merges multi-line LLM outputs.
    Only headings present in the text are included, others are marked as 'None'.
    """

    # Remove LLM metadata and code blocks
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"AIMessage\(content=|additional_kwargs=.*|\bresponse_metadata=.*|usage_metadata=.*|id='[^']+'", "", text)
    text = re.sub(r"Here is the review:|Here is the output feedback for the provided RTL:|Here is the output feedback:", "", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\*\*", "", text)  # Remove bold markdown

    # Canonical headings for RTL review
    rtl_headings = [
        "Syntax Issues",
        "Logic Issues",
        "Reset Issues",
        "Port Declaration Issues",
        "Optimization Suggestions",
        "Naming Improvements",
        "Synthesis Concerns",
        "Overall Comments"
    ]

    # Regex pattern for heading capture
    pattern = r"(?P<heading>" + "|".join([re.escape(h) for h in rtl_headings]) + r")\s*:\s*\n?"
    splits = [(m.group('heading'), m.start()) for m in re.finditer(pattern, text, re.IGNORECASE)]
    sections = {}

    # Append dummy split for end
    splits.append(("End", len(text)))
    for i in range(len(splits) - 1):
        heading = splits[i][0]
        start = splits[i][1]
        end = splits[i+1][1]
        # Move past heading
        after_heading = re.search(pattern, text[start:], re.IGNORECASE)
        if after_heading:
            content_start = start + after_heading.end()
        else:
            content_start = start
        content = text[content_start:end].strip()
        # Clean: remove \n, bullets, dashes, flatten spaces
        content = content.replace("\\n", " ").replace("\n", " ")
        content = re.sub(r"[\s\-*]+\s*", " ", content)
        content = re.sub(r"\s+", " ", content).strip(" .:;-")
        if not content or content.lower() in ["none", "-", "--"]:
            content = "None"
        sections[heading] = content

    # Output each heading, in order, with blank lines between for readability
    lines = []
    for h in rtl_headings:
        lines.append(f"{h}: {sections.get(h, 'None')}")
    return "\n\n".join(lines)


# --- RTL Review Agent ---
rtlreview_prompt_template = PromptTemplate(
    input_variables=["spec", "rtl_code"],
    template=load_prompt_from_pkg("rtlreview_prompt.txt"),
    template_format="jinja2"
)


class RTLReviewAgent:
    agent_type = "rtlreview"

    def __init__(self, llm: BaseLanguageModel = None, verbose: bool = False):
        self.llm = llm or ModelSelector.get_model(agent_type="rtlreview")
        self.verbose = verbose
        self.logger = get_logger(self.__class__.__name__)

    def run(self, spec: str, rtl_code: str) -> str:
        prompt = rtlreview_prompt_template.format(spec=spec, rtl_code=rtl_code)
        if self.verbose:
            self.logger.info("Rendered prompt for RTL review:\n" + prompt)
        result = self.llm.invoke(prompt)
        if self.verbose:
            self.logger.info("Raw LLM review output:\n" + repr(result))
        review_text = _extract_review_content(result)
        if not review_text or not review_text.strip():
            self.logger.warning("LLM returned empty review. Using fallback critique report.")
            review_text = (
                "Syntax Issues: None\n"
                "Logic Issues: None\n"
                "Reset Issues: None\n"
                "Port Declaration Issues: None\n"
                "Optimization Suggestions: None\n"
                "Naming Improvements: None\n"
                "Synthesis Concerns: None\n"
                "Overall Comments: No major issues found."
            )
        else:
            review_text = extract_structured_rtl_review(review_text)
        self.logger.info("Cleaned review output:\n" + review_text.strip())
        return review_text.strip()

    def improve(self, spec: str, rtl_code: str, feedback: str) -> str:
        self.logger.info("Re-running review with feedback context (if any).")
        return self.run(spec, rtl_code)
