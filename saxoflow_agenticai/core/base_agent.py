# saxoflow_agenticai/core/agent_base.py
"""
Base agent abstraction for SaxoFlow Agentic AI.

This module defines a reusable abstract base class (`BaseAgent`) for agents
that render prompts, call an LLM, and log I/O in a consistent, testable way.

Key features
------------
- Safe prompt rendering from a template file (cached after first use)
- Default templating via LangChain PromptTemplate
- Optional templating via Jinja2 (PromptManager) when `use_jinja=True` or
  the template file ends with `.j2`
- Pluggable LangChain LLM (`BaseLanguageModel`) with .invoke(...)
- Optional verbose, colorized console logging and file logging
- Defensive error handling with explicit exceptions
- Additive conveniences for LCEL runnables, structured outputs, and tools
  (kept optional to avoid breaking existing behavior)

Public API (kept stable)
------------------------
- class BaseAgent(ABC)
    - run(...) -> str (abstract)
    - improve(...) -> str (default raises NotImplementedError)
    - render_prompt(context: dict, template_name: Optional[str] = None) -> str
    - query_model(prompt: str) -> str

Python: 3.9+
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

import click
from langchain.prompts import PromptTemplate
from langchain_core.language_models import BaseLanguageModel

# Optional imports for extended LangChain usage (kept optional).
try:  # pragma: no cover - optional at runtime
    from langchain_core.runnables import Runnable
    from langchain_core.tools import BaseTool
    _HAS_LCEL = True
except Exception:  # pragma: no cover - keep import-safe
    _HAS_LCEL = False

try:  # pragma: no cover - optional at runtime
    from pydantic import BaseModel as _PydanticModel
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover
    _HAS_PYDANTIC = False

# Optional import of the Jinja2 wrapper. Only used when `use_jinja=True`
# or when the template filename ends with `.j2`.
try:  # pragma: no cover - optional at runtime
    from saxoflow_agenticai.core.prompt_manager import (
        PromptManager as _PromptManager,
        PromptRenderError as _PMRenderError,
    )
    _HAS_PROMPT_MANAGER = True
except Exception:  # pragma: no cover
    _HAS_PROMPT_MANAGER = False


__all__ = ["BaseAgent", "MissingLLMError", "TemplateNotFoundError", "PromptRenderError"]


# -----------------
# Module-level log
# -----------------

logger = logging.getLogger("saxoflow_agenticai")


# -----------------
# Custom exceptions
# -----------------

class MissingLLMError(RuntimeError):
    """Raised when an operation that needs an LLM is called without one."""


class TemplateNotFoundError(FileNotFoundError):
    """Raised when the referenced prompt template file cannot be found."""


class PromptRenderError(RuntimeError):
    """Raised when prompt rendering fails due to bad/missing variables."""


# ---------------
# Base agent class
# ---------------

class BaseAgent(ABC):
    """
    Abstract base class for SaxoFlow agents.

    Parameters
    ----------
    template_name : str
        Filename (relative to `prompt_dir`) of the template used by this agent.
    name : Optional[str]
        Logical agent name for logs (defaults to class name).
    description : Optional[str]
        Human-readable description (for registry/UX).
    agent_type : Optional[str]
        Key used by configuration (e.g., to resolve provider/model).
    verbose : bool
        If True, print colorized prompt/response blocks via `click`.
    log_to_file : Optional[str]
        Path to an append-only log file for this agent's sessions.
    llm : Optional[BaseLanguageModel]
        A LangChain LLM instance. If None, you can set it later.
        # TODO: (future) allow auto-initialization via ModelSelector if llm is None.
    prompt_dir : Optional[os.PathLike]
        Directory containing prompt templates. Defaults to:
        - env var `SAXOFLOW_PROMPT_DIR`, else
        - local "prompts" folder (relative to current working directory).
    use_jinja : bool, default False
        If True (or when the template file ends with ".j2"), render with Jinja2
        using PromptManager. Otherwise use LangChain PromptTemplate (default).
    prompt_manager : Optional[_PromptManager]
        Inject a preconfigured PromptManager (for advanced setups/testing).
    **llm_kwargs
        Currently unused. Kept for backward compatibility and a future
        auto-initialization path (see the TODO above).
    """

    # Color theme for verbose console logs.
    _LOG_COLORS: Dict[str, str] = {
        "PROMPT SENT TO LLM": "blue",
        "LLM RESPONSE": "magenta",
        "REVIEW FEEDBACK": "yellow",
        "INFO": "green",
        "WARNING": "red",
    }

    def __init__(
        self,
        template_name: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        agent_type: Optional[str] = None,
        verbose: bool = False,
        log_to_file: Optional[str] = None,
        llm: Optional[BaseLanguageModel] = None,
        prompt_dir: Optional[os.PathLike] = None,
        *,
        use_jinja: bool = False,
        prompt_manager: Optional["_PromptManager"] = None,  # type: ignore[name-defined]
        **llm_kwargs: Any,
    ) -> None:
        self.name: str = name or self.__class__.__name__
        self.description: str = description or "No description provided."
        self.agent_type: str = (agent_type or self.name).lower()
        self.verbose: bool = bool(verbose)
        self.log_to_file: Optional[str] = log_to_file
        self.llm: Optional[BaseLanguageModel] = llm

        # Prompt template handling
        self.template_name: str = template_name
        self.prompt_templates: Dict[str, PromptTemplate] = {}
        default_prompt_dir = os.getenv("SAXOFLOW_PROMPT_DIR", "prompts")
        self.prompt_dir: Path = Path(prompt_dir or default_prompt_dir)

        # Jinja2 (optional)
        self.use_jinja: bool = bool(use_jinja)
        self._prompt_manager: Optional["_PromptManager"] = (
            prompt_manager if _HAS_PROMPT_MANAGER else None  # type: ignore[name-defined]
        )

        # NOTE: llm_kwargs is currently unused to preserve behavior while keeping
        # room for future auto-construction via ModelSelector.
        # if self.llm is None and llm_kwargs:
        #     from saxoflow_agenticai.core.model_selector import ModelSelector  # lazy import
        #     self.llm = ModelSelector.get_model(agent_type=self.agent_type, **llm_kwargs)

        # Session banner
        if self.log_to_file:
            try:
                with open(self.log_to_file, "a", encoding="utf-8") as f:
                    from datetime import datetime
                    f.write(
                        "\n\n========== NEW SESSION: "
                        f"{datetime.now()} ({self.name}) ==========\n"
                    )
            except OSError as exc:  # pragma: no cover - file system error
                logger.warning("Failed to write session banner: %s", exc)

        if self.llm:
            logger.info("[%s] Using LLM: %s", self.name, type(self.llm).__name__)
            if self.verbose:
                click.secho(
                    f"\n[{self.name}] Using LLM: {type(self.llm).__name__}\n",
                    fg="green",
                    bold=True,
                )
                if self.log_to_file:
                    try:
                        with open(self.log_to_file, "a", encoding="utf-8") as f:
                            f.write(f"[{self.name}] Using LLM: {type(self.llm).__name__}\n")
                    except OSError as exc:  # pragma: no cover
                        logger.warning("Failed to write LLM banner: %s", exc)

    # -------------------
    # Abstract operations
    # -------------------

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> str:
        """Execute the agent's main task and return a textual result."""
        raise NotImplementedError

    # Keep improve() as a soft-contract; not all agents need a second pass.
    def improve(self, *args: Any, **kwargs: Any) -> str:
        """Optional improvement pass; default raises NotImplementedError."""
        raise NotImplementedError(f"{self.name} has no improve() implemented.")

    # --------------
    # Logging helpers
    # --------------

    def _log_block(self, title: str, content: str) -> None:
        """
        Print and optionally persist a formatted block for verbose inspection.

        The appearance is controlled by `_LOG_COLORS`. This method is used only
        when `verbose` is True in current code paths.
        """
        color = self._LOG_COLORS.get(title, "white")
        safe_content = (content or "").strip()
        header = f"\n========== [{self.name} | {title}] =========="
        footer = "\n" + "=" * len(header)
        block = f"{header}\n{safe_content}{footer}\n"

        try:
            click.secho(header, fg=color, bold=True)
            click.secho(safe_content, fg=color)
            click.secho(footer + "\n", fg=color)
        except Exception:  # pragma: no cover - very defensive
            logger.debug("click.secho failed; falling back to plain logs.")
            logger.info(block)

        if self.log_to_file:
            try:
                with open(self.log_to_file, "a", encoding="utf-8") as f:
                    f.write(block)
                    f.flush()
            except OSError as exc:  # pragma: no cover
                logger.warning("Failed writing log block: %s", exc)

    # -------------------
    # Prompt construction
    # -------------------

    def render_prompt(self, context: Dict[str, Any], template_name: Optional[str] = None) -> str:
        """
        Render a prompt string from a template file and the given context.

        Behavior
        --------
        - If `use_jinja` is True OR the template file ends with ".j2", render via
          PromptManager (Jinja2).
        - Otherwise, render via LangChain PromptTemplate (current default path).

        Parameters
        ----------
        context : Dict[str, Any]
            Variables to render into the template.
        template_name : Optional[str]
            If provided, overrides `self.template_name` for this call.

        Returns
        -------
        str
            The fully rendered prompt string.

        Raises
        ------
        TemplateNotFoundError
            If the template file cannot be found.
        PromptRenderError
            If the context cannot satisfy the template variables or Jinja errors.
        """
        template_file = template_name or self.template_name

        # Choose engine: Jinja (opt-in or .j2) vs LangChain PromptTemplate (default)
        use_jinja = self.use_jinja or str(template_file).lower().endswith(".j2")

        if use_jinja:
            if not _HAS_PROMPT_MANAGER:
                # Friendly message if the wrapper is unavailable.
                raise PromptRenderError(
                    "PromptManager (Jinja2) is not available. Ensure "
                    "`saxoflow_agenticai.core.prompt_manager` is present and importable."
                )

            # Lazily create a PromptManager if not injected.
            if self._prompt_manager is None:
                self._prompt_manager = _PromptManager(template_dir=self.prompt_dir)

            try:
                rendered = self._prompt_manager.render(template_file, context)
            except FileNotFoundError as exc:
                raise TemplateNotFoundError(str(exc)) from exc
            except _PMRenderError as exc:  # type: ignore[name-defined]
                raise PromptRenderError(str(exc)) from exc
            except Exception as exc:  # pragma: no cover
                raise PromptRenderError(
                    f"Unexpected error rendering Jinja template '{template_file}': {exc}"
                ) from exc

            logger.debug("[%s] Prompt rendered via Jinja '%s'", self.name, template_file)
            if self.verbose:
                self._log_block("PROMPT SENT TO LLM", rendered)
            return rendered

        # Default: LangChain PromptTemplate path (existing behavior)
        template_path = self.prompt_dir / template_file

        if template_file not in self.prompt_templates:
            # Load and cache the template (first use)
            if not template_path.exists():
                raise TemplateNotFoundError(
                    f"Prompt template not found: {template_path}"
                )
            try:
                template_str = template_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise TemplateNotFoundError(
                    f"Failed to read template: {template_path}"
                ) from exc

            # Infer input variables from provided context. If the file requires
            # variables not in `context`, PromptTemplate.format will raise.
            self.prompt_templates[template_file] = PromptTemplate(
                input_variables=list(context.keys()),
                template=template_str,
            )

        try:
            prompt = self.prompt_templates[template_file].format(**context)
        except Exception as exc:
            # NOTE: We intentionally keep the exception broad here to include
            # KeyError (missing variables) and ValueError (format issues).
            raise PromptRenderError(
                f"Failed to render prompt using template '{template_file}': {exc}"
            ) from exc

        logger.debug("[%s] Prompt rendered via LangChain '%s'", self.name, template_file)
        if self.verbose:
            self._log_block("PROMPT SENT TO LLM", prompt)
        return prompt

    # --------------
    # LLM invocation
    # --------------

    def query_model(self, prompt: str) -> str:
        """
        Invoke the configured LLM with a string prompt and return text output.

        This retains the project's existing behavior: a single .invoke(prompt)
        call and a string result. If the underlying LangChain LLM returns a
        message object (e.g., AIMessage), we extract `.content` when present.

        Raises
        ------
        MissingLLMError
            If `self.llm` is not set.
        """
        if self.llm is None:
            raise MissingLLMError(
                f"{self.name} has no LLM configured. "
                "Pass an llm=... at construction time "
                "or wire ModelSelector.get_model(...) before calling query_model()."
            )

        logger.info("[%s] Querying model with prompt.", self.name)
        try:
            result = self.llm.invoke(prompt)
        except Exception as exc:  # pragma: no cover - provider/network failure
            # TODO: consider retries at the call site using LangChain's Runnable.retry
            raise RuntimeError(f"Model invocation failed in '{self.name}': {exc}") from exc

        result_str = self._extract_text(result)
        if self.verbose:
            self._log_block("LLM RESPONSE", result_str)
        return result_str

    @staticmethod
    def _extract_text(result: Any) -> str:
        """
        Best-effort conversion of various LangChain result objects to plain text.
        """
        # Many Chat models return an AIMessage with a .content attribute.
        content = getattr(result, "content", None)
        if isinstance(content, str):
            return content.strip()

        # Some LLMs might return a dataclass with `.text` or raw strings.
        text = getattr(result, "text", None)
        if isinstance(text, str):
            return text.strip()

        if isinstance(result, str):
            return result.strip()

        # Fallback: stringification (kept to preserve "some output" principle).
        return str(result).strip()

    # --------------------------------------------------------
    # Optional: best-practice LangChain helpers (kept additive)
    # --------------------------------------------------------

    # NOTE: The methods below are conveniences for LCEL usage.
    # They are NOT used by existing code paths and are kept to extend
    # agents incrementally without breaking current behavior. If `langchain_core`
    # Runnable / tools are unavailable, we raise clear guidance.

    def build_runnable(
        self,
        *,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Return a Runnable for this agent's LLM with LangSmith tags/metadata.

        Usage (opt-in):
            r = agent.build_runnable(tags=["rtlgen"])
            text = r.invoke("Hello")

        Raises
        ------
        MissingLLMError
            If `self.llm` is not set.
        RuntimeError
            If LCEL is unavailable in the environment.
        """
        if self.llm is None:
            raise MissingLLMError(f"{self.name} has no LLM configured.")
        if not _HAS_LCEL:
            raise RuntimeError(
                "LangChain LCEL is not available. "
                "Install langchain-core>=0.2 to use build_runnable()."
            )

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)
        # Returning llm.with_config preserves the simple .invoke/.stream API.
        return self.llm.with_config(config)

    def build_structured(
        self,
        schema: Any,
        *,
        strict: bool = True,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Return a Runnable enforcing structured output.

        If `schema` is a Pydantic model class, use `with_structured_output`.
        Otherwise, bind JSON mode (response_format={"type":"json_object"}).

        Raises
        ------
        MissingLLMError
            If `self.llm` is not set.
        RuntimeError
            If Pydantic or LCEL is unavailable and schema is a Pydantic class.
        """
        if self.llm is None:
            raise MissingLLMError(f"{self.name} has no LLM configured.")
        if not _HAS_LCEL:
            raise RuntimeError(
                "LangChain LCEL is not available. "
                "Install langchain-core>=0.2 to use build_structured()."
            )

        runnable = None
        if _HAS_PYDANTIC and isinstance(schema, type) and issubclass(schema, _PydanticModel):
            try:
                runnable = self.llm.with_structured_output(schema=schema, strict=strict)
            except Exception as exc:  # pragma: no cover
                # Fall back to JSON mode if provider doesn't support structured output.
                logger.debug("with_structured_output not supported, falling back: %s", exc)
                runnable = self.llm.bind(response_format={"type": "json_object"})
        else:
            runnable = self.llm.bind(response_format={"type": "json_object"})

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)
        return runnable.with_config(config)

    def build_with_tools(
        self,
        tools: Sequence["BaseTool"],  # quoted to avoid import when tools unused
        *,
        tool_choice: Optional[str] = None,  # "auto" | "none" | specific name (if provider supports)
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """
        Return a Runnable configured for tool calling (function calling).

        Raises
        ------
        MissingLLMError
            If `self.llm` is not set.
        RuntimeError
            If LCEL is unavailable in the environment.
        """
        if self.llm is None:
            raise MissingLLMError(f"{self.name} has no LLM configured.")
        if not _HAS_LCEL:
            raise RuntimeError(
                "LangChain LCEL is not available. "
                "Install langchain-core>=0.2 to use build_with_tools()."
            )

        runnable = self.llm.bind_tools(tools)
        if tool_choice:
            # Not all providers honor `tool_choice`; bind it if provided.
            runnable = runnable.bind(tool_choice=tool_choice)

        config: Dict[str, Any] = {}
        if tags:
            config["tags"] = list(tags)
        if metadata:
            config["metadata"] = dict(metadata)
        return runnable.with_config(config)
