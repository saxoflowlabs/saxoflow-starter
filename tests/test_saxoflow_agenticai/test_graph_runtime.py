"""Tests for Phase 3 graph state schema scaffolding."""

from __future__ import annotations

import pytest


def test_graph_task_state_validates_minimal_task():
    from saxoflow.graph.state import GraphTaskState

    task = GraphTaskState.from_mapping(
        {
            "task_id": "task-1",
            "task_type": "run",
            "prompt": "improve timing slack",
            "workspace": "/workspace/demo",
        }
    )

    assert task.task_id == "task-1"
    assert task.task_type == "run"
    assert task.prompt == "improve timing slack"
    assert task.workspace == "/workspace/demo"
    assert task.status == "pending"
    assert task.thread_id is None
    assert task.context_bundle is None
    assert task.metadata == {}
    assert task.outputs == {}


def test_graph_state_validates_minimal_task_container():
    from saxoflow.graph.state import GraphState

    state = GraphState.from_mapping(
        {
            "run_id": "run-1",
            "task": {
                "task_id": "task-1",
                "task_type": "ask",
                "prompt": "summarize lint findings",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-1",
        }
    )

    assert state.run_id == "run-1"
    assert len(state.tasks) == 1
    assert state.tasks[0].task_type == "ask"
    assert state.active_task_id == "task-1"


def test_graph_state_round_trips_top_level_context_bundle():
    from saxoflow.graph.state import GraphState

    state = GraphState.from_mapping(
        {
            "run_id": "run-context",
            "task": {
                "task_id": "task-context",
                "task_type": "ask",
                "prompt": "explain module",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-context",
            "context_bundle": {
                "workspace_root": "/workspace/demo",
                "references": [
                    {"path": "source/rtl/top.sv", "kind": "file"},
                    {"path": "docs/spec.md", "kind": "file"},
                ],
            },
        }
    )

    assert state.context_bundle is not None
    assert state.context_bundle.workspace_root == "/workspace/demo"
    assert len(state.context_bundle.references) == 2
    assert state.context_bundle.references[0].path == "source/rtl/top.sv"

    payload = state.to_dict()
    assert payload["context_bundle"]["workspace_root"] == "/workspace/demo"
    assert payload["context_bundle"]["references"][1]["path"] == "docs/spec.md"


def test_graph_task_state_validates_lead_task_plan_contract():
    from saxoflow.graph.state import GraphTaskState

    task = GraphTaskState.from_mapping(
        {
            "task_id": "task-plan-1",
            "task_type": "plan",
            "prompt": "decompose workflow",
            "workspace": "/workspace/demo",
            "lead_task_plan": {
                "objective": "Close lint and simulation issues",
                "rationale": "Split by deterministic validation stages",
                "subtasks": [
                    {
                        "subtask_id": "sub-1",
                        "title": "Analyze diagnostics",
                        "stage": "analysis",
                        "required_capabilities": ["report.read"],
                    },
                    {
                        "subtask_id": "sub-2",
                        "title": "Run lint validation",
                        "stage": "validation",
                        "required_capabilities": ["eda.run", "report.read"],
                    },
                ],
                "decomposition_policy": {
                    "strategy": "hybrid",
                    "max_parallel_branches": 2,
                    "allow_llm_fallback": True,
                },
            },
        }
    )

    assert task.lead_task_plan is not None
    assert task.lead_task_plan.objective == "Close lint and simulation issues"
    assert task.lead_task_plan.decomposition_policy.strategy == "hybrid"
    assert task.lead_task_plan.decomposition_policy.max_parallel_branches == 2
    assert len(task.lead_task_plan.subtasks) == 2
    assert task.lead_task_plan.subtasks[1].required_capabilities == ("eda.run", "report.read")

    payload = task.to_dict()
    assert payload["lead_task_plan"]["subtasks"][0]["stage"] == "analysis"
    assert payload["lead_task_plan"]["decomposition_policy"]["strategy"] == "hybrid"


def test_graph_task_state_rejects_invalid_lead_task_plan_constraints():
    from saxoflow.graph.state import GraphStateSchemaError, GraphTaskState

    try:
        GraphTaskState.from_mapping(
            {
                "task_id": "task-plan-invalid",
                "task_type": "plan",
                "prompt": "decompose workflow",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Invalid plan",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Analyze diagnostics",
                            "stage": "analysis",
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "parallel",
                        "max_parallel_branches": 0,
                    },
                },
            }
        )
    except GraphStateSchemaError as exc:
        assert "lead_task_plan.decomposition_policy.max_parallel_branches" in str(exc)
    else:
        raise AssertionError("Invalid lead-task decomposition constraints were accepted.")


def test_graph_task_state_rejects_missing_required_fields():
    from saxoflow.graph.state import GraphStateSchemaError, GraphTaskState

    try:
        GraphTaskState.from_mapping(
            {
                "task_id": "task-1",
                "task_type": "run",
                "workspace": "/workspace/demo",
            }
        )
    except GraphStateSchemaError as exc:
        assert "graph_task.prompt" in str(exc)
    else:
        raise AssertionError("Invalid graph task state was accepted.")


def test_graph_runtime_can_start_fake_graph():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            task["thread_id"] = "thread-1"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-1",
            "task": {
                "task_id": "task-1",
                "task_type": "run",
                "prompt": "close timing violations",
                "workspace": "/workspace/demo",
                "status": "pending",
            },
            "active_task_id": "task-1",
        }
    )

    started_state = runtime.start(initial_state)

    assert started_state.run_id == "run-1"
    assert started_state.active_task_id == "task-1"
    assert len(started_state.tasks) == 1
    assert started_state.tasks[0].status == "running"
    assert started_state.tasks[0].thread_id == "thread-1"


def test_workflow_service_start_task_uses_runtime_to_start_graph():
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
        task_type="plan",
        prompt="derive verification milestones",
        workspace="/workspace/demo",
        run_id="run-service",
        task_id="task-service",
        metadata={"source": "test"},
    )

    assert state.run_id == "run-service"
    assert state.active_task_id == "task-service"
    assert len(state.tasks) == 1
    assert state.tasks[0].task_type == "plan"
    assert state.tasks[0].status == "running"
    assert state.tasks[0].metadata == {"source": "test"}


def test_workflow_service_context_bundle_is_visible_to_graph_nodes():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.schemas.context import ContextBundle
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            assert payload["context_bundle"]["workspace_root"] == "/workspace/demo"
            refs = payload["context_bundle"]["references"]
            assert [ref["path"] for ref in refs] == ["source/rtl/top.sv", "docs/spec.md"]
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
                "context_bundle": payload["context_bundle"],
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

    state = service.start_run_task(
        prompt="run validation",
        workspace="/workspace/demo",
        context_bundle=context_bundle,
        run_id="run-context-visible",
        task_id="task-context-visible",
    )

    assert state.run_id == "run-context-visible"
    assert state.tasks[0].status == "running"
    assert state.context_bundle is not None
    assert [ref.path for ref in state.context_bundle.references] == [
        "source/rtl/top.sv",
        "docs/spec.md",
    ]


def test_graph_runtime_saves_and_loads_checkpoint():
    from saxoflow.graph.runtime import GraphRuntime, LocalGraphCheckpointer
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["status"] = "running"
            task["thread_id"] = "thread-checkpoint"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(
        graph_factory=lambda: FakeGraph(),
        checkpointer=LocalGraphCheckpointer(),
    )
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-checkpoint",
            "task": {
                "task_id": "task-checkpoint",
                "task_type": "run",
                "prompt": "run synthesis",
                "workspace": "/workspace/demo",
                "status": "pending",
            },
            "active_task_id": "task-checkpoint",
        }
    )

    started_state = runtime.start(initial_state)
    loaded_state = runtime.load_checkpoint("run-checkpoint")

    assert started_state.tasks[0].status == "running"
    assert loaded_state.run_id == "run-checkpoint"
    assert loaded_state.tasks[0].thread_id == "thread-checkpoint"
    assert loaded_state.tasks[0].status == "running"


def test_graph_runtime_can_resume_from_checkpoint():
    from saxoflow.graph.runtime import GraphRuntime, LocalGraphCheckpointer
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            if task.get("status") == "running":
                task["status"] = "completed"
            else:
                task["status"] = "running"
            task["thread_id"] = "thread-resume"
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(
        graph_factory=lambda: FakeGraph(),
        checkpointer=LocalGraphCheckpointer(),
    )
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-resume",
            "task": {
                "task_id": "task-resume",
                "task_type": "resume",
                "prompt": "continue workflow",
                "workspace": "/workspace/demo",
                "status": "pending",
            },
            "active_task_id": "task-resume",
        }
    )

    started_state = runtime.start(initial_state)
    resumed_state = runtime.resume("run-resume")

    assert started_state.tasks[0].status == "running"
    assert resumed_state.run_id == "run-resume"
    assert resumed_state.tasks[0].thread_id == "thread-resume"
    assert resumed_state.tasks[0].status == "completed"


@pytest.mark.parametrize(
    ("method_name", "expected_task_type"),
    [
        ("start_ask_task", "ask"),
        ("start_plan_task", "plan"),
        ("start_run_task", "run"),
        ("start_research_task", "research"),
        ("start_resume_task", "resume"),
    ],
)
def test_workflow_service_task_apis_create_graph_threads(method_name, expected_task_type):
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    method = getattr(service, method_name)

    state = method(
        prompt="task prompt",
        workspace="/workspace/demo",
        run_id=f"run-{expected_task_type}",
        task_id=f"task-{expected_task_type}",
    )

    assert state.run_id == f"run-{expected_task_type}"
    assert state.active_task_id == f"task-{expected_task_type}"
    assert len(state.tasks) == 1
    task = state.tasks[0]
    assert task.task_type == expected_task_type
    assert task.thread_id is not None
    assert task.thread_id.startswith(f"thread-{expected_task_type}-")


def test_workflow_service_start_ask_task_sets_grounded_contract_metadata():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_ask_task(
        prompt="summarize context",
        workspace="/workspace/demo",
        run_id="run-ask-contract",
        task_id="task-ask-contract",
        metadata={"source": "tui"},
    )

    task = state.tasks[0]
    assert task.task_type == "ask"
    assert task.metadata["source"] == "tui"
    assert task.metadata["ask_workflow_contract"] == {
        "mode": "grounded_read_only",
        "citation_required": True,
        "visibly_distinct": True,
    }


def test_workflow_service_start_plan_task_sets_structured_contract_metadata():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_plan_task(
        prompt="create verification milestones",
        workspace="/workspace/demo",
        run_id="run-plan-contract",
        task_id="task-plan-contract",
        metadata={"source": "tui"},
    )

    task = state.tasks[0]
    assert task.task_type == "plan"
    assert task.metadata["source"] == "tui"
    assert task.metadata["plan_workflow_contract"] == {
        "mode": "structured_read_only",
        "feasibility_validation_required": True,
        "bounded_docs_persistence": True,
        "required_sections": [
            "milestones",
            "prerequisites",
            "risks",
            "approval_checkpoints",
        ],
    }


def test_workflow_service_start_research_task_sets_evidence_synthesis_contract_metadata():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_research_task(
        prompt="compare research workflows",
        workspace="/workspace/demo",
        run_id="run-research-contract",
        task_id="task-research-contract",
        metadata={"source": "tui"},
    )

    task = state.tasks[0]
    assert task.task_type == "research"
    assert task.metadata["source"] == "tui"
    assert task.metadata["research_workflow_contract"] == {
        "mode": "evidence_synthesis_read_only",
        "citations_required": True,
        "web_retrieval_optional": True,
        "bounded_docs_persistence": True,
        "required_sections": [
            "comparisons",
            "citations",
            "confidence",
            "open_questions",
        ],
    }


def test_workflow_service_start_run_task_sets_bounded_execution_contract_metadata():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_run_task(
        prompt="execute bounded flow",
        workspace="/workspace/demo",
        run_id="run-bounded-contract",
        task_id="task-bounded-contract",
        metadata={"source": "tui"},
    )

    task = state.tasks[0]
    assert task.task_type == "run"
    assert task.metadata["source"] == "tui"
    assert task.metadata["run_workflow_contract"] == {
        "mode": "bounded_agent_execution",
        "approval_required": True,
        "adapter_mediation": True,
        "scenario_classification_required": True,
        "resumable_state": True,
        "artifact_and_event_visibility": True,
    }
    assert task.metadata["run_adapter_routing"] == {
        "requested": False,
        "classification_status": "not_requested",
        "scenario": None,
        "adapter_module": None,
        "reason": "eda.run capability was not requested",
    }


def test_workflow_service_start_run_task_classifies_eda_run_synthesis_scenario():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_run_task(
        prompt="optimize area and timing",
        workspace="/workspace/demo",
        run_id="run-bounded-synthesis",
        task_id="task-bounded-synthesis",
        metadata={
            "requested_capabilities": ["file.read", "eda.run"],
            "requested_agent": "my_ppa_agent",
        },
    )

    routing = state.tasks[0].metadata["run_adapter_routing"]
    assert routing["requested"] is True
    assert routing["classification_status"] == "classified"
    assert routing["scenario"] == "synthesis"
    assert routing["adapter_module"] == "saxoflow.tools.adapters.synthesis"


def test_workflow_service_start_run_task_classifies_prototype_tests_to_simulation():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_run_task(
        prompt="prototype tests",
        workspace="/workspace/demo",
        run_id="run-bounded-simulation",
        task_id="task-bounded-simulation",
        metadata={
            "requested_capabilities": ["eda.run"],
        },
    )

    routing = state.tasks[0].metadata["run_adapter_routing"]
    assert routing["requested"] is True
    assert routing["classification_status"] == "classified"
    assert routing["scenario"] == "simulation"
    assert routing["adapter_module"] == "saxoflow.tools.adapters.simulation"


def test_workflow_service_start_run_task_rejects_ambiguous_eda_run_scenario():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))

    state = service.start_run_task(
        prompt="run eda flow",
        workspace="/workspace/demo",
        run_id="run-bounded-ambiguous",
        task_id="task-bounded-ambiguous",
        metadata={
            "requested_capabilities": ["eda.run"],
        },
    )

    routing = state.tasks[0].metadata["run_adapter_routing"]
    assert routing["requested"] is True
    assert routing["classification_status"] == "rejected"
    assert routing["scenario"] is None
    assert "Could not classify `eda.run` intent" in routing["reason"]


def test_graph_runtime_policy_first_single_stage_routes_relevant_subgraph_only():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            route = payload["tasks"][0]["metadata"]["supervisor_route"]
            assert route["selected_subgraphs"] == ["verification"]
            assert route["fallback_used"] is False
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-routing-single-stage",
            "task": {
                "task_id": "task-routing-single-stage",
                "task_type": "run",
                "prompt": "close verification issues",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Run one validation step",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Validate design",
                            "stage": "validation",
                            "required_capabilities": ["eda.run", "report.read"],
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "sequential",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-routing-single-stage",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["verification"]
    assert route["subagent_catalog"]
    generic_roles = [
        entry for entry in route["subagent_catalog"] if entry["role_type"] == "generic"
    ]
    assert generic_roles

    selected_roles = route["subagent_selection"]
    assert len(selected_roles) == 1
    assert selected_roles[0]["role"] == "verification_runner"
    assert selected_roles[0]["capability_tags"] == ["eda.run", "test.run", "report.read"]
    assert "policy-first" in selected_roles[0]["selection_rationale"]


def test_graph_runtime_supervisor_router_uses_fallback_when_ambiguous_and_allowed():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-routing-fallback",
            "task": {
                "task_id": "task-routing-fallback",
                "task_type": "run",
                "prompt": "summarize project status",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Prepare final summary",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Build report",
                            "stage": "report",
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "hybrid",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": True,
                    },
                },
            },
            "active_task_id": "task-routing-fallback",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["general_purpose_fallback"]
    assert route["fallback_used"] is True
    assert route["fallback_contract"]["profile_name"] == "general-purpose"
    assert route["fallback_contract"]["replacement_source"] == "built-in"
    assert route["fallback_contract"]["replaced_builtin"] is False
    assert len(route["subagent_selection"]) == 1
    assert route["subagent_selection"][0]["role"] == "general-purpose"
    assert route["subagent_selection"][0]["role_type"] == "generic"
    assert "artifact.read" in route["subagent_selection"][0]["capability_tags"]


def test_graph_runtime_supervisor_router_respects_no_fallback_policy():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-routing-no-fallback",
            "task": {
                "task_id": "task-routing-no-fallback",
                "task_type": "run",
                "prompt": "summarize project status",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Prepare final summary",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Build report",
                            "stage": "report",
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "hybrid",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-routing-no-fallback",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == []
    assert route["fallback_used"] is False


def test_graph_runtime_supervisor_router_replaces_builtin_fallback_with_user_profile():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-routing-fallback-user-profile",
            "task": {
                "task_id": "task-routing-fallback-user-profile",
                "task_type": "ask",
                "prompt": "find recent CDC verification guidance",
                "workspace": "/workspace/demo",
                "metadata": {
                    "agent_profiles": {
                        "general-purpose": {
                            "role": "custom-general-purpose",
                            "role_type": "generic",
                            "capability_tags": ["report.read", "web.search", "report.read"],
                        }
                    }
                },
                "lead_task_plan": {
                    "objective": "Ambiguous task requiring fallback",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Clarify and gather guidance",
                            "stage": "report",
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "hybrid",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": True,
                    },
                },
            },
            "active_task_id": "task-routing-fallback-user-profile",
        }
    )

    first_state = runtime.start(initial_state)
    second_state = runtime.start(initial_state)

    first_route = first_state.tasks[0].metadata["supervisor_route"]
    second_route = second_state.tasks[0].metadata["supervisor_route"]

    assert first_route == second_route
    assert first_route["selected_subgraphs"] == ["general_purpose_fallback"]
    assert first_route["fallback_used"] is True
    assert first_route["fallback_contract"]["profile_name"] == "general-purpose"
    assert first_route["fallback_contract"]["replacement_source"] == "user-defined"
    assert first_route["fallback_contract"]["replaced_builtin"] is True
    assert first_route["fallback_contract"]["role"] == "custom-general-purpose"
    assert first_route["fallback_contract"]["capability_tags"] == ["report.read", "web.search"]
    assert len(first_route["subagent_selection"]) == 1
    assert first_route["subagent_selection"][0]["role"] == "custom-general-purpose"
    assert first_route["subagent_selection"][0]["capability_tags"] == ["report.read", "web.search"]


def test_graph_runtime_web_research_routes_only_when_requested_and_allowed():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-web-routing-allowed",
            "task": {
                "task_id": "task-web-routing-allowed",
                "task_type": "research",
                "prompt": "compare latest open-source PnR QoR workflows",
                "workspace": "/workspace/demo",
                "metadata": {
                    "web_research_policy": {
                        "allow_web_research": True,
                        "approved_capabilities": ["web.search", "web.fetch"],
                    }
                },
                "lead_task_plan": {
                    "objective": "Gather external references",
                    "subtasks": [
                        {
                            "subtask_id": "sub-web",
                            "title": "Search and fetch references",
                            "stage": "report",
                            "required_capabilities": ["web.search", "web.fetch"],
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "sequential",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-web-routing-allowed",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["web_research"]
    assert route["fallback_used"] is False
    assert route["web_research_policy"]["requested"] is True
    assert route["web_research_policy"]["allowed"] is True
    assert route["web_research_policy"]["blocked"] is False
    assert route["subagent_selection"][0]["role"] == "web_research_specialist"
    assert route["subagent_selection"][0]["capability_tags"] == [
        "web.search",
        "web.fetch",
        "report.read",
    ]


def test_graph_runtime_web_research_stays_blocked_when_requested_but_not_allowed():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-web-routing-blocked",
            "task": {
                "task_id": "task-web-routing-blocked",
                "task_type": "research",
                "prompt": "compare latest open-source PnR QoR workflows",
                "workspace": "/workspace/demo",
                "metadata": {
                    "web_research_policy": {
                        "allow_web_research": False,
                        "approved_capabilities": ["web.search", "web.fetch"],
                    }
                },
                "lead_task_plan": {
                    "objective": "Gather external references",
                    "subtasks": [
                        {
                            "subtask_id": "sub-web",
                            "title": "Search and fetch references",
                            "stage": "report",
                            "required_capabilities": ["web.search"],
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "hybrid",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": True,
                    },
                },
            },
            "active_task_id": "task-web-routing-blocked",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["general_purpose_fallback"]
    assert route["fallback_used"] is True
    assert route["web_research_policy"]["requested"] is True
    assert route["web_research_policy"]["allowed"] is False
    assert route["web_research_policy"]["blocked"] is True
    assert route["subagent_selection"][0]["role"] != "web_research_specialist"


@pytest.mark.parametrize(
    (
        "scenario",
        "task_type",
        "subtasks",
        "metadata",
        "allow_llm_fallback",
        "expected_subgraphs",
        "expected_roles",
        "rationale_contains",
    ),
    [
        (
            "domain",
            "run",
            [
                {
                    "subtask_id": "sub-domain",
                    "title": "Run verification",
                    "stage": "validation",
                    "required_capabilities": ["eda.run"],
                }
            ],
            {},
            False,
            ["verification"],
            ["verification_runner"],
            "policy-first stage routing",
        ),
        (
            "fallback",
            "ask",
            [
                {
                    "subtask_id": "sub-fallback",
                    "title": "Clarify request",
                    "stage": "report",
                }
            ],
            {},
            True,
            ["general_purpose_fallback"],
            ["general-purpose"],
            "selected general-purpose fallback",
        ),
        (
            "web-research",
            "research",
            [
                {
                    "subtask_id": "sub-web",
                    "title": "Search web",
                    "stage": "report",
                    "required_capabilities": ["web.search", "web.fetch"],
                }
            ],
            {
                "web_research_policy": {
                    "allow_web_research": True,
                    "approved_capabilities": ["web.search", "web.fetch"],
                }
            },
            True,
            ["web_research"],
            ["web_research_specialist"],
            "web-research was policy-approved",
        ),
    ],
)
def test_workflow_service_routing_scenario_matrix_emits_rationale_and_selected_subagents_only(
    scenario,
    task_type,
    subtasks,
    metadata,
    allow_llm_fallback,
    expected_subgraphs,
    expected_roles,
    rationale_contains,
):
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    state = service.start_task(
        task_type=task_type,
        prompt=f"scenario: {scenario}",
        workspace="/workspace/demo",
        run_id=f"run-routing-matrix-{scenario}",
        task_id=f"task-routing-matrix-{scenario}",
        metadata=metadata,
        lead_task_plan={
            "objective": f"route scenario {scenario}",
            "subtasks": subtasks,
            "decomposition_policy": {
                "strategy": "hybrid",
                "max_parallel_branches": 1,
                "allow_llm_fallback": allow_llm_fallback,
            },
        },
    )

    route = state.tasks[0].metadata["supervisor_route"]
    report = service.get_run_report(state.run_id, state)
    summary = report["routing"][0]

    assert route["selected_subgraphs"] == expected_subgraphs
    assert summary["selected_subgraphs"] == expected_subgraphs
    assert rationale_contains in route["rationale"]
    assert rationale_contains in summary["rationale"]

    selected_roles = [entry["role"] for entry in route["subagent_selection"]]
    summary_roles = [entry["role"] for entry in summary["subagent_selection"]]
    assert selected_roles == expected_roles
    assert summary_roles == expected_roles

    catalog_selected_roles = {
        entry["role"]
        for entry in route["subagent_catalog"]
        if entry["selected"]
    }
    assert catalog_selected_roles == set(expected_roles)


def test_workflow_service_run_report_includes_supervisor_routing_summary():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            return payload

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    state = service.start_run_task(
        prompt="close verification issues",
        workspace="/workspace/demo",
        run_id="run-routing-report",
        task_id="task-routing-report",
        lead_task_plan={
            "objective": "Run one validation step",
            "subtasks": [
                {
                    "subtask_id": "sub-1",
                    "title": "Validate design",
                    "stage": "validation",
                    "required_capabilities": ["eda.run"],
                }
            ],
            "decomposition_policy": {
                "strategy": "sequential",
                "max_parallel_branches": 1,
                "allow_llm_fallback": False,
            },
        },
    )

    report = service.get_run_report("run-routing-report", state)
    assert report["routing"]
    assert report["routing"][0]["selected_subgraphs"] == ["verification"]
    assert report["routing"][0]["web_research_policy"]["requested"] is False
    assert report["routing"][0]["fallback_contract"]["profile_name"] == "general-purpose"
    assert report["routing"][0]["fallback_contract"]["replacement_source"] == "built-in"
    selection = report["routing"][0]["subagent_selection"]
    assert len(selection) == 1
    assert selection[0]["role"] == "verification_runner"
    assert selection[0]["role_type"] == "domain"
    assert selection[0]["capability_tags"] == ["eda.run", "test.run", "report.read"]
    assert "policy-first" in selection[0]["selection_rationale"]


def test_graph_runtime_supervisor_router_uses_capability_route_when_stage_mapping_missing():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            return payload

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    initial_state = GraphState.from_mapping(
        {
            "run_id": "run-routing-capability",
            "task": {
                "task_id": "task-routing-capability",
                "task_type": "run",
                "prompt": "repair issue",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Repair code",
                    "subtasks": [
                        {
                            "subtask_id": "sub-1",
                            "title": "Patch files",
                            "stage": "report",
                            "required_capabilities": ["file.edit"],
                        }
                    ],
                    "decomposition_policy": {
                        "strategy": "sequential",
                        "max_parallel_branches": 1,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-routing-capability",
        }
    )

    started_state = runtime.start(initial_state)
    route = started_state.tasks[0].metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["repair"]
    assert route["fallback_used"] is False


def test_graph_runtime_build_graph_and_invoke_error_paths():
    from saxoflow.graph.runtime import GraphRuntime, GraphRuntimeError

    runtime = GraphRuntime(graph_factory=None)
    with pytest.raises(GraphRuntimeError):
        runtime.build_graph()

    runtime = GraphRuntime(graph_factory=lambda: None)
    with pytest.raises(GraphRuntimeError):
        runtime.build_graph()

    with pytest.raises(GraphRuntimeError):
        GraphRuntime._invoke_graph(object(), {"run_id": "x"})


def test_graph_runtime_start_and_mapping_error_paths():
    from saxoflow.graph.runtime import GraphRuntime, GraphRuntimeError
    from saxoflow.graph.state import GraphState

    class BadResultGraph:
        def invoke(self, payload):
            return "not-a-mapping"

    runtime = GraphRuntime(graph_factory=lambda: BadResultGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-bad-result",
            "task": {
                "task_id": "task-bad-result",
                "task_type": "ask",
                "prompt": "x",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-bad-result",
        }
    )
    with pytest.raises(GraphRuntimeError):
        runtime.start(state)

    with pytest.raises(GraphRuntimeError):
        runtime.start_from_mapping({"run_id": "missing-tasks-prompt"})


def test_graph_runtime_checkpoint_error_paths_and_callable_graph_support():
    from saxoflow.graph.runtime import GraphRuntime, GraphRuntimeError, LocalGraphCheckpointer
    from saxoflow.graph.state import GraphState

    runtime = GraphRuntime(graph_factory=lambda: (lambda payload: payload))
    state = GraphState.from_mapping(
        {
            "run_id": "run-callable-graph",
            "task": {
                "task_id": "task-callable-graph",
                "task_type": "ask",
                "prompt": "x",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-callable-graph",
        }
    )
    started_state = runtime.start(state)
    assert started_state.run_id == "run-callable-graph"

    with pytest.raises(GraphRuntimeError):
        runtime.load_checkpoint("missing")

    with pytest.raises(GraphRuntimeError):
        LocalGraphCheckpointer().load("missing")


def test_graph_runtime_lead_monitor_marks_retry_when_failure_and_budget_available():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

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

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-monitor-retry",
            "task": {
                "task_id": "task-monitor-retry",
                "task_type": "run",
                "prompt": "run validation",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-monitor-retry",
        }
    )

    started_state = runtime.start(state)
    monitor = started_state.tasks[0].metadata["lead_monitor"]
    assert monitor["decision"] == "retry"
    assert monitor["retries_used"] == 1
    assert monitor["retry_budget"] == 2


def test_graph_runtime_lead_monitor_escalates_when_budget_exhausted():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

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

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-monitor-escalate",
            "task": {
                "task_id": "task-monitor-escalate",
                "task_type": "run",
                "prompt": "run validation",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-monitor-escalate",
        }
    )

    started_state = runtime.start(state)
    monitor = started_state.tasks[0].metadata["lead_monitor"]
    assert monitor["decision"] == "escalate"
    assert monitor["retries_used"] == 1
    assert monitor["retry_budget"] == 1


def test_graph_runtime_lead_monitor_completes_when_all_returns_succeed():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["returns"] = [
                {
                    "handoff_id": "handoff-1",
                    "subagent_role": "verification_runner",
                    "status": "success",
                    "summary": "verification passed",
                },
                {
                    "handoff_id": "handoff-2",
                    "subagent_role": "diagnostics_reviewer",
                    "status": "success",
                    "summary": "diagnostics clear",
                },
            ]
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-monitor-complete",
            "task": {
                "task_id": "task-monitor-complete",
                "task_type": "run",
                "prompt": "run validation",
                "workspace": "/workspace/demo",
            },
            "active_task_id": "task-monitor-complete",
        }
    )

    started_state = runtime.start(state)
    monitor = started_state.tasks[0].metadata["lead_monitor"]
    assert monitor["decision"] == "complete"


def test_graph_runtime_bounded_parallel_branches_respect_concurrency_limit():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["handoffs"] = [
                {
                    "handoff_id": "handoff-c",
                    "parent_task_id": "task-parallel-limit",
                    "subtask_id": "sub-03",
                    "subagent_role": "verification_runner",
                },
                {
                    "handoff_id": "handoff-a",
                    "parent_task_id": "task-parallel-limit",
                    "subtask_id": "sub-01",
                    "subagent_role": "diagnostics_reviewer",
                },
                {
                    "handoff_id": "handoff-b",
                    "parent_task_id": "task-parallel-limit",
                    "subtask_id": "sub-02",
                    "subagent_role": "repair_specialist",
                },
            ]
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-parallel-limit",
            "task": {
                "task_id": "task-parallel-limit",
                "task_type": "run",
                "prompt": "execute independent subtasks",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Execute independent branches",
                    "subtasks": [
                        {"subtask_id": "sub-01", "title": "A", "stage": "analysis"},
                        {"subtask_id": "sub-02", "title": "B", "stage": "validation"},
                        {"subtask_id": "sub-03", "title": "C", "stage": "repair"},
                    ],
                    "decomposition_policy": {
                        "strategy": "parallel",
                        "max_parallel_branches": 2,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-parallel-limit",
        }
    )

    started_state = runtime.start(state)
    task = started_state.tasks[0]
    assert len(task.handoffs) == 2
    assert [item.handoff_id for item in task.handoffs] == ["handoff-a", "handoff-b"]

    parallel = task.metadata["parallel_execution"]
    assert parallel["max_parallel_branches"] == 2
    assert parallel["active_handoff_ids"] == ["handoff-a", "handoff-b"]
    assert parallel["deferred_handoff_ids"] == ["handoff-c"]
    assert parallel["merge_rule"] == "deterministic_by_subtask_then_handoff_id"


def test_graph_runtime_bounded_parallel_branches_enforce_deterministic_return_merge_order():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.graph.state import GraphState

    class FakeGraph:
        def invoke(self, payload):
            task = dict(payload["tasks"][0])
            task["handoffs"] = [
                {
                    "handoff_id": "handoff-2",
                    "parent_task_id": "task-parallel-merge",
                    "subtask_id": "sub-02",
                    "subagent_role": "verification_runner",
                },
                {
                    "handoff_id": "handoff-1",
                    "parent_task_id": "task-parallel-merge",
                    "subtask_id": "sub-01",
                    "subagent_role": "diagnostics_reviewer",
                },
                {
                    "handoff_id": "handoff-3",
                    "parent_task_id": "task-parallel-merge",
                    "subtask_id": "sub-03",
                    "subagent_role": "repair_specialist",
                },
            ]
            task["returns"] = [
                {
                    "handoff_id": "handoff-3",
                    "subagent_role": "repair_specialist",
                    "status": "success",
                    "summary": "C done",
                },
                {
                    "handoff_id": "handoff-1",
                    "subagent_role": "diagnostics_reviewer",
                    "status": "success",
                    "summary": "A done",
                },
                {
                    "handoff_id": "handoff-2",
                    "subagent_role": "verification_runner",
                    "status": "success",
                    "summary": "B done",
                },
            ]
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    runtime = GraphRuntime(graph_factory=lambda: FakeGraph())
    state = GraphState.from_mapping(
        {
            "run_id": "run-parallel-merge",
            "task": {
                "task_id": "task-parallel-merge",
                "task_type": "run",
                "prompt": "execute independent subtasks",
                "workspace": "/workspace/demo",
                "lead_task_plan": {
                    "objective": "Execute independent branches",
                    "subtasks": [
                        {"subtask_id": "sub-01", "title": "A", "stage": "analysis"},
                        {"subtask_id": "sub-02", "title": "B", "stage": "validation"},
                        {"subtask_id": "sub-03", "title": "C", "stage": "repair"},
                    ],
                    "decomposition_policy": {
                        "strategy": "parallel",
                        "max_parallel_branches": 2,
                        "allow_llm_fallback": False,
                    },
                },
            },
            "active_task_id": "task-parallel-merge",
        }
    )

    started_state = runtime.start(state)
    task = started_state.tasks[0]
    parallel = task.metadata["parallel_execution"]

    assert parallel["merge_order"] == ["handoff-1", "handoff-2", "handoff-3"]
    assert parallel["merged_return_order"] == ["handoff-1", "handoff-2", "handoff-3"]
    assert [item.handoff_id for item in task.returns] == ["handoff-1", "handoff-2", "handoff-3"]


def test_graph_runtime_e2e_single_stage_reaches_final_outcome_with_relevant_subagent_only():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            route = payload["tasks"][0]["metadata"]["supervisor_route"]
            selected_roles = [entry["role"] for entry in route["subagent_selection"]]
            assert selected_roles == ["verification_runner"]

            task = dict(payload["tasks"][0])
            task["handoffs"] = [
                {
                    "handoff_id": "handoff-verify",
                    "parent_task_id": task["task_id"],
                    "subtask_id": "sub-verify",
                    "subagent_role": "verification_runner",
                    "capability_tags": ["eda.run"],
                }
            ]
            task["returns"] = [
                {
                    "handoff_id": "handoff-verify",
                    "subagent_role": "verification_runner",
                    "status": "success",
                    "summary": "verification passed",
                }
            ]
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    state = service.start_run_task(
        prompt="close verification issues",
        workspace="/workspace/demo",
        run_id="run-e2e-single-stage",
        task_id="task-e2e-single-stage",
        lead_task_plan={
            "objective": "Run verification and finish",
            "subtasks": [
                {
                    "subtask_id": "sub-verify",
                    "title": "Run verification",
                    "stage": "validation",
                    "required_capabilities": ["eda.run"],
                }
            ],
            "decomposition_policy": {
                "strategy": "sequential",
                "max_parallel_branches": 1,
                "allow_llm_fallback": False,
            },
        },
    )

    task = state.tasks[0]
    route = task.metadata["supervisor_route"]
    assert route["selected_subgraphs"] == ["verification"]
    assert [entry["role"] for entry in route["subagent_selection"]] == ["verification_runner"]
    assert task.metadata["lead_monitor"]["decision"] == "complete"


def test_graph_runtime_e2e_multi_stage_reaches_final_outcome_with_only_relevant_subagents():
    from saxoflow.graph.runtime import GraphRuntime
    from saxoflow.services.workflow_service import WorkflowService

    class FakeGraph:
        def invoke(self, payload):
            route = payload["tasks"][0]["metadata"]["supervisor_route"]
            selected_roles = {entry["role"] for entry in route["subagent_selection"]}
            assert selected_roles == {
                "context_intake_specialist",
                "diagnostics_reviewer",
                "verification_runner",
                "repair_specialist",
            }

            task = dict(payload["tasks"][0])
            task["handoffs"] = [
                {
                    "handoff_id": "handoff-repair",
                    "parent_task_id": task["task_id"],
                    "subtask_id": "sub-repair",
                    "subagent_role": "repair_specialist",
                },
                {
                    "handoff_id": "handoff-analysis",
                    "parent_task_id": task["task_id"],
                    "subtask_id": "sub-analysis",
                    "subagent_role": "context_intake_specialist",
                },
                {
                    "handoff_id": "handoff-verify",
                    "parent_task_id": task["task_id"],
                    "subtask_id": "sub-validate",
                    "subagent_role": "verification_runner",
                },
            ]
            task["returns"] = [
                {
                    "handoff_id": "handoff-verify",
                    "subagent_role": "verification_runner",
                    "status": "success",
                    "summary": "verification passed",
                },
                {
                    "handoff_id": "handoff-analysis",
                    "subagent_role": "context_intake_specialist",
                    "status": "success",
                    "summary": "analysis complete",
                },
                {
                    "handoff_id": "handoff-repair",
                    "subagent_role": "repair_specialist",
                    "status": "success",
                    "summary": "repair complete",
                },
            ]
            return {
                "run_id": payload["run_id"],
                "tasks": [task],
                "active_task_id": payload["active_task_id"],
            }

    service = WorkflowService(runtime=GraphRuntime(graph_factory=lambda: FakeGraph()))
    state = service.start_run_task(
        prompt="run analysis, validation, and repair",
        workspace="/workspace/demo",
        run_id="run-e2e-multi-stage",
        task_id="task-e2e-multi-stage",
        lead_task_plan={
            "objective": "Close all issues across stages",
            "subtasks": [
                {
                    "subtask_id": "sub-analysis",
                    "title": "Analyze diagnostics",
                    "stage": "analysis",
                    "required_capabilities": ["context.read", "report.read"],
                },
                {
                    "subtask_id": "sub-validate",
                    "title": "Run verification",
                    "stage": "validation",
                    "required_capabilities": ["eda.run"],
                },
                {
                    "subtask_id": "sub-repair",
                    "title": "Repair findings",
                    "stage": "repair",
                    "required_capabilities": ["file.edit"],
                },
            ],
            "decomposition_policy": {
                "strategy": "parallel",
                "max_parallel_branches": 2,
                "allow_llm_fallback": False,
            },
        },
    )

    task = state.tasks[0]
    route = task.metadata["supervisor_route"]
    assert route["selected_subgraphs"] == [
        "context_intake",
        "diagnostics_review",
        "repair",
        "verification",
    ]
    assert {entry["role"] for entry in route["subagent_selection"]} == {
        "context_intake_specialist",
        "diagnostics_reviewer",
        "verification_runner",
        "repair_specialist",
    }
    assert all(entry["role"] != "general-purpose" for entry in route["subagent_selection"])
    assert task.metadata["lead_monitor"]["decision"] == "complete"
