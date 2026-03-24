"""Schema helpers for SaxoFlow workspace contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SCHEMA_VERSION = 1
WORKSPACE_DIRNAME = ".saxoflow"
PROJECT_FILE_NAME = "project.yaml"
TOOLCHAIN_LOCK_FILE_NAME = "toolchain.lock.yaml"
MODELS_LOCK_FILE_NAME = "models.lock.yaml"


@dataclass(frozen=True)
class WorkspacePaths:
    """Resolved filesystem paths for a workspace contract."""

    root: Path
    workspace_dir: Path
    project_file: Path
    toolchain_lock_file: Path
    models_lock_file: Path
    backup_dir: Path


def workspace_paths(root: Path | str = ".") -> WorkspacePaths:
    """Return canonical workspace contract paths for *root*."""
    resolved_root = Path(root).resolve()
    workspace_dir = resolved_root / WORKSPACE_DIRNAME
    return WorkspacePaths(
        root=resolved_root,
        workspace_dir=workspace_dir,
        project_file=workspace_dir / PROJECT_FILE_NAME,
        toolchain_lock_file=workspace_dir / TOOLCHAIN_LOCK_FILE_NAME,
        models_lock_file=workspace_dir / MODELS_LOCK_FILE_NAME,
        backup_dir=workspace_dir / "backups",
    )


def normalize_selected_tools(selected_tools: Optional[List[str]] = None) -> List[str]:
    """Return sorted unique tool selections as strings."""
    if not selected_tools:
        return []
    return sorted({str(tool) for tool in selected_tools if str(tool).strip()})


def detect_project_layout(root: Path | str) -> str:
    """Best-effort layout detection for migration/bootstrap flows."""
    resolved = Path(root)
    legacy_markers = [
        resolved / "source",
        resolved / "simulation",
        resolved / "synthesis",
        resolved / "formal",
    ]
    return "legacy-unit" if any(marker.exists() for marker in legacy_markers) else "workspace"


def default_project_data(
    project_name: str,
    selected_tools: Optional[List[str]] = None,
    *,
    layout: str = "workspace",
) -> Dict[str, Any]:
    """Return default project contract data for a workspace."""
    tools = normalize_selected_tools(selected_tools)
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "name": str(project_name),
            "layout": layout,
        },
        "toolchain": {
            "backend": "system",
            "selected_tools": tools,
        },
        "models": {
            "selection_policy": "inherit",
        },
        "migration": {
            "legacy_tools_file": ".saxoflow_tools.json" if tools else None,
        },
    }


def validate_project_data(data: Dict[str, Any]) -> List[str]:
    """Validate project contract data and return a list of errors."""
    errors: List[str] = []
    if not isinstance(data, dict):
        return ["project contract must be a mapping"]

    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")

    project = data.get("project")
    if not isinstance(project, dict):
        errors.append("project section is required")
    else:
        name = project.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append("project.name must be a non-empty string")
        layout = project.get("layout")
        if layout is not None and not isinstance(layout, str):
            errors.append("project.layout must be a string when provided")

    toolchain = data.get("toolchain")
    if not isinstance(toolchain, dict):
        errors.append("toolchain section is required")
    else:
        backend = toolchain.get("backend")
        if not isinstance(backend, str) or not backend.strip():
            errors.append("toolchain.backend must be a non-empty string")
        selected_tools = toolchain.get("selected_tools")
        if not isinstance(selected_tools, list):
            errors.append("toolchain.selected_tools must be a list")
        elif any(not isinstance(tool, str) or not tool.strip() for tool in selected_tools):
            errors.append("toolchain.selected_tools must contain non-empty strings")

    models = data.get("models")
    if not isinstance(models, dict):
        errors.append("models section is required")
    else:
        policy = models.get("selection_policy")
        if policy is not None and not isinstance(policy, str):
            errors.append("models.selection_policy must be a string when provided")

    migration = data.get("migration")
    if migration is not None and not isinstance(migration, dict):
        errors.append("migration section must be a mapping when provided")

    return errors


def _atomic_write_yaml(path: Path, data: Dict[str, Any]) -> None:
    """Atomically write YAML data to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp_path.replace(path)


def write_project_data(root: Path | str, data: Dict[str, Any]) -> Path:
    """Validate and write project contract data."""
    errors = validate_project_data(data)
    if errors:
        raise ValueError("; ".join(errors))

    paths = workspace_paths(root)
    _atomic_write_yaml(paths.project_file, data)
    return paths.project_file


def load_project_data(root: Path | str = ".") -> Optional[Dict[str, Any]]:
    """Load workspace project contract if present and parseable."""
    paths = workspace_paths(root)
    if not paths.project_file.exists():
        return None
    try:
        loaded = yaml.safe_load(paths.project_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def read_selected_tools(root: Path | str = ".") -> List[str]:
    """Read selected tools from project contract, returning [] when absent/invalid."""
    data = load_project_data(root)
    if not data:
        return []
    toolchain = data.get("toolchain")
    if not isinstance(toolchain, dict):
        return []
    selected_tools = toolchain.get("selected_tools")
    if not isinstance(selected_tools, list):
        return []
    return normalize_selected_tools(selected_tools)