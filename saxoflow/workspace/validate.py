"""Workspace contract validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .schema import normalize_selected_tools, validate_project_data, workspace_paths


@dataclass(frozen=True)
class WorkspaceValidationResult:
    """Validation summary for a workspace contract."""

    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


def _load_yaml_file(path: Path) -> Dict[str, Any] | None:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def validate_workspace(root: Path | str = ".") -> WorkspaceValidationResult:
    """Validate workspace contract files and cross-file consistency."""
    paths = workspace_paths(root)
    errors: List[str] = []
    warnings: List[str] = []

    project_data = None
    if not paths.project_file.exists():
        errors.append("missing .saxoflow/project.yaml")
    else:
        project_data = _load_yaml_file(paths.project_file)
        if project_data is None:
            errors.append("project contract file is unreadable")
        else:
            errors.extend(validate_project_data(project_data))

    toolchain_lock = None
    if paths.toolchain_lock_file.exists():
        toolchain_lock = _load_yaml_file(paths.toolchain_lock_file)
        if toolchain_lock is None:
            errors.append("toolchain lockfile is unreadable")
    else:
        warnings.append("missing .saxoflow/toolchain.lock.yaml")

    models_lock = None
    if paths.models_lock_file.exists():
        models_lock = _load_yaml_file(paths.models_lock_file)
        if models_lock is None:
            errors.append("models lockfile is unreadable")
    else:
        warnings.append("missing .saxoflow/models.lock.yaml")

    if project_data and toolchain_lock:
        selected_tools = normalize_selected_tools(project_data.get("toolchain", {}).get("selected_tools", []))
        locked_tools = normalize_selected_tools(
            [entry.get("name", "") for entry in toolchain_lock.get("toolchain", {}).get("tools", [])]
        )
        if selected_tools != locked_tools:
            warnings.append("toolchain lockfile does not match selected_tools in project.yaml")

    return WorkspaceValidationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        details={
            "project_file": str(paths.project_file),
            "toolchain_lock_file": str(paths.toolchain_lock_file),
            "models_lock_file": str(paths.models_lock_file),
            "project": project_data,
            "toolchain_lock": toolchain_lock,
            "models_lock": models_lock,
        },
    )


def format_validation_report(result: WorkspaceValidationResult) -> str:
    """Format a user-facing validation report."""
    lines: List[str] = []
    if result.is_valid:
        lines.append("SUCCESS: Workspace contract is valid.")
    else:
        lines.append("ERROR: Workspace contract validation failed.")
    for error in result.errors:
        lines.append(f"ERROR: {error}")
    for warning in result.warnings:
        lines.append(f"WARNING: {warning}")
    return "\n".join(lines)