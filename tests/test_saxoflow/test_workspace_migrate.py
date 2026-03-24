from __future__ import annotations

import json

import pytest
import yaml

from saxoflow.workspace import migrate as sut
from saxoflow.workspace.schema import load_project_data, read_selected_tools


def test_load_legacy_selection_missing_invalid_and_valid(tmp_path):
    assert sut.load_legacy_selection(tmp_path) == []

    legacy = tmp_path / ".saxoflow_tools.json"
    legacy.write_text("{broken", encoding="utf-8")
    assert sut.load_legacy_selection(tmp_path) == []

    legacy.write_text(json.dumps(["yosys", "iverilog", "yosys"]), encoding="utf-8")
    assert sut.load_legacy_selection(tmp_path) == ["iverilog", "yosys"]


def test_sync_workspace_selection_creates_and_updates_contract(tmp_path):
    created = sut.sync_workspace_selection(tmp_path, ["yosys", "iverilog"], project_name="demo")
    assert len(created) == 3
    assert read_selected_tools(tmp_path) == ["iverilog", "yosys"]

    created_2 = sut.sync_workspace_selection(tmp_path, ["iverilog"], project_name="demo")
    assert created_2 == created
    assert read_selected_tools(tmp_path) == ["iverilog"]


def test_migrate_legacy_workspace_is_idempotent_and_creates_backup(tmp_path):
    (tmp_path / "source").mkdir()
    legacy = tmp_path / ".saxoflow_tools.json"
    legacy.write_text(json.dumps(["yosys", "iverilog"]), encoding="utf-8")

    first = sut.migrate_legacy_workspace(tmp_path)
    second = sut.migrate_legacy_workspace(tmp_path)

    assert first.migrated is True
    assert second.migrated is True
    assert first.selected_tools == ["iverilog", "yosys"]
    assert second.selected_tools == ["iverilog", "yosys"]
    assert first.backup_file is not None
    assert second.backup_file is not None

    project = load_project_data(tmp_path)
    assert project is not None
    assert project["project"]["layout"] == "legacy-unit"
    assert project["toolchain"]["selected_tools"] == ["iverilog", "yosys"]


def test_migrate_without_legacy_file_creates_empty_workspace(tmp_path):
    result = sut.migrate_legacy_workspace(tmp_path, backup=False)
    assert result.selected_tools == []
    project = load_project_data(tmp_path)
    assert project is not None
    assert project["toolchain"]["selected_tools"] == []


def test_sync_workspace_selection_repairs_malformed_existing_project(tmp_path):
    saxo_dir = tmp_path / ".saxoflow"
    saxo_dir.mkdir()
    (saxo_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "project": [],
                "toolchain": [],
                "models": [],
                "migration": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    sut.sync_workspace_selection(tmp_path, ["yosys"], project_name="demo", layout="workspace")
    project = load_project_data(tmp_path)
    assert project is not None
    assert project["project"]["name"] == "demo"
    assert project["toolchain"]["selected_tools"] == ["yosys"]
    assert project["models"]["selection_policy"] == "inherit"
    assert project["migration"]["legacy_tools_file"] == ".saxoflow_tools.json"


def test_sync_workspace_selection_rolls_back_when_lock_write_fails(tmp_path, monkeypatch):
    # Baseline existing project content that should survive rollback.
    original = {
        "schema_version": 1,
        "project": {"name": "baseline", "layout": "workspace"},
        "toolchain": {"backend": "system", "selected_tools": ["iverilog"]},
        "models": {"selection_policy": "inherit"},
        "migration": {"legacy_tools_file": ".saxoflow_tools.json"},
    }
    sut.sync_workspace_selection(tmp_path, ["iverilog"], project_name="baseline")

    # Force lockfile writer failure after project write to test rollback.
    monkeypatch.setattr(sut, "write_lockfiles", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        sut.sync_workspace_selection(tmp_path, ["yosys"], project_name="changed")

    restored = load_project_data(tmp_path)
    assert restored == original


def test_sync_workspace_selection_rolls_back_new_files_on_fresh_workspace(tmp_path, monkeypatch):
    # No workspace files exist initially.
    monkeypatch.setattr(sut, "write_lockfiles", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        sut.sync_workspace_selection(tmp_path, ["iverilog"], project_name="fresh")

    saxo_dir = tmp_path / ".saxoflow"
    assert not (saxo_dir / "project.yaml").exists()
    assert not (saxo_dir / "toolchain.lock.yaml").exists()
    assert not (saxo_dir / "models.lock.yaml").exists()


def test_sync_workspace_selection_rolls_back_when_project_write_fails(tmp_path, monkeypatch):
    # Create baseline contract files that should remain unchanged after rollback.
    sut.sync_workspace_selection(tmp_path, ["iverilog"], project_name="baseline")
    before = load_project_data(tmp_path)
    assert before is not None

    def _boom(*_args, **_kwargs):
        raise RuntimeError("project write failed")

    monkeypatch.setattr(sut, "write_project_data", _boom)

    with pytest.raises(RuntimeError, match="project write failed"):
        sut.sync_workspace_selection(tmp_path, ["yosys"], project_name="changed")

    after = load_project_data(tmp_path)
    assert after == before