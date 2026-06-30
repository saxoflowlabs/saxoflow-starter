"""Tests for policy service web-research routing gates."""

from __future__ import annotations


def test_web_research_policy_allows_requested_capability_when_explicitly_enabled():
    from saxoflow.services.policy_service import WebResearchRoutingPolicy

    decision = WebResearchRoutingPolicy(
        allow_web_research=True,
        approved_capabilities=("web.search", "web.fetch"),
    ).evaluate(["web.search"])

    assert decision.requested is True
    assert decision.allowed is True
    assert decision.blocked is False
    assert decision.requested_capabilities == ("web.search",)


def test_web_research_policy_blocks_when_requested_but_disabled():
    from saxoflow.services.policy_service import WebResearchRoutingPolicy

    decision = WebResearchRoutingPolicy(
        allow_web_research=False,
        approved_capabilities=("web.search", "web.fetch"),
    ).evaluate(["web.fetch"])

    assert decision.requested is True
    assert decision.allowed is False
    assert decision.blocked is True
    assert "blocked by policy" in decision.reason


def test_web_research_policy_reports_not_requested_without_blocking():
    from saxoflow.services.policy_service import WebResearchRoutingPolicy

    decision = WebResearchRoutingPolicy(
        allow_web_research=True,
        approved_capabilities=("web.search",),
    ).evaluate(["report.read", "context.read"])

    assert decision.requested is False
    assert decision.allowed is False
    assert decision.blocked is False
    assert decision.requested_capabilities == ()


def test_plan_workflow_policy_rejects_incompatible_capabilities(tmp_path):
    from saxoflow.services.policy_service import PlanWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    decision = PlanWorkflowPolicy(workspace_root=workspace).evaluate(["file.read", "eda.run"])

    assert decision.feasible is False
    assert decision.persist_plan_artifact is False
    assert decision.unsupported_capabilities == ("eda.run",)
    assert "rejects incompatible capabilities" in decision.reason


def test_plan_workflow_policy_bounds_artifacts_to_docs_tree(tmp_path):
    from saxoflow.services.policy_service import PlanWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = PlanWorkflowPolicy(workspace_root=workspace)

    bounded = policy.ensure_docs_path("plan.md")

    assert str(bounded).startswith(str((workspace / "docs").resolve()))

    try:
        policy.ensure_docs_path("../outside.md")
    except ValueError as exc:
        assert "docs tree" in str(exc)
    else:
        raise AssertionError("Expected docs path containment check to reject workspace escape.")


def test_research_workflow_policy_accepts_web_and_artifact_capabilities(tmp_path):
    from saxoflow.services.policy_service import ResearchWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    decision = ResearchWorkflowPolicy(workspace_root=workspace).evaluate(
        ["file.read", "web.search", "artifact.write"]
    )

    assert decision.feasible is True
    assert decision.persist_research_artifact is True
    assert decision.approval_checkpoints == ("web.search", "artifact.write")
    assert str(workspace.joinpath("docs").resolve()) == decision.allowed_docs_root


def test_research_workflow_policy_rejects_incompatible_capabilities_and_bounds_docs_tree(tmp_path):
    from saxoflow.services.policy_service import ResearchWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = ResearchWorkflowPolicy(workspace_root=workspace)

    decision = policy.evaluate(["report.read", "eda.run"])

    assert decision.feasible is False
    assert decision.persist_research_artifact is False
    assert decision.unsupported_capabilities == ("eda.run",)
    assert "rejects incompatible capabilities" in decision.reason

    bounded = policy.ensure_docs_path("notes.md")
    assert str(bounded).startswith(str((workspace / "docs").resolve()))

    try:
        policy.ensure_docs_path("../outside.md")
    except ValueError as exc:
        assert "docs tree" in str(exc)
    else:
        raise AssertionError("Expected docs path containment check to reject workspace escape.")


def test_run_workflow_policy_accepts_adapter_mediated_run_capabilities(tmp_path):
    from saxoflow.services.policy_service import RunWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()

    decision = RunWorkflowPolicy(workspace_root=workspace).evaluate(
        ["file.read", "eda.run", "artifact.write", "web.search"]
    )

    assert decision.feasible is True
    assert decision.persist_run_artifact is True
    assert decision.adapter_mediation_enabled is True
    assert decision.resumable_execution is True
    assert decision.approval_checkpoints == ("eda.run", "artifact.write", "web.search")
    assert str(workspace.joinpath("docs").resolve()) == decision.allowed_docs_root


def test_run_workflow_policy_rejects_incompatible_capabilities_and_bounds_docs_tree(tmp_path):
    from saxoflow.services.policy_service import RunWorkflowPolicy

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    policy = RunWorkflowPolicy(workspace_root=workspace)

    decision = policy.evaluate(["report.read", "shell.exec"])

    assert decision.feasible is False
    assert decision.persist_run_artifact is False
    assert decision.unsupported_capabilities == ("shell.exec",)
    assert "rejects incompatible capabilities" in decision.reason

    bounded = policy.ensure_docs_path("run.md")
    assert str(bounded).startswith(str((workspace / "docs").resolve()))

    try:
        policy.ensure_docs_path("../outside.md")
    except ValueError as exc:
        assert "docs tree" in str(exc)
    else:
        raise AssertionError("Expected docs path containment check to reject workspace escape.")
