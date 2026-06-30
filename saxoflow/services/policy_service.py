"""Policy helpers for repository safety, containment, and routing gates."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class RepositorySafetyDecision:
    """Result of evaluating whether a repository path is permitted."""

    allowed: bool
    approval_required: bool
    reason: str
    approved_root: str | None = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "allowed": self.allowed,
            "approval_required": self.approval_required,
            "reason": self.reason,
        }
        if self.approved_root is not None:
            data["approved_root"] = self.approved_root
        return data


@dataclass(frozen=True)
class ExternalRepositorySafetyPolicy:
    """Keep imported repositories inside approved workspace zones."""

    workspace_root: Path
    approved_directory_names: Tuple[str, ...] = ("repos", "staging", "imports")
    approval_required_actions: Tuple[str, ...] = ("clone", "fetch", "checkout")

    def approved_roots(self) -> Tuple[Path, ...]:
        workspace = Path(self.workspace_root).expanduser().resolve()
        roots = [workspace]
        for directory_name in self.approved_directory_names:
            roots.append((workspace / directory_name).resolve(strict=False))
        return tuple(roots)

    def requires_approval(self, action: str) -> bool:
        return action.strip().lower() in {item.strip().lower() for item in self.approval_required_actions}

    def evaluate_path(self, candidate: str | Path, action: str) -> RepositorySafetyDecision:
        path = Path(candidate).expanduser().resolve(strict=False)
        approved_root = self._approved_root_for(path)
        if approved_root is None:
            return RepositorySafetyDecision(
                allowed=False,
                approval_required=self.requires_approval(action),
                reason=(
                    "Repository path must stay in the approved workspace or staging areas: "
                    f"{', '.join(str(root) for root in self.approved_roots())}"
                ),
            )

        return RepositorySafetyDecision(
            allowed=True,
            approval_required=self.requires_approval(action),
            reason="Repository path is inside an approved workspace or staging area.",
            approved_root=str(approved_root),
        )

    def ensure_path(self, candidate: str | Path, action: str) -> RepositorySafetyDecision:
        decision = self.evaluate_path(candidate, action)
        if not decision.allowed:
            raise ValueError(decision.reason)
        return decision

    def _approved_root_for(self, candidate: Path) -> Path | None:
        approved_roots = self.approved_roots()
        for root in approved_roots:
            if candidate == root:
                return root
            try:
                candidate.relative_to(root)
            except ValueError:
                continue
            return root
        return None


@dataclass(frozen=True)
class WebResearchDecision:
    """Result of evaluating policy-gated web-research routing."""

    requested: bool
    allowed: bool
    blocked: bool
    approved_capabilities: Tuple[str, ...]
    requested_capabilities: Tuple[str, ...]
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "requested": self.requested,
            "allowed": self.allowed,
            "blocked": self.blocked,
            "approved_capabilities": list(self.approved_capabilities),
            "requested_capabilities": list(self.requested_capabilities),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WebResearchRoutingPolicy:
    """Explicit policy gate for internet-capable web research routing."""

    allow_web_research: bool = False
    approved_capabilities: Tuple[str, ...] = ("web.search", "web.fetch")

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for capability in capabilities:
            text = str(capability).strip()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def evaluate(self, requested_capabilities: Iterable[str]) -> WebResearchDecision:
        requested = tuple(
            capability
            for capability in self._normalize_capabilities(requested_capabilities)
            if capability in {"web.search", "web.fetch"}
        )
        if not requested:
            return WebResearchDecision(
                requested=False,
                allowed=False,
                blocked=False,
                approved_capabilities=self._normalize_capabilities(self.approved_capabilities),
                requested_capabilities=tuple(),
                reason="web-research capability was not requested",
            )

        approved = self._normalize_capabilities(self.approved_capabilities)
        if not self.allow_web_research:
            return WebResearchDecision(
                requested=True,
                allowed=False,
                blocked=True,
                approved_capabilities=approved,
                requested_capabilities=requested,
                reason="web-research capability was requested but blocked by policy",
            )

        allowed_requested = tuple(capability for capability in requested if capability in set(approved))
        if not allowed_requested:
            return WebResearchDecision(
                requested=True,
                allowed=False,
                blocked=True,
                approved_capabilities=approved,
                requested_capabilities=requested,
                reason="web-research capability was requested but not approved by capability policy",
            )

        return WebResearchDecision(
            requested=True,
            allowed=True,
            blocked=False,
            approved_capabilities=approved,
            requested_capabilities=requested,
            reason="web-research capability requested and approved by policy",
        )


@dataclass(frozen=True)
class AgentCapabilityPolicyDecision:
    """Result of intersecting requested capabilities with policy-approved capabilities."""

    selected_capabilities: Tuple[str, ...]
    requested_capabilities: Tuple[str, ...]
    approved_capabilities: Tuple[str, ...]
    denied_by_policy: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        return {
            "selected_capabilities": list(self.selected_capabilities),
            "requested_capabilities": list(self.requested_capabilities),
            "approved_capabilities": list(self.approved_capabilities),
            "denied_by_policy": list(self.denied_by_policy),
        }


@dataclass(frozen=True)
class AgentCapabilityRoutingPolicy:
    """Policy gate for custom-agent requested capability subsets."""

    approved_capabilities: Tuple[str, ...] = tuple()

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for capability in capabilities:
            text = str(capability).strip()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def evaluate(self, requested_capabilities: Iterable[str]) -> AgentCapabilityPolicyDecision:
        requested = self._normalize_capabilities(requested_capabilities)
        approved = self._normalize_capabilities(self.approved_capabilities)

        if not approved:
            return AgentCapabilityPolicyDecision(
                selected_capabilities=requested,
                requested_capabilities=requested,
                approved_capabilities=tuple(),
                denied_by_policy=tuple(),
            )

        approved_set = set(approved)
        selected = tuple(capability for capability in requested if capability in approved_set)
        denied = tuple(capability for capability in requested if capability not in approved_set)
        return AgentCapabilityPolicyDecision(
            selected_capabilities=selected,
            requested_capabilities=requested,
            approved_capabilities=approved,
            denied_by_policy=denied,
        )


@dataclass(frozen=True)
class PlanWorkflowPolicyDecision:
    """Result of validating requested capabilities for the plan workflow."""

    feasible: bool
    persist_plan_artifact: bool
    unsupported_capabilities: Tuple[str, ...]
    approval_checkpoints: Tuple[str, ...]
    allowed_docs_root: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "feasible": self.feasible,
            "persist_plan_artifact": self.persist_plan_artifact,
            "unsupported_capabilities": list(self.unsupported_capabilities),
            "approval_checkpoints": list(self.approval_checkpoints),
            "allowed_docs_root": self.allowed_docs_root,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class PlanWorkflowPolicy:
    """Policy gate for P6.04c structured plan workflow behavior."""

    workspace_root: Path
    allowed_capabilities: Tuple[str, ...] = (
        "file.read",
        "context.read",
        "artifact.read",
        "report.read",
        "artifact.write",
    )
    approval_required_capabilities: Tuple[str, ...] = ("artifact.write",)

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for capability in capabilities:
            text = str(capability).strip()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def docs_root(self) -> Path:
        return (Path(self.workspace_root).expanduser().resolve() / "docs").resolve(strict=False)

    def evaluate(self, requested_capabilities: Iterable[str]) -> PlanWorkflowPolicyDecision:
        requested = self._normalize_capabilities(requested_capabilities)
        allowed_set = set(self.allowed_capabilities)
        unsupported = tuple(capability for capability in requested if capability not in allowed_set)
        persist_plan_artifact = "artifact.write" in requested and not unsupported
        approval_checkpoints = tuple(
            capability
            for capability in requested
            if capability in set(self.approval_required_capabilities)
        )
        feasible = len(unsupported) == 0

        if feasible:
            reason = "Plan capability set is feasible for structured read-only planning."
        else:
            reason = (
                "Plan workflow rejects incompatible capabilities: "
                + ", ".join(unsupported)
            )

        return PlanWorkflowPolicyDecision(
            feasible=feasible,
            persist_plan_artifact=persist_plan_artifact,
            unsupported_capabilities=unsupported,
            approval_checkpoints=approval_checkpoints,
            allowed_docs_root=str(self.docs_root()),
            reason=reason,
        )

    def ensure_docs_path(self, candidate: str | Path) -> Path:
        docs_root = self.docs_root()
        path = Path(candidate).expanduser()
        resolved = path if path.is_absolute() else (docs_root / path)
        resolved = resolved.resolve(strict=False)
        if resolved == docs_root:
            return resolved
        try:
            resolved.relative_to(docs_root)
        except ValueError as exc:
            raise ValueError(
                "Plan artifacts must be written under the active unit docs tree "
                f"`{docs_root}`."
            ) from exc
        return resolved


@dataclass(frozen=True)
class ResearchWorkflowPolicyDecision:
    """Result of validating requested capabilities for the research workflow."""

    feasible: bool
    persist_research_artifact: bool
    unsupported_capabilities: Tuple[str, ...]
    approval_checkpoints: Tuple[str, ...]
    allowed_docs_root: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "feasible": self.feasible,
            "persist_research_artifact": self.persist_research_artifact,
            "unsupported_capabilities": list(self.unsupported_capabilities),
            "approval_checkpoints": list(self.approval_checkpoints),
            "allowed_docs_root": self.allowed_docs_root,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ResearchWorkflowPolicy:
    """Policy gate for P6.04d evidence-synthesis workflow behavior."""

    workspace_root: Path
    allowed_capabilities: Tuple[str, ...] = (
        "file.read",
        "context.read",
        "artifact.read",
        "report.read",
        "artifact.write",
        "web.search",
        "web.fetch",
    )
    approval_required_capabilities: Tuple[str, ...] = (
        "artifact.write",
        "web.search",
        "web.fetch",
    )

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for capability in capabilities:
            text = str(capability).strip()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def docs_root(self) -> Path:
        return (Path(self.workspace_root).expanduser().resolve() / "docs").resolve(strict=False)

    def evaluate(self, requested_capabilities: Iterable[str]) -> ResearchWorkflowPolicyDecision:
        requested = self._normalize_capabilities(requested_capabilities)
        allowed_set = set(self.allowed_capabilities)
        unsupported = tuple(capability for capability in requested if capability not in allowed_set)
        persist_research_artifact = "artifact.write" in requested and not unsupported
        approval_checkpoints = tuple(
            capability
            for capability in requested
            if capability in set(self.approval_required_capabilities)
        )
        feasible = len(unsupported) == 0

        if feasible:
            reason = "Research capability set is feasible for evidence-synthesis planning."
        else:
            reason = (
                "Research workflow rejects incompatible capabilities: "
                + ", ".join(unsupported)
            )

        return ResearchWorkflowPolicyDecision(
            feasible=feasible,
            persist_research_artifact=persist_research_artifact,
            unsupported_capabilities=unsupported,
            approval_checkpoints=approval_checkpoints,
            allowed_docs_root=str(self.docs_root()),
            reason=reason,
        )

    def ensure_docs_path(self, candidate: str | Path) -> Path:
        docs_root = self.docs_root()
        path = Path(candidate).expanduser()
        resolved = path if path.is_absolute() else (docs_root / path)
        resolved = resolved.resolve(strict=False)
        if resolved == docs_root:
            return resolved
        try:
            resolved.relative_to(docs_root)
        except ValueError as exc:
            raise ValueError(
                "Research notes must be written under the active unit docs tree "
                f"`{docs_root}`."
            ) from exc
        return resolved


@dataclass(frozen=True)
class RunWorkflowPolicyDecision:
    """Result of validating requested capabilities for bounded run workflow."""

    feasible: bool
    persist_run_artifact: bool
    unsupported_capabilities: Tuple[str, ...]
    approval_checkpoints: Tuple[str, ...]
    adapter_mediation_enabled: bool
    resumable_execution: bool
    allowed_docs_root: str
    reason: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "feasible": self.feasible,
            "persist_run_artifact": self.persist_run_artifact,
            "unsupported_capabilities": list(self.unsupported_capabilities),
            "approval_checkpoints": list(self.approval_checkpoints),
            "adapter_mediation_enabled": self.adapter_mediation_enabled,
            "resumable_execution": self.resumable_execution,
            "allowed_docs_root": self.allowed_docs_root,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RunWorkflowPolicy:
    """Policy gate for P6.04e bounded agent-mode run workflow behavior."""

    workspace_root: Path
    allowed_capabilities: Tuple[str, ...] = (
        "file.read",
        "context.read",
        "artifact.read",
        "report.read",
        "artifact.write",
        "eda.run",
        "web.search",
        "web.fetch",
    )
    approval_required_capabilities: Tuple[str, ...] = (
        "artifact.write",
        "eda.run",
        "web.search",
        "web.fetch",
    )

    @staticmethod
    def _normalize_capabilities(capabilities: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for capability in capabilities:
            text = str(capability).strip()
            if text:
                normalized.append(text)
        return tuple(dict.fromkeys(normalized))

    def docs_root(self) -> Path:
        return (Path(self.workspace_root).expanduser().resolve() / "docs").resolve(strict=False)

    def evaluate(self, requested_capabilities: Iterable[str]) -> RunWorkflowPolicyDecision:
        requested = self._normalize_capabilities(requested_capabilities)
        allowed_set = set(self.allowed_capabilities)
        unsupported = tuple(capability for capability in requested if capability not in allowed_set)
        persist_run_artifact = "artifact.write" in requested and not unsupported
        approval_checkpoints = tuple(
            capability
            for capability in requested
            if capability in set(self.approval_required_capabilities)
        )
        feasible = len(unsupported) == 0
        adapter_mediation_enabled = "eda.run" in requested and feasible

        if feasible:
            reason = "Run capability set is feasible for bounded agent-mode execution."
        else:
            reason = (
                "Run workflow rejects incompatible capabilities: "
                + ", ".join(unsupported)
            )

        return RunWorkflowPolicyDecision(
            feasible=feasible,
            persist_run_artifact=persist_run_artifact,
            unsupported_capabilities=unsupported,
            approval_checkpoints=approval_checkpoints,
            adapter_mediation_enabled=adapter_mediation_enabled,
            resumable_execution=True,
            allowed_docs_root=str(self.docs_root()),
            reason=reason,
        )

    def ensure_docs_path(self, candidate: str | Path) -> Path:
        docs_root = self.docs_root()
        path = Path(candidate).expanduser()
        resolved = path if path.is_absolute() else (docs_root / path)
        resolved = resolved.resolve(strict=False)
        if resolved == docs_root:
            return resolved
        try:
            resolved.relative_to(docs_root)
        except ValueError as exc:
            raise ValueError(
                "Run artifacts must be written under the active unit docs tree "
                f"`{docs_root}`."
            ) from exc
        return resolved