"""Focused tests for agent tool registry capability metadata and safety contracts."""

from __future__ import annotations

import pytest


def test_agent_tool_registry_exposes_builtins_with_safety_metadata():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry

    registry = AgentToolRegistry.builtins()
    resolved = registry.resolve_tool_registry()

    expected = {
        "context.read",
        "file.read",
        "artifact.read",
        "report.read",
        "file.edit",
        "file.write",
        "file.delete",
        "artifact.write",
        "eda.run",
        "test.run",
        "web.search",
        "web.fetch",
    }
    assert expected.issubset(set(resolved.keys()))

    low = resolved["file.read"]
    assert low["risk_level"] == "low"
    assert low["approval_required"] is False
    assert low["registration_source"] == "built-in"

    high = resolved["eda.run"]
    assert high["risk_level"] == "high"
    assert high["approval_required"] is True


def test_agent_tool_registry_unknown_capability_raises():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry, AgentToolRegistryError

    with pytest.raises(AgentToolRegistryError):
        AgentToolRegistry.builtins().get_capability_metadata("notreal.capability")


def test_agent_tool_registry_requested_subset_normalizes_and_validates():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry, AgentToolRegistryError

    registry = AgentToolRegistry.builtins()

    normalized = registry.validate_requested_capabilities(
        ["file.read", "eda.run", "file.read", "test.run"]
    )
    assert normalized == ("file.read", "eda.run", "test.run")

    with pytest.raises(AgentToolRegistryError):
        registry.validate_requested_capabilities("file.read")

    with pytest.raises(AgentToolRegistryError):
        registry.validate_requested_capabilities(["file.read", "unknown.capability"])


def test_agent_tool_registry_intersects_requested_allowlist_and_policy_subset():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry

    registry = AgentToolRegistry.builtins()
    selected = registry.intersect_with_allowlist_and_policy(
        requested_capabilities=("file.read", "eda.run", "web.fetch"),
        allowed_capabilities=("file.read", "eda.run"),
        policy_approved_capabilities=("file.read",),
    )

    assert selected == ("file.read",)


def test_agent_tool_registry_validates_known_capability_names():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry, AgentToolRegistryError

    registry = AgentToolRegistry.builtins()

    assert registry.validate_capability_name(" file.read ") == "file.read"
    assert registry.validate_capability_names(["file.read", "eda.run", "file.read"]) == (
        "file.read",
        "eda.run",
    )

    with pytest.raises(AgentToolRegistryError):
        registry.validate_capability_name("command.run")

    with pytest.raises(AgentToolRegistryError):
        registry.validate_capability_names(["file.read", "command.run"])


def test_agent_tool_registry_rejects_invalid_risk_and_handles_empty_inputs():
    from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry, AgentToolRegistryError

    with pytest.raises(AgentToolRegistryError):
        AgentToolRegistry(capabilities={"file.read": {"risk_level": "extreme", "approval_required": False}}).resolve_tool_registry()

    registry = AgentToolRegistry.builtins()
    assert registry.validate_capability_names(None) == tuple()
    assert registry.intersect_with_allowlist_and_policy(
        requested_capabilities=("file.read", "eda.run"),
        allowed_capabilities=("file.read",),
    ) == ("file.read",)
