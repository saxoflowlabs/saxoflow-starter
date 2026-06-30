"""Agent tool capability registry with safety metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Tuple


class AgentToolRegistryError(ValueError):
    """Raised when requested agent tool capabilities are malformed or unknown."""


DEFAULT_AGENT_TOOL_CAPABILITIES: Mapping[str, Mapping[str, Any]] = {
    "context.read": {"risk_level": "low", "approval_required": False},
    "file.read": {"risk_level": "low", "approval_required": False},
    "artifact.read": {"risk_level": "low", "approval_required": False},
    "report.read": {"risk_level": "low", "approval_required": False},
    "file.edit": {"risk_level": "medium", "approval_required": True},
    "file.write": {"risk_level": "high", "approval_required": True},
    "file.delete": {"risk_level": "high", "approval_required": True},
    "artifact.write": {"risk_level": "medium", "approval_required": True},
    "eda.run": {"risk_level": "high", "approval_required": True},
    "test.run": {"risk_level": "high", "approval_required": True},
    "web.search": {"risk_level": "medium", "approval_required": True},
    "web.fetch": {"risk_level": "medium", "approval_required": True},
}


@dataclass(frozen=True)
class AgentToolRegistry:
    """Registry API for capability metadata and requested capability validation."""

    capabilities: Mapping[str, Mapping[str, Any]]

    @classmethod
    def builtins(cls) -> "AgentToolRegistry":
        return cls(capabilities=DEFAULT_AGENT_TOOL_CAPABILITIES)

    def resolve_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """Return deterministic metadata for all registered capabilities."""
        resolved: Dict[str, Dict[str, Any]] = {}
        for capability, meta in self.capabilities.items():
            risk = str(meta.get("risk_level") or "medium").strip().lower()
            if risk not in {"low", "medium", "high"}:
                raise AgentToolRegistryError(
                    f"Capability `{capability}` has invalid risk_level `{risk}`."
                )
            resolved[capability] = {
                "capability": capability,
                "risk_level": risk,
                "approval_required": bool(meta.get("approval_required", False)),
                "registration_source": "built-in",
            }
        return resolved

    def get_capability_metadata(self, capability: str) -> Dict[str, Any]:
        """Return metadata for one capability."""
        metadata = self.resolve_tool_registry().get(capability)
        if metadata is None:
            known = ", ".join(sorted(self.capabilities.keys()))
            raise AgentToolRegistryError(
                f"Unknown capability `{capability}`. Known: {known}"
            )
        return metadata

    def validate_capability_name(self, capability: str) -> str:
        """Validate one capability name and return the normalized value."""
        if not isinstance(capability, str) or not capability.strip():
            raise AgentToolRegistryError("Capability names must be non-empty strings.")

        normalized = capability.strip()
        self.get_capability_metadata(normalized)
        return normalized

    def validate_capability_names(self, capabilities: Any) -> Tuple[str, ...]:
        """Validate and normalize a capability name list."""
        if capabilities is None:
            return tuple()
        if not isinstance(capabilities, (list, tuple)):
            raise AgentToolRegistryError("Capability names must be a list of strings.")

        normalized = [self.validate_capability_name(item) for item in capabilities]
        return tuple(dict.fromkeys(normalized))

    def validate_requested_capabilities(self, requested: Any) -> Tuple[str, ...]:
        """Validate and normalize a requested capability subset."""
        if requested is None:
            return tuple()
        if not isinstance(requested, (list, tuple)):
            raise AgentToolRegistryError(
                "Requested capabilities must be a list of capability names."
            )

        known = self.resolve_tool_registry()
        normalized = []
        for entry in requested:
            if not isinstance(entry, str) or not entry.strip():
                raise AgentToolRegistryError(
                    "Requested capabilities must contain non-empty strings."
                )
            capability = entry.strip()
            if capability not in known:
                known_names = ", ".join(sorted(known.keys()))
                raise AgentToolRegistryError(
                    f"Unknown capability `{capability}`. Known: {known_names}"
                )
            normalized.append(capability)

        # Keep deterministic request order while removing duplicates.
        return tuple(dict.fromkeys(normalized))

    def intersect_with_allowlist_and_policy(
        self,
        *,
        requested_capabilities: Tuple[str, ...],
        allowed_capabilities: Tuple[str, ...],
        policy_approved_capabilities: Tuple[str, ...] = tuple(),
    ) -> Tuple[str, ...]:
        """Return requested capabilities bounded by allowlist and optional policy approvals."""
        requested = tuple(dict.fromkeys(str(item).strip() for item in requested_capabilities if str(item).strip()))
        allowed = tuple(dict.fromkeys(str(item).strip() for item in allowed_capabilities if str(item).strip()))
        allowed_set = set(allowed)

        bounded = tuple(capability for capability in requested if capability in allowed_set)
        if not policy_approved_capabilities:
            return bounded

        approved = tuple(
            dict.fromkeys(
                str(item).strip() for item in policy_approved_capabilities if str(item).strip()
            )
        )
        approved_set = set(approved)
        return tuple(capability for capability in bounded if capability in approved_set)
