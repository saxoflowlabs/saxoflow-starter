"""Graph runtime service scaffolding for SaxoFlow workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Set, Tuple

from saxoflow.graph.state import GraphState, GraphStateSchemaError, GraphTaskState
from saxoflow.services.policy_service import WebResearchRoutingPolicy
from saxoflow_agenticai.core.agent_registry import AgentRegistry, AgentRegistryError


STAGE_TO_SUBGRAPHS: Mapping[str, Tuple[str, ...]] = {
    "analysis": ("context_intake", "diagnostics_review"),
    "generation": ("design_generation",),
    "validation": ("verification",),
    "repair": ("repair",),
}

CAPABILITY_TO_SUBGRAPH: Mapping[str, str] = {
    "context.read": "context_intake",
    "file.read": "context_intake",
    "report.read": "diagnostics_review",
    "eda.run": "verification",
    "test.run": "verification",
    "file.edit": "repair",
    "file.write": "repair",
    "web.search": "web_research",
    "web.fetch": "web_research",
}

BASE_SUBAGENT_ROLE_CATALOG: Mapping[str, Mapping[str, Any]] = {
    "context_intake": {
        "role": "context_intake_specialist",
        "role_type": "domain",
        "capability_tags": ("context.read", "file.read"),
    },
    "diagnostics_review": {
        "role": "diagnostics_reviewer",
        "role_type": "domain",
        "capability_tags": ("report.read",),
    },
    "design_generation": {
        "role": "design_generator",
        "role_type": "domain",
        "capability_tags": ("file.write",),
    },
    "verification": {
        "role": "verification_runner",
        "role_type": "domain",
        "capability_tags": ("eda.run", "test.run", "report.read"),
    },
    "repair": {
        "role": "repair_specialist",
        "role_type": "domain",
        "capability_tags": ("file.edit", "file.write", "test.run"),
    },
    "web_research": {
        "role": "web_research_specialist",
        "role_type": "domain",
        "capability_tags": ("web.search", "web.fetch", "report.read"),
    },
    "general_purpose_fallback": {
        "role": "general-purpose",
        "role_type": "generic",
        "capability_tags": ("context.read", "file.read", "artifact.read", "report.read"),
    },
}


class GraphRuntimeError(ValueError):
    """Raised when a graph cannot be constructed or started."""


class GraphCheckpointer(Protocol):
    """Protocol for saving and loading graph state snapshots by run ID."""

    def save(self, state: GraphState) -> None:
        """Persist a graph state snapshot."""

    def load(self, run_id: str) -> GraphState:
        """Load a previously persisted graph state snapshot."""


@dataclass
class LocalGraphCheckpointer:
    """Simple in-memory checkpointer used for local runtime durability tests."""

    _store: Dict[str, Dict[str, Any]]

    def __init__(self) -> None:
        self._store = {}

    def save(self, state: GraphState) -> None:
        self._store[state.run_id] = state.to_dict()

    def load(self, run_id: str) -> GraphState:
        snapshot = self._store.get(run_id)
        if snapshot is None:
            raise GraphRuntimeError(f"No checkpoint exists for run_id `{run_id}`.")
        try:
            return GraphState.from_mapping(snapshot)
        except GraphStateSchemaError as exc:
            raise GraphRuntimeError(str(exc)) from exc


@dataclass
class GraphRuntime:
    """Thin runtime wrapper that starts one graph invocation from GraphState."""

    graph_factory: Optional[Callable[[], Any]] = None
    checkpointer: Optional[GraphCheckpointer] = None

    def build_graph(self) -> Any:
        """Construct and return the underlying graph object."""
        if self.graph_factory is None:
            raise GraphRuntimeError("Graph runtime is not configured with a graph factory.")

        graph = self.graph_factory()
        if graph is None:
            raise GraphRuntimeError("Graph factory returned no graph instance.")
        return graph

    def start(self, state: GraphState) -> GraphState:
        """Start the graph from a validated GraphState payload."""
        state = self.apply_supervisor_routing(state)
        graph = self.build_graph()
        payload = state.to_dict()
        result = self._invoke_graph(graph, payload)

        if isinstance(result, GraphState):
            result = self.apply_bounded_parallel_branches(result)
            result = self.apply_lead_monitor_loop(result)
            self.save_checkpoint(result)
            return result
        if not isinstance(result, Mapping):
            raise GraphRuntimeError("Graph invocation result must be a mapping or GraphState.")

        try:
            started_state = GraphState.from_mapping(dict(result))
        except GraphStateSchemaError as exc:
            raise GraphRuntimeError(str(exc)) from exc
        started_state = self.apply_bounded_parallel_branches(started_state)
        started_state = self.apply_lead_monitor_loop(started_state)
        self.save_checkpoint(started_state)
        return started_state

    def apply_bounded_parallel_branches(self, state: GraphState) -> GraphState:
        """Enforce branch concurrency bounds and deterministic merge ordering."""
        bounded_tasks = []
        for task in state.tasks:
            if task.lead_task_plan is None or not task.handoffs:
                bounded_tasks.append(task)
                continue

            max_parallel = max(1, task.lead_task_plan.decomposition_policy.max_parallel_branches)
            ordered_handoffs = tuple(
                sorted(task.handoffs, key=lambda item: (item.subtask_id, item.handoff_id, item.subagent_role))
            )
            active_handoffs = ordered_handoffs[:max_parallel]
            deferred_handoffs = ordered_handoffs[max_parallel:]

            active_ids = [item.handoff_id for item in active_handoffs]
            deferred_ids = [item.handoff_id for item in deferred_handoffs]
            merge_order = active_ids + deferred_ids

            merge_index = {handoff_id: idx for idx, handoff_id in enumerate(merge_order)}
            ordered_returns = tuple(
                sorted(
                    task.returns,
                    key=lambda item: (
                        merge_index.get(item.handoff_id, len(merge_index)),
                        item.handoff_id,
                        item.subagent_role,
                    ),
                )
            )

            metadata = dict(task.metadata)
            metadata["parallel_execution"] = {
                "max_parallel_branches": max_parallel,
                "active_handoff_ids": active_ids,
                "deferred_handoff_ids": deferred_ids,
                "merge_order": merge_order,
                "merged_return_order": [item.handoff_id for item in ordered_returns],
                "merge_rule": "deterministic_by_subtask_then_handoff_id",
            }

            updated_task = GraphTaskState.from_mapping(
                {
                    **task.to_dict(),
                    "handoffs": [item.to_dict() for item in active_handoffs],
                    "returns": [item.to_dict() for item in ordered_returns],
                    "metadata": metadata,
                }
            )
            bounded_tasks.append(updated_task)

        return GraphState(
            run_id=state.run_id,
            tasks=tuple(bounded_tasks),
            active_task_id=state.active_task_id,
            context_bundle=state.context_bundle,
        )

    def apply_lead_monitor_loop(self, state: GraphState) -> GraphState:
        """Attach lead-monitor decision metadata for retry, escalation, and completion."""
        monitored_tasks = []
        for task in state.tasks:
            monitor = self._monitor_decision_for_task(task)
            if monitor is None:
                monitored_tasks.append(task)
                continue

            metadata = dict(task.metadata)
            metadata["lead_monitor"] = monitor
            updated_task = GraphTaskState.from_mapping({**task.to_dict(), "metadata": metadata})
            monitored_tasks.append(updated_task)

        return GraphState(
            run_id=state.run_id,
            tasks=tuple(monitored_tasks),
            active_task_id=state.active_task_id,
            context_bundle=state.context_bundle,
        )

    @staticmethod
    def _monitor_decision_for_task(task: GraphTaskState) -> Optional[Dict[str, Any]]:
        if not task.returns:
            return None

        existing_monitor = dict(task.metadata).get("lead_monitor")
        if isinstance(existing_monitor, Mapping):
            retries_used = int(existing_monitor.get("retries_used", 0) or 0)
            retry_budget = int(existing_monitor.get("retry_budget", 1) or 1)
        else:
            retries_used = 0
            retry_budget = 1

        statuses = {item.status for item in task.returns}
        if statuses and statuses.issubset({"success"}):
            return {
                "decision": "complete",
                "retry_budget": retry_budget,
                "retries_used": retries_used,
                "rationale": "all subagent returns completed successfully",
            }

        if "failed" in statuses or "blocked" in statuses:
            if retries_used < retry_budget:
                return {
                    "decision": "retry",
                    "retry_budget": retry_budget,
                    "retries_used": retries_used + 1,
                    "rationale": "subagent return failure detected; retry budget available",
                }
            return {
                "decision": "escalate",
                "retry_budget": retry_budget,
                "retries_used": retries_used,
                "rationale": "subagent return failure detected; retry budget exhausted",
            }

        if "cancelled" in statuses:
            return {
                "decision": "escalate",
                "retry_budget": retry_budget,
                "retries_used": retries_used,
                "rationale": "subagent return was cancelled and requires escalation",
            }

        return None

    def apply_supervisor_routing(self, state: GraphState) -> GraphState:
        """Attach policy-first route metadata to the active task when lead plan is present."""
        if state.active_task_id is None:
            return state

        routed_tasks = []
        for task in state.tasks:
            if task.task_id != state.active_task_id or task.lead_task_plan is None:
                routed_tasks.append(task)
                continue

            selected_subgraphs, fallback_used, rationale, web_policy = self._select_subgraphs(task)
            role_catalog, fallback_contract = self._resolve_subagent_role_catalog(task)
            subagent_catalog = self._build_subagent_catalog(
                selected_subgraphs=selected_subgraphs,
                selected_rationale=rationale,
                role_catalog=role_catalog,
            )
            selected_subagents = [entry for entry in subagent_catalog if entry["selected"]]

            metadata = dict(task.metadata)
            metadata["supervisor_route"] = {
                "selected_subgraphs": list(selected_subgraphs),
                "policy": "policy-first",
                "fallback_used": fallback_used,
                "rationale": rationale,
                "web_research_policy": web_policy,
                "fallback_contract": fallback_contract,
                "subagent_catalog": subagent_catalog,
                "subagent_selection": selected_subagents,
            }

            updated_task = GraphTaskState.from_mapping(
                {
                    **task.to_dict(),
                    "metadata": metadata,
                }
            )
            routed_tasks.append(updated_task)

        return GraphState(
            run_id=state.run_id,
            tasks=tuple(routed_tasks),
            active_task_id=state.active_task_id,
            context_bundle=state.context_bundle,
        )

    @staticmethod
    def _build_subagent_catalog(
        *,
        selected_subgraphs: Tuple[str, ...],
        selected_rationale: str,
        role_catalog: Mapping[str, Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        selected = set(selected_subgraphs)
        catalog: List[Dict[str, Any]] = []

        for subgraph_name, descriptor in role_catalog.items():
            is_selected = subgraph_name in selected
            rationale = selected_rationale
            if not is_selected:
                rationale = "not selected by policy-first routing for this task"

            catalog.append(
                {
                    "subgraph": subgraph_name,
                    "role": descriptor["role"],
                    "role_type": descriptor["role_type"],
                    "capability_tags": list(descriptor["capability_tags"]),
                    "selected": is_selected,
                    "selection_rationale": rationale,
                }
            )

        return catalog

    @staticmethod
    def _resolve_subagent_role_catalog(
        task: GraphTaskState,
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
        metadata = dict(task.metadata)
        raw_profiles = metadata.get("agent_profiles")
        if raw_profiles is not None and not isinstance(raw_profiles, Mapping):
            raise GraphRuntimeError("Task metadata field `agent_profiles` must be a mapping when set.")

        try:
            registry = AgentRegistry.from_mapping(raw_profiles if isinstance(raw_profiles, Mapping) else None)
            fallback_profile = registry.resolve_general_purpose_profile()
        except AgentRegistryError as exc:
            raise GraphRuntimeError(str(exc)) from exc

        catalog = {
            key: {
                "role": str(value["role"]),
                "role_type": str(value["role_type"]),
                "capability_tags": tuple(value["capability_tags"]),
            }
            for key, value in BASE_SUBAGENT_ROLE_CATALOG.items()
        }
        catalog["general_purpose_fallback"] = {
            "role": str(fallback_profile["role"]),
            "role_type": str(fallback_profile["role_type"]),
            "capability_tags": tuple(fallback_profile["capability_tags"]),
        }
        fallback_contract = {
            "profile_name": "general-purpose",
            "replacement_source": str(fallback_profile["replacement_source"]),
            "replaced_builtin": bool(fallback_profile["replaced_builtin"]),
            "role": str(fallback_profile["role"]),
            "role_type": str(fallback_profile["role_type"]),
            "capability_tags": list(fallback_profile["capability_tags"]),
        }
        return catalog, fallback_contract

    @staticmethod
    def _select_subgraphs(
        task: GraphTaskState,
    ) -> Tuple[Tuple[str, ...], bool, str, Dict[str, Any]]:
        assert task.lead_task_plan is not None

        web_policy = GraphRuntime._resolve_web_research_policy(task)

        stage_selection: Set[str] = set()
        stages = {subtask.stage for subtask in task.lead_task_plan.subtasks}
        for stage in stages:
            stage_selection.update(STAGE_TO_SUBGRAPHS.get(stage, ()))
        if stage_selection:
            return (
                tuple(sorted(stage_selection)),
                False,
                "policy-first stage routing selected subgraphs from lead task stages",
                web_policy,
            )

        capability_selection: Set[str] = set()
        for subtask in task.lead_task_plan.subtasks:
            for capability in subtask.required_capabilities:
                mapped = CAPABILITY_TO_SUBGRAPH.get(capability)
                if mapped is not None:
                    if mapped == "web_research" and not bool(web_policy.get("allowed", False)):
                        continue
                    capability_selection.add(mapped)
        if capability_selection:
            rationale = "policy-first capability routing selected subgraphs from required capabilities"
            if "web_research" in capability_selection and bool(web_policy.get("requested", False)):
                rationale += "; web-research was policy-approved"
            return (
                tuple(sorted(capability_selection)),
                False,
                rationale,
                web_policy,
            )

        if bool(web_policy.get("blocked", False)):
            blocked_rationale = str(web_policy.get("reason") or "web-research blocked by policy")
            if task.lead_task_plan.decomposition_policy.allow_llm_fallback:
                return (
                    ("general_purpose_fallback",),
                    True,
                    blocked_rationale + "; selected general-purpose fallback",
                    web_policy,
                )
            return tuple(), False, blocked_rationale, web_policy

        if task.lead_task_plan.decomposition_policy.allow_llm_fallback:
            return (
                ("general_purpose_fallback",),
                True,
                "policy routing was ambiguous; selected general-purpose fallback",
                web_policy,
            )

        return (
            tuple(),
            False,
            "policy routing was ambiguous and fallback was disabled",
            web_policy,
        )

    @staticmethod
    def _resolve_web_research_policy(task: GraphTaskState) -> Dict[str, Any]:
        metadata = dict(task.metadata)
        raw_policy = metadata.get("web_research_policy")
        policy_map: Dict[str, Any] = {}
        if isinstance(raw_policy, Mapping):
            policy_map = dict(raw_policy)

        policy = WebResearchRoutingPolicy(
            allow_web_research=bool(policy_map.get("allow_web_research", False)),
            approved_capabilities=tuple(policy_map.get("approved_capabilities", ("web.search", "web.fetch"))),
        )
        requested_capabilities = [
            capability
            for subtask in task.lead_task_plan.subtasks
            for capability in subtask.required_capabilities
        ]
        return policy.evaluate(requested_capabilities).to_dict()

    def save_checkpoint(self, state: GraphState) -> None:
        """Persist the current graph state if a checkpointer is configured."""
        if self.checkpointer is None:
            return
        self.checkpointer.save(state)

    def load_checkpoint(self, run_id: str) -> GraphState:
        """Load a previously persisted graph state for a run ID."""
        if self.checkpointer is None:
            raise GraphRuntimeError("Graph runtime has no configured checkpointer.")
        return self.checkpointer.load(run_id)

    def resume(self, run_id: str) -> GraphState:
        """Resume a graph run from the latest checkpointed state."""
        state = self.load_checkpoint(run_id)
        return self.start(state)

    def start_from_mapping(self, raw_state: Mapping[str, Any]) -> GraphState:
        """Parse and start the graph from a raw state mapping."""
        try:
            state = GraphState.from_mapping(raw_state)
        except GraphStateSchemaError as exc:
            raise GraphRuntimeError(str(exc)) from exc
        return self.start(state)

    @staticmethod
    def _invoke_graph(graph: Any, payload: Dict[str, Any]) -> Any:
        """Invoke a graph via `.invoke(...)` or callable fallback."""
        invoke = getattr(graph, "invoke", None)
        if callable(invoke):
            return invoke(payload)
        if callable(graph):
            return graph(payload)
        raise GraphRuntimeError("Graph instance must expose `invoke(payload)` or be callable.")
