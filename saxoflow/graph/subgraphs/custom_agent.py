"""Custom-agent graph template with capability allowlist enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from saxoflow.services.policy_service import AgentCapabilityRoutingPolicy
from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry
from saxoflow_agenticai.core.custom_agent_loader import (
    CustomAgentDefinition,
    CustomAgentLoadError,
    load_custom_agent_mapping,
)


class CustomAgentGraphError(ValueError):
    """Raised when custom-agent graph payloads are invalid or disallowed."""


def _normalize_requested_capabilities(raw: Any) -> Tuple[str, ...]:
    if raw is None:
        return tuple()
    if not isinstance(raw, (list, tuple)):
        raise CustomAgentGraphError("Requested capabilities must be a list of strings.")

    normalized = []
    for entry in raw:
        if not isinstance(entry, str) or not entry.strip():
            raise CustomAgentGraphError("Requested capabilities must contain non-empty strings.")
        normalized.append(entry.strip())

    return tuple(dict.fromkeys(normalized))


def _effective_allowlist(definition: CustomAgentDefinition) -> Tuple[str, ...]:
    denied = set(definition.tools_deny)
    allowed = [capability for capability in definition.tools_allow if capability not in denied]
    return tuple(dict.fromkeys(allowed))


def resolve_custom_agent_capabilities(
    definition: CustomAgentDefinition,
    requested_capabilities: Iterable[str] | None,
    *,
    policy_approved_capabilities: Tuple[str, ...] = tuple(),
) -> Tuple[str, ...]:
    """Resolve capabilities for one invocation and enforce custom-agent allowlist."""
    allowed = _effective_allowlist(definition)
    if not requested_capabilities:
        return allowed

    requested = tuple(dict.fromkeys(str(item).strip() for item in requested_capabilities if str(item).strip()))
    blocked = [capability for capability in requested if capability not in allowed]
    if blocked:
        blocked_csv = ", ".join(sorted(set(blocked)))
        raise CustomAgentGraphError(
            f"Custom agent `{definition.name}` denied requested capabilities: {blocked_csv}"
        )

    return AgentToolRegistry.builtins().intersect_with_allowlist_and_policy(
        requested_capabilities=requested,
        allowed_capabilities=allowed,
        policy_approved_capabilities=policy_approved_capabilities,
    )


@dataclass(frozen=True)
class CustomAgentGraphTemplate:
    """Graph-callable template that validates custom-agent capability constraints."""

    def invoke(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        raw_agent = payload.get("custom_agent")
        if isinstance(raw_agent, CustomAgentDefinition):
            definition = raw_agent
        elif isinstance(raw_agent, Mapping):
            try:
                definition = load_custom_agent_mapping(raw_agent)
            except CustomAgentLoadError as exc:
                raise CustomAgentGraphError(str(exc)) from exc
        else:
            raise CustomAgentGraphError(
                "Custom-agent graph payload missing `custom_agent` mapping/definition."
            )

        policy_map = payload.get("capability_policy")
        if policy_map is not None and not isinstance(policy_map, Mapping):
            raise CustomAgentGraphError("Custom-agent graph `capability_policy` must be a mapping.")
        policy = AgentCapabilityRoutingPolicy(
            approved_capabilities=tuple((policy_map or {}).get("approved_capabilities") or ())
        )

        requested = _normalize_requested_capabilities(payload.get("requested_capabilities"))
        policy_decision = policy.evaluate(requested)
        selected = resolve_custom_agent_capabilities(
            definition,
            requested,
            policy_approved_capabilities=policy_decision.approved_capabilities,
        )

        return {
            "status": "ready",
            "agent_name": definition.name,
            "graph_template": definition.graph_template,
            "selected_capabilities": list(selected),
            "allowlist": list(_effective_allowlist(definition)),
            "requested_capabilities": list(requested),
            "policy_capabilities": policy_decision.to_dict(),
        }
