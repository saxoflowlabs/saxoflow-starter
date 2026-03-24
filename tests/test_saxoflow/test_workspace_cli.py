from __future__ import annotations

import importlib
import json
import sys

from click.testing import CliRunner


def _reload_cli():
    sys.modules.pop("saxoflow.cli", None)
    return importlib.import_module("saxoflow.cli")


def test_workspace_init_and_validate_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sut = _reload_cli()
    runner = CliRunner()

    result = runner.invoke(sut.cli, ["workspace", "init"])
    assert result.exit_code == 0
    assert (tmp_path / ".saxoflow" / "project.yaml").exists()

    validate = runner.invoke(sut.cli, ["workspace", "validate"])
    assert validate.exit_code == 0
    assert "Workspace contract is valid" in validate.output


def test_workspace_migrate_and_lock_commands(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".saxoflow_tools.json").write_text(json.dumps(["iverilog", "yosys"]), encoding="utf-8")
    sut = _reload_cli()
    runner = CliRunner()

    migrate = runner.invoke(sut.cli, ["workspace", "migrate"])
    assert migrate.exit_code == 0
    assert "Migrated tools: iverilog, yosys" in migrate.output

    lock = runner.invoke(sut.cli, ["workspace", "lock"])
    assert lock.exit_code == 0
    assert (tmp_path / ".saxoflow" / "toolchain.lock.yaml").exists()


def test_workspace_lock_requires_project_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sut = _reload_cli()
    runner = CliRunner()

    result = runner.invoke(sut.cli, ["workspace", "lock"])
    assert result.exit_code != 0
    assert "Run 'saxoflow workspace init' first" in result.output