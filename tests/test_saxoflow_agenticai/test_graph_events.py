"""Tests for Phase 3 graph event schema validation and serialization."""

from __future__ import annotations


def test_graph_event_validates_minimal_node_start_event():
    from saxoflow.schemas.events import GraphEvent

    event = GraphEvent.from_mapping(
        {
            "event_id": "evt-1",
            "run_id": "run-1",
            "timestamp": "2026-06-28T10:00:00Z",
            "phase": "intake",
            "node": "intake_router",
            "event_type": "node_start",
        }
    )

    assert event.event_id == "evt-1"
    assert event.run_id == "run-1"
    assert event.phase == "intake"
    assert event.node == "intake_router"
    assert event.event_type == "node_start"
    assert event.context_refs == ()
    assert event.artifact_refs == ()
    assert event.diagnostic_refs == ()


def test_graph_event_serializes_optional_fields():
    from saxoflow.schemas.events import GraphEvent

    event = GraphEvent.from_mapping(
        {
            "event_id": "evt-2",
            "run_id": "run-2",
            "timestamp": "2026-06-28T10:05:00Z",
            "phase": "lint",
            "node": "lint_node",
            "event_type": "tool_run_update",
            "user_message": "Linting in progress",
            "detail_level": "summary",
            "context_refs": ["source/rtl/top.sv", "docs/spec.md"],
            "artifact_refs": ["artifact-1"],
            "diagnostic_refs": ["diag-1", "diag-2"],
            "elapsed_ms": 420,
            "progress_current": 2,
            "progress_total": 5,
        }
    )

    payload = event.to_dict()
    assert payload["event_id"] == "evt-2"
    assert payload["event_type"] == "tool_run_update"
    assert payload["context_refs"] == ["source/rtl/top.sv", "docs/spec.md"]
    assert payload["artifact_refs"] == ["artifact-1"]
    assert payload["diagnostic_refs"] == ["diag-1", "diag-2"]
    assert payload["elapsed_ms"] == 420
    assert payload["progress_current"] == 2
    assert payload["progress_total"] == 5


def test_graph_event_rejects_unknown_event_type():
    from saxoflow.schemas.events import GraphEvent, GraphEventSchemaError

    try:
        GraphEvent.from_mapping(
            {
                "event_id": "evt-3",
                "run_id": "run-3",
                "timestamp": "2026-06-28T10:10:00Z",
                "phase": "run",
                "node": "runner",
                "event_type": "unknown_type",
            }
        )
    except GraphEventSchemaError as exc:
        assert "graph_event.event_type" in str(exc)
    else:
        raise AssertionError("Unknown graph event type was accepted.")


def test_graph_event_rejects_inconsistent_progress_fields():
    from saxoflow.schemas.events import GraphEvent, GraphEventSchemaError

    try:
        GraphEvent.from_mapping(
            {
                "event_id": "evt-4",
                "run_id": "run-4",
                "timestamp": "2026-06-28T10:15:00Z",
                "phase": "run",
                "node": "runner",
                "event_type": "node_end",
                "progress_current": 3,
            }
        )
    except GraphEventSchemaError as exc:
        assert "progress fields" in str(exc)
    else:
        raise AssertionError("Inconsistent graph event progress fields were accepted.")


def test_subagent_handoff_and_return_schemas_round_trip():
    from saxoflow.schemas.events import SubagentHandoff, SubagentReturn

    handoff = SubagentHandoff.from_mapping(
        {
            "handoff_id": "handoff-1",
            "parent_task_id": "task-plan-1",
            "subtask_id": "sub-validate",
            "subagent_role": "verification_runner",
            "capability_tags": ["eda.run", "report.read"],
            "rationale": "validation stage requires deterministic checks",
            "payload": {"prompt": "run verification and summarize failures"},
            "requested_artifact_kinds": ["report", "log"],
        }
    )
    assert handoff.subagent_role == "verification_runner"
    assert handoff.capability_tags == ("eda.run", "report.read")

    result = SubagentReturn.from_mapping(
        {
            "handoff_id": "handoff-1",
            "subagent_role": "verification_runner",
            "status": "success",
            "summary": "verification completed",
            "capability_tags": ["eda.run", "report.read"],
            "artifact_refs": ["art-verify-report"],
            "diagnostic_refs": ["diag-verify-1"],
            "payload": {"exit_code": 0},
        }
    )
    assert result.status == "success"
    assert result.summary == "verification completed"

    handoff_payload = handoff.to_dict()
    result_payload = result.to_dict()
    assert handoff_payload["handoff_id"] == "handoff-1"
    assert handoff_payload["requested_artifact_kinds"] == ["report", "log"]
    assert result_payload["artifact_refs"] == ["art-verify-report"]
    assert result_payload["diagnostic_refs"] == ["diag-verify-1"]


def test_graph_task_state_replays_typed_handoffs_and_returns():
    from saxoflow.graph.state import GraphTaskState

    task = GraphTaskState.from_mapping(
        {
            "task_id": "task-replay-1",
            "task_type": "run",
            "prompt": "coordinate verification",
            "workspace": "/workspace/demo",
            "handoffs": [
                {
                    "handoff_id": "handoff-1",
                    "parent_task_id": "task-replay-1",
                    "subtask_id": "sub-verify",
                    "subagent_role": "verification_runner",
                    "capability_tags": ["eda.run"],
                    "payload": {"step": 1},
                }
            ],
            "returns": [
                {
                    "handoff_id": "handoff-1",
                    "subagent_role": "verification_runner",
                    "status": "success",
                    "summary": "verification passed",
                    "capability_tags": ["eda.run"],
                    "artifact_refs": ["art-1"],
                    "payload": {"step": 1, "outcome": "pass"},
                }
            ],
        }
    )

    assert len(task.handoffs) == 1
    assert len(task.returns) == 1
    assert task.handoffs[0].handoff_id == "handoff-1"
    assert task.returns[0].status == "success"

    replayed = GraphTaskState.from_mapping(task.to_dict())
    assert replayed.handoffs[0].payload["step"] == 1
    assert replayed.returns[0].payload["outcome"] == "pass"


def test_graph_task_state_rejects_invalid_subagent_return_status():
    from saxoflow.graph.state import GraphStateSchemaError, GraphTaskState

    try:
        GraphTaskState.from_mapping(
            {
                "task_id": "task-invalid-return",
                "task_type": "run",
                "prompt": "coordinate verification",
                "workspace": "/workspace/demo",
                "returns": [
                    {
                        "handoff_id": "handoff-1",
                        "subagent_role": "verification_runner",
                        "status": "unknown",
                        "summary": "bad status",
                    }
                ],
            }
        )
    except GraphStateSchemaError as exc:
        assert "subagent_return.status" in str(exc)
    else:
        raise AssertionError("Invalid subagent return status was accepted.")


def test_workflow_service_stream_events_in_order():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    state = service.start_task(
        task_type="run",
        prompt="close lint issues",
        workspace="/workspace/demo",
        run_id="run-events",
        task_id="task-events",
    )
    assert state.run_id == "run-events"

    service.emit_event(
        {
            "event_id": "evt-tool-start",
            "run_id": "run-events",
            "timestamp": "2026-06-28T12:00:00Z",
            "phase": "lint",
            "node": "lint_adapter",
            "event_type": "tool_run_start",
        }
    )
    service.emit_event(
        {
            "event_id": "evt-tool-end",
            "run_id": "run-events",
            "timestamp": "2026-06-28T12:00:01Z",
            "phase": "lint",
            "node": "lint_adapter",
            "event_type": "tool_run_end",
        }
    )

    events = service.stream_events("run-events")
    event_types = [event.event_type for event in events]
    assert event_types == ["node_start", "node_end", "tool_run_start", "tool_run_end"]


def test_workflow_service_stream_events_from_index_is_ordered_slice():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    for index, event_type in enumerate(["node_start", "node_end", "retry"]):
        service.emit_event(
            {
                "event_id": f"evt-{index}",
                "run_id": "run-slice",
                "timestamp": f"2026-06-28T12:10:0{index}Z",
                "phase": "workflow",
                "node": "node",
                "event_type": event_type,
            }
        )

    sliced = service.stream_events_from_index("run-slice", 1)
    assert [event.event_type for event in sliced] == ["node_end", "retry"]

    empty = service.stream_events("unknown-run")
    assert empty == ()


def test_workflow_service_emits_llm_usage_event_from_graph_output():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            task["outputs"] = {
                "llm_result": {
                    "usage": {
                        "provider": "openai",
                        "model": "gpt-5-mini",
                        "prompt_tokens": 11,
                        "completion_tokens": 7,
                        "total_tokens": 18,
                    }
                }
            }
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    service.start_task(
        task_type="ask",
        prompt="summarize lint report",
        workspace="/workspace/demo",
        run_id="run-llm-usage",
        task_id="task-llm-usage",
    )

    usage_events = [
        event
        for event in service.stream_events("run-llm-usage")
        if event.event_type == "llm_call_end"
    ]
    assert len(usage_events) == 1
    usage_event = usage_events[0]
    assert usage_event.phase == "ask"
    assert usage_event.node == "graph_runtime"
    assert usage_event.user_message == "LLM usage: 11 in, 7 out, 18 total."


def test_workflow_service_start_events_and_report_include_context_refs():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.schemas.context import ContextBundle
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
                "context_bundle": payload.get("context_bundle"),
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    context_bundle = ContextBundle.from_mapping(
        {
            "workspace_root": "/workspace/demo",
            "references": [
                {"path": "source/rtl/top.sv", "kind": "file"},
                {"path": "docs/spec.md", "kind": "file"},
            ],
        }
    )

    state = service.start_task(
        task_type="ask",
        prompt="explain design",
        workspace="/workspace/demo",
        context_bundle=context_bundle,
        run_id="run-context-report",
        task_id="task-context-report",
    )

    events = service.stream_events("run-context-report")
    assert [event.event_type for event in events] == ["node_start", "node_end"]
    assert events[0].context_refs == ("source/rtl/top.sv", "docs/spec.md")
    assert events[1].context_refs == ("source/rtl/top.sv", "docs/spec.md")

    report = service.get_run_report("run-context-report", state)
    assert report["run_id"] == "run-context-report"
    assert report["event_count"] == 2
    assert report["task_count"] == 1
    assert report["context_refs"] == ["docs/spec.md", "source/rtl/top.sv"]


def test_workflow_service_emits_retry_monitor_event_from_runtime_decision():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["returns"] = [
                {
                    "handoff_id": "handoff-1",
                    "subagent_role": "verification_runner",
                    "status": "failed",
                    "summary": "verification failed",
                }
            ]
            task["metadata"] = {"lead_monitor": {"retry_budget": 2, "retries_used": 0}}
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    service.start_task(
        task_type="run",
        prompt="close verification issues",
        workspace="/workspace/demo",
        run_id="run-monitor-retry-events",
        task_id="task-monitor-retry-events",
    )

    events = service.stream_events("run-monitor-retry-events")
    retry_events = [event for event in events if event.event_type == "retry"]
    assert len(retry_events) == 1
    assert retry_events[0].node == "lead_monitor_loop"
    assert "Lead monitor decision: retry" in (retry_events[0].user_message or "")


def test_workflow_service_emits_escalation_monitor_event_from_runtime_decision():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["returns"] = [
                {
                    "handoff_id": "handoff-1",
                    "subagent_role": "verification_runner",
                    "status": "failed",
                    "summary": "verification failed",
                }
            ]
            task["metadata"] = {"lead_monitor": {"retry_budget": 1, "retries_used": 1}}
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    service.start_task(
        task_type="run",
        prompt="close verification issues",
        workspace="/workspace/demo",
        run_id="run-monitor-escalate-events",
        task_id="task-monitor-escalate-events",
    )

    events = service.stream_events("run-monitor-escalate-events")
    block_events = [event for event in events if event.event_type == "block"]
    assert len(block_events) == 1
    assert block_events[0].node == "lead_monitor_loop"
    assert "Lead monitor decision: escalate" in (block_events[0].user_message or "")
