"""Graph runtime state schemas for SaxoFlow workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from saxoflow.schemas.agents import AgentSchemaError, LeadTaskPlan
from saxoflow.schemas.context import ContextBundle, ContextSchemaError
from saxoflow.schemas.events import GraphEventSchemaError, SubagentHandoff, SubagentReturn


class GraphStateSchemaError(ValueError):
    """Raised when graph state payloads are missing required data."""


ALLOWED_TASK_TYPES = {"ask", "plan", "run", "research", "resume"}
ALLOWED_TASK_STATUSES = {"pending", "running", "completed", "failed", "cancelled"}


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphStateSchemaError(f"Graph state field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphStateSchemaError(f"Graph state field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


@dataclass(frozen=True)
class GraphTaskState:
    """One graph-managed workflow task with normalized metadata."""

    task_id: str
    task_type: str
    prompt: str
    workspace: str
    status: str = "pending"
    thread_id: Optional[str] = None
    context_bundle: Optional[ContextBundle] = None
    lead_task_plan: Optional[LeadTaskPlan] = None
    handoffs: Tuple[SubagentHandoff, ...] = field(default_factory=tuple)
    returns: Tuple[SubagentReturn, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphTaskState":
        data = _as_mapping(raw, "graph_task")

        task_type = _as_string(data.get("task_type"), "graph_task.task_type").lower()
        if task_type not in ALLOWED_TASK_TYPES:
            allowed = ", ".join(sorted(ALLOWED_TASK_TYPES))
            raise GraphStateSchemaError(
                f"Graph state field `graph_task.task_type` must be one of: {allowed}."
            )

        status = _as_string(data.get("status", "pending"), "graph_task.status").lower()
        if status not in ALLOWED_TASK_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_TASK_STATUSES))
            raise GraphStateSchemaError(
                f"Graph state field `graph_task.status` must be one of: {allowed}."
            )

        context_bundle = None
        if data.get("context_bundle") is not None:
            try:
                context_bundle = ContextBundle.from_mapping(data.get("context_bundle"))
            except ContextSchemaError as exc:
                raise GraphStateSchemaError(str(exc)) from exc

        lead_task_plan = None
        if data.get("lead_task_plan") is not None:
            try:
                lead_task_plan = LeadTaskPlan.from_mapping(data.get("lead_task_plan"))
            except AgentSchemaError as exc:
                raise GraphStateSchemaError(str(exc)) from exc

        handoffs_raw = data.get("handoffs") or []
        if not isinstance(handoffs_raw, list):
            raise GraphStateSchemaError("Graph state field `graph_task.handoffs` must be a list.")
        try:
            handoffs = tuple(SubagentHandoff.from_mapping(item) for item in handoffs_raw)
        except GraphEventSchemaError as exc:
            raise GraphStateSchemaError(str(exc)) from exc

        returns_raw = data.get("returns") or []
        if not isinstance(returns_raw, list):
            raise GraphStateSchemaError("Graph state field `graph_task.returns` must be a list.")
        try:
            returns = tuple(SubagentReturn.from_mapping(item) for item in returns_raw)
        except GraphEventSchemaError as exc:
            raise GraphStateSchemaError(str(exc)) from exc

        metadata = data.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            raise GraphStateSchemaError("Graph state field `graph_task.metadata` must be a mapping.")

        outputs = data.get("outputs") or {}
        if not isinstance(outputs, Mapping):
            raise GraphStateSchemaError("Graph state field `graph_task.outputs` must be a mapping.")

        return cls(
            task_id=_as_string(data.get("task_id"), "graph_task.task_id"),
            task_type=task_type,
            prompt=_as_string(data.get("prompt"), "graph_task.prompt"),
            workspace=_as_string(data.get("workspace"), "graph_task.workspace"),
            status=status,
            thread_id=_optional_string(data.get("thread_id"), "graph_task.thread_id"),
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            handoffs=handoffs,
            returns=returns,
            metadata=dict(metadata),
            outputs=dict(outputs),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "workspace": self.workspace,
            "status": self.status,
            "metadata": dict(self.metadata),
            "outputs": dict(self.outputs),
        }
        if self.thread_id is not None:
            data["thread_id"] = self.thread_id
        if self.context_bundle is not None:
            data["context_bundle"] = self.context_bundle.to_dict()
        if self.lead_task_plan is not None:
            data["lead_task_plan"] = self.lead_task_plan.to_dict()
        if self.handoffs:
            data["handoffs"] = [handoff.to_dict() for handoff in self.handoffs]
        if self.returns:
            data["returns"] = [result.to_dict() for result in self.returns]
        return data


@dataclass(frozen=True)
class GraphState:
    """Top-level state container for the graph runtime."""

    run_id: str
    tasks: Tuple[GraphTaskState, ...] = field(default_factory=tuple)
    active_task_id: Optional[str] = None
    context_bundle: Optional[ContextBundle] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphState":
        data = _as_mapping(raw, "graph_state")
        tasks_raw = data.get("tasks")
        if tasks_raw is None and data.get("task") is not None:
            tasks_raw = [data.get("task")]
        if tasks_raw is None:
            tasks_raw = []
        if not isinstance(tasks_raw, list):
            raise GraphStateSchemaError("Graph state field `graph_state.tasks` must be a list.")

        tasks = tuple(GraphTaskState.from_mapping(item) for item in tasks_raw)
        active_task_id = _optional_string(data.get("active_task_id"), "graph_state.active_task_id")
        context_bundle = None
        if data.get("context_bundle") is not None:
            try:
                context_bundle = ContextBundle.from_mapping(data.get("context_bundle"))
            except ContextSchemaError as exc:
                raise GraphStateSchemaError(str(exc)) from exc

        if active_task_id is not None and active_task_id not in {task.task_id for task in tasks}:
            raise GraphStateSchemaError(
                "Graph state field `graph_state.active_task_id` must match one of the task IDs."
            )

        return cls(
            run_id=_as_string(data.get("run_id"), "graph_state.run_id"),
            tasks=tasks,
            active_task_id=active_task_id,
            context_bundle=context_bundle,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "run_id": self.run_id,
            "tasks": [task.to_dict() for task in self.tasks],
        }
        if self.active_task_id is not None:
            data["active_task_id"] = self.active_task_id
        if self.context_bundle is not None:
            data["context_bundle"] = self.context_bundle.to_dict()
        return data
