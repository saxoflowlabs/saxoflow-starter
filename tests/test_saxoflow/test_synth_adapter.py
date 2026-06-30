"""Tests for the Phase 2 synthesis tool adapter."""

from __future__ import annotations

from pathlib import Path

import saxoflow.makeflow as makeflow
import saxoflow.synthflow as synthflow
from saxoflow.schemas.tools import ToolRequest
from saxoflow.tools.adapters.synthesis import SynthesisToolAdapter


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _unit_root(tmp_path: Path) -> Path:
    _write(tmp_path / "Makefile", "all:\n\t@true\n")
    _write(tmp_path / "source/rtl/verilog/sample_core.v", "module sample_core; endmodule\n")
    return tmp_path


def _mock_yosys(monkeypatch):
    monkeypatch.setattr(
        synthflow,
        "select_yosys",
        lambda frontend, has_sv: ("/tools/yosys", "builtin", None),
    )


def test_synthesis_adapter_returns_success_and_manifest_paths(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _mock_yosys(monkeypatch)

    def fake_run_make(target, extra_vars=None):
        _write(root / "synthesis/reports/yosys.log", "Yosys log line\n")
        _write(root / "synthesis/out/synthesized.v", "module sample_core; endmodule\n")
        _write(root / "synthesis/out/synthesized.json", "{}\n")
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)

    adapter = SynthesisToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "synth.run",
            "workspace": str(root),
            "options": {
                "synthesis": {
                    "top": "sample_core",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert run.capability == "synth.run"
    assert run.tool_name == "yosys"
    assert run.exit_code == 0
    assert run.diagnostics == ()
    assert "saxoflow_synth_manifest.json" in (run.stdout or "")
    assert "synthesis/reports" in (run.stdout or "")
    assert "synthesis/out/synthesized.v" in (run.stdout or "")


def test_synthesis_adapter_returns_failure_on_make_error(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _mock_yosys(monkeypatch)

    def fake_run_make(target, extra_vars=None):
        _write(root / "synthesis/reports/yosys.log", "Yosys log line\n")
        return {"stdout": "", "stderr": "ERROR: synthesis failed", "returncode": 2}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)

    adapter = SynthesisToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "synth.run",
            "workspace": str(root),
            "options": {
                "synthesis": {
                    "top": "sample_core",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "failed"
    assert run.capability == "synth.run"
    assert run.exit_code == 1
    assert len(run.diagnostics) == 1
    assert "synthesis failed" in run.diagnostics[0].message.lower()


def test_synthesis_adapter_dry_run_returns_planned_command_without_execution(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)

    def fail_run_synthesis(**kwargs):
        raise AssertionError("dry-run should not execute synthesis")

    monkeypatch.setattr(synthflow, "run_synthesis", fail_run_synthesis)

    adapter = SynthesisToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "synth.run",
            "workspace": str(root),
            "dry_run": True,
            "options": {
                "synthesis": {
                    "target": "generic",
                    "frontend": "auto",
                }
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "skipped"
    assert run.capability == "synth.run"
    assert run.tool_name == "yosys"
    assert run.command == "saxoflow synth --target generic --frontend auto"
    assert run.diagnostics == ()


def test_synthesis_adapter_uses_bender_source_manifest_for_rtl_specs(tmp_path, monkeypatch):
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
                "    target: [synth]",
            ]
        )
        + "\n",
    )

    captured = {}

    def fake_run_synthesis(**kwargs):
        captured["rtl_specs"] = tuple(kwargs.get("rtl_specs") or ())

    monkeypatch.setattr(synthflow, "run_synthesis", fake_run_synthesis)

    adapter = SynthesisToolAdapter()
    request = ToolRequest.from_mapping(
        {
            "capability": "synth.run",
            "workspace": str(root),
            "options": {
                "synthesis": {
                    "top": "custom_core",
                },
                "source_manifest": {
                    "provider": "bender",
                    "target": "synth",
                },
            },
        }
    )

    run = adapter.run(request)

    assert run.status == "success"
    assert captured["rtl_specs"] == ("rtl/custom_core.sv",)
