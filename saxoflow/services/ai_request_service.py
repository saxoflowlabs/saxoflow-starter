"""Grounded request-envelope helpers for explicit AI task entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from saxoflow.graph.runtime import GraphRuntime
from saxoflow.schemas.context import ContextBundle, ContextRef
from saxoflow.services.context_service import ContextService
from saxoflow.services.workflow_service import WorkflowService
from saxoflow_agenticai.core.agent_registry import AgentRegistry, AgentRegistryError
from saxoflow_agenticai.core.prompt_registry import PromptRegistry, PromptRegistryError


class AIRequestServiceError(ValueError):
    """Raised when an explicit AI request cannot be grounded safely."""


class _PassThroughGraph:
    """Minimal graph used to persist grounded request envelopes during Phase P6.04a."""

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return dict(payload)


@dataclass(frozen=True)
class AIRequestService:
    """Resolve explicit AI metadata into workflow-ready grounded request state."""

    workspace_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "workspace_root", Path(self.workspace_root).expanduser().resolve())

    def build_workflow_service(self) -> WorkflowService:
        return WorkflowService(runtime=GraphRuntime(graph_factory=lambda: _PassThroughGraph()))

    def resolve_context_bundle(
        self,
        requested_context_paths: list[str],
        *,
        task_type: str,
    ) -> Optional[ContextBundle]:
        if not requested_context_paths:
            return None

        context_service = ContextService.from_workspace(self.workspace_root)
        refs = []
        for raw_path in requested_context_paths:
            try:
                resolved_path = context_service.resolve_path(raw_path)
            except ValueError as exc:
                raise AIRequestServiceError(str(exc)) from exc
            refs.append(
                ContextRef(
                    path=str(raw_path),
                    kind="directory" if resolved_path.is_dir() else "file",
                    source=f"tui-explicit-{task_type}",
                )
            )

        return context_service.resolve_bundle(
            ContextBundle(
                workspace_root=str(self.workspace_root),
                references=tuple(refs),
                notes=f"Explicit TUI {task_type} request",
            )
        )

    def resolve_request_metadata(
        self,
        task_type: str,
        request_metadata: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        resolved = dict(request_metadata)
        requested_agent = str(resolved.get("requested_agent") or "").strip()

        agent_registry = AgentRegistry.from_mapping(None)
        if requested_agent:
            try:
                resolved["agent_contract"] = agent_registry.get_builtin_agent_metadata(requested_agent)
            except AgentRegistryError:
                resolved["agent_contract"] = {
                    "agent_name": requested_agent,
                    "registration_source": "requested-unresolved",
                    "task_type": task_type,
                }

        prompt_registry = PromptRegistry.builtins()
        prompt_provenance = {
            "registry_source_path": str(prompt_registry.source_path),
            "prompt_dir": str(prompt_registry.prompt_dir),
            "selected_bundle": None,
        }
        if requested_agent:
            try:
                prompt_provenance["selected_bundle"] = prompt_registry.get(requested_agent).to_dict()
            except PromptRegistryError:
                pass
        resolved["prompt_provenance"] = prompt_provenance
        return resolved

    def start_grounded_task(
        self,
        task_type: str,
        prompt: str,
        *,
        metadata: Optional[Mapping[str, Any]] = None,
    ):
        request_metadata = dict(metadata or {})
        requested_context_paths = list(request_metadata.get("requested_context_paths") or [])
        context_bundle = self.resolve_context_bundle(requested_context_paths, task_type=task_type)
        resolved_metadata = self.resolve_request_metadata(task_type, request_metadata)

        workflow_service = self.build_workflow_service()
        starter_name = {
            "ask": "start_ask_task",
            "plan": "start_plan_task",
            "run": "start_run_task",
            "research": "start_research_task",
        }.get(task_type)
        start_task = getattr(workflow_service, starter_name, None) if starter_name else None
        if start_task is None:
            raise AIRequestServiceError(f"Unsupported AI task type `{task_type}`.")

        return start_task(
            prompt=prompt,
            workspace=str(self.workspace_root),
            context_bundle=context_bundle,
            metadata=resolved_metadata,
        )