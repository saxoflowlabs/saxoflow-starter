"""Tests for the design-agnostic SaxoFlow RTL lint command."""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import List

from click.testing import CliRunner

import saxoflow.lintflow as lintflow


def _chdir(path: Path):
    class _Context:
        def __enter__(self):
            self.previous = Path.cwd()
            os.chdir(path)
            return path

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self.previous)

    return _Context()


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _unit_root(tmp_path: Path) -> Path:
    _write(tmp_path / "Makefile", "all:\n\t@true\n")
    return tmp_path


def _install_fake_engines(monkeypatch, available=("verible", "verilator")):
    binaries = {
        "verible": "/tools/verible-verilog-lint",
        "verilator": "/tools/verilator",
    }
    monkeypatch.setattr(
        lintflow,
        "_find_engine_binary",
        lambda engine: binaries[engine] if engine in available else None,
    )


def test_lint_is_design_agnostic():
    source = Path(lintflow.__file__).read_text(encoding="utf-8")
    assert "traffic_controller" not in source


def test_lint_default_discovery_runs_both_engines_and_writes_reports(
    tmp_path,
    monkeypatch,
):
    root = _unit_root(tmp_path)
    _write(
        root / "source/rtl/systemverilog/z_types.sv",
        "package sample_types; typedef logic bit_t; endpackage\n",
    )
    _write(
        root / "source/rtl/systemverilog/a_core.sv",
        "module sample_core; endmodule\n",
    )
    _write(root / "source/rtl/verilog/helper.v", "module helper; endmodule\n")
    (root / "source/rtl/include").mkdir(parents=True)
    _install_fake_engines(monkeypatch)
    commands: List[List[str]] = []

    def fake_run(command, cwd, capture_output, text):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(lintflow.subprocess, "run", fake_run)

    with _chdir(root):
        result = CliRunner().invoke(lintflow.lint, [])

    assert result.exit_code == 0, result.output
    assert len(commands) == 2
    assert commands[0][0] == "/tools/verible-verilog-lint"
    assert commands[1][0] == "/tools/verilator"
    package_index = commands[1].index("source/rtl/systemverilog/z_types.sv")
    core_index = commands[1].index("source/rtl/systemverilog/a_core.sv")
    assert package_index < core_index
    assert "-Isource/rtl/include" in commands[1]
    reports = sorted((root / "lint/reports").glob("*.log"))
    assert len(reports) == 2
    assert any(path.name.endswith("-verible.log") for path in reports)
    assert any(path.name.endswith("-verilator.log") for path in reports)


def test_lint_explicit_file_directory_glob_and_testbench(
    tmp_path,
    monkeypatch,
):
    root = _unit_root(tmp_path)
    _write(root / "custom/rtl/a.sv", "module a; endmodule\n")
    _write(root / "custom/rtl/nested/b.v", "module b; endmodule\n")
    _write(root / "source/tb/systemverilog/a_tb.sv", "module a_tb; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verilator",))
    commands = []

    def fake_run(command, cwd, capture_output, text):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(lintflow.subprocess, "run", fake_run)

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            [
                "--rtl",
                "custom/rtl/a.sv",
                "--rtl",
                "custom/rtl",
                "--rtl",
                "custom/rtl/**/*.v",
                "--include-tb",
                "--tool",
                "verilator",
                "--top",
                "a_tb",
            ],
        )

    assert result.exit_code == 0, result.output
    command = commands[0]
    assert command.count("custom/rtl/a.sv") == 1
    assert command.count("custom/rtl/nested/b.v") == 1
    assert "source/tb/systemverilog/a_tb.sv" in command
    assert "--timing" in command
    assert command[command.index("--top-module") + 1] == "a_tb"


def test_lint_verible_options_are_forwarded(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _write(root / ".rules.verible_lint", "")
    _write(root / "lint.waiver", "")
    _install_fake_engines(monkeypatch, available=("verible",))
    commands = []

    def fake_run(command, cwd, capture_output, text):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(lintflow.subprocess, "run", fake_run)

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            [
                "--tool",
                "verible",
                "--ruleset",
                "all",
                "--rules",
                "-line-length",
                "--config",
                ".rules.verible_lint",
                "--waiver",
                "lint.waiver",
            ],
        )

    assert result.exit_code == 0, result.output
    command = commands[0]
    assert "--ruleset=all" in command
    assert "--rules=-line-length" in command
    assert "--rules_config=.rules.verible_lint" in command
    assert "--waiver_files=lint.waiver" in command
    assert "--rules_config_search" not in command


def test_lint_auto_warns_and_uses_available_engine(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/systemverilog/sample_core.sv", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verible",))
    monkeypatch.setattr(
        lintflow.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )

    with _chdir(root):
        result = CliRunner().invoke(lintflow.lint, [])

    assert result.exit_code == 0
    assert "Skipping unavailable lint engine(s): verilator" in result.output
    assert "verible passed" in result.output


def test_lint_all_requires_both_engines(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verible",))

    with _chdir(root):
        result = CliRunner().invoke(lintflow.lint, ["--tool", "all"])

    assert result.exit_code != 0
    assert "Requested lint engines are missing: verilator" in result.output


def test_lint_rejects_vhdl_input(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "custom/sample_core.vhd", "entity sample_core is end entity;\n")
    _install_fake_engines(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            ["--rtl", "custom/sample_core.vhd"],
        )

    assert result.exit_code != 0
    assert "VHDL linting is not supported" in result.output


def test_lint_no_fail_preserves_report_and_returns_success(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verilator",))
    monkeypatch.setattr(
        lintflow.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="%Warning-WIDTH: width mismatch",
        ),
    )

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            ["--tool", "verilator", "--no-fail"],
        )

    assert result.exit_code == 0, result.output
    assert "Lint issues were found, but --no-fail was requested" in result.output
    report = next((root / "lint/reports").glob("*-verilator.log"))
    assert "width mismatch" in report.read_text(encoding="utf-8")


def test_lint_failure_returns_nonzero(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verible",))
    monkeypatch.setattr(
        lintflow.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="source/rtl/verilog/sample_core.v:1: style issue",
            stderr="",
        ),
    )

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            ["--tool", "verible"],
        )

    assert result.exit_code == 1
    assert "verible reported issues" in result.output


def test_lint_no_fail_does_not_hide_engine_launch_errors(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=("verible",))

    def fail_to_launch(*args, **kwargs):
        raise OSError("not executable")

    monkeypatch.setattr(lintflow.subprocess, "run", fail_to_launch)

    with _chdir(root):
        result = CliRunner().invoke(
            lintflow.lint,
            ["--tool", "verible", "--no-fail"],
        )

    assert result.exit_code == 1
    assert "Failed to execute" in result.output


def test_lint_reports_missing_sources_and_tools(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    with _chdir(root):
        no_sources = CliRunner().invoke(lintflow.lint, [])
    assert no_sources.exit_code != 0
    assert "No Verilog/SystemVerilog RTL files found" in no_sources.output

    _write(root / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _install_fake_engines(monkeypatch, available=())
    with _chdir(root):
        no_tools = CliRunner().invoke(lintflow.lint, [])
    assert no_tools.exit_code != 0
    assert "No lint engine is installed" in no_tools.output
    assert "saxoflow install lint" in no_tools.output


def test_lint_requires_unit_root(tmp_path):
    with _chdir(tmp_path):
        result = CliRunner().invoke(lintflow.lint, [])
    assert result.exit_code != 0
    assert "Run `saxoflow lint` from a SaxoFlow unit root" in result.output
