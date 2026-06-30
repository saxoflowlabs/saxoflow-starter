"""Tests for the Phase 2 simulation tool adapter."""

from __future__ import annotations

from pathlib import Path

import saxoflow.makeflow as makeflow
from saxoflow.schemas.tools import ToolRequest
from saxoflow.tools.adapters.simulation import SimulationToolAdapter


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _unit_root(tmp_path: Path) -> Path:
    _write(tmp_path / "Makefile", "all:\n\t@true\n")
    _write(tmp_path / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    _write(tmp_path / "source/tb/verilog/sample_core_tb.v", "module sample_core_tb; endmodule\n")
    return tmp_path


def test_simulation_adapter_returns_toolrun_success(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda target, extra_vars=None: {
            "stdout": "Simulation completed",
            "stderr": "",
            "returncode": 0,
        },
    )

    adapter = SimulationToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "sim.run",
            "workspace": str(root),
            "options": {
                "simulation": {
                    "tb": "sample_core_tb",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert run.capability == "sim.run"
    assert run.tool_name == "iverilog"
    assert run.exit_code == 0
    assert run.diagnostics == ()
    assert run.command is not None
    assert "sim-icarus" in run.command
    assert "TOP_TB=sample_core_tb" in run.command


def test_simulation_adapter_returns_toolrun_failure(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda target, extra_vars=None: {
            "stdout": "",
            "stderr": "compile error: syntax error",
            "returncode": 2,
        },
    )

    adapter = SimulationToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "sim.run",
            "workspace": str(root),
            "options": {
                "simulation": {
                    "tb": "sample_core_tb",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.capability == "sim.run"
    assert run.exit_code == 2
    assert len(run.diagnostics) >= 1
    assert "compile error" in run.diagnostics[0].message.lower()


def test_simulation_adapter_dry_run_returns_planned_command_without_execution(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    def fail_run_make(target, extra_vars=None):
        raise AssertionError("dry-run should not execute simulation")

    monkeypatch.setattr(makeflow, "run_make", fail_run_make)

    adapter = SimulationToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "sim.run",
            "workspace": str(root),
            "dry_run": True,
            "options": {
                "simulation": {
                    "tb": "sample_core_tb",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "skipped"
    assert run.capability == "sim.run"
    assert run.tool_name == "iverilog"
    assert run.command is not None
    assert "make sim-icarus" in run.command
    assert run.diagnostics == ()


def test_simulation_adapter_uses_bender_source_manifest_for_rtl_specs(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "rtl/custom_core.sv", "module custom_core; endmodule\n")
    _write(
        root / "Bender.yml",
        "\n".join(
            [
                "package:",
                "  name: demo",
                "sources:",
                "  - files:",
                "      - rtl/custom_core.sv",
                "    target: [sim]",
            ]
        )
        + "\n",
    )

    captured = {}

    def fake_build_icarus_vars(tb_file, rtl_specs=(), tb_specs=(), include_specs=()):
        captured["rtl_specs"] = tuple(rtl_specs)
        return {"TOP_TB": "sample_core_tb"}

    monkeypatch.setattr(makeflow, "_build_icarus_vars", fake_build_icarus_vars)
    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda target, extra_vars=None: {
            "stdout": "Simulation completed",
            "stderr": "",
            "returncode": 0,
        },
    )

    adapter = SimulationToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "sim.run",
            "workspace": str(root),
            "options": {
                "simulation": {
                    "tb": "sample_core_tb",
                },
                "source_manifest": {
                    "provider": "bender",
                    "target": "sim",
                },
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert captured["rtl_specs"] == ("rtl/custom_core.sv",)
