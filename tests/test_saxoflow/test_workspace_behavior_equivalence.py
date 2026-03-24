from __future__ import annotations

import json

from saxoflow.workspace.migrate import migrate_legacy_workspace, sync_workspace_selection
from saxoflow.workspace.schema import load_project_data, workspace_paths
from saxoflow.workspace.validate import validate_workspace


def _lockfile_bytes(root):
    paths = workspace_paths(root)
    return (
        paths.toolchain_lock_file.read_bytes(),
        paths.models_lock_file.read_bytes(),
    )


def test_fresh_and_migrated_workspace_are_behavior_equivalent(tmp_path):
    tools = ["iverilog", "yosys"]

    fresh_root = tmp_path / "fresh" / "workspace"
    migrated_root = tmp_path / "migrated" / "workspace"
    fresh_root.mkdir(parents=True)
    migrated_root.mkdir(parents=True)

    # Fresh initialization path.
    sync_workspace_selection(
        fresh_root,
        tools,
        project_name=fresh_root.name,
        layout="legacy-unit",
    )

    # Legacy migration path.
    (migrated_root / "source").mkdir()
    (migrated_root / ".saxoflow_tools.json").write_text(
        json.dumps(["yosys", "iverilog", "yosys"]),
        encoding="utf-8",
    )
    migrate_legacy_workspace(migrated_root, backup=False)

    fresh_project = load_project_data(fresh_root)
    migrated_project = load_project_data(migrated_root)

    assert fresh_project == migrated_project
    assert _lockfile_bytes(fresh_root) == _lockfile_bytes(migrated_root)

    fresh_validation = validate_workspace(fresh_root)
    migrated_validation = validate_workspace(migrated_root)

    assert fresh_validation.is_valid is True
    assert migrated_validation.is_valid is True
    assert fresh_validation.errors == migrated_validation.errors == []
    assert fresh_validation.warnings == migrated_validation.warnings == []
