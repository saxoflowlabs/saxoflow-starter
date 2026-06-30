from __future__ import annotations

from pathlib import Path

import pytest


def test_ai_request_service_resolves_context_bundle_and_provenance(tmp_path):
    from saxoflow.services.ai_request_service import AIRequestService

    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "source" / "rtl").mkdir(parents=True)
    (workspace / "docs" / "spec.md").write_text("spec\n", encoding="utf-8")

    service = AIRequestService(workspace)
    bundle = service.resolve_context_bundle(["docs/spec.md", "source/rtl"], task_type="plan")
    metadata = service.resolve_request_metadata(
        "plan",
        {
            "requested_agent": "report",
            "requested_capabilities": ["file.read"],
        },
    )

    assert bundle is not None
    assert bundle.workspace_root == str(workspace.resolve())
    assert [ref.path for ref in bundle.references] == ["docs/spec.md", "source/rtl"]
    assert [ref.kind for ref in bundle.references] == ["file", "directory"]
    assert metadata["agent_contract"]["agent_name"] == "report"
    assert metadata["prompt_provenance"]["selected_bundle"]["name"] == "report"


def test_ai_request_service_marks_unresolved_agent_without_failing(tmp_path):
    from saxoflow.services.ai_request_service import AIRequestService

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = AIRequestService(workspace)

    metadata = service.resolve_request_metadata("ask", {"requested_agent": "custom_unknown"})

    assert metadata["agent_contract"] == {
        "agent_name": "custom_unknown",
        "registration_source": "requested-unresolved",
        "task_type": "ask",
    }
    assert metadata["prompt_provenance"]["selected_bundle"] is None


def test_ai_request_service_rejects_invalid_context_path(tmp_path):
    from saxoflow.services.ai_request_service import AIRequestService, AIRequestServiceError

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    service = AIRequestService(workspace)

    with pytest.raises(AIRequestServiceError, match="does not exist"):
        service.resolve_context_bundle(["docs/missing.md"], task_type="ask")


def test_ai_request_service_starts_task_with_pass_through_graph(tmp_path):
    from saxoflow.services.ai_request_service import AIRequestService

    workspace = tmp_path / "workspace"
    (workspace / "docs").mkdir(parents=True)
    (workspace / "docs" / "spec.md").write_text("spec\n", encoding="utf-8")

    service = AIRequestService(workspace)
    state = service.start_grounded_task(
        "ask",
        "explain",
        metadata={
            "requested_context_paths": ["docs/spec.md"],
            "requested_agent": "report",
            "requested_capabilities": ["file.read"],
        },
    )

    assert state.tasks[0].task_type == "ask"
    assert state.tasks[0].metadata["requested_agent"] == "report"
    assert state.tasks[0].metadata["agent_contract"]["agent_name"] == "report"
    assert state.context_bundle is not None
    assert [ref.path for ref in state.context_bundle.references] == ["docs/spec.md"]