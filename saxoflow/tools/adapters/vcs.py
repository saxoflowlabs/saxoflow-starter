"""VCS adapter that wraps repository acquisition and comparison actions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from saxoflow.schemas.tools import ToolRequest, ToolRun
from saxoflow.services.project_service import ProjectService, ProjectServiceError, RepositoryPolicy
from saxoflow.tools.adapters.base import BaseToolAdapter, ToolAdapterError


class VcsToolAdapter(BaseToolAdapter):
    """Capability adapter for repository acquisition and VCS action previews."""

    capability = "repo.acquire"

    def __init__(
        self,
        *,
        policy: Optional[RepositoryPolicy] = None,
        executor: Any = None,
    ) -> None:
        self.policy = policy or RepositoryPolicy()
        self.executor = executor
        super().__init__()

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._vcs_options(request)
        service = ProjectService.from_workspace(root, policy=self.policy, executor=self.executor)

        try:
            operation = self._dispatch(service, options)
        except ProjectServiceError as exc:
            return ToolRun.from_mapping(
                {
                    "status": "failed",
                    "capability": self.capability,
                    "tool_name": "git",
                    "command": options["command_preview"],
                    "diagnostics": [
                        {
                            "message": str(exc),
                            "severity": "error",
                            "source": "project_service",
                        }
                    ],
                }
            )

        stdout = json.dumps(operation.to_dict(), indent=2, sort_keys=True)
        if request.dry_run:
            return ToolRun.from_mapping(
                {
                    "status": "skipped",
                    "capability": self.capability,
                    "tool_name": "git",
                    "command": options["command_preview"],
                    "stdout": stdout,
                    "diagnostics": [],
                }
            )

        status = "success" if operation.exit_code in (None, 0) else "failed"
        payload = {
            "status": status,
            "capability": self.capability,
            "tool_name": "git",
            "command": options["command_preview"],
            "stdout": stdout,
            "diagnostics": [],
        }
        if operation.exit_code is not None:
            payload["exit_code"] = operation.exit_code
        if operation.stderr:
            payload["stderr"] = operation.stderr
        return ToolRun.from_mapping(payload)

    def _dispatch(self, service: ProjectService, options: Mapping[str, Any]):
        action = options["action"]
        if action == "clone":
            return service.clone_repository(
                options["remote_url"],
                options["destination"],
                branch=options.get("reference"),
                dry_run=options["dry_run"],
            )
        if action == "fetch":
            return service.fetch_repository(
                options["repository_root"],
                remote=options.get("remote", "origin"),
                dry_run=options["dry_run"],
            )
        if action == "checkout":
            return service.checkout_repository(
                options["repository_root"],
                options["reference"],
                dry_run=options["dry_run"],
            )
        if action == "diff":
            return service.diff_repository(
                options["repository_root"],
                base=options.get("base", "HEAD"),
                target=options.get("target", "HEAD"),
                dry_run=options["dry_run"],
            )
        raise ToolAdapterError("VCS action must be one of: clone, fetch, checkout, diff.")

    def _vcs_options(self, request: ToolRequest) -> Dict[str, Any]:
        raw = request.options.get("vcs") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        action = str(options.get("action", "clone")).strip().lower()

        if action not in {"clone", "fetch", "checkout", "diff"}:
            raise ToolAdapterError("VCS option `action` must be one of: clone, fetch, checkout, diff.")

        command_preview = self._command_preview(action, options)
        resolved: Dict[str, Any] = {
            "action": action,
            "dry_run": bool(options.get("dry_run", request.dry_run)),
            "command_preview": command_preview,
        }

        if action == "clone":
            remote_url = self._optional_string(options.get("remote_url"))
            destination = self._optional_string(options.get("destination"))
            if remote_url is None or destination is None:
                raise ToolAdapterError("Clone requires `remote_url` and `destination`.")
            resolved.update(
                {
                    "remote_url": remote_url,
                    "destination": destination,
                    "reference": self._optional_string(options.get("branch")),
                }
            )
        else:
            repository_root = self._optional_string(options.get("repository_root"))
            if repository_root is None:
                raise ToolAdapterError(f"VCS action `{action}` requires `repository_root`.")
            resolved["repository_root"] = repository_root
            if action == "fetch":
                resolved["remote"] = self._optional_string(options.get("remote")) or "origin"
            elif action == "checkout":
                reference = self._optional_string(options.get("reference"))
                if reference is None:
                    raise ToolAdapterError("Checkout requires `reference`.")
                resolved["reference"] = reference
            elif action == "diff":
                resolved["base"] = self._optional_string(options.get("base")) or "HEAD"
                resolved["target"] = self._optional_string(options.get("target")) or "HEAD"

        return resolved

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _command_preview(action: str, options: Mapping[str, Any]) -> str:
        if action == "clone":
            branch = options.get("branch")
            branch_text = f" --branch {branch}" if branch else ""
            return f"git clone{branch_text} {options.get('remote_url')} {options.get('destination')}"
        if action == "fetch":
            return f"git fetch {options.get('remote') or 'origin'} {options.get('repository_root')}"
        if action == "checkout":
            return f"git checkout {options.get('reference')} {options.get('repository_root')}"
        return f"git diff {options.get('base') or 'HEAD'} {options.get('target') or 'HEAD'} {options.get('repository_root')}"