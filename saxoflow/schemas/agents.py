"""Agent planning schemas for lead-task decomposition policy contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

try:
    from pydantic import BaseModel as _PydanticBaseModel  # type: ignore[assignment]
    _HAS_PYDANTIC = True
except Exception:  # pragma: no cover - optional dependency fallback
    _PydanticBaseModel = object  # type: ignore[assignment]
    _HAS_PYDANTIC = False


class AgentSchemaError(ValueError):
    """Raised when agent planning schema payloads are malformed."""


ALLOWED_DECOMPOSITION_STRATEGIES = {"sequential", "parallel", "hybrid"}
ALLOWED_SUBTASK_STAGES = {"analysis", "generation", "validation", "repair", "report"}
ALLOWED_AGENT_ROLES = {
    "lead",
    "specialist",
    "reviewer",
    "tutor",
    "researcher",
    "fallback",
    "generic",
    "domain",
}
ALLOWED_AGENT_INTENTS = {
    "tutor",
    "researcher",
    "engineer",
    "deterministic_flow",
    "unsafe_request",
    "clarify",
}
ALLOWED_FORMAL_PROOF_STATUSES = {"pass", "fail", "timeout", "cover", "error", "unknown"}

_RTL_REVIEW_HEADINGS = (
    ("Syntax Issues", "syntax_issues"),
    ("Logic Issues", "logic_issues"),
    ("Reset Issues", "reset_issues"),
    ("Port Declaration Issues", "port_declaration_issues"),
    ("Optimization Suggestions", "optimization_suggestions"),
    ("Naming Improvements", "naming_improvements"),
    ("Synthesis Concerns", "synthesis_concerns"),
    ("Overall Comments", "overall_comments"),
)


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise AgentSchemaError(f"Agent field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AgentSchemaError(f"Agent field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _positive_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise AgentSchemaError(f"Agent field `{field_name}` must be a positive integer.")
    return value


def _bounded_float(value: Any, field_name: str) -> float:
    if not isinstance(value, (int, float)):
        raise AgentSchemaError(f"Agent field `{field_name}` must be a float in the range [0, 1].")
    parsed = float(value)
    if parsed < 0.0 or parsed > 1.0:
        raise AgentSchemaError(f"Agent field `{field_name}` must be a float in the range [0, 1].")
    return parsed


def _string_tuple(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return tuple()
    if not isinstance(value, list):
        raise AgentSchemaError(f"Agent field `{field_name}` must be a list of strings.")
    return tuple(_as_string(item, field_name) for item in value)


@dataclass(frozen=True)
class AgentToolPolicy:
    """Capability policy contract attached to one agent profile."""

    allowed_tools: Tuple[str, ...] = field(default_factory=tuple)
    denied_tools: Tuple[str, ...] = field(default_factory=tuple)
    approval_required: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "AgentToolPolicy":
        if raw is None:
            return cls()
        data = _as_mapping(raw, "agent.tool_policy")
        allowed_tools = _string_tuple(data.get("allowed_tools"), "agent.tool_policy.allowed_tools")
        denied_tools = _string_tuple(data.get("denied_tools"), "agent.tool_policy.denied_tools")
        return cls(
            allowed_tools=allowed_tools,
            denied_tools=denied_tools,
            approval_required=bool(data.get("approval_required", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed_tools": list(self.allowed_tools),
            "denied_tools": list(self.denied_tools),
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True)
class AgentProfile:
    """Common structured contract describing an agent role and capabilities."""

    name: str
    role: str
    description: Optional[str] = None
    capability_tags: Tuple[str, ...] = field(default_factory=tuple)
    input_schema: Optional[str] = None
    output_schema: Optional[str] = None
    cost_profile: Optional[str] = None
    tool_policy: AgentToolPolicy = field(default_factory=AgentToolPolicy)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AgentProfile":
        data = _as_mapping(raw, "agent_profile")
        role = _as_string(data.get("role"), "agent_profile.role").lower()
        if role not in ALLOWED_AGENT_ROLES:
            allowed = ", ".join(sorted(ALLOWED_AGENT_ROLES))
            raise AgentSchemaError(
                f"Agent field `agent_profile.role` must be one of: {allowed}."
            )

        capability_tags = _string_tuple(
            data.get("capability_tags"),
            "agent_profile.capability_tags",
        )
        if not capability_tags:
            raise AgentSchemaError(
                "Agent field `agent_profile.capability_tags` must include at least one capability tag."
            )

        return cls(
            name=_as_string(data.get("name"), "agent_profile.name"),
            role=role,
            description=_optional_string(data.get("description"), "agent_profile.description"),
            capability_tags=capability_tags,
            input_schema=_optional_string(data.get("input_schema"), "agent_profile.input_schema"),
            output_schema=_optional_string(data.get("output_schema"), "agent_profile.output_schema"),
            cost_profile=_optional_string(data.get("cost_profile"), "agent_profile.cost_profile"),
            tool_policy=AgentToolPolicy.from_mapping(data.get("tool_policy")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "capability_tags": list(self.capability_tags),
            "tool_policy": self.tool_policy.to_dict(),
        }
        if self.description is not None:
            data["description"] = self.description
        if self.input_schema is not None:
            data["input_schema"] = self.input_schema
        if self.output_schema is not None:
            data["output_schema"] = self.output_schema
        if self.cost_profile is not None:
            data["cost_profile"] = self.cost_profile
        return data


@dataclass(frozen=True)
class AgentIntentClassification:
    """Structured intent result for explicit AI command routing."""

    intent: str
    confidence: float
    rationale: Optional[str] = None
    suggested_agent: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "AgentIntentClassification":
        data = _as_mapping(raw, "agent_intent")
        intent = _as_string(data.get("intent"), "agent_intent.intent").lower()
        if intent not in ALLOWED_AGENT_INTENTS:
            allowed = ", ".join(sorted(ALLOWED_AGENT_INTENTS))
            raise AgentSchemaError(
                f"Agent field `agent_intent.intent` must be one of: {allowed}."
            )

        return cls(
            intent=intent,
            confidence=_bounded_float(data.get("confidence"), "agent_intent.confidence"),
            rationale=_optional_string(data.get("rationale"), "agent_intent.rationale"),
            suggested_agent=_optional_string(
                data.get("suggested_agent"),
                "agent_intent.suggested_agent",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "intent": self.intent,
            "confidence": self.confidence,
        }
        if self.rationale is not None:
            data["rationale"] = self.rationale
        if self.suggested_agent is not None:
            data["suggested_agent"] = self.suggested_agent
        return data


class RTLProposal(str):
    """Structured RTL proposal returned by the RTL generator agent.

    The object behaves like the generated RTL string while carrying explicit
    structured metadata for downstream checks and serialization.
    """

    def __new__(cls, *, rtl_code: str, spec: str, prompt: Optional[str] = None):
        value = _as_string(rtl_code, "rtl_proposal.rtl_code")
        obj = str.__new__(cls, value)
        obj.rtl_code = value  # type: ignore[attr-defined]
        obj.spec = _as_string(spec, "rtl_proposal.spec")  # type: ignore[attr-defined]
        obj.prompt = _optional_string(prompt, "rtl_proposal.prompt")  # type: ignore[attr-defined]
        return obj

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RTLProposal":
        data = _as_mapping(raw, "rtl_proposal")
        return cls(
            rtl_code=_as_string(data.get("rtl_code"), "rtl_proposal.rtl_code"),
            spec=_as_string(data.get("spec"), "rtl_proposal.spec"),
            prompt=_optional_string(data.get("prompt"), "rtl_proposal.prompt"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "rtl_code": self.rtl_code,
            "spec": self.spec,
        }
        if self.prompt is not None:
            data["prompt"] = self.prompt
        return data


@dataclass(frozen=True)
class FormalPropertySpec:
    """Structured formal property specification contract for formal flows."""

    top_module: str
    property_text: str
    intent: Optional[str] = None
    source_path: Optional[str] = None
    language: str = "systemverilog"

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FormalPropertySpec":
        data = _as_mapping(raw, "formal_property_spec")
        language = _as_string(data.get("language", "systemverilog"), "formal_property_spec.language").lower()
        return cls(
            top_module=_as_string(data.get("top_module"), "formal_property_spec.top_module"),
            property_text=_as_string(data.get("property_text"), "formal_property_spec.property_text"),
            intent=_optional_string(data.get("intent"), "formal_property_spec.intent"),
            source_path=_optional_string(data.get("source_path"), "formal_property_spec.source_path"),
            language=language,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "top_module": self.top_module,
            "property_text": self.property_text,
            "language": self.language,
        }
        if self.intent is not None:
            data["intent"] = self.intent
        if self.source_path is not None:
            data["source_path"] = self.source_path
        return data


@dataclass(frozen=True)
class FormalProofSummary:
    """Structured summary of a formal proof outcome."""

    status: str
    engine: Optional[str] = None
    task: Optional[str] = None
    summary: Optional[str] = None
    counterexample_refs: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "FormalProofSummary":
        data = _as_mapping(raw, "formal_proof_summary")
        status = _as_string(data.get("status"), "formal_proof_summary.status").lower()
        if status not in ALLOWED_FORMAL_PROOF_STATUSES:
            allowed = ", ".join(sorted(ALLOWED_FORMAL_PROOF_STATUSES))
            raise AgentSchemaError(
                f"Agent field `formal_proof_summary.status` must be one of: {allowed}."
            )
        return cls(
            status=status,
            engine=_optional_string(data.get("engine"), "formal_proof_summary.engine"),
            task=_optional_string(data.get("task"), "formal_proof_summary.task"),
            summary=_optional_string(data.get("summary"), "formal_proof_summary.summary"),
            counterexample_refs=_string_tuple(
                data.get("counterexample_refs"),
                "formal_proof_summary.counterexample_refs",
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "counterexample_refs": list(self.counterexample_refs),
        }
        if self.engine is not None:
            data["engine"] = self.engine
        if self.task is not None:
            data["task"] = self.task
        if self.summary is not None:
            data["summary"] = self.summary
        return data


if _HAS_PYDANTIC:

    class RTLReviewReport(_PydanticBaseModel):
        """Structured RTL review payload returned by the reviewer agent."""

        syntax_issues: str = "None"
        logic_issues: str = "None"
        reset_issues: str = "None"
        port_declaration_issues: str = "None"
        optimization_suggestions: str = "None"
        naming_improvements: str = "None"
        synthesis_concerns: str = "None"
        overall_comments: str = "None"

        @classmethod
        def from_mapping(cls, raw: Mapping[str, Any]) -> "RTLReviewReport":
            data = _as_mapping(raw, "rtl_review_report")
            normalized = {}
            for heading, field_name in _RTL_REVIEW_HEADINGS:
                normalized[field_name] = _optional_string(data.get(field_name, "None"), field_name) or "None"
            return cls(**normalized)

        @classmethod
        def from_text(cls, text: str) -> "RTLReviewReport":
            sections: Dict[str, str] = {}
            for line in str(text or "").splitlines():
                if ":" not in line:
                    continue
                heading, value = line.split(":", 1)
                normalized_heading = heading.strip().lower()
                for canonical_heading, field_name in _RTL_REVIEW_HEADINGS:
                    if normalized_heading == canonical_heading.lower():
                        sections[field_name] = _optional_string(value, field_name) or "None"
                        break
            for _, field_name in _RTL_REVIEW_HEADINGS:
                sections.setdefault(field_name, "None")
            return cls(**sections)

        def to_dict(self) -> Dict[str, Any]:
            if hasattr(self, "model_dump"):
                data = self.model_dump()  # type: ignore[attr-defined]
            else:  # pragma: no cover - pydantic v1 fallback
                data = self.dict()  # type: ignore[call-arg]
            return dict(data)

        def to_text(self) -> str:
            return "\n\n".join(
                f"{heading}: {getattr(self, field_name)}" for heading, field_name in _RTL_REVIEW_HEADINGS
            )

else:

    @dataclass(frozen=True)
    class RTLReviewReport:
        """Structured RTL review payload returned by the reviewer agent."""

        syntax_issues: str = "None"
        logic_issues: str = "None"
        reset_issues: str = "None"
        port_declaration_issues: str = "None"
        optimization_suggestions: str = "None"
        naming_improvements: str = "None"
        synthesis_concerns: str = "None"
        overall_comments: str = "None"

        @classmethod
        def from_mapping(cls, raw: Mapping[str, Any]) -> "RTLReviewReport":
            data = _as_mapping(raw, "rtl_review_report")
            normalized = {}
            for heading, field_name in _RTL_REVIEW_HEADINGS:
                normalized[field_name] = _optional_string(data.get(field_name, "None"), field_name) or "None"
            return cls(**normalized)

        @classmethod
        def from_text(cls, text: str) -> "RTLReviewReport":
            sections: Dict[str, str] = {}
            for line in str(text or "").splitlines():
                if ":" not in line:
                    continue
                heading, value = line.split(":", 1)
                normalized_heading = heading.strip().lower()
                for canonical_heading, field_name in _RTL_REVIEW_HEADINGS:
                    if normalized_heading == canonical_heading.lower():
                        sections[field_name] = _optional_string(value, field_name) or "None"
                        break
            for _, field_name in _RTL_REVIEW_HEADINGS:
                sections.setdefault(field_name, "None")
            return cls(**sections)

        def to_dict(self) -> Dict[str, Any]:
            return {
                field_name: getattr(self, field_name)
                for _, field_name in _RTL_REVIEW_HEADINGS
            }

        def to_text(self) -> str:
            return "\n\n".join(
                f"{heading}: {getattr(self, field_name)}" for heading, field_name in _RTL_REVIEW_HEADINGS
            )


@dataclass(frozen=True)
class LeadSubTaskPlan:
    """One decomposed subtask selected by a lead planner."""

    subtask_id: str
    title: str
    stage: str
    required_capabilities: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LeadSubTaskPlan":
        data = _as_mapping(raw, "lead_task_plan.subtasks item")
        stage = _as_string(data.get("stage"), "lead_task_plan.subtasks.stage").lower()
        if stage not in ALLOWED_SUBTASK_STAGES:
            allowed = ", ".join(sorted(ALLOWED_SUBTASK_STAGES))
            raise AgentSchemaError(
                "Agent field `lead_task_plan.subtasks.stage` must be one of: " + allowed + "."
            )
        return cls(
            subtask_id=_as_string(data.get("subtask_id"), "lead_task_plan.subtasks.subtask_id"),
            title=_as_string(data.get("title"), "lead_task_plan.subtasks.title"),
            stage=stage,
            required_capabilities=_string_tuple(
                data.get("required_capabilities"), "lead_task_plan.subtasks.required_capabilities"
            ),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subtask_id": self.subtask_id,
            "title": self.title,
            "stage": self.stage,
            "required_capabilities": list(self.required_capabilities),
        }


@dataclass(frozen=True)
class DecompositionPolicy:
    """Policy constraints that govern lead-task decomposition behavior."""

    strategy: str = "sequential"
    max_parallel_branches: int = 1
    allow_llm_fallback: bool = False

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "DecompositionPolicy":
        if raw is None:
            return cls()
        data = _as_mapping(raw, "lead_task_plan.decomposition_policy")
        strategy = _as_string(
            data.get("strategy", "sequential"), "lead_task_plan.decomposition_policy.strategy"
        ).lower()
        if strategy not in ALLOWED_DECOMPOSITION_STRATEGIES:
            allowed = ", ".join(sorted(ALLOWED_DECOMPOSITION_STRATEGIES))
            raise AgentSchemaError(
                "Agent field `lead_task_plan.decomposition_policy.strategy` must be one of: "
                + allowed
                + "."
            )

        return cls(
            strategy=strategy,
            max_parallel_branches=_positive_int(
                data.get("max_parallel_branches", 1),
                "lead_task_plan.decomposition_policy.max_parallel_branches",
            ),
            allow_llm_fallback=bool(data.get("allow_llm_fallback", False)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "max_parallel_branches": self.max_parallel_branches,
            "allow_llm_fallback": self.allow_llm_fallback,
        }


@dataclass(frozen=True)
class LeadTaskPlan:
    """Lead planner output containing decomposition steps and policy constraints."""

    objective: str
    rationale: Optional[str] = None
    subtasks: Tuple[LeadSubTaskPlan, ...] = field(default_factory=tuple)
    decomposition_policy: DecompositionPolicy = field(default_factory=DecompositionPolicy)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "LeadTaskPlan":
        data = _as_mapping(raw, "lead_task_plan")
        subtasks_raw = data.get("subtasks") or []
        if not isinstance(subtasks_raw, list):
            raise AgentSchemaError("Agent field `lead_task_plan.subtasks` must be a list.")
        subtasks = tuple(LeadSubTaskPlan.from_mapping(item) for item in subtasks_raw)
        if not subtasks:
            raise AgentSchemaError(
                "Agent field `lead_task_plan.subtasks` must include at least one subtask."
            )

        return cls(
            objective=_as_string(data.get("objective"), "lead_task_plan.objective"),
            rationale=_optional_string(data.get("rationale"), "lead_task_plan.rationale"),
            subtasks=subtasks,
            decomposition_policy=DecompositionPolicy.from_mapping(data.get("decomposition_policy")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "objective": self.objective,
            "subtasks": [subtask.to_dict() for subtask in self.subtasks],
            "decomposition_policy": self.decomposition_policy.to_dict(),
        }
        if self.rationale is not None:
            data["rationale"] = self.rationale
        return data
