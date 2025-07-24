import click
from abc import ABC, abstractmethod
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel
import logging
import os

logger = logging.getLogger("saxoflow_agenticai")

class BaseAgent(ABC):
    _LOG_COLORS = {
        "PROMPT SENT TO LLM": "blue",
        "LLM RESPONSE": "magenta",
        "REVIEW FEEDBACK": "yellow",
        "INFO": "green",
        "WARNING": "red"
    }

    def __init__(
        self,
        template_name: str,
        name: str = None,
        description: str = None,
        agent_type: str = None,
        verbose: bool = False,
        log_to_file: str = None,
        llm: BaseLanguageModel | None = None,
        **llm_kwargs
    ):
        """
        agent_type: Used for config. 
        llm: (Optional) Pass a LangChain LLM instance directly.
        llm_kwargs: Used to construct a default LLM if none provided.
        """
        self.name = name or self.__class__.__name__
        self.description = description or "No description provided."
        self.agent_type = agent_type or self.name.lower()
        self.verbose = verbose
        self.log_to_file = log_to_file

        self.llm = llm

        # Support direct PromptTemplate loading for each agent
        self.template_name = template_name
        self.prompt_templates = {}

        # Banner/log
        if self.log_to_file:
            with open(self.log_to_file, 'a') as f:
                import datetime
                f.write(f"\n\n========== NEW SESSION: {datetime.datetime.now()} ({self.name}) ==========\n")
        if self.llm: # Only log if LLM is present
            logger.info(f"[{self.name}] Using LLM: {type(self.llm).__name__}")

        if self.verbose and self.llm: # Only log if LLM is present and verbose
            click.secho(f"\n[{self.name}] Using LLM: {type(self.llm).__name__}\n", fg="green", bold=True)
            if self.log_to_file:
                with open(self.log_to_file, 'a') as f:
                    f.write(f"[{self.name}] Using LLM: {type(self.llm).__name__}\n")

    @abstractmethod
    def run(self, *args, **kwargs) -> str:
        pass

    def improve(self, *args, **kwargs) -> str:
        raise NotImplementedError(f"{self.name} has no improve() implemented.")

    def _log_block(self, title: str, content: str):
        color = self._LOG_COLORS.get(title, "white")
        header = f"\n========== [{self.name} | {title}] =========="
        footer = "\n" + "="*len(header)
        block = f"{header}\n{content.strip()}{footer}\n"
        click.secho(header, fg=color, bold=True)
        click.secho(content.strip(), fg=color)
        click.secho(footer + "\n", fg=color)
        if self.log_to_file:
            with open(self.log_to_file, 'a') as f:
                f.write(block)
                f.flush()

    def render_prompt(self, context: dict, template_name: str = None) -> str:
        """Render using LangChain PromptTemplate from file."""
        template_file = template_name if template_name else self.template_name
        if template_file not in self.prompt_templates:
            # Load and cache template
            template_path = os.path.join("prompts", template_file)
            with open(template_path, "r") as f:
                template_str = f.read()
            # Guess input variables from context
            self.prompt_templates[template_file] = PromptTemplate(
                input_variables=list(context.keys()),
                template=template_str
            )
        prompt = self.prompt_templates[template_file].format(**context)
        logger.debug(f"[{self.name}] Prompt rendered using template '{template_file}'")
        if self.verbose:
            self._log_block("PROMPT SENT TO LLM", prompt)
        return prompt

    def query_model(self, prompt: str) -> str:
        logger.info(f"[{self.name}] Querying model with prompt.")
        result = self.llm.invoke(prompt)
        result_str = str(result).strip() if result else ""
        if self.verbose:
            self._log_block("LLM RESPONSE", result_str)
        return result_str