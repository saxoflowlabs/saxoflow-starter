"""Migration helpers from legacy workspace state to M2 contract files."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from .lockfiles import write_lockfiles
from .schema import (
    default_project_data,
    detect_project_layout,
    load_project_data,
    normalize_selected_tools,
    workspace_paths,
    write_project_data,
)

LEGACY_TOOLS_FILE = ".saxoflow_tools.json"


def _snapshot_contract_files(root: Path) -> Dict[Path, bytes]:
    """Capture current contract file bytes for rollback."""
    paths = workspace_paths(root)
    snapshots: Dict[Path, bytes] = {}
    for path in (paths.project_file, paths.toolchain_lock_file, paths.models_lock_file):
        if path.exists():
            snapshots[path] = path.read_bytes()
    return snapshots


def _restore_contract_files(root: Path, snapshots: Dict[Path, bytes]) -> None:
    """Restore captured contract file bytes and remove newly-created files."""
    paths = workspace_paths(root)
    managed_paths = (paths.project_file, paths.toolchain_lock_file, paths.models_lock_file)

    for path in managed_paths:
        if path in snapshots:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(snapshots[path])
        elif path.exists():
            path.unlink()


@dataclass(frozen=True)
class MigrationResult:
    """Result of a workspace migration run."""

    migrated: bool
    created_files: List[str]
    backup_file: Optional[str]
    selected_tools: List[str]


def load_legacy_selection(root: Path | str = ".") -> List[str]:
    """Load selected tools from legacy `.saxoflow_tools.json`."""
    legacy_file = Path(root) / LEGACY_TOOLS_FILE
    if not legacy_file.exists():
        return []
    try:
        loaded = json.loads(legacy_file.read_text(encoding="utf-8"))
    except Exception:
        return []
    return normalize_selected_tools(loaded if isinstance(loaded, list) else [])


def sync_workspace_selection(
    root: Path | str = ".",
    selected_tools: Optional[List[str]] = None,
    *,
    project_name: Optional[str] = None,
    layout: Optional[str] = None,
) -> List[str]:
    """Synchronize selected tools into the M2 workspace contract and lockfiles."""
    resolved_root = Path(root).resolve()
    snapshots = _snapshot_contract_files(resolved_root)
    normalized_tools = normalize_selected_tools(selected_tools or [])
    existing = load_project_data(resolved_root)

    if existing is None:
        project_data = default_project_data(
            project_name or resolved_root.name,
            normalized_tools,
            layout=layout or detect_project_layout(resolved_root),
        )
    else:
        project_data = existing
        project_section = project_data.setdefault("project", {})
        if not isinstance(project_section, dict):
            project_section = {}
            project_data["project"] = project_section
        project_section.setdefault("name", project_name or resolved_root.name)
        project_section.setdefault("layout", layout or detect_project_layout(resolved_root))

        toolchain = project_data.setdefault("toolchain", {})
        if not isinstance(toolchain, dict):
            toolchain = {}
            project_data["toolchain"] = toolchain
        toolchain["backend"] = str(toolchain.get("backend") or "system")
        toolchain["selected_tools"] = normalized_tools

        models = project_data.setdefault("models", {})
        if not isinstance(models, dict):
            models = {}
            project_data["models"] = models
        models.setdefault("selection_policy", "inherit")

        migration = project_data.setdefault("migration", {})
        if not isinstance(migration, dict):
            migration = {}
            project_data["migration"] = migration
        migration["legacy_tools_file"] = LEGACY_TOOLS_FILE if normalized_tools else None

    try:
        write_project_data(resolved_root, project_data)
        write_lockfiles(resolved_root, project_data)
    except Exception:
        _restore_contract_files(resolved_root, snapshots)
        raise

    paths = workspace_paths(resolved_root)
    return [
        str(paths.project_file),
        str(paths.toolchain_lock_file),
        str(paths.models_lock_file),
    ]


def migrate_legacy_workspace(root: Path | str = ".", *, backup: bool = True) -> MigrationResult:
    """Migrate legacy workspace state into the M2 contract files."""
    resolved_root = Path(root).resolve()
    paths = workspace_paths(resolved_root)
    legacy_file = resolved_root / LEGACY_TOOLS_FILE
    selected_tools = load_legacy_selection(resolved_root)

    backup_file: Optional[str] = None
    if backup and legacy_file.exists():
        paths.backup_dir.mkdir(parents=True, exist_ok=True)
        backup_path = paths.backup_dir / f"{LEGACY_TOOLS_FILE}.bak"
        shutil.copy2(legacy_file, backup_path)
        backup_file = str(backup_path)

    created_files = sync_workspace_selection(
        resolved_root,
        selected_tools,
        project_name=resolved_root.name,
        layout=detect_project_layout(resolved_root),
    )
    return MigrationResult(
        migrated=True,
        created_files=created_files,
        backup_file=backup_file,
        selected_tools=selected_tools,
    )