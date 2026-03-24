"""
M2 Integration tests: workspace contract lifecycle, schema edge-case coverage,
and installer-contract integration paths.

Coverage goals
--------------
- validate_project_data: all missing error branches (non-dict input, missing
  sections, wrong types for layout/toolchain/selected_tools/models)
- write_project_data: error-path (invalid data raises ValueError)
- load_project_data: non-dict YAML payload returns None
- read_selected_tools: toolchain not dict → []; selected_tools not list → []
- Full unit-project lifecycle: unit init → workspace migrate → validate → lock
- Installer-contract integration: dump_tool_selection updates workspace contract
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from saxoflow.workspace import schema as sut
from saxoflow.workspace.migrate import migrate_legacy_workspace, sync_workspace_selection
from saxoflow.workspace.validate import validate_workspace


# ---------------------------------------------------------------------------
# validate_project_data edge-case branches
# ---------------------------------------------------------------------------

class TestValidateProjectDataEdgeCases:
    """Cover all missing branches of validate_project_data."""

    def test_non_dict_input_returns_early_with_error(self):
        """Non-dict input returns early without checking other fields."""
        errors = sut.validate_project_data("not a dict")
        assert errors == ["project contract must be a mapping"]

    def test_project_not_dict_emits_section_required(self):
        """project key present but not a dict triggers 'project section is required'."""
        data = sut.default_project_data("demo")
        data["project"] = "not_a_dict"
        errors = sut.validate_project_data(data)
        assert any("project section is required" in e for e in errors)

    def test_project_layout_not_string_when_provided(self):
        """project.layout set to non-string triggers layout error."""
        data = sut.default_project_data("demo")
        data["project"]["layout"] = 42
        errors = sut.validate_project_data(data)
        assert any("project.layout" in e for e in errors)

    def test_toolchain_not_dict_triggers_section_required(self):
        """toolchain key present but not a dict triggers 'toolchain section is required'."""
        data = sut.default_project_data("demo")
        data["toolchain"] = "not_a_dict"
        errors = sut.validate_project_data(data)
        assert any("toolchain section is required" in e for e in errors)

    def test_selected_tools_not_list_triggers_error(self):
        """toolchain.selected_tools set to non-list triggers list error."""
        data = sut.default_project_data("demo")
        data["toolchain"]["selected_tools"] = "iverilog"
        errors = sut.validate_project_data(data)
        assert any("selected_tools must be a list" in e for e in errors)

    def test_models_not_dict_triggers_section_required(self):
        """models key present but not a dict triggers 'models section is required'."""
        data = sut.default_project_data("demo")
        data["models"] = "not_a_dict"
        errors = sut.validate_project_data(data)
        assert any("models section is required" in e for e in errors)


# ---------------------------------------------------------------------------
# write_project_data error path
# ---------------------------------------------------------------------------

def test_write_project_data_raises_on_invalid_data(tmp_path):
    """write_project_data should raise ValueError when validation fails."""
    bad_data = {"schema_version": 99, "project": {"name": "bad"}}
    with pytest.raises(ValueError, match="schema_version"):
        sut.write_project_data(tmp_path, bad_data)


# ---------------------------------------------------------------------------
# load_project_data: non-dict YAML
# ---------------------------------------------------------------------------

def test_load_project_data_non_dict_yaml_returns_none(tmp_path):
    """YAML with non-dict root (e.g., a plain list) returns None."""
    ws_dir = tmp_path / ".saxoflow"
    ws_dir.mkdir()
    (ws_dir / "project.yaml").write_text(
        yaml.safe_dump(["a", "b", "c"]), encoding="utf-8"
    )
    assert sut.load_project_data(tmp_path) is None


# ---------------------------------------------------------------------------
# read_selected_tools edge cases
# ---------------------------------------------------------------------------

def test_read_selected_tools_toolchain_not_dict_returns_empty(tmp_path):
    """When project.yaml has toolchain as a non-dict, read_selected_tools returns []."""
    data = sut.default_project_data("demo", ["yosys"])
    data["toolchain"] = "oops_not_a_dict"
    ws_dir = tmp_path / ".saxoflow"
    ws_dir.mkdir()
    (ws_dir / "project.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert sut.read_selected_tools(tmp_path) == []


def test_read_selected_tools_selected_tools_not_list_returns_empty(tmp_path):
    """When toolchain.selected_tools is a string (not list), returns empty."""
    data = sut.default_project_data("demo", ["yosys"])
    data["toolchain"]["selected_tools"] = "yosys"
    ws_dir = tmp_path / ".saxoflow"
    ws_dir.mkdir()
    (ws_dir / "project.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert sut.read_selected_tools(tmp_path) == []


# ---------------------------------------------------------------------------
# normalize_selected_tools: empty / None input
# ---------------------------------------------------------------------------

def test_normalize_selected_tools_with_empty_and_none():
    """normalize_selected_tools([]) and normalize_selected_tools(None) both return []."""
    assert sut.normalize_selected_tools([]) == []
    assert sut.normalize_selected_tools(None) == []


# ---------------------------------------------------------------------------
# Full unit-project workspace lifecycle
# ---------------------------------------------------------------------------

def test_unit_project_full_workspace_lifecycle(tmp_path):
    """
    Simulates the complete workspace lifecycle for a unit project:
      1. Scaffold project structure (as `saxoflow unit` does)
      2. sync_workspace_selection → creates .saxoflow/project.yaml + lockfiles
      3. Add a legacy .saxoflow_tools.json (simulating pre-M2 project)
      4. migrate_legacy_workspace → reads legacy file, updates contract, creates backup
      5. validate_workspace → reports valid contract

    This covers the full M2 exit criterion:
      "Migration succeeds on representative legacy projects."
    """
    # Step 1: Scaffold project structure (mimics saxoflow unit init)
    proj = tmp_path / "myproject"
    proj.mkdir()
    for sub in ["source/rtl/verilog", "simulation/icarus", "synthesis/scripts"]:
        (proj / sub).mkdir(parents=True, exist_ok=True)

    # Step 2: Init workspace contract (initial tool selection: yosys)
    sync_workspace_selection(proj, ["yosys"], project_name="myproject")
    proj_yaml = proj / ".saxoflow" / "project.yaml"
    assert proj_yaml.exists()
    data = yaml.safe_load(proj_yaml.read_text(encoding="utf-8"))
    assert data["toolchain"]["selected_tools"] == ["yosys"]

    # Step 3: Add legacy .saxoflow_tools.json as if user selected tools before M2
    legacy_file = proj / ".saxoflow_tools.json"
    legacy_file.write_text(json.dumps(["iverilog", "yosys", "gtkwave", "yosys"]))

    # Step 4: Run migration — should pick up legacy tools, deduplicate, create backup
    result = migrate_legacy_workspace(proj, backup=True)
    assert result.migrated
    assert sorted(result.selected_tools) == ["gtkwave", "iverilog", "yosys"]

    # Step 5: Validate workspace contract
    validation = validate_workspace(proj)
    assert validation.is_valid
    assert validation.errors == []


# ---------------------------------------------------------------------------
# Installer-contract integration: dump_tool_selection updates workspace contract
# ---------------------------------------------------------------------------

def test_dump_tool_selection_updates_workspace_contract(tmp_path, monkeypatch):
    """
    When dump_tool_selection is called (e.g., from interactive env setup),
    the workspace contract at .saxoflow/project.yaml is updated to reflect
    the new tool selection.

    Verifies M2 integration between installer/interactive_env.py and
    the workspace contract system.
    """
    import saxoflow.installer.interactive_env as env_sut

    legacy_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(env_sut, "TOOLS_FILE", legacy_file, raising=True)

    # Simulate initial tool selection via interactive env
    tools = ["iverilog", "yosys", "gtkwave"]
    env_sut.dump_tool_selection(tools)

    # Legacy file should exist
    assert legacy_file.exists()
    assert json.loads(legacy_file.read_text()) == tools

    # Workspace contract should be updated via sync_workspace_selection
    project_yaml = tmp_path / ".saxoflow" / "project.yaml"
    assert project_yaml.exists(), "Workspace contract must be created by dump_tool_selection"
    data = yaml.safe_load(project_yaml.read_text(encoding="utf-8"))
    assert sorted(data["toolchain"]["selected_tools"]) == sorted(set(tools))


# ---------------------------------------------------------------------------
# Real-world migrate → validate round-trip for multiple project shapes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout_dirs,legacy_tools,expect_valid", [
    # Shape A: standard SaxoFlow unit project with EDA layout
    (["source/rtl/verilog", "simulation/icarus", "synthesis/scripts", "formal/scripts"],
     ["iverilog", "yosys", "symbiyosys"],
     True),
    # Shape B: minimal project with only simulation layout
    (["simulation"],
     ["iverilog"],
     True),
    # Shape C: no layout markers (workspace-only)
    ([],
     ["gtkwave"],
     True),
    # Shape D: project with duplicate tools in legacy file
    (["source", "simulation"],
     ["yosys", "iverilog", "yosys", "gtkwave", "iverilog"],
     True),
])
def test_real_project_migration_matrix_shapes(
    tmp_path, layout_dirs, legacy_tools, expect_valid
):
    """
    Migrate legacy project shapes to workspace contract and verify:
    - migrate_legacy_workspace succeeds
    - migrated tools are deduplicated and normalized
    - workspace contract passes validation after migration
    """
    proj = tmp_path / "project"
    proj.mkdir()
    for sub in layout_dirs:
        (proj / sub).mkdir(parents=True, exist_ok=True)

    (proj / ".saxoflow_tools.json").write_text(json.dumps(legacy_tools))

    result = migrate_legacy_workspace(proj, backup=False)
    assert result.migrated, f"Migration failed: {result}"
    assert result.selected_tools == sorted(set(legacy_tools))

    validation = validate_workspace(proj)
    assert validation.is_valid == expect_valid
    if expect_valid:
        assert validation.errors == []


# ---------------------------------------------------------------------------
# CLI-level workspace lifecycle test (subprocess-based real command surface)
# ---------------------------------------------------------------------------

def test_workspace_cli_end_to_end(tmp_path):
    """
    End-to-end CLI invocation test:
      1. Create a project directory with legacy .saxoflow_tools.json
      2. Run `saxoflow workspace migrate` → must exit 0
      3. Run `saxoflow workspace validate` → must exit 0 and report valid
    """
    proj = tmp_path / "cli_test_proj"
    proj.mkdir()
    (proj / ".saxoflow_tools.json").write_text(json.dumps(["yosys", "iverilog"]))

    migrate_result = subprocess.run(
        [sys.executable, "-m", "saxoflow.cli", "workspace", "migrate", "--no-backup"],
        cwd=str(proj),
        capture_output=True,
        text=True,
    )
    assert migrate_result.returncode == 0, (
        f"workspace migrate failed:\nstdout: {migrate_result.stdout}\nstderr: {migrate_result.stderr}"
    )

    validate_result = subprocess.run(
        [sys.executable, "-m", "saxoflow.cli", "workspace", "validate"],
        cwd=str(proj),
        capture_output=True,
        text=True,
    )
    assert validate_result.returncode == 0, (
        f"workspace validate failed:\nstdout: {validate_result.stdout}\nstderr: {validate_result.stderr}"
    )
    output = validate_result.stdout + validate_result.stderr
    # validate must report valid status
    assert any(kw in output.lower() for kw in ["valid", "ok", "passed", "success"]), (
        f"Expected 'valid' in output but got:\n{output}"
    )
