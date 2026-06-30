"""Focused tests for custom-agent graph template capability allowlist enforcement (P4.08)."""

from __future__ import annotations

import pytest

from saxoflow_agenticai.core.custom_agent_loader import CustomAgentDefinition


def _custom_agent_definition() -> CustomAgentDefinition:
    return CustomAgentDefinition(
        name="my_ppa_agent",
        description="Explore PPA tradeoffs.",
        model_profile="researcher_coder",
        graph_template="research_variant_loop",
        prompt_system="prompts/system.md",
        prompt_task="prompts/task.md",
        input_schema="schemas/request.json",
        output_schema="schemas/report.json",
        tools_allow=("context.read", "file.read", "artifact.read", "eda.run", "file.delete"),
        tools_deny=("file.delete",),
        approvals={"eda.run": "required"},
        source_path=None,
    )


def test_custom_agent_graph_allows_default_allowlist_minus_deny():
    from saxoflow.graph.subgraphs.custom_agent import CustomAgentGraphTemplate

    graph = CustomAgentGraphTemplate()
    result = graph.invoke({"custom_agent": _custom_agent_definition()})

    assert result["status"] == "ready"
    assert result["agent_name"] == "my_ppa_agent"
    assert result["graph_template"] == "research_variant_loop"
    assert result["selected_capabilities"] == [
        "context.read",
        "file.read",
        "artifact.read",
        "eda.run",
    ]
    assert "file.delete" not in result["allowlist"]


def test_custom_agent_graph_enforces_requested_capability_allowlist():
    from saxoflow.graph.subgraphs.custom_agent import CustomAgentGraphError, CustomAgentGraphTemplate

    graph = CustomAgentGraphTemplate()

    ok = graph.invoke(
        {
            "custom_agent": _custom_agent_definition(),
            "requested_capabilities": ["file.read", "eda.run"],
        }
    )
    assert ok["selected_capabilities"] == ["file.read", "eda.run"]

    with pytest.raises(CustomAgentGraphError):
        graph.invoke(
            {
                "custom_agent": _custom_agent_definition(),
                "requested_capabilities": ["file.read", "web.fetch"],
            }
        )


def test_custom_agent_graph_accepts_mapping_payload_and_rejects_bad_request_shape():
    from saxoflow.graph.subgraphs.custom_agent import CustomAgentGraphError, CustomAgentGraphTemplate

    graph = CustomAgentGraphTemplate()
    payload = {
        "name": "mapping_agent",
        "model_profile": "profile_a",
        "graph_template": "custom_loop",
        "prompt": {
            "system": "prompts/system.md",
            "task": "prompts/task.md",
        },
        "tools": {
            "allow": ["file.read", "artifact.read"],
            "deny": [],
        },
        "approvals": {"file.read": "optional"},
    }

    result = graph.invoke({"custom_agent": payload})
    assert result["selected_capabilities"] == ["file.read", "artifact.read"]

    with pytest.raises(CustomAgentGraphError):
        graph.invoke({"custom_agent": payload, "requested_capabilities": "file.read"})


def test_custom_agent_graph_intersects_requested_capabilities_with_policy():
    from saxoflow.graph.subgraphs.custom_agent import CustomAgentGraphTemplate

    graph = CustomAgentGraphTemplate()
    result = graph.invoke(
        {
            "custom_agent": _custom_agent_definition(),
            "requested_capabilities": ["file.read", "eda.run"],
            "capability_policy": {"approved_capabilities": ["file.read"]},
        }
    )

    assert result["selected_capabilities"] == ["file.read"]
    assert result["policy_capabilities"]["denied_by_policy"] == ["eda.run"]


def test_custom_agent_graph_rejects_non_mapping_capability_policy():
    from saxoflow.graph.subgraphs.custom_agent import CustomAgentGraphError, CustomAgentGraphTemplate

    graph = CustomAgentGraphTemplate()
    with pytest.raises(CustomAgentGraphError):
        graph.invoke(
            {
                "custom_agent": _custom_agent_definition(),
                "requested_capabilities": ["file.read"],
                "capability_policy": ["file.read"],
            }
        )
