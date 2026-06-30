"""Repository acquisition and qualification helpers for SaxoFlow projects."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from saxoflow.project_manifest import ProjectLogicalProfile, ProjectManifest, discover_manifest_path
from saxoflow.project_manifest import infer_logical_project_profile
from saxoflow.services.policy_service import ExternalRepositorySafetyPolicy, RepositorySafetyDecision


class ProjectServiceError(ValueError):
    """Raised when a repository operation cannot be completed safely."""


@dataclass(frozen=True)
class RepositoryPolicy:
    """Policy gate for repository acquisition and VCS actions."""

    allowed_actions: Tuple[str, ...] = ("clone", "fetch", "checkout", "diff")

    def allows(self, action: str) -> bool:
        return action.strip().lower() in {item.strip().lower() for item in self.allowed_actions}


@dataclass(frozen=True)
class RepositoryProvenance:
    """Normalized provenance for one repository action."""

    workspace_root: str
    repository_root: str
    action: str
    command: Tuple[str, ...]
    remote_url: Optional[str] = None
    reference: Optional[str] = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "workspace_root": self.workspace_root,
            "repository_root": self.repository_root,
            "action": self.action,
            "command": list(self.command),
            "extra": dict(self.extra),
        }
        if self.remote_url is not None:
            data["remote_url"] = self.remote_url
        if self.reference is not None:
            data["reference"] = self.reference
        return data


@dataclass(frozen=True)
class RepositoryOperation:
    """Result of one repository acquisition or VCS action."""

    status: str
    action: str
    command: Tuple[str, ...]
    workspace_root: str
    repository_root: str
    provenance: RepositoryProvenance
    remote_url: Optional[str] = None
    reference: Optional[str] = None
    approval_required: bool = False
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "status": self.status,
            "action": self.action,
            "command": list(self.command),
            "workspace_root": self.workspace_root,
            "repository_root": self.repository_root,
            "provenance": self.provenance.to_dict(),
        }
        if self.remote_url is not None:
            data["remote_url"] = self.remote_url
        if self.reference is not None:
            data["reference"] = self.reference
        data["approval_required"] = self.approval_required
        if self.exit_code is not None:
            data["exit_code"] = self.exit_code
        if self.stdout is not None:
            data["stdout"] = self.stdout
        if self.stderr is not None:
            data["stderr"] = self.stderr
        return data


@dataclass(frozen=True)
class RepositoryQualificationReport:
    """Normalized readiness report for an imported repository."""

    workspace_root: str
    repository_root: str
    manifest_path: Optional[str]
    profile: ProjectLogicalProfile
    ready: bool
    readiness: Mapping[str, str]

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "workspace_root": self.workspace_root,
            "repository_root": self.repository_root,
            "manifest_path": self.manifest_path,
            "profile": self.profile.to_dict(),
            "ready": self.ready,
            "readiness": dict(self.readiness),
        }
        return data


class ProjectService:
    """Thin repository acquisition service with policy gating and provenance."""

    def __init__(
        self,
        workspace_root: Path,
        *,
        policy: Optional[RepositoryPolicy] = None,
        safety_policy: Optional[ExternalRepositorySafetyPolicy] = None,
        executor: Optional[Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]] = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).expanduser().resolve()
        self.policy = policy or RepositoryPolicy()
        self.safety_policy = safety_policy or ExternalRepositorySafetyPolicy(self.workspace_root)
        self.executor = executor or self._default_executor

    @classmethod
    def from_workspace(
        cls,
        workspace_root: Path,
        *,
        policy: Optional[RepositoryPolicy] = None,
        safety_policy: Optional[ExternalRepositorySafetyPolicy] = None,
        executor: Optional[Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]] = None,
    ) -> "ProjectService":
        return cls(workspace_root=workspace_root, policy=policy, safety_policy=safety_policy, executor=executor)

    def clone_repository(
        self,
        remote_url: str,
        destination: str | Path,
        *,
        branch: Optional[str] = None,
        dry_run: bool = False,
    ) -> RepositoryOperation:
        destination_root = self._resolve_repository_root(destination)
        destination_decision = self._ensure_safe_repository_path(destination_root, action="clone")
        command: list[str] = ["git", "clone"]
        if branch:
            command.extend(["--branch", branch])
        command.extend([remote_url, str(destination_root)])
        return self._run(
            action="clone",
            command=tuple(command),
            repository_root=destination_root,
            remote_url=remote_url,
            reference=branch,
            approval_required=destination_decision.approval_required,
            dry_run=dry_run,
        )

    def fetch_repository(
        self,
        repository_root: str | Path,
        *,
        remote: str = "origin",
        dry_run: bool = False,
    ) -> RepositoryOperation:
        root = self._resolve_repository_root(repository_root)
        approval_required = self._ensure_safe_repository_path(root, action="fetch").approval_required
        command = ("git", "fetch", remote)
        return self._run(
            action="fetch",
            command=command,
            repository_root=root,
            reference=remote,
            approval_required=approval_required,
            dry_run=dry_run,
        )

    def checkout_repository(
        self,
        repository_root: str | Path,
        ref: str,
        *,
        dry_run: bool = False,
    ) -> RepositoryOperation:
        root = self._resolve_repository_root(repository_root)
        approval_required = self._ensure_safe_repository_path(root, action="checkout").approval_required
        command = ("git", "checkout", ref)
        return self._run(
            action="checkout",
            command=command,
            repository_root=root,
            reference=ref,
            approval_required=approval_required,
            dry_run=dry_run,
        )

    def diff_repository(
        self,
        repository_root: str | Path,
        *,
        base: str = "HEAD",
        target: str = "HEAD",
        dry_run: bool = False,
    ) -> RepositoryOperation:
        root = self._resolve_repository_root(repository_root)
        approval_required = self._ensure_safe_repository_path(root, action="diff").approval_required
        command = ("git", "diff", base, target)
        return self._run(
            action="diff",
            command=command,
            repository_root=root,
            reference=f"{base}..{target}",
            approval_required=approval_required,
            dry_run=dry_run,
        )

    def qualify_repository(self, repository_root: str | Path) -> RepositoryQualificationReport:
        """Inspect an imported repository and return a normalized readiness report."""
        root = self._resolve_repository_root(repository_root, allow_external=True)
        self._ensure_safe_repository_path(root, action="qualify")
        manifest_path = discover_manifest_path(root)
        manifest = ProjectManifest.discover_from_root(root)
        if manifest is None:
            profile = infer_logical_project_profile(root)
        else:
            profile = manifest.infer_logical_profile(root)

        ready = profile.flow_readiness.get("overall") == "ready"
        return RepositoryQualificationReport(
            workspace_root=str(self.workspace_root),
            repository_root=str(root),
            manifest_path=str(manifest_path.relative_to(root)) if manifest_path is not None else None,
            profile=profile,
            ready=ready,
            readiness=dict(profile.flow_readiness),
        )

    def _run(
        self,
        *,
        action: str,
        command: Tuple[str, ...],
        repository_root: Path,
        approval_required: bool,
        remote_url: Optional[str] = None,
        reference: Optional[str] = None,
        dry_run: bool,
    ) -> RepositoryOperation:
        self._validate_action(action)

        provenance = RepositoryProvenance(
            workspace_root=str(self.workspace_root),
            repository_root=str(repository_root),
            action=action,
            command=command,
            remote_url=remote_url,
            reference=reference,
        )

        if dry_run:
            return RepositoryOperation(
                status="skipped",
                action=action,
                command=command,
                workspace_root=str(self.workspace_root),
                repository_root=str(repository_root),
                provenance=provenance,
                remote_url=remote_url,
                reference=reference,
                approval_required=approval_required,
            )

        result = self.executor(command, repository_root)
        status = "success" if result.returncode == 0 else "failed"
        return RepositoryOperation(
            status=status,
            action=action,
            command=command,
            workspace_root=str(self.workspace_root),
            repository_root=str(repository_root),
            provenance=provenance,
            remote_url=remote_url,
            reference=reference,
            approval_required=approval_required,
            exit_code=result.returncode,
            stdout=(result.stdout or None),
            stderr=(result.stderr or None),
        )

    def _validate_action(self, action: str) -> None:
        if not self.policy.allows(action):
            raise ProjectServiceError(f"Repository action `{action}` is not allowed by policy.")

    def _resolve_repository_root(self, repository_root: str | Path, *, allow_external: bool = False) -> Path:
        candidate = Path(repository_root).expanduser()
        resolved = candidate if candidate.is_absolute() else self.workspace_root / candidate
        resolved = resolved.resolve(strict=False)
        if not allow_external:
            try:
                resolved.relative_to(self.workspace_root)
            except ValueError as exc:
                raise ProjectServiceError(
                    f"Repository path `{repository_root}` escapes the workspace root `{self.workspace_root}`."
                ) from exc
        return resolved

    def _ensure_safe_repository_path(self, repository_root: Path, *, action: str) -> RepositorySafetyDecision:
        try:
            return self.safety_policy.ensure_path(repository_root, action)
        except ValueError as exc:
            raise ProjectServiceError(str(exc)) from exc

    @staticmethod
    def _default_executor(command: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True)