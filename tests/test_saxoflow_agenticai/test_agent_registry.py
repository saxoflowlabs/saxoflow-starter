"""Tests for fallback profile contract resolution in the agent registry."""

from __future__ import annotations

import pytest


def test_agent_registry_uses_builtin_general_purpose_profile_by_default():
    from saxoflow_agenticai.core.agent_registry import AgentRegistry

    profile = AgentRegistry.from_mapping(None).resolve_general_purpose_profile()

    assert profile["profile_name"] == "general-purpose"
    assert profile["replacement_source"] == "built-in"
    assert profile["replaced_builtin"] is False
    assert profile["role"] == "general-purpose"
    assert profile["role_type"] == "generic"
    assert profile["capability_tags"] == [
        "context.read",
        "file.read",
        "artifact.read",
        "report.read",
    ]


def test_agent_registry_user_defined_general_purpose_profile_replaces_builtin_deterministically():
    from saxoflow_agenticai.core.agent_registry import AgentRegistry

    mapping = {
        "general-purpose": {
            "role": "custom-general-purpose",
            "role_type": "generic",
            "capability_tags": ["report.read", "web.search", "report.read"],
        }
    }

    registry = AgentRegistry.from_mapping(mapping)
    first = registry.resolve_general_purpose_profile()
    second = registry.resolve_general_purpose_profile()

    assert first == second
    assert first["replacement_source"] == "user-defined"
    assert first["replaced_builtin"] is True
    assert first["role"] == "custom-general-purpose"
    assert first["capability_tags"] == ["report.read", "web.search"]


def test_agent_registry_rejects_invalid_general_purpose_profile():
    from saxoflow_agenticai.core.agent_registry import AgentRegistry, AgentRegistryError

    with pytest.raises(AgentRegistryError):
        AgentRegistry.from_mapping(
            {
                "general-purpose": {
                    "role": "bad-profile",
                    "capability_tags": [],
                }
            }
        ).resolve_general_purpose_profile()


def test_agent_registry_registers_builtin_agents_with_metadata():
    from saxoflow_agenticai.core.agent_registry import AgentRegistry

    registry = AgentRegistry.from_mapping(None)
    builtins = registry.resolve_builtin_agent_registry()

    expected = {
        "rtlgen",
        "tbgen",
        "fpropgen",
        "report",
        "rtlreview",
        "tbreview",
        "fpropreview",
        "debug",
        "sim",
        "synth",
        "pnr",
        "tutor",
    }
    assert expected.issubset(set(builtins.keys()))

    rtlgen = builtins["rtlgen"]
    assert rtlgen["agent_name"] == "rtlgen"
    assert rtlgen["registration_source"] == "built-in"
    assert rtlgen["role"] == "generator"
    assert rtlgen["role_type"] == "domain"
    assert "rtl.generate" in rtlgen["capability_tags"]


def test_agent_registry_get_builtin_agent_metadata_unknown_agent_raises():
    from saxoflow_agenticai.core.agent_registry import AgentRegistry, AgentRegistryError

    with pytest.raises(AgentRegistryError):
        AgentRegistry.from_mapping(None).get_builtin_agent_metadata("notreal")
