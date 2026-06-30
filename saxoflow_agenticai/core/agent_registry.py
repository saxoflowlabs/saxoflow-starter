"""Agent registry helpers for built-in and user-defined profile contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple


class AgentRegistryError(ValueError):
    """Raised when a user-defined agent profile is malformed."""


DEFAULT_GENERAL_PURPOSE_PROFILE: Mapping[str, Any] = {
    "profile_name": "general-purpose",
    "role": "general-purpose",
    "role_type": "generic",
    "capability_tags": ("context.read", "file.read", "artifact.read", "report.read"),
}


DEFAULT_BUILTIN_AGENT_METADATA: Mapping[str, Mapping[str, Any]] = {
    "rtlgen": {
        "role": "generator",
        "role_type": "domain",
        "capability_tags": ("code.generate", "rtl.generate", "structured_output"),
    },
    "tbgen": {
        "role": "generator",
        "role_type": "domain",
        "capability_tags": ("code.generate", "testbench.generate", "structured_output"),
    },
    "fpropgen": {
        "role": "generator",
        "role_type": "domain",
        "capability_tags": ("formal.generate", "structured_output"),
    },
    "report": {
        "role": "generator",
        "role_type": "generic",
        "capability_tags": ("report.generate", "artifact.read", "structured_output"),
    },
    "rtlreview": {
        "role": "reviewer",
        "role_type": "domain",
        "capability_tags": ("rtl.review", "diagnostics.emit"),
    },
    "tbreview": {
        "role": "reviewer",
        "role_type": "domain",
        "capability_tags": ("testbench.review", "diagnostics.emit"),
    },
    "fpropreview": {
        "role": "reviewer",
        "role_type": "domain",
        "capability_tags": ("formal.review", "diagnostics.emit"),
    },
    "debug": {
        "role": "reviewer",
        "role_type": "generic",
        "capability_tags": ("debug.analyze", "diagnostics.emit"),
    },
    "sim": {
        "role": "tool",
        "role_type": "domain",
        "capability_tags": ("eda.run", "simulation.run"),
    },
    "synth": {
        "role": "tool",
        "role_type": "domain",
        "capability_tags": ("eda.run", "synthesis.run"),
    },
    "pnr": {
        "role": "tool",
        "role_type": "domain",
        "capability_tags": ("eda.run", "pnr.run"),
    },
    "tutor": {
        "role": "tutor",
        "role_type": "generic",
        "capability_tags": ("context.read", "teach.explain"),
    },
}


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentRegistryError(f"Agent profile field `{field_name}` must be a mapping.")
    return dict(value)


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise AgentRegistryError(
            f"Agent profile field `{field_name}` must be a non-empty string when set."
        )
    return value.strip()


def _normalize_capability_tags(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, (list, tuple)):
        raise AgentRegistryError(
            f"Agent profile field `{field_name}` must be a list of capability strings."
        )
    normalized = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AgentRegistryError(
                f"Agent profile field `{field_name}` entries must be non-empty strings."
            )
        normalized.append(item.strip())
    return tuple(dict.fromkeys(normalized))


def _normalize_builtin_metadata(agent_name: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
    role = _optional_string(payload.get("role"), f"builtin_agents.{agent_name}.role")
    role_type = _optional_string(payload.get("role_type"), f"builtin_agents.{agent_name}.role_type")
    capability_tags = _normalize_capability_tags(
        payload.get("capability_tags"),
        f"builtin_agents.{agent_name}.capability_tags",
    )
    if not capability_tags:
        raise AgentRegistryError(
            f"Built-in agent `{agent_name}` must include at least one capability tag."
        )
    return {
        "agent_name": agent_name,
        "role": role or "generic",
        "role_type": role_type or "generic",
        "capability_tags": list(capability_tags),
        "registration_source": "built-in",
    }


@dataclass(frozen=True)
class AgentRegistry:
    """Resolve built-in and user-defined agent profile contracts."""

    user_profiles: Mapping[str, Mapping[str, Any]]

    @classmethod
    def from_mapping(cls, raw_profiles: Optional[Mapping[str, Any]]) -> "AgentRegistry":
        if raw_profiles is None:
            return cls(user_profiles={})
        profiles = _as_mapping(raw_profiles, "agent_profiles")
        normalized: Dict[str, Dict[str, Any]] = {}
        for profile_name, payload in profiles.items():
            normalized_name = _optional_string(profile_name, "agent_profiles profile name")
            assert normalized_name is not None
            normalized[normalized_name] = _as_mapping(
                payload,
                f"agent_profiles.{normalized_name}",
            )
        return cls(user_profiles=normalized)

    def resolve_general_purpose_profile(self) -> Dict[str, Any]:
        """Return the active general-purpose profile with replacement metadata."""
        default = dict(DEFAULT_GENERAL_PURPOSE_PROFILE)
        default_caps = tuple(default["capability_tags"])
        override = self.user_profiles.get("general-purpose")
        if override is None:
            return {
                "profile_name": "general-purpose",
                "role": str(default["role"]),
                "role_type": str(default["role_type"]),
                "capability_tags": list(default_caps),
                "replacement_source": "built-in",
                "replaced_builtin": False,
            }

        role = _optional_string(override.get("role"), "agent_profiles.general-purpose.role")
        role_type = _optional_string(
            override.get("role_type"),
            "agent_profiles.general-purpose.role_type",
        )
        capability_tags = _normalize_capability_tags(
            override.get("capability_tags"),
            "agent_profiles.general-purpose.capability_tags",
        )
        if not capability_tags:
            raise AgentRegistryError(
                "Agent profile `general-purpose` must include at least one capability tag."
            )

        return {
            "profile_name": "general-purpose",
            "role": role or str(default["role"]),
            "role_type": role_type or str(default["role_type"]),
            "capability_tags": list(capability_tags),
            "replacement_source": "user-defined",
            "replaced_builtin": True,
        }

    def resolve_builtin_agent_registry(self) -> Dict[str, Dict[str, Any]]:
        """Return deterministic metadata for all built-in agent registrations."""
        resolved: Dict[str, Dict[str, Any]] = {}
        for agent_name, payload in DEFAULT_BUILTIN_AGENT_METADATA.items():
            resolved[agent_name] = _normalize_builtin_metadata(agent_name, payload)
        return resolved

    def get_builtin_agent_metadata(self, agent_name: str) -> Dict[str, Any]:
        """Return built-in metadata for one agent key."""
        metadata = self.resolve_builtin_agent_registry().get(agent_name)
        if metadata is None:
            known = ", ".join(sorted(DEFAULT_BUILTIN_AGENT_METADATA.keys()))
            raise AgentRegistryError(
                f"Unknown built-in agent `{agent_name}`. Known: {known}"
            )
        return metadata
