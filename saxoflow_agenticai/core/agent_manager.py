# saxoflow_agenticai/core/agent_manager.py
"""
Agent factory/registry for SaxoFlow Agentic AI.

This module centralizes creation of agent instances by string key and wires up
the correct LLM per agent using the project-wide ModelSelector when an LLM is
not explicitly supplied by the caller.

Public API (kept stable):
- AgentManager.get_agent(agent_name: str, verbose: bool = False, llm = None, **kwargs)
- AgentManager.all_agent_names() -> list[str]

Additions (non-breaking):
- Clear exceptions and defensive logging
- Optional provider/model overrides via kwargs: 'provider', 'model_name'
  (they are consumed by the manager and NOT forwarded to the agent __init__)

Python: 3.9+
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List, Optional, Type

from saxoflow_agenticai.agents.generators.fprop_gen import FormalPropGenAgent
from saxoflow_agenticai.agents.generators.report_agent import ReportAgent
from saxoflow_agenticai.agents.generators.rtl_gen import RTLGenAgent
from saxoflow_agenticai.agents.generators.tb_gen import TBGenAgent
from saxoflow_agenticai.agents.reviewers.debug_agent import DebugAgent
from saxoflow_agenticai.agents.reviewers.fprop_review import FormalPropReviewAgent
from saxoflow_agenticai.agents.reviewers.rtl_review import RTLReviewAgent
from saxoflow_agenticai.agents.reviewers.tb_review import TBReviewAgent
from saxoflow_agenticai.agents.sim_agent import SimAgent
from saxoflow_agenticai.core.base_agent import BaseAgent
from saxoflow_agenticai.core.model_selector import ModelSelector

__all__ = ["AgentManager", "UnknownAgentError"]

logger = logging.getLogger("saxoflow_agenticai")


# -----------------
# Custom exceptions
# -----------------

class UnknownAgentError(ValueError):
    """Raised when an unknown agent key is requested."""


# --------------
# Agent registry
# --------------

class AgentManager:
    """
    Factory/registry for agent instances by string key.

    Supported agent keys
    --------------------
    - Generators: "rtlgen", "tbgen", "fpropgen", "report"
    - Reviewers : "rtlreview", "tbreview", "fpropreview", "debug"
    - Tools     : "sim" (non-LLM)

    Behavior
    --------
    If `llm` is not provided for LLM-driven agents, the correct model for
    `agent_name` is resolved from the project's model configuration using
    `ModelSelector.get_model(agent_type=agent_name)`.

    The "sim" agent does not use an LLM and is instantiated directly.

    Notes
    -----
    - To override the provider/model at call time (without editing YAML),
      you may pass kwargs: `provider="groq"`, `model_name="llama3-8b-8192"`.
      These override values are consumed by this manager and are NOT forwarded
      to the agent constructor.
    """

    AGENT_MAP: Dict[str, Type[BaseAgent]] = {
        "rtlgen": RTLGenAgent,
        "tbgen": TBGenAgent,
        "fpropgen": FormalPropGenAgent,
        "report": ReportAgent,
        "rtlreview": RTLReviewAgent,
        "tbreview": TBReviewAgent,
        "fpropreview": FormalPropReviewAgent,
        "debug": DebugAgent,
        "sim": SimAgent,
    }

    @staticmethod
    def _apply_quiet_defaults(cls: Type[BaseAgent], verbose: bool, ctor_kwargs: Dict[str, Any]) -> None:
        """
        Apply quiet/verbosity-related defaults to agent constructor kwargs,
        but only if the agent actually supports such parameters. This keeps
        behavior non-breaking while making agents quiet-by-default.
        """
        try:
            sig = inspect.signature(cls.__init__)
            params = sig.parameters
        except (TypeError, ValueError):  # pragma: no cover - very unlikely
            return

        # Prefer explicit caller-provided values if present.
        if not verbose:
            if "emit_stdout" in params and "emit_stdout" not in ctor_kwargs:
                ctor_kwargs["emit_stdout"] = False
            if "quiet" in params and "quiet" not in ctor_kwargs:
                ctor_kwargs["quiet"] = True
            if "silent" in params and "silent" not in ctor_kwargs:
                ctor_kwargs["silent"] = True
            if "log_level" in params and "log_level" not in ctor_kwargs:
                ctor_kwargs["log_level"] = logging.WARNING
        else:
            if "log_level" in params and "log_level" not in ctor_kwargs:
                ctor_kwargs["log_level"] = logging.INFO

        # Also downshift the module logger for the agent’s module when not verbose.
        agent_logger_name = cls.__module__
        agent_logger = logging.getLogger(agent_logger_name)
        agent_logger.setLevel(logging.INFO if verbose else logging.WARNING)

    @staticmethod
    def get_agent(
        agent_name: str,
        verbose: bool = False,
        llm: Any = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """
        Retrieve and construct an agent instance by name.

        Parameters
        ----------
        agent_name : str
            Key in the registry (see AGENT_MAP).
        verbose : bool
            If True, passed to the agent constructor for verbose logging.
        llm : Any
            Optional LangChain-compatible LLM instance. If None, an appropriate
            LLM is selected via ModelSelector for the given agent (except "sim").
        **kwargs : Any
            Extra keyword arguments forwarded to the agent constructor.
            Special-case overrides (consumed here, not forwarded):
              - provider   : Optional[str]  -> preferred provider key
              - model_name : Optional[str]  -> preferred concrete model name

        Returns
        -------
        BaseAgent
            An instance of the requested agent class.

        Raises
        ------
        UnknownAgentError
            If `agent_name` is not in the registry.
        RuntimeError
            If LLM resolution fails unexpectedly.
        """
        cls = AgentManager.AGENT_MAP.get(agent_name)
        if not cls:
            raise UnknownAgentError(f"Unknown agent: {agent_name}")

        # Extract optional provider/model overrides from kwargs (do NOT forward).
        provider_override: Optional[str] = kwargs.pop("provider", None)
        model_override: Optional[str] = kwargs.pop("model_name", None)

        if agent_name == "sim":
            # SimAgent does not use an LLM; ignore any provided `llm`.
            ctor_kwargs: Dict[str, Any] = {"verbose": verbose}
            ctor_kwargs.update(kwargs)
            AgentManager._apply_quiet_defaults(cls, verbose, ctor_kwargs)
            return cls(**ctor_kwargs)

        # Ensure we have an LLM instance; defer to ModelSelector when not supplied.
        resolved_llm = llm
        if resolved_llm is None:
            try:
                resolved_llm = ModelSelector.get_model(
                    agent_type=agent_name,
                    provider=provider_override,
                    model_name=model_override,
                )
            except Exception as exc:
                logger.error(
                    "Failed to resolve LLM for agent '%s' (provider=%r, model=%r): %s",
                    agent_name,
                    provider_override,
                    model_override,
                    exc,
                )
                raise

        # Construct the agent with the resolved LLM and remaining kwargs.
        try:
            ctor_kwargs = {"verbose": verbose, "llm": resolved_llm}
            ctor_kwargs.update(kwargs)
            AgentManager._apply_quiet_defaults(cls, verbose, ctor_kwargs)
            return cls(**ctor_kwargs)
        except TypeError as exc:
            # Helpful message if kwargs mismatch the agent's __init__ signature.
            raise RuntimeError(
                f"Failed to construct agent '{agent_name}' with kwargs {list(kwargs.keys())}: {exc}"
            ) from exc

    @staticmethod
    def all_agent_names() -> List[str]:
        """
        Return all valid agent keys in registration order.

        Returns
        -------
        list[str]
            The list of keys that `get_agent` accepts.
        """
        return list(AgentManager.AGENT_MAP.keys())
