from __future__ import annotations

import yaml

from saxoflow.workspace.lockfiles import write_lockfiles
from saxoflow.workspace.schema import default_project_data, write_project_data
from saxoflow.workspace.validate import format_validation_report, validate_workspace


def test_validate_workspace_reports_missing_project(tmp_path):
    result = validate_workspace(tmp_path)
    assert result.is_valid is False
    assert "missing .saxoflow/project.yaml" in result.errors
    assert "missing .saxoflow/toolchain.lock.yaml" in result.warnings
    assert "missing .saxoflow/models.lock.yaml" in result.warnings


def test_validate_workspace_reports_unreadable_lockfiles(tmp_path):
    project = default_project_data("demo", ["yosys"])
    write_project_data(tmp_path, project)
    saxo_dir = tmp_path / ".saxoflow"
    (saxo_dir / "toolchain.lock.yaml").write_text(": bad", encoding="utf-8")
    (saxo_dir / "models.lock.yaml").write_text("[]", encoding="utf-8")

    result = validate_workspace(tmp_path)
    assert result.is_valid is False
    assert "toolchain lockfile is unreadable" in result.errors
    assert "models lockfile is unreadable" in result.errors


def test_validate_workspace_warns_when_selected_tools_do_not_match_lockfile(tmp_path):
    project = default_project_data("demo", ["iverilog", "yosys"])
    write_project_data(tmp_path, project)
    write_lockfiles(tmp_path, project)

    toolchain_lock = tmp_path / ".saxoflow" / "toolchain.lock.yaml"
    data = yaml.safe_load(toolchain_lock.read_text(encoding="utf-8"))
    data["toolchain"]["tools"] = [{"name": "iverilog", "source": "apt", "version": "unknown"}]
    toolchain_lock.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    result = validate_workspace(tmp_path)
    assert result.is_valid is True
    assert "toolchain lockfile does not match selected_tools in project.yaml" in result.warnings


def test_format_validation_report_for_success_and_failure(tmp_path):
    project = default_project_data("demo", ["yosys"])
    write_project_data(tmp_path, project)
    write_lockfiles(tmp_path, project)

    success = validate_workspace(tmp_path)
    assert format_validation_report(success) == "SUCCESS: Workspace contract is valid."

    (tmp_path / ".saxoflow" / "project.yaml").write_text("[]", encoding="utf-8")
    failure = validate_workspace(tmp_path)
    report = format_validation_report(failure)
    assert report.startswith("ERROR: Workspace contract validation failed.")
    assert "ERROR: project contract file is unreadable" in report