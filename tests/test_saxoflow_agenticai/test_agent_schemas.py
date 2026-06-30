"""Tests for common structured agent schemas (Phase 4 P4.01)."""

from __future__ import annotations

import pytest


def test_agent_tool_policy_validates_example_mapping():
    from saxoflow.schemas.agents import AgentToolPolicy

    policy = AgentToolPolicy.from_mapping(
        {
            "allowed_tools": ["file.read", "report.read"],
            "denied_tools": ["file.delete"],
            "approval_required": True,
        }
    )

    assert policy.allowed_tools == ("file.read", "report.read")
    assert policy.denied_tools == ("file.delete",)
    assert policy.approval_required is True
    assert policy.to_dict() == {
        "allowed_tools": ["file.read", "report.read"],
        "denied_tools": ["file.delete"],
        "approval_required": True,
    }


def test_agent_tool_policy_defaults_when_mapping_is_none():
    from saxoflow.schemas.agents import AgentToolPolicy

    policy = AgentToolPolicy.from_mapping(None)

    assert policy.allowed_tools == ()
    assert policy.denied_tools == ()
    assert policy.approval_required is False


def test_agent_tool_policy_rejects_non_mapping_payload():
    from saxoflow.schemas.agents import AgentSchemaError, AgentToolPolicy

    with pytest.raises(AgentSchemaError):
        AgentToolPolicy.from_mapping("invalid")


def test_agent_tool_policy_rejects_non_list_allowed_tools():
    from saxoflow.schemas.agents import AgentSchemaError, AgentToolPolicy

    with pytest.raises(AgentSchemaError):
        AgentToolPolicy.from_mapping(
            {
                "allowed_tools": "eda.run",
            }
        )


def test_agent_tool_policy_rejects_empty_tool_name():
    from saxoflow.schemas.agents import AgentSchemaError, AgentToolPolicy

    with pytest.raises(AgentSchemaError):
        AgentToolPolicy.from_mapping(
            {
                "allowed_tools": ["   "],
            }
        )


def test_agent_profile_validates_common_schema_example():
    from saxoflow.schemas.agents import AgentProfile

    profile = AgentProfile.from_mapping(
        {
            "name": "verification-runner",
            "role": "domain",
            "description": "Runs deterministic verification checks.",
            "capability_tags": ["eda.run", "test.run", "report.read"],
            "input_schema": "schemas/verification_request.json",
            "output_schema": "schemas/verification_result.json",
            "cost_profile": "standard",
            "tool_policy": {
                "allowed_tools": ["eda.run", "report.read"],
                "approval_required": False,
            },
        }
    )

    assert profile.name == "verification-runner"
    assert profile.role == "domain"
    assert profile.capability_tags == ("eda.run", "test.run", "report.read")
    assert profile.input_schema == "schemas/verification_request.json"
    assert profile.output_schema == "schemas/verification_result.json"
    assert profile.tool_policy.allowed_tools == ("eda.run", "report.read")


def test_agent_profile_to_dict_includes_optional_fields_when_set():
    from saxoflow.schemas.agents import AgentProfile, AgentToolPolicy

    profile = AgentProfile(
        name="agent-a",
        role="lead",
        description="Coordinates planning",
        capability_tags=("plan",),
        input_schema="schemas/input.json",
        output_schema="schemas/output.json",
        cost_profile="premium",
        tool_policy=AgentToolPolicy(allowed_tools=("file.read",)),
    )

    data = profile.to_dict()
    assert data["description"] == "Coordinates planning"
    assert data["input_schema"] == "schemas/input.json"
    assert data["output_schema"] == "schemas/output.json"
    assert data["cost_profile"] == "premium"


def test_agent_profile_rejects_empty_capability_tags():
    from saxoflow.schemas.agents import AgentProfile, AgentSchemaError

    with pytest.raises(AgentSchemaError):
        AgentProfile.from_mapping(
            {
                "name": "broken-agent",
                "role": "specialist",
                "capability_tags": [],
            }
        )


def test_agent_profile_rejects_unknown_role():
    from saxoflow.schemas.agents import AgentProfile, AgentSchemaError

    with pytest.raises(AgentSchemaError):
        AgentProfile.from_mapping(
            {
                "name": "broken-agent",
                "role": "wizard",
                "capability_tags": ["file.read"],
            }
        )


def test_agent_intent_classification_validates_example_mapping():
    from saxoflow.schemas.agents import AgentIntentClassification

    classification = AgentIntentClassification.from_mapping(
        {
            "intent": "engineer",
            "confidence": 0.87,
            "rationale": "Request is implementation-focused.",
            "suggested_agent": "rtlgen",
        }
    )

    assert classification.intent == "engineer"
    assert classification.confidence == 0.87
    assert classification.rationale == "Request is implementation-focused."
    assert classification.suggested_agent == "rtlgen"
    assert classification.to_dict() == {
        "intent": "engineer",
        "confidence": 0.87,
        "rationale": "Request is implementation-focused.",
        "suggested_agent": "rtlgen",
    }


def test_agent_intent_classification_rejects_out_of_range_confidence():
    from saxoflow.schemas.agents import AgentIntentClassification, AgentSchemaError

    with pytest.raises(AgentSchemaError):
        AgentIntentClassification.from_mapping(
            {
                "intent": "researcher",
                "confidence": 1.5,
            }
        )


def test_agent_intent_classification_rejects_non_numeric_confidence():
    from saxoflow.schemas.agents import AgentIntentClassification, AgentSchemaError

    with pytest.raises(AgentSchemaError):
        AgentIntentClassification.from_mapping(
            {
                "intent": "researcher",
                "confidence": "high",
            }
        )


def test_agent_intent_classification_rejects_unknown_intent():
    from saxoflow.schemas.agents import AgentIntentClassification, AgentSchemaError

    with pytest.raises(AgentSchemaError):
        AgentIntentClassification.from_mapping(
            {
                "intent": "random",
                "confidence": 0.4,
            }
        )


def test_rtl_proposal_validates_and_roundtrips():
    from saxoflow.schemas.agents import RTLProposal

    proposal = RTLProposal.from_mapping(
        {
            "spec": "create a 2-bit adder",
            "rtl_code": "module adder; endmodule",
            "prompt": "System:\n...",
        }
    )

    assert proposal.spec == "create a 2-bit adder"
    assert proposal.rtl_code == "module adder; endmodule"
    assert str(proposal) == "module adder; endmodule"
    assert proposal.to_dict() == {
        "spec": "create a 2-bit adder",
        "rtl_code": "module adder; endmodule",
        "prompt": "System:\n...",
    }


def test_rtl_review_report_validates_and_roundtrips():
    from saxoflow.schemas.agents import RTLReviewReport

    report = RTLReviewReport.from_mapping(
        {
            "syntax_issues": "spacing issue",
            "logic_issues": "None",
            "reset_issues": "None",
            "port_declaration_issues": "None",
            "optimization_suggestions": "Consider register insertion",
            "naming_improvements": "None",
            "synthesis_concerns": "None",
            "overall_comments": "Looks good",
        }
    )

    assert report.syntax_issues == "spacing issue"
    assert report.optimization_suggestions == "Consider register insertion"
    assert report.to_dict()["overall_comments"] == "Looks good"
    assert "Syntax Issues: spacing issue" in report.to_text()
    assert "Overall Comments: Looks good" in report.to_text()


def test_lead_task_plan_schema_validates_example_and_roundtrips():
    from saxoflow.schemas.agents import LeadTaskPlan

    plan = LeadTaskPlan.from_mapping(
        {
            "objective": "Close verification issues",
            "subtasks": [
                {
                    "subtask_id": "sub-1",
                    "title": "Run checks",
                    "stage": "validation",
                    "required_capabilities": ["eda.run", "report.read"],
                }
            ],
            "decomposition_policy": {
                "strategy": "sequential",
                "max_parallel_branches": 1,
                "allow_llm_fallback": False,
            },
        }
    )

    assert plan.objective == "Close verification issues"
    assert len(plan.subtasks) == 1
    assert plan.subtasks[0].required_capabilities == ("eda.run", "report.read")
    assert plan.to_dict()["objective"] == "Close verification issues"


def test_lead_subtask_plan_rejects_unknown_stage():
    from saxoflow.schemas.agents import AgentSchemaError, LeadSubTaskPlan

    with pytest.raises(AgentSchemaError):
        LeadSubTaskPlan.from_mapping(
            {
                "subtask_id": "sub-1",
                "title": "Bad stage",
                "stage": "deploy",
            }
        )


def test_decomposition_policy_defaults_when_missing():
    from saxoflow.schemas.agents import DecompositionPolicy

    policy = DecompositionPolicy.from_mapping(None)

    assert policy.strategy == "sequential"
    assert policy.max_parallel_branches == 1
    assert policy.allow_llm_fallback is False


def test_decomposition_policy_rejects_unknown_strategy():
    from saxoflow.schemas.agents import AgentSchemaError, DecompositionPolicy

    with pytest.raises(AgentSchemaError):
        DecompositionPolicy.from_mapping(
            {
                "strategy": "anything",
            }
        )


def test_lead_task_plan_rejects_non_list_subtasks():
    from saxoflow.schemas.agents import AgentSchemaError, LeadTaskPlan

    with pytest.raises(AgentSchemaError):
        LeadTaskPlan.from_mapping(
            {
                "objective": "Oops",
                "subtasks": "not-a-list",
            }
        )


def test_lead_task_plan_rejects_empty_subtasks_list():
    from saxoflow.schemas.agents import AgentSchemaError, LeadTaskPlan

    with pytest.raises(AgentSchemaError):
        LeadTaskPlan.from_mapping(
            {
                "objective": "Oops",
                "subtasks": [],
            }
        )
