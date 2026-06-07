"""Tests for the generic SaxoFlow Yosys synthesis wrapper."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import saxoflow.makeflow as makeflow
import saxoflow.synthflow as synthflow


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


def _mock_yosys(monkeypatch, frontend="builtin"):
    monkeypatch.setattr(
        synthflow,
        "select_yosys",
        lambda requested, has_sv: ("/tools/yosys", frontend, None),
    )


def _mock_make(monkeypatch, returncode=0):
    calls = []

    def fake_run_make(target, extra_vars=None):
        calls.append((target, extra_vars or {}))
        return {"stdout": "", "stderr": "", "returncode": returncode}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)
    return calls


def test_collect_sources_handles_files_directories_globs_and_packages(tmp_path):
    root = _unit_root(tmp_path)
    package = _write(
        root / "custom/z_types.sv",
        "package sample_types; endpackage\n",
    )
    core = _write(root / "custom/a_core.sv", "module sample_core; endmodule\n")
    helper = _write(root / "custom/nested/helper.v", "module helper; endmodule\n")

    sources, unmatched, vhdl = synthflow.collect_sources(
        root,
        ["custom/a_core.sv", "custom", "custom/**/*.v"],
        explicit=True,
    )

    assert unmatched == []
    assert vhdl == []
    assert sources == [package, core, helper]


def test_default_discovery_includes_systemverilog_verilog_and_synthesis_src(
    tmp_path,
):
    root = _unit_root(tmp_path)
    sv = _write(root / "source/rtl/systemverilog/core.sv", "module core; endmodule\n")
    verilog = _write(root / "source/rtl/verilog/helper.v", "module helper; endmodule\n")
    wrapper = _write(root / "synthesis/src/wrapper.sv", "module wrapper; endmodule\n")

    sources, unmatched, vhdl = synthflow.collect_sources(
        root,
        synthflow.DEFAULT_RTL_SPECS,
        explicit=False,
    )

    assert unmatched == []
    assert vhdl == []
    assert set(sources) == {sv, verilog, wrapper}


def test_select_yosys_prefers_slang_capable_binary_for_systemverilog(
    monkeypatch,
):
    monkeypatch.setattr(
        synthflow,
        "_yosys_candidates",
        lambda: ["/usr/bin/yosys", "/managed/yosys"],
    )
    monkeypatch.setattr(
        synthflow,
        "slang_available",
        lambda path: path == "/managed/yosys",
    )

    binary, frontend, warning = synthflow.select_yosys("auto", True)

    assert binary == "/managed/yosys"
    assert frontend == "slang"
    assert warning is None


def test_select_yosys_auto_falls_back_to_builtin(monkeypatch):
    monkeypatch.setattr(
        synthflow,
        "_yosys_candidates",
        lambda: ["/usr/bin/yosys"],
    )
    monkeypatch.setattr(synthflow, "slang_available", lambda path: False)

    binary, frontend, warning = synthflow.select_yosys("auto", True)

    assert binary == "/usr/bin/yosys"
    assert frontend == "builtin"
    assert "limited built-in" in warning


def test_select_yosys_explicit_slang_requires_plugin(monkeypatch):
    monkeypatch.setattr(
        synthflow,
        "_yosys_candidates",
        lambda: ["/usr/bin/yosys"],
    )
    monkeypatch.setattr(synthflow, "slang_available", lambda path: False)

    with pytest.raises(Exception, match="Slang frontend was requested"):
        synthflow.select_yosys("slang", True)


def test_synth_generates_generic_script_with_options(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(
        root / "source/rtl/systemverilog/types.sv",
        "package sample_types; endpackage\n",
    )
    _write(
        root / "source/rtl/systemverilog/core.sv",
        "module sample_core #(parameter WIDTH=8); endmodule\n",
    )
    (root / "source/rtl/include").mkdir(parents=True)
    _mock_yosys(monkeypatch, frontend="slang")
    calls = _mock_make(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            [
                "--top",
                "sample_core",
                "--param",
                "WIDTH=16",
                "--define",
                "SYNTH_MODE=1",
                "--lut",
                "4",
                "--format",
                "blif",
                "--output-prefix",
                "mapped/sample_core",
            ],
        )

    assert result.exit_code == 0, result.output
    script = (root / "synthesis/reports/saxoflow_synth.ys").read_text()
    assert "plugin -i slang" in script
    assert "-DSYNTH_MODE=1" in script
    assert "--top sample_core" in script
    assert "-GWIDTH=16" in script
    assert "synth -top sample_core -flatten -lut 4" in script
    assert "write_blif \"synthesis/out/mapped/sample_core.blif\"" in script
    assert script.index("types.sv") < script.index("core.sv")
    assert calls[0][0] == "synth"
    assert calls[0][1]["YOSYS_BIN"] == "/tools/yosys"
    assert calls[0][1]["YOSYS_SCRIPT"] == "synthesis/reports/saxoflow_synth.ys"


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (
            ["--target", "ice40", "--top", "sample_core", "--device", "u"],
            "synth_ice40 -top sample_core -device u",
        ),
        (
            ["--target", "ecp5", "--top", "sample_core"],
            "synth_ecp5 -top sample_core",
        ),
        (
            ["--target", "xilinx", "--top", "sample_core", "--family", "xcu"],
            "synth_xilinx -top sample_core -family xcu -flatten",
        ),
    ],
)
def test_synth_generates_fpga_target_scripts(
    tmp_path,
    monkeypatch,
    arguments,
    expected,
):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module sample_core; endmodule\n")
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(makeflow.synth, arguments)

    assert result.exit_code == 0, result.output
    script = (root / "synthesis/reports/saxoflow_synth.ys").read_text()
    assert expected in script
    assert "write_json \"synthesis/out/synthesized.json\"" in script
    assert "write_verilog" not in script


def test_synth_generates_asic_mapping_script(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module sample_core; endmodule\n")
    _write(root / "constraints/cells.lib", "library(test) {}\n")
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            [
                "--target",
                "asic",
                "--top",
                "sample_core",
                "--liberty",
                "constraints/cells.lib",
                "--clock-period",
                "2.5",
            ],
        )

    assert result.exit_code == 0, result.output
    script = (root / "synthesis/reports/saxoflow_synth.ys").read_text()
    assert "read_liberty -lib \"constraints/cells.lib\"" in script
    assert "dfflibmap -liberty \"constraints/cells.lib\"" in script
    assert "abc -liberty \"constraints/cells.lib\" -D 2500" in script
    assert "stat -liberty \"constraints/cells.lib\"" in script


def test_custom_script_is_unchanged_and_passed_to_make(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    custom = _write(root / "custom/custom.ys", "read_verilog exact.v\n")
    _mock_yosys(monkeypatch)
    calls = _mock_make(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--script", "custom/custom.ys"],
        )

    assert result.exit_code == 0, result.output
    assert custom.read_text() == "read_verilog exact.v\n"
    assert calls[0][1]["YOSYS_SCRIPT"] == "custom/custom.ys"
    assert not (root / "synthesis/reports/saxoflow_synth.ys").exists()
    assert "Use --schematic-input FILE" in result.output


def test_custom_script_uses_explicit_schematic_input(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "custom/custom.ys", "write_json custom/result.json\n")
    netlist = _write(
        root / "custom/result.json",
        '{"modules":{"core":{"ports":{},"cells":{}}}}\n',
    )
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch)
    captured = {}

    def fake_render(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(synthflow, "render_schematic", fake_render)
    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            [
                "--script",
                "custom/custom.ys",
                "--schematic-input",
                "custom/result.json",
                "--no-show-log",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["input_path"] == netlist


def test_custom_script_rejects_generated_flow_options(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "custom/custom.ys", "")
    _mock_yosys(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--script", "custom/custom.ys", "--top", "sample_core"],
        )

    assert result.exit_code != 0
    assert "cannot be combined" in result.output


def test_preflight_receives_selected_sources(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    rtl = _write(root / "custom/core.v", "module sample_core; endmodule\n")
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch)
    captured = {}

    def fake_preflight(project_root, sources=None, include_dirs=None, top=None):
        captured["root"] = project_root
        captured["sources"] = list(sources or [])
        captured["top"] = top

    monkeypatch.setattr(synthflow, "_run_preflight", fake_preflight)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            [
                "--rtl",
                "custom/core.v",
                "--top",
                "sample_core",
                "--preflight-lint",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured == {
        "root": root,
        "sources": [rtl],
        "top": "sample_core",
    }


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--target", "asic"], "--liberty is required"),
        (["--target", "ecp5", "--lut", "4"], "--lut is only valid"),
        (["--target", "generic", "--clock-period", "2"], "only valid with --target asic"),
        (["--param", "WIDTH=8"], "--param requires an explicit --top"),
        (["--define", "1BAD"], "Invalid --define"),
        (["--output-prefix", "core.json"], "must not include a file extension"),
    ],
)
def test_synth_validates_options(tmp_path, monkeypatch, arguments, message):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module sample_core; endmodule\n")
    _mock_yosys(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(makeflow.synth, arguments)

    assert result.exit_code != 0
    assert message in result.output


def test_synth_rejects_vhdl_and_missing_sources(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/vhdl/core.vhd", "entity core is end entity;\n")
    _mock_yosys(monkeypatch)

    with _chdir(root):
        vhdl_result = CliRunner().invoke(makeflow.synth, [])
    assert vhdl_result.exit_code != 0
    assert "VHDL synthesis is not supported" in vhdl_result.output

    (root / "source/rtl/vhdl/core.vhd").unlink()
    with _chdir(root):
        missing_result = CliRunner().invoke(makeflow.synth, [])
    assert missing_result.exit_code != 0
    assert "No Verilog/SystemVerilog RTL files found" in missing_result.output


def test_synth_failure_prints_yosys_log(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module sample_core; endmodule\n")
    _write(root / "synthesis/reports/yosys.log", "ERROR: failed mapping\n")
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch, returncode=2)

    with _chdir(root):
        result = CliRunner().invoke(makeflow.synth, [])

    assert result.exit_code != 0
    assert "Yosys log:" in result.output
    assert "failed mapping" in result.output


def test_synth_success_prints_complete_yosys_log(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module core; endmodule\n")
    _mock_yosys(monkeypatch)

    def fake_run_make(target, extra_vars=None):
        _write(
            root / "synthesis/reports/yosys.log",
            "Yosys banner\nExecuting SYNTH pass\nEnd of script\n",
        )
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)
    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--no-schematic"],
        )

    assert result.exit_code == 0, result.output
    assert "Yosys log:" in result.output
    assert "Executing SYNTH pass" in result.output
    assert "End of script" in result.output


def test_successful_synthesis_writes_downstream_handoff_manifest(
    tmp_path, monkeypatch
):
    root = _unit_root(tmp_path)
    source = _write(
        root / "source/rtl/systemverilog/core.sv",
        "module sample_core; endmodule\n",
    )
    _mock_yosys(monkeypatch, frontend="slang")

    def fake_run_make(target, extra_vars=None):
        _write(root / "synthesis/out/.gitkeep")
        _write(root / "synthesis/out/stale.v", "module stale; endmodule\n")
        _write(root / "synthesis/out/synthesized.v", "module sample_core; endmodule\n")
        _write(root / "synthesis/out/synthesized.json", "{}\n")
        return {"stdout": "", "stderr": "", "returncode": 0}

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)
    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--top", "sample_core", "--no-schematic", "--no-show-log"],
        )

    assert result.exit_code == 0, result.output
    data = json.loads(
        (root / "synthesis/reports/saxoflow_synth_manifest.json").read_text()
    )
    assert data["status"] == "success"
    assert data["target"] == "generic"
    assert data["top"] == "sample_core"
    assert data["sources"] == [str(source.relative_to(root))]
    assert data["outputs"] == [
        "synthesis/out/synthesized.json",
        "synthesis/out/synthesized.v",
    ]
    assert ".gitkeep" not in result.output


def test_synth_no_show_log_suppresses_success_log(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module core; endmodule\n")
    _write(root / "synthesis/reports/yosys.log", "hidden log line\n")
    _mock_yosys(monkeypatch)
    _mock_make(monkeypatch)

    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--no-show-log", "--no-schematic"],
        )

    assert result.exit_code == 0, result.output
    assert "hidden log line" not in result.output


def test_synth_automatically_renders_json_schematic(tmp_path, monkeypatch):
    root = _unit_root(tmp_path)
    _write(root / "source/rtl/verilog/core.v", "module core; endmodule\n")
    _mock_yosys(monkeypatch)
    captured = {}

    def fake_run_make(target, extra_vars=None):
        _write(
            root / "synthesis/out/synthesized.json",
            '{"modules":{"core":{"ports":{},"cells":{}}}}\n',
        )
        return {"stdout": "", "stderr": "", "returncode": 0}

    def fake_render(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(makeflow, "run_make", fake_run_make)
    monkeypatch.setattr(synthflow, "render_schematic", fake_render)
    with _chdir(root):
        result = CliRunner().invoke(
            makeflow.synth,
            ["--format", "verilog", "--no-show-log"],
        )

    assert result.exit_code == 0, result.output
    script = (root / "synthesis/reports/saxoflow_synth.ys").read_text()
    assert "write_verilog" in script
    assert "write_json" in script
    assert captured["input_path"] == root / "synthesis/out/synthesized.json"
    assert captured["output_path"] == root / "synthesis/reports/schematic.svg"
    assert captured["missing_ok"] is True
    assert captured["open_viewer"] is True


def test_slang_paths_with_whitespace_fail_clearly(tmp_path):
    root = _unit_root(tmp_path)
    source = _write(root / "source/rtl/systemverilog/core file.sv", "")

    with pytest.raises(Exception, match="cannot read paths containing whitespace"):
        synthflow.generate_script(
            root,
            [source],
            [],
            [],
            None,
            [],
            "slang",
            "generic",
            "hx",
            "xc7",
            None,
            None,
            None,
            True,
            ["json"],
            root / "synthesis/out/synthesized",
        )


def test_synthflow_has_no_design_specific_production_name():
    source = Path(synthflow.__file__).read_text(encoding="utf-8")
    assert "traffic_controller" not in source
