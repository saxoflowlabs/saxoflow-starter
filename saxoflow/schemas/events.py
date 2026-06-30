"""Graph event schema for workflow runtime progress and observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


class GraphEventSchemaError(ValueError):
    """Raised when a graph event payload is missing required fields or malformed."""


ALLOWED_GRAPH_EVENT_TYPES = {
    "node_start",
    "node_end",
    "tool_run_start",
    "tool_run_update",
    "tool_run_end",
    "approval_request",
    "artifact_created",
    "diagnostic_summary",
    "retry",
    "block",
    "llm_call_start",
    "llm_call_end",
}

ALLOWED_SUBAGENT_RETURN_STATUSES = {"success", "failed", "blocked", "cancelled"}


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphEventSchemaError(f"Graph event field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GraphEventSchemaError(
            f"Graph event field `{field_name}` must be a non-empty string."
        )
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise GraphEventSchemaError(
            f"Graph event field `{field_name}` must be a non-negative integer when set."
        )
    return value


def _string_list(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list):
        raise GraphEventSchemaError(f"Graph event field `{field_name}` must be a list of strings.")
    return tuple(_as_string(item, field_name) for item in value)


@dataclass(frozen=True)
class SubagentHandoff:
    """Typed handoff payload from lead orchestrator to a selected subagent."""

    handoff_id: str
    parent_task_id: str
    subtask_id: str
    subagent_role: str
    capability_tags: Tuple[str, ...] = field(default_factory=tuple)
    rationale: Optional[str] = None
    payload: Mapping[str, Any] = field(default_factory=dict)
    requested_artifact_kinds: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SubagentHandoff":
        data = _as_mapping(raw, "subagent_handoff")
        payload = data.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise GraphEventSchemaError("Graph event field `subagent_handoff.payload` must be a mapping.")

        return cls(
            handoff_id=_as_string(data.get("handoff_id"), "subagent_handoff.handoff_id"),
            parent_task_id=_as_string(
                data.get("parent_task_id"), "subagent_handoff.parent_task_id"
            ),
            subtask_id=_as_string(data.get("subtask_id"), "subagent_handoff.subtask_id"),
            subagent_role=_as_string(data.get("subagent_role"), "subagent_handoff.subagent_role"),
            capability_tags=_string_list(
                data.get("capability_tags"), "subagent_handoff.capability_tags"
            ),
            rationale=_optional_string(data.get("rationale"), "subagent_handoff.rationale"),
            payload=dict(payload),
            requested_artifact_kinds=_string_list(
                data.get("requested_artifact_kinds"),
                "subagent_handoff.requested_artifact_kinds",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "handoff_id": self.handoff_id,
            "parent_task_id": self.parent_task_id,
            "subtask_id": self.subtask_id,
            "subagent_role": self.subagent_role,
            "capability_tags": list(self.capability_tags),
            "payload": dict(self.payload),
            "requested_artifact_kinds": list(self.requested_artifact_kinds),
        }
        if self.rationale is not None:
            data["rationale"] = self.rationale
        return data


@dataclass(frozen=True)
class SubagentReturn:
    """Typed return payload emitted by a subagent after processing one handoff."""

    handoff_id: str
    subagent_role: str
    status: str
    summary: str
    capability_tags: Tuple[str, ...] = field(default_factory=tuple)
    artifact_refs: Tuple[str, ...] = field(default_factory=tuple)
    diagnostic_refs: Tuple[str, ...] = field(default_factory=tuple)
    payload: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SubagentReturn":
        data = _as_mapping(raw, "subagent_return")
        status = _as_string(data.get("status"), "subagent_return.status").lower()
        if status not in ALLOWED_SUBAGENT_RETURN_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_SUBAGENT_RETURN_STATUSES))
            raise GraphEventSchemaError(
                "Graph event field `subagent_return.status` must be one of: " + allowed + "."
            )

        payload = data.get("payload") or {}
        if not isinstance(payload, Mapping):
            raise GraphEventSchemaError("Graph event field `subagent_return.payload` must be a mapping.")

        return cls(
            handoff_id=_as_string(data.get("handoff_id"), "subagent_return.handoff_id"),
            subagent_role=_as_string(data.get("subagent_role"), "subagent_return.subagent_role"),
            status=status,
            summary=_as_string(data.get("summary"), "subagent_return.summary"),
            capability_tags=_string_list(
                data.get("capability_tags"), "subagent_return.capability_tags"
            ),
            artifact_refs=_string_list(data.get("artifact_refs"), "subagent_return.artifact_refs"),
            diagnostic_refs=_string_list(
                data.get("diagnostic_refs"), "subagent_return.diagnostic_refs"
            ),
            payload=dict(payload),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "subagent_role": self.subagent_role,
            "status": self.status,
            "summary": self.summary,
            "capability_tags": list(self.capability_tags),
            "artifact_refs": list(self.artifact_refs),
            "diagnostic_refs": list(self.diagnostic_refs),
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class GraphEvent:
    """Public event payload for graph lifecycle, tool, and approval progress."""

    event_id: str
    run_id: str
    timestamp: str
    phase: str
    node: str
    event_type: str
    user_message: Optional[str] = None
    detail_level: Optional[str] = None
    context_refs: Tuple[str, ...] = field(default_factory=tuple)
    artifact_refs: Tuple[str, ...] = field(default_factory=tuple)
    diagnostic_refs: Tuple[str, ...] = field(default_factory=tuple)
    elapsed_ms: Optional[int] = None
    progress_current: Optional[int] = None
    progress_total: Optional[int] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "GraphEvent":
        data = _as_mapping(raw, "graph_event")

        event_type = _as_string(data.get("event_type"), "graph_event.event_type").lower()
        if event_type not in ALLOWED_GRAPH_EVENT_TYPES:
            allowed = ", ".join(sorted(ALLOWED_GRAPH_EVENT_TYPES))
            raise GraphEventSchemaError(
                f"Graph event field `graph_event.event_type` must be one of: {allowed}."
            )

        progress_current = _optional_int(data.get("progress_current"), "graph_event.progress_current")
        progress_total = _optional_int(data.get("progress_total"), "graph_event.progress_total")
        if (progress_current is None) != (progress_total is None):
            raise GraphEventSchemaError(
                "Graph event progress fields must be set together: "
                "`graph_event.progress_current` and `graph_event.progress_total`."
            )
        if progress_total is not None and progress_total < 1:
            raise GraphEventSchemaError(
                "Graph event field `graph_event.progress_total` must be at least 1 when set."
            )
        if progress_current is not None and progress_total is not None and progress_current > progress_total:
            raise GraphEventSchemaError(
                "Graph event field `graph_event.progress_current` cannot exceed "
                "`graph_event.progress_total`."
            )

        return cls(
            event_id=_as_string(data.get("event_id"), "graph_event.event_id"),
            run_id=_as_string(data.get("run_id"), "graph_event.run_id"),
            timestamp=_as_string(data.get("timestamp"), "graph_event.timestamp"),
            phase=_as_string(data.get("phase"), "graph_event.phase"),
            node=_as_string(data.get("node"), "graph_event.node"),
            event_type=event_type,
            user_message=_optional_string(data.get("user_message"), "graph_event.user_message"),
            detail_level=_optional_string(data.get("detail_level"), "graph_event.detail_level"),
            context_refs=_string_list(data.get("context_refs"), "graph_event.context_refs"),
            artifact_refs=_string_list(data.get("artifact_refs"), "graph_event.artifact_refs"),
            diagnostic_refs=_string_list(data.get("diagnostic_refs"), "graph_event.diagnostic_refs"),
            elapsed_ms=_optional_int(data.get("elapsed_ms"), "graph_event.elapsed_ms"),
            progress_current=progress_current,
            progress_total=progress_total,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "node": self.node,
            "event_type": self.event_type,
            "context_refs": list(self.context_refs),
            "artifact_refs": list(self.artifact_refs),
            "diagnostic_refs": list(self.diagnostic_refs),
        }
        if self.user_message is not None:
            data["user_message"] = self.user_message
        if self.detail_level is not None:
            data["detail_level"] = self.detail_level
        if self.elapsed_ms is not None:
            data["elapsed_ms"] = self.elapsed_ms
        if self.progress_current is not None:
            data["progress_current"] = self.progress_current
        if self.progress_total is not None:
            data["progress_total"] = self.progress_total
        return data
