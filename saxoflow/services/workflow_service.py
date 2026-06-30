"""Workflow service entrypoints backed by the graph runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple
from uuid import uuid4

from saxoflow.graph.runtime import GraphRuntime
from saxoflow.graph.state import GraphState, GraphTaskState
from saxoflow.schemas.context import ContextBundle
from saxoflow.schemas.events import GraphEvent
from saxoflow_agenticai.core.usage import LLMUsage


@dataclass
class WorkflowService:
    """Service layer for starting graph-backed ask/plan/run/research tasks."""

    runtime: GraphRuntime
    _events_by_run: Dict[str, List[GraphEvent]] = field(default_factory=dict)

    def emit_event(self, raw_event: Mapping[str, Any]) -> GraphEvent:
        """Validate and store one graph event for ordered run-level streaming."""
        event = GraphEvent.from_mapping(raw_event)
        self._events_by_run.setdefault(event.run_id, []).append(event)
        return event

    def stream_events(self, run_id: str) -> Tuple[GraphEvent, ...]:
        """Return all stored events for a run in insertion order."""
        return tuple(self._events_by_run.get(run_id, ()))

    def stream_events_from_index(self, run_id: str, start_index: int) -> Tuple[GraphEvent, ...]:
        """Return ordered events for a run starting at a specific index."""
        if start_index < 0:
            raise ValueError("start_index must be a non-negative integer.")
        events = self._events_by_run.get(run_id, ())
        return tuple(events[start_index:])

    @staticmethod
    def _utc_timestamp() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _new_thread_id(task_type: str) -> str:
        return f"thread-{task_type}-{uuid4().hex}"

    @staticmethod
    def _context_refs(context_bundle: Optional[ContextBundle]) -> List[str]:
        if context_bundle is None:
            return []
        return [ref.path for ref in context_bundle.references]

    @staticmethod
    def _classify_run_adapter_scenario(
        *,
        prompt: str,
        requested_capabilities: Optional[List[str]] = None,
        requested_agent: Optional[str] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        requested = [str(item).strip() for item in (requested_capabilities or []) if str(item).strip()]
        if "eda.run" not in requested:
            return {
                "requested": False,
                "classification_status": "not_requested",
                "scenario": None,
                "adapter_module": None,
                "reason": "eda.run capability was not requested",
            }

        adapter_module_by_scenario = {
            "simulation": "saxoflow.tools.adapters.simulation",
            "synthesis": "saxoflow.tools.adapters.synthesis",
            "formal": "saxoflow.tools.adapters.formal",
            "pnr": "saxoflow.tools.adapters.pnr",
        }
        scores: Dict[str, int] = {
            "simulation": 0,
            "synthesis": 0,
            "formal": 0,
            "pnr": 0,
        }

        prompt_l = str(prompt or "").strip().lower()
        keyword_map = {
            "simulation": (
                "simulate",
                "simulation",
                "testbench",
                "test",
                "tests",
                "iverilog",
                "verilator",
                "wave",
            ),
            "synthesis": ("synth", "synthesis", "optimize area", "area", "timing", "qor", "yosys"),
            "formal": ("formal", "prove", "property", "assertion", "sby", "symbiyosys"),
            "pnr": ("pnr", "place", "route", "openroad", "floorplan", "cts", "gds"),
        }

        for scenario, keywords in keyword_map.items():
            for keyword in keywords:
                if keyword in prompt_l:
                    scores[scenario] += 1

        if "prototype tests" in prompt_l or "prototype test" in prompt_l:
            scores["simulation"] += 2

        agent_l = str(requested_agent or "").strip().lower()
        if agent_l:
            for scenario, keywords in keyword_map.items():
                if any(keyword in agent_l for keyword in keywords):
                    scores[scenario] += 2

        plan_subtasks = list((lead_task_plan or {}).get("subtasks") or [])
        for subtask in plan_subtasks:
            if not isinstance(subtask, Mapping):
                continue
            stage = str(subtask.get("stage") or "").strip().lower()
            title = str(subtask.get("title") or "").strip().lower()
            stage_text = f"{stage} {title}".strip()
            if any(token in stage_text for token in ("sim", "validation", "testbench", "verify")):
                scores["simulation"] += 2
            if any(token in stage_text for token in ("synth", "area", "timing", "qor")):
                scores["synthesis"] += 2
            if any(token in stage_text for token in ("formal", "proof", "property", "assert")):
                scores["formal"] += 2
            if any(token in stage_text for token in ("pnr", "place", "route", "floorplan", "cts")):
                scores["pnr"] += 2

        best_score = max(scores.values()) if scores else 0
        if best_score <= 0:
            return {
                "requested": True,
                "classification_status": "rejected",
                "scenario": None,
                "adapter_module": None,
                "reason": (
                    "Could not classify `eda.run` intent. "
                    "Include simulation, synthesis, formal, or pnr intent in the prompt or agent profile."
                ),
            }

        winning = [scenario for scenario, score in scores.items() if score == best_score]
        if len(winning) != 1:
            return {
                "requested": True,
                "classification_status": "rejected",
                "scenario": None,
                "adapter_module": None,
                "reason": (
                    "Ambiguous `eda.run` intent; multiple adapter scenarios matched. "
                    "Clarify whether the goal is simulation, synthesis, formal, or pnr."
                ),
            }

        scenario = winning[0]
        return {
            "requested": True,
            "classification_status": "classified",
            "scenario": scenario,
            "adapter_module": adapter_module_by_scenario[scenario],
            "reason": f"Classified eda.run intent as `{scenario}`.",
        }

    @staticmethod
    def _extract_route_summary(state: GraphState) -> List[Dict[str, Any]]:
        summaries: List[Dict[str, Any]] = []
        for task in state.tasks:
            route = dict(task.metadata).get("supervisor_route")
            if not isinstance(route, Mapping):
                continue

            selection_entries: List[Dict[str, Any]] = []
            for entry in route.get("subagent_selection") or []:
                if not isinstance(entry, Mapping):
                    continue
                selection_entries.append(
                    {
                        "subgraph": str(entry.get("subgraph") or "").strip(),
                        "role": str(entry.get("role") or "").strip(),
                        "role_type": str(entry.get("role_type") or "").strip(),
                        "capability_tags": [
                            str(tag).strip()
                            for tag in (entry.get("capability_tags") or [])
                            if str(tag).strip()
                        ],
                        "selection_rationale": str(entry.get("selection_rationale") or "").strip(),
                    }
                )

            fallback_contract = route.get("fallback_contract")
            fallback_summary: Dict[str, Any] = {}
            if isinstance(fallback_contract, Mapping):
                fallback_summary = {
                    "profile_name": str(fallback_contract.get("profile_name") or "").strip(),
                    "replacement_source": str(
                        fallback_contract.get("replacement_source") or ""
                    ).strip(),
                    "replaced_builtin": bool(fallback_contract.get("replaced_builtin", False)),
                    "role": str(fallback_contract.get("role") or "").strip(),
                    "role_type": str(fallback_contract.get("role_type") or "").strip(),
                    "capability_tags": [
                        str(tag).strip()
                        for tag in (fallback_contract.get("capability_tags") or [])
                        if str(tag).strip()
                    ],
                }

            web_research_policy = route.get("web_research_policy")
            web_policy_summary: Dict[str, Any] = {}
            if isinstance(web_research_policy, Mapping):
                web_policy_summary = {
                    "requested": bool(web_research_policy.get("requested", False)),
                    "allowed": bool(web_research_policy.get("allowed", False)),
                    "blocked": bool(web_research_policy.get("blocked", False)),
                    "approved_capabilities": [
                        str(capability).strip()
                        for capability in (web_research_policy.get("approved_capabilities") or [])
                        if str(capability).strip()
                    ],
                    "requested_capabilities": [
                        str(capability).strip()
                        for capability in (web_research_policy.get("requested_capabilities") or [])
                        if str(capability).strip()
                    ],
                    "reason": str(web_research_policy.get("reason") or "").strip(),
                }

            summaries.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type,
                    "selected_subgraphs": list(route.get("selected_subgraphs") or []),
                    "fallback_used": bool(route.get("fallback_used", False)),
                    "rationale": str(route.get("rationale") or "").strip(),
                    "web_research_policy": web_policy_summary,
                    "fallback_contract": fallback_summary,
                    "subagent_selection": selection_entries,
                }
            )
        return summaries

    def _emit_usage_events_from_state(self, state: GraphState) -> None:
        """Emit graph usage events for any task outputs that carry an LLM usage envelope."""
        for task in state.tasks:
            outputs = dict(task.outputs or {})
            llm_result = outputs.get("llm_result")
            if not isinstance(llm_result, Mapping):
                continue

            usage_payload = llm_result.get("usage")
            if not isinstance(usage_payload, Mapping):
                continue

            usage = LLMUsage.from_mapping(usage_payload)
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            if prompt_tokens is None and completion_tokens is None and total_tokens is None:
                continue

            message_parts = []
            if prompt_tokens is not None:
                message_parts.append(f"{prompt_tokens} in")
            if completion_tokens is not None:
                message_parts.append(f"{completion_tokens} out")
            if total_tokens is not None:
                message_parts.append(f"{total_tokens} total")

            self.emit_event(
                {
                    "event_id": f"evt-{uuid4().hex}",
                    "run_id": state.run_id,
                    "timestamp": self._utc_timestamp(),
                    "phase": task.task_type,
                    "node": "graph_runtime",
                    "event_type": "llm_call_end",
                    "user_message": "LLM usage: " + ", ".join(message_parts) + ".",
                    "detail_level": "summary",
                    "context_refs": self._context_refs(task.context_bundle or state.context_bundle),
                }
            )

    def _emit_monitor_events_from_state(self, state: GraphState) -> None:
        """Emit monitor-loop events for retry, escalation, and completion decisions."""
        for task in state.tasks:
            monitor = dict(task.metadata).get("lead_monitor")
            if not isinstance(monitor, Mapping):
                continue

            decision = str(monitor.get("decision") or "").strip().lower()
            if decision not in {"retry", "escalate", "complete"}:
                continue

            event_type = "node_end"
            if decision == "retry":
                event_type = "retry"
            elif decision == "escalate":
                event_type = "block"

            rationale = str(monitor.get("rationale") or "").strip()
            retries_used = int(monitor.get("retries_used", 0) or 0)
            retry_budget = int(monitor.get("retry_budget", 0) or 0)
            self.emit_event(
                {
                    "event_id": f"evt-{uuid4().hex}",
                    "run_id": state.run_id,
                    "timestamp": self._utc_timestamp(),
                    "phase": task.task_type,
                    "node": "lead_monitor_loop",
                    "event_type": event_type,
                    "user_message": (
                        f"Lead monitor decision: {decision}. "
                        f"Retries: {retries_used}/{retry_budget}. {rationale}"
                    ).strip(),
                    "detail_level": "summary",
                    "context_refs": self._context_refs(task.context_bundle or state.context_bundle),
                }
            )

    def get_run_report(self, run_id: str, state: Optional[GraphState] = None) -> Dict[str, Any]:
        """Return a compact run report including context refs used by the run."""
        report: Dict[str, Any] = {
            "run_id": run_id,
            "event_count": len(self._events_by_run.get(run_id, ())),
            "task_count": 0,
            "context_refs": [],
            "routing": [],
        }
        if state is None:
            return report

        context_refs = set(self._context_refs(state.context_bundle))
        for task in state.tasks:
            context_refs.update(self._context_refs(task.context_bundle))

        report["task_count"] = len(state.tasks)
        report["context_refs"] = sorted(context_refs)
        report["routing"] = self._extract_route_summary(state)
        return report

    def start_task(
        self,
        *,
        task_type: str,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        """Create an initial graph task state and start it through the runtime."""
        resolved_run_id = run_id or f"run-{uuid4().hex}"
        resolved_task_id = task_id or f"task-{uuid4().hex}"
        resolved_thread_id = self._new_thread_id(task_type)

        self.emit_event(
            {
                "event_id": f"evt-{uuid4().hex}",
                "run_id": resolved_run_id,
                "timestamp": self._utc_timestamp(),
                "phase": "workflow",
                "node": "start_task",
                "event_type": "node_start",
                "user_message": f"Starting {task_type} task.",
                "context_refs": self._context_refs(context_bundle),
            }
        )

        task = GraphTaskState.from_mapping(
            {
                "task_id": resolved_task_id,
                "task_type": task_type,
                "prompt": prompt,
                "workspace": workspace,
                "status": "pending",
                "thread_id": resolved_thread_id,
                "context_bundle": context_bundle.to_dict() if context_bundle is not None else None,
                "lead_task_plan": lead_task_plan,
                "metadata": dict(metadata or {}),
            }
        )

        initial_state = GraphState(
            run_id=resolved_run_id,
            tasks=(task,),
            active_task_id=resolved_task_id,
            context_bundle=context_bundle,
        )
        started_state = self.runtime.start(initial_state)
        self._emit_usage_events_from_state(started_state)
        self._emit_monitor_events_from_state(started_state)

        route_summary = self._extract_route_summary(started_state)
        route_message = ""
        if route_summary:
            selected = route_summary[0].get("selected_subgraphs") or []
            if selected:
                route_message = " Routed via: " + ", ".join(selected) + "."

        self.emit_event(
            {
                "event_id": f"evt-{uuid4().hex}",
                "run_id": resolved_run_id,
                "timestamp": self._utc_timestamp(),
                "phase": "workflow",
                "node": "start_task",
                "event_type": "node_end",
                "user_message": f"Started {task_type} task.{route_message}",
                "context_refs": self._context_refs(started_state.context_bundle),
            }
        )
        return started_state

    def start_ask_task(
        self,
        *,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        ask_metadata = dict(metadata or {})
        ask_metadata.setdefault(
            "ask_workflow_contract",
            {
                "mode": "grounded_read_only",
                "citation_required": True,
                "visibly_distinct": True,
            },
        )
        return self.start_task(
            task_type="ask",
            prompt=prompt,
            workspace=workspace,
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            metadata=ask_metadata,
            run_id=run_id,
            task_id=task_id,
        )

    def start_plan_task(
        self,
        *,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        plan_metadata = dict(metadata or {})
        plan_metadata.setdefault(
            "plan_workflow_contract",
            {
                "mode": "structured_read_only",
                "feasibility_validation_required": True,
                "bounded_docs_persistence": True,
                "required_sections": [
                    "milestones",
                    "prerequisites",
                    "risks",
                    "approval_checkpoints",
                ],
            },
        )
        return self.start_task(
            task_type="plan",
            prompt=prompt,
            workspace=workspace,
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            metadata=plan_metadata,
            run_id=run_id,
            task_id=task_id,
        )

    def start_run_task(
        self,
        *,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        run_metadata = dict(metadata or {})
        run_adapter_routing = self._classify_run_adapter_scenario(
            prompt=prompt,
            requested_capabilities=list(run_metadata.get("requested_capabilities") or []),
            requested_agent=str(run_metadata.get("requested_agent") or "").strip() or None,
            lead_task_plan=lead_task_plan,
        )
        run_metadata.setdefault("run_adapter_routing", run_adapter_routing)
        run_metadata.setdefault(
            "run_workflow_contract",
            {
                "mode": "bounded_agent_execution",
                "approval_required": True,
                "adapter_mediation": True,
                "scenario_classification_required": True,
                "resumable_state": True,
                "artifact_and_event_visibility": True,
            },
        )
        return self.start_task(
            task_type="run",
            prompt=prompt,
            workspace=workspace,
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            metadata=run_metadata,
            run_id=run_id,
            task_id=task_id,
        )

    def start_research_task(
        self,
        *,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        research_metadata = dict(metadata or {})
        research_metadata.setdefault(
            "research_workflow_contract",
            {
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
            },
        )
        return self.start_task(
            task_type="research",
            prompt=prompt,
            workspace=workspace,
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            metadata=research_metadata,
            run_id=run_id,
            task_id=task_id,
        )

    def start_resume_task(
        self,
        *,
        prompt: str,
        workspace: str,
        context_bundle: Optional[ContextBundle] = None,
        lead_task_plan: Optional[Mapping[str, Any]] = None,
        metadata: Optional[Mapping[str, Any]] = None,
        run_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> GraphState:
        return self.start_task(
            task_type="resume",
            prompt=prompt,
            workspace=workspace,
            context_bundle=context_bundle,
            lead_task_plan=lead_task_plan,
            metadata=metadata,
            run_id=run_id,
            task_id=task_id,
        )
