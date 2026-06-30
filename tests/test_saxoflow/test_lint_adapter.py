"""Tests for the Phase 2 lint tool adapter."""

from __future__ import annotations

from pathlib import Path

import saxoflow.lintflow as lintflow
from saxoflow.schemas.tools import ToolRequest
from saxoflow.tools.adapters.lint import LintToolAdapter


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _unit_root(tmp_path: Path) -> Path:
    _write(tmp_path / "Makefile", "all:\n\t@true\n")
    _write(tmp_path / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    return tmp_path


def test_lint_adapter_returns_normalized_diagnostics(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    monkeypatch.setattr(
        lintflow,
        "_find_engine_binary",
        lambda engine: "/tools/verible-verilog-lint" if engine == "verible" else None,
    )
    monkeypatch.setattr(
        lintflow,
        "_run_engine",
        lambda command, cwd: (
            1,
            "source/rtl/verilog/sample_core.v:12:3: warning: style issue",
            False,
        ),
    )

    adapter = LintToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "lint.run",
            "workspace": str(root),
            "options": {
                "lint": {
                    "tool": "verible",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.tool_name == "verible"
    assert run.exit_code == 1
    assert len(run.diagnostics) >= 1
    first = run.diagnostics[0]
    assert first.source == "verible"
    assert first.path == "source/rtl/verilog/sample_core.v"
    assert first.line == 12
    assert first.column == 3
    assert first.severity == "warning"


def test_lint_adapter_reports_missing_engine_as_diagnostic(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    monkeypatch.setattr(lintflow, "_find_engine_binary", lambda engine: None)

    adapter = LintToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "lint.run",
            "workspace": str(root),
            "options": {
                "lint": {
                    "tool": "verible",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.exit_code == 1
    assert len(run.diagnostics) == 1
    assert "not installed" in run.diagnostics[0].message.lower()


def test_lint_adapter_dry_run_returns_planned_command_without_execution(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    monkeypatch.setattr(
        lintflow,
        "_find_engine_binary",
        lambda engine: "/tools/verible-verilog-lint" if engine == "verible" else None,
    )

    def fail_run_engine(command, cwd):
        raise AssertionError("dry-run should not execute lint engines")

    monkeypatch.setattr(lintflow, "_run_engine", fail_run_engine)

    adapter = LintToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "lint.run",
            "workspace": str(root),
            "dry_run": True,
            "options": {
                "lint": {
                    "tool": "verible",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "skipped"
    assert run.capability == "lint.run"
    assert run.command is not None
    assert "verible-verilog-lint" in run.command
    assert run.diagnostics == ()
