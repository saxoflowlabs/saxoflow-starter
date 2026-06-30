"""Tests for the Phase 2 formal tool adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

import saxoflow.makeflow as makeflow
from saxoflow.schemas.agents import AgentSchemaError, FormalPropertySpec, FormalProofSummary
from saxoflow.schemas.tools import FormalProofResult, FormalRunOptions, ToolRequest, ToolSchemaError
from saxoflow.tools.adapters.formal import FormalToolAdapter


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _unit_root(tmp_path: Path) -> Path:
    _write(tmp_path / "Makefile", "all:\n\t@true\n")
    _write(tmp_path / "source/rtl/systemverilog/sample_core.sv", "module sample_core; endmodule\n")
    _write(tmp_path / "formal/source/sample_core_formal.sv", "module sample_core_formal; endmodule\n")
    _write(tmp_path / "formal/scripts/prop.sby", "[options]\nmode bmc\n")
    return tmp_path


def test_formal_adapter_returns_success_and_reports_outputs(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    monkeypatch.setattr(makeflow.shutil, "which", lambda *_: "/usr/bin/z3")

    def fake_run_make(target, extra_vars=None):
        _write(root / "formal/reports/result.txt", "proof result\n")
        _write(root / "formal/out/counterexample.vcd", "trace\n")
        return {"stdout": "formal complete", "stderr": "", "returncode": 0}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)

    adapter = FormalToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "formal.run",
            "workspace": str(root),
            "options": {
                "formal": {
                    "solver": "z3",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert run.capability == "formal.run"
    assert run.tool_name == "symbiyosys"
    assert run.exit_code == 0
    assert run.diagnostics == ()
    assert "formal complete" in (run.stdout or "")
    assert "Formal outputs" in (run.stdout or "")
    assert "formal/reports/result.txt" in (run.stdout or "")
    assert "formal/out/counterexample.vcd" in (run.stdout or "")
    assert "Counterexample references:" in (run.stdout or "")


def test_formal_adapter_parses_counterexample_refs_on_failure(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    monkeypatch.setattr(makeflow.shutil, "which", lambda *_: "/usr/bin/z3")

    def fake_run_make(target, extra_vars=None):
        _write(root / "formal/out/counterexample.vcd", "trace\n")
        return {
            "stdout": "formal run complete with failures",
            "stderr": "assert failed at formal/out/counterexample.vcd:42",
            "returncode": 2,
        }

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)

    adapter = FormalToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "formal.run",
            "workspace": str(root),
            "options": {
                "formal": {
                    "solver": "z3",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.diagnostics
    messages = [diag.message for diag in run.diagnostics]
    assert any("Counterexample references:" in message for message in messages)
    assert any("counterexample.vcd:42" in message or "formal/out/counterexample.vcd" in message for message in messages)


def test_formal_adapter_returns_failure_on_solver_or_make_error(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    monkeypatch.setattr(makeflow.shutil, "which", lambda *_: None)

    def fake_run_make(target, extra_vars=None):
        return {"stdout": "", "stderr": "ERROR: proof failed", "returncode": 2}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)

    adapter = FormalToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "formal.run",
            "workspace": str(root),
            "options": {
                "formal": {
                    "solver": "z3",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.capability == "formal.run"
    assert run.exit_code == 1
    assert len(run.diagnostics) == 1
    assert "not available" in run.diagnostics[0].message.lower()


def test_formal_adapter_dry_run_returns_planned_command_without_execution(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    def fail_run_make(target, extra_vars=None):
        raise AssertionError("dry-run should not execute formal flow")

    monkeypatch.setattr(makeflow, "run_make", fail_run_make)

    adapter = FormalToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "formal.run",
            "workspace": str(root),
            "dry_run": True,
            "options": {
                "formal": {
                    "solver": "z3",
                    "timeout": 30,
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "skipped"
    assert run.capability == "formal.run"
    assert run.tool_name == "symbiyosys"
    assert run.command is not None
    assert "saxoflow formal" in run.command
    assert "--solver z3" in run.command
    assert "--timeout 30" in run.command
    assert run.diagnostics == ()


def test_formal_property_and_proof_schemas_validate():
    prop = FormalPropertySpec.from_mapping(
        {
            "top_module": "counter_8bit",
            "property_text": "assert property (@(posedge clk) disable iff(!reset_n) count <= 8'hFF);",
            "intent": "overflow_safety",
            "source_path": "formal/source/counter_props.sv",
            "language": "SystemVerilog",
        }
    )
    assert prop.top_module == "counter_8bit"
    assert prop.language == "systemverilog"

    summary = FormalProofSummary.from_mapping(
        {
            "status": "pass",
            "engine": "smtbmc",
            "task": "bmc",
            "summary": "All properties passed",
            "counterexample_refs": [],
        }
    )
    assert summary.status == "pass"
    assert summary.counterexample_refs == ()

    options = FormalRunOptions.from_mapping(
        {
            "solver": "z3",
            "task": "prove",
            "timeout_seconds": 60,
            "autotune": True,
            "rtl_specs": ["source/rtl/systemverilog/counter.sv"],
            "sva_specs": ["formal/source/counter_props.sv"],
        }
    )
    assert options.timeout_seconds == 60
    assert options.rtl_specs == ("source/rtl/systemverilog/counter.sv",)

    proof = FormalProofResult.from_mapping(
        {
            "status": "fail",
            "engine": "smtbmc",
            "summary": "Counterexample generated",
            "report_paths": ["formal/reports/result.txt"],
            "trace_paths": ["formal/out/counterexample.vcd"],
            "counterexample_refs": ["counterexample.vcd:12"],
        }
    )
    assert proof.status == "fail"
    assert proof.trace_paths == ("formal/out/counterexample.vcd",)


def test_formal_schemas_reject_invalid_status_and_timeout():
    with pytest.raises(AgentSchemaError):
        FormalProofSummary.from_mapping({"status": "mystery"})

    with pytest.raises(ToolSchemaError):
        FormalProofResult.from_mapping({"status": "unsupported"})

    with pytest.raises(ToolSchemaError):
        FormalRunOptions.from_mapping({"timeout_seconds": 0})
