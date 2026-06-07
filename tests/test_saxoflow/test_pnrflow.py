"""Tests for the generic ORFS-backed P&R wrapper."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from saxoflow import pdk_registry
from saxoflow.pnrflow import (
    PnrError,
    _run_platform_synthesis,
    _verify_mapped_cells,
    detect_top,
    orfs_command,
    pnr,
    resolve_flow,
)


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _environment(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    data = tmp_path / "data"
    orfs = tmp_path / "orfs"
    platform = orfs / "flow/platforms/sky130hd"
    _write(orfs / "flow/Makefile", "all:\n\t@true\n")
    _write(
        platform / "lib/sky130_fd_sc_hd__tt_025C_1v80.lib",
        "library(test) {}\n",
    )
    _write(platform / "lef/cells.lef", "VERSION 5.8 ;\n")
    _write(platform / "lef/sky130_fd_sc_hd.tlef", "VERSION 5.8 ;\n")
    _write(platform / "lef/sky130_fd_sc_hd_merged.lef", "VERSION 5.8 ;\n")
    _write(platform / "gds/cells.gds", "GDS\n")
    _write(platform / "rcx_patterns.rules", "rules\n")
    _write(platform / "setRC.tcl", "set_wire_rc -signal -layer met1\n")
    _write(platform / "sky130hd.lyt", "<technology/>\n")
    _write(platform / "drc/sky130hd.lydrc", "drc\n")
    _write(platform / "lvs/sky130hd.lylvs", "lvs\n")
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(data))
    monkeypatch.setenv("SAXOFLOW_ORFS_HOME", str(orfs))
    manifest = pdk_registry.get_manifest("sky130hd")
    pdk_registry.activate_orfs_platform(manifest)

    unit = tmp_path / "unit"
    _write(unit / "Makefile", "all:\n\t@true\n")
    _write(
        unit / "synthesis/out/mapped.v",
        "module leaf; endmodule\nmodule sample_core; leaf u_leaf(); endmodule\n",
    )
    _write(unit / "constraints/design.sdc", "create_clock -period 10 [get_ports clk]\n")
    return unit, orfs


def _chdir(path: Path):
    class Context:
        def __enter__(self):
            self.previous = Path.cwd()
            os.chdir(path)

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self.previous)

    return Context()


def test_detect_top_uses_unique_module_graph_root(tmp_path):
    rtl = _write(
        tmp_path / "design.v",
        "module child; endmodule\nmodule root; child u_child(); endmodule\n",
    )
    assert detect_top([rtl]) == "root"


def test_detect_top_rejects_ambiguous_roots(tmp_path):
    rtl = _write(tmp_path / "design.v", "module first; endmodule\nmodule second; endmodule\n")
    with pytest.raises(PnrError, match="Multiple possible top modules"):
        detect_top([rtl])


def test_pnr_init_requires_installed_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("SAXOFLOW_DATA_HOME", str(tmp_path / "empty"))
    unit = tmp_path / "unit"
    _write(unit / "Makefile", "all:\n\t@true\n")
    with _chdir(unit):
        result = CliRunner().invoke(
            pnr,
            ["init", "--platform", "sky130hd", "--top", "sample_core"],
        )
    assert result.exit_code != 0
    assert "not activated" in result.output


def test_init_and_dry_run_generate_locked_generic_orfs_config(tmp_path, monkeypatch):
    unit, orfs = _environment(tmp_path, monkeypatch)
    runner = CliRunner()
    with _chdir(unit):
        initialized = runner.invoke(
            pnr,
            [
                "init",
                "--platform",
                "sky130hd",
                "--top",
                "sample_core",
                "--netlist",
                "synthesis/out/mapped.v",
                "--sdc",
                "constraints/design.sdc",
            ],
        )
        initial_lock = (unit / "pnr/platform.lock.yaml").read_text()
        dry_run = runner.invoke(
            pnr,
            [
                "run",
                "--dry-run",
                "--variant",
                "density-60",
                "--place-density",
                "0.60",
                "--set",
                "GPL_ROUTABILITY_DRIVEN=1",
            ],
        )

    assert initialized.exit_code == 0, initialized.output
    assert "platform: sky130hd" in initial_lock
    assert "library: sky130_fd_sc_hd" in initial_lock
    assert dry_run.exit_code == 0, dry_run.output
    generated = (unit / "pnr/generated/density-60.mk").read_text()
    assert "export DESIGN_NAME := sample_core" in generated
    assert "export PLATFORM := sky130hd" in generated
    assert "export SYNTH_NETLIST_FILES :=" in generated
    assert "export GPL_ROUTABILITY_DRIVEN := 1" in generated
    assert "export MIN_ROUTING_LAYER := met1" in generated
    assert "export MAX_ROUTING_LAYER := met5" in generated
    lock = (unit / "pnr/platform.lock.yaml").read_text()
    assert "platform: sky130hd" in lock
    assert str(orfs) in dry_run.output


def test_stage_cli_reports_resolution_error_without_traceback(tmp_path, monkeypatch):
    unit, orfs = _environment(tmp_path, monkeypatch)
    runner = CliRunner()
    with _chdir(unit):
        initialized = runner.invoke(
            pnr,
            [
                "init",
                "--platform",
                "sky130hd",
                "--top",
                "sample_core",
                "--netlist",
                "synthesis/out/mapped.v",
                "--sdc",
                "constraints/design.sdc",
            ],
        )
        (orfs / "flow/Makefile").unlink()
        result = runner.invoke(pnr, ["run", "--dry-run"])

    assert initialized.exit_code == 0, initialized.output
    assert result.exit_code != 0
    assert "ORFS flow Makefile was not found" in result.output
    assert "Traceback" not in result.output


def test_resolve_flow_rejects_unsafe_override(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )
    with pytest.raises(PnrError, match="Unsafe"):
        resolve_flow(unit, {"overrides": ("DESIGN_NAME=other",)})


def test_resolve_flow_requires_manifest_environment(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )
    original = pdk_registry.get_manifest("sky130hd")
    data = dict(original.data)
    data["required_environment"] = ["CUSTOM_PDK_ROOT"]
    manifest = pdk_registry.PlatformManifest(data, original.source_path)
    monkeypatch.delenv("CUSTOM_PDK_ROOT", raising=False)
    monkeypatch.setattr("saxoflow.pnrflow.get_manifest", lambda _identifier: manifest)

    with pytest.raises(PnrError, match="CUSTOM_PDK_ROOT"):
        resolve_flow(unit, {})


def test_explicit_floorplan_omits_auto_floorplan_variables(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )

    flow = resolve_flow(
        unit,
        {
            "die_area": "0 0 50 50",
            "core_area": "5 5 45 45",
        },
    )
    generated = flow.config_mk.read_text()

    assert "export DIE_AREA := 0 0 50 50" in generated
    assert "export CORE_AREA := 5 5 45 45" in generated
    assert "CORE_UTILIZATION" not in generated
    assert "CORE_ASPECT_RATIO" not in generated
    assert "CORE_MARGIN" not in generated


def test_orfs_command_uses_managed_flow_and_variant(tmp_path, monkeypatch):
    unit, orfs = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )
    monkeypatch.setattr(
        "saxoflow.pnrflow._openroad_binary",
        lambda: "/tools/openroad",
    )
    monkeypatch.setattr(
        "saxoflow.pnrflow._yosys_binary",
        lambda: "/tools/yosys",
    )
    flow = resolve_flow(unit, {"variant": "experiment-a"})
    command = orfs_command(flow, "floorplan")

    assert command[:3] == ["make", "-C", str(orfs / "flow")]
    assert "FLOW_VARIANT=experiment-a" in command
    assert "OPENROAD_EXE=/tools/openroad" in command
    assert "YOSYS_EXE=/tools/yosys" in command
    assert command[-1] == "floorplan"


def test_stage_failure_records_manifest_and_log_excerpt(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )

    def fake_run(command, *, cwd, log_path, show_output=True):
        _write(log_path, "ERROR: routing failed\n")
        return 2

    monkeypatch.setattr("saxoflow.pnrflow.run_streaming", fake_run)
    with _chdir(unit):
        result = CliRunner().invoke(pnr, ["route"])

    assert result.exit_code != 0
    manifest = json.loads(
        (unit / "pnr/runs/default/saxoflow-run.json").read_text()
    )
    assert manifest["status"] == "failed"
    assert manifest["stage"] == "route"
    assert "routing failed" in result.output


def test_small_core_pdn_failure_prints_actionable_guidance(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )

    def fake_run(command, *, cwd, log_path, show_output=True):
        _write(
            log_path,
            "[ERROR PDN-0185] Insufficient width to add straps on layer met5.\n",
        )
        return 2

    monkeypatch.setattr("saxoflow.pnrflow.run_streaming", fake_run)
    with _chdir(unit):
        result = CliRunner().invoke(pnr, ["floorplan"])

    assert result.exit_code != 0
    assert "core is too small" in result.output
    assert "--die-area" in result.output
    assert "--core-area" in result.output


def test_successful_stage_writes_artifact_indexes(tmp_path, monkeypatch):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )

    def fake_run(command, *, cwd, log_path, show_output=True):
        _write(log_path, "completed\n")
        _write(unit / "pnr/runs/default/reports/metrics.json", "{}\n")
        _write(unit / "pnr/runs/default/results/final.gds", "GDS\n")
        return 0

    monkeypatch.setattr("saxoflow.pnrflow.run_streaming", fake_run)
    with _chdir(unit):
        result = CliRunner().invoke(pnr, ["finish"])

    assert result.exit_code == 0, result.output
    report_index = json.loads(
        (unit / "pnr/reports/default/artifacts.json").read_text()
    )
    result_index = json.loads(
        (unit / "pnr/results/default/artifacts.json").read_text()
    )
    assert report_index["artifacts"] == [
        "pnr/runs/default/reports/metrics.json"
    ]
    assert result_index["artifacts"] == ["pnr/runs/default/results/final.gds"]


def test_explicit_netlist_rejects_conflicting_synthesis_provenance(
    tmp_path, monkeypatch
):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "netlists: [synthesis/out/mapped.v]\nsdc: constraints/design.sdc\n",
    )
    _write(
        unit / "synthesis/reports/saxoflow_synth_manifest.json",
        json.dumps(
            {
                "outputs": ["synthesis/out/mapped.v"],
                "platform": "gf180mcu",
                "library": "other",
                "corner": "typical",
            }
        ),
    )

    with pytest.raises(PnrError, match="different platform"):
        resolve_flow(unit, {})
    flow = resolve_flow(unit, {"unsafe_netlist": True})
    assert flow.netlists == [(unit / "synthesis/out/mapped.v").resolve()]


def test_automatic_synthesis_handoff_uses_only_verilog_netlist(
    tmp_path, monkeypatch
):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\ntop: sample_core\n"
        "sdc: constraints/design.sdc\n",
    )
    verilog = _write(
        unit / "synthesis/out/synthesized.v",
        "module sample_core; endmodule\n",
    )
    _write(unit / "synthesis/out/synthesized.json", "{}\n")
    _write(
        unit / "synthesis/reports/saxoflow_synth_manifest.json",
        json.dumps(
            {
                "status": "success",
                "target": "asic",
                "top": "sample_core",
                "platform": "sky130hd",
                "library": "sky130_fd_sc_hd",
                "corner": "tt",
                "outputs": [
                    "synthesis/out/synthesized.json",
                    "synthesis/out/synthesized.v",
                ],
            }
        ),
    )

    flow = resolve_flow(unit, {})

    assert flow.netlists == [verilog.resolve()]
    assert "synthesized.json" not in flow.config_mk.read_text()


def test_mapped_cell_verification_accepts_selected_liberty(tmp_path):
    liberty = _write(
        tmp_path / "cells.lib",
        "library(test) { cell (BUF_X1) { } }\n",
    )
    netlist = _write(
        tmp_path / "mapped.v",
        "module sample_core(input a, output y); BUF_X1 u0(.A(a), .Y(y)); endmodule\n",
    )
    _verify_mapped_cells(netlist, liberty)

    netlist.write_text(
        "module sample_core(input a, output y); OTHER_X1 u0(.A(a), .Y(y)); endmodule\n",
        encoding="utf-8",
    )
    with pytest.raises(PnrError, match="outside the selected Liberty"):
        _verify_mapped_cells(netlist, liberty)


def test_external_netlist_only_platform_rejects_synthesis(tmp_path):
    manifest = pdk_registry.get_manifest("asap7")
    library = manifest.library()
    corner = manifest.corner(library)
    with pytest.raises(PnrError, match="unavailable for `asap7`"):
        _run_platform_synthesis(
            tmp_path,
            manifest,
            tmp_path,
            library,
            corner,
            "sample_core",
            (),
            (),
            (),
            (),
            None,
        )


def test_report_collects_metrics_by_variant(tmp_path):
    unit = tmp_path / "unit"
    _write(
        unit / "pnr/runs/base/reports/metrics.json",
        json.dumps(
            {
                "timing": {"wns": -0.1},
                "design": {
                    "area": 1200,
                    "instance_count": 45,
                    "buffer_count": 8,
                },
                "route": {"congestion": 0.12},
            }
        ),
    )
    _write(
        unit / "pnr/runs/base/saxoflow-run.json",
        json.dumps(
            {
                "artifact_indexes": {
                    "results": "pnr/results/base/artifacts.json",
                }
            }
        ),
    )
    with _chdir(unit):
        result = CliRunner().invoke(pnr, ["report", "--variant", "base"])
    assert result.exit_code == 0
    assert "timing.wns: -0.1" in result.output
    assert "design.area: 1200" in result.output
    assert "design.instance_count: 45" in result.output
    assert "design.buffer_count: 8" in result.output
    assert "route.congestion: 0.12" in result.output
    assert "results artifacts: pnr/results/base/artifacts.json" in result.output


def test_gui_loads_timing_context_and_canonical_stage_database(
    tmp_path, monkeypatch
):
    unit, _ = _environment(tmp_path, monkeypatch)
    _write(
        unit / "pnr/config.yaml",
        "schema_version: 1\nplatform: sky130hd\n"
        "library: sky130_fd_sc_hd\ncorner: tt\n",
    )
    database = _write(
        unit
        / "pnr/runs/default/results/sky130hd/sample_core/default/6_final.odb",
        "ODB\n",
    )
    sdc = _write(database.with_suffix(".sdc"), "create_clock -period 10 clk\n")
    launched = {}

    class Process:
        pass

    def fake_popen(command, *, cwd, env):
        launched["command"] = command
        launched["cwd"] = cwd
        launched["env"] = env
        return Process()

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.delenv("QT_QPA_PLATFORM", raising=False)
    monkeypatch.setattr(
        "saxoflow.pnrflow._openroad_binary",
        lambda: "/tools/openroad",
    )
    monkeypatch.setattr("saxoflow.pnrflow.subprocess.Popen", fake_popen)

    with _chdir(unit):
        result = CliRunner().invoke(pnr, ["gui", "--stage", "finish"])

    assert result.exit_code == 0, result.output
    script = unit / "pnr/generated/gui-default.tcl"
    contents = script.read_text()
    assert "read_liberty {" in contents
    assert f"read_db {{{database}}}" in contents
    assert f"read_sdc {{{sdc}}}" in contents
    assert "source {" in contents
    assert launched["command"] == ["/tools/openroad", "-gui", str(script)]
    assert launched["env"]["QT_QPA_PLATFORM"] == "xcb"


def test_gui_preserves_explicit_qt_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    monkeypatch.setenv("QT_QPA_PLATFORM", "wayland")

    from saxoflow.pnrflow import _gui_environment

    assert _gui_environment()["QT_QPA_PLATFORM"] == "wayland"
