# saxoflow/teach/agent_dispatcher.py
"""
Agent dispatcher for the SaxoFlow tutoring subsystem.

Provides a thin, testable adapter between step ``agent_invocations`` YAML
declarations and the ``AgentManager`` factory.

Architecture contract
---------------------
- This is the **only** file in ``saxoflow/teach/`` that imports from
  ``saxoflow_agenticai``.
- Every agent invocation goes through :func:`dispatch_agent` — never by
  calling ``AgentManager.get_agent()`` directly from a step runner.
- Results are stored in ``session.agent_results`` keyed by step ID.

Python: 3.9+
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from saxoflow.teach.session import AgentInvocationDef, TeachSession

__all__ = ["dispatch_agent", "dispatch_step_agents", "AgentDispatchError"]

logger = logging.getLogger("saxoflow.teach.agent_dispatcher")


class AgentDispatchError(RuntimeError):
    """Raised when an agent invocation fails unrecoverably."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def dispatch_step_agents(
    session: TeachSession,
    verbose: bool = False,
) -> List[str]:
    """Execute all ``agent_invocations`` for the current step in order.

    Results are stored in ``session.agent_results[step.id]`` as a list
    of (agent_key, result) tuples.

    Parameters
    ----------
    session:
        Active :class:`~saxoflow.teach.session.TeachSession`.
    verbose:
        Passed through to ``AgentManager.get_agent()``.

    Returns
    -------
    list[str]
        Agent result strings, one per invocation.  Empty if the step has
        no agent invocations.
    """
    step = session.current_step
    if step is None or not step.agent_invocations:
        return []

    results: List[str] = []
    for inv in step.agent_invocations:
        try:
            result = dispatch_agent(inv, verbose=verbose)
            session.store_agent_result(step.id, result)
            results.append(result)
        except AgentDispatchError as exc:
            logger.error("Agent invocation failed: %s", exc)
            err_str = f"[Agent error: {exc}]"
            session.store_agent_result(step.id, err_str)
            results.append(err_str)

    return results


def dispatch_agent(
    inv: AgentInvocationDef,
    verbose: bool = False,
) -> str:
    """Invoke one agent and return its result string.

    Parameters
    ----------
    inv:
        The :class:`~saxoflow.teach.session.AgentInvocationDef` from the
        lesson step YAML.
    verbose:
        Passed to ``AgentManager.get_agent()``.

    Returns
    -------
    str
        The agent's string output.

    Raises
    ------
    AgentDispatchError
        When the agent key is unknown or agent execution raises.
    """
    # Lazy import to keep saxoflow/teach free of hard dependency at import time.
    try:
        from saxoflow_agenticai.core.agent_manager import AgentManager, UnknownAgentError  # noqa: PLC0415
    except ImportError as exc:
        raise AgentDispatchError(
            f"Could not import AgentManager: {exc}"
        ) from exc

    try:
        agent = AgentManager.get_agent(
            inv.agent_key, verbose=verbose, **inv.args
        )
    except UnknownAgentError as exc:
        raise AgentDispatchError(str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise AgentDispatchError(
            f"Failed to construct agent '{inv.agent_key}': {exc}"
        ) from exc

    try:
        result = agent.run(**inv.args)
        return str(result)
    except Exception as exc:
        raise AgentDispatchError(
            f"Agent '{inv.agent_key}' raised during run(): {exc}"
        ) from exc
