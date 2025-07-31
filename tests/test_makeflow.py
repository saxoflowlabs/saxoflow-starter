import os
import shutil
import sys
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest import mock

import saxoflow.makeflow as makeflow

# Utility for quick file writing
def touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("// testbench")

# =========== TESTS ==============

def test_require_makefile_raises(tmp_path):
    runner = CliRunner()
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(SystemExit):
            makeflow.require_makefile()
    finally:
        os.chdir(cwd)

def test_run_make_invokes_subprocess(monkeypatch):
    # (Already present in your test.)
    def fake_run(cmd, capture_output, text):
        class Result:
            stdout = "ok"
            stderr = ""
            returncode = 0
        nonlocal received_cmd
        received_cmd = cmd
        return Result()
    received_cmd = None
    monkeypatch.setattr(makeflow.subprocess, "run", fake_run)
    result = makeflow.run_make("sim-icarus", extra_vars={"TOP_TB": "tb"})
    assert received_cmd[:2] == ["make", "sim-icarus"]
    assert result == {"stdout": "ok", "stderr": "", "returncode": 0}

# --- CLI: sim ---

def test_sim_no_testbenches(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim, [])
    assert "No testbenches" in result.output

def test_sim_one_testbench(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    tbfile = tmp_path / "source/tb/verilog/tb1.v"
    touch(tbfile)
    monkeypatch.setattr(makeflow, "run_make", lambda t, extra_vars=None: {"stdout": "s", "stderr": "", "returncode": 0})
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim, [])
    assert "Running Icarus Verilog simulation" in result.output

def test_sim_multiple_testbenches_user_select(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    tb1 = tmp_path / "source/tb/verilog/tb1.v"
    tb2 = tmp_path / "source/tb/verilog/tb2.v"
    touch(tb1)
    touch(tb2)
    os.chdir(tmp_path)
    monkeypatch.setattr(makeflow, "run_make", lambda t, extra_vars=None: {"stdout": "", "stderr": "", "returncode": 0})
    # Simulate user entering "2" at the prompt
    monkeypatch.setattr(makeflow.click, "prompt", lambda msg, type=int, default=1: 2)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim, [])
    assert "Multiple testbenches found" in result.output
    assert "tb2.v" in result.output or "tb1.v" in result.output

def test_sim_tb_argument_not_found(tmp_path):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim, ["--tb", "nonexistent"])
    assert "not found in any source/tb/" in result.output

def test_sim_tb_argument_found(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    tbfile = tmp_path / "source/tb/verilog/mytb.v"
    touch(tbfile)
    os.chdir(tmp_path)
    monkeypatch.setattr(makeflow, "run_make", lambda t, extra_vars=None: {"stdout": "", "stderr": "", "returncode": 0})
    runner = CliRunner()
    result = runner.invoke(makeflow.sim, ["--tb", "mytb"])
    assert "Running Icarus Verilog simulation" in result.output

# --- CLI: sim_verilator ---

def test_sim_verilator_missing_tool(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    os.chdir(tmp_path)
    monkeypatch.setattr(makeflow.shutil, "which", lambda name: None)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim_verilator, [])
    assert "Verilator not found in PATH" in result.output

def test_sim_verilator_no_testbenches(tmp_path, monkeypatch):
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    os.chdir(tmp_path)
    monkeypatch.setattr(makeflow.shutil, "which", lambda name: "/usr/bin/verilator")
    runner = CliRunner()
    result = runner.invoke(makeflow.sim_verilator, [])
    assert "No testbenches" in result.output

# --- CLI: sim_verilator_run ---

def test_sim_verilator_run_no_binaries(tmp_path):
    bin_dir = tmp_path / "simulation/verilator/obj_dir"
    bin_dir.mkdir(parents=True)
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim_verilator_run, [])
    assert "No Verilator simulation executable found" in result.output

def test_sim_verilator_run_missing_exe(tmp_path):
    bin_dir = tmp_path / "simulation/verilator/obj_dir"
    bin_dir.mkdir(parents=True)
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.sim_verilator_run, ["--tb", "nope"])
    assert "not found. Did you build it with sim-verilator" in result.output

# --- CLI: wave ---

def test_wave_no_vcd(tmp_path):
    vcd_dir = tmp_path / "simulation/icarus"
    vcd_dir.mkdir(parents=True)
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.wave, [])
    assert "No VCD files found" in result.output

def test_wave_select_from_multiple(tmp_path, monkeypatch):
    vcd_dir = tmp_path / "simulation/icarus"
    vcd_dir.mkdir(parents=True)
    (vcd_dir / "foo.vcd").write_text("")
    (vcd_dir / "bar.vcd").write_text("")
    os.chdir(tmp_path)
    monkeypatch.setattr(makeflow.click, "prompt", lambda *a, **k: 2)
    monkeypatch.setattr(makeflow.subprocess, "run", lambda cmd: None)
    runner = CliRunner()
    result = runner.invoke(makeflow.wave, [])
    assert "Multiple VCD files found" in result.output

# --- CLI: synth, formal, clean ---

def test_synth_missing_script(tmp_path):
    tmp_path.mkdir(exist_ok=True)
    os.chdir(tmp_path)
    makefile = tmp_path / "Makefile"
    makefile.write_text("all:")
    runner = CliRunner()
    result = runner.invoke(makeflow.synth, [])
    assert "synthesis/scripts/synth.ys not found" in result.output

def test_formal_no_sby(tmp_path):
    sdir = tmp_path / "formal/scripts"
    sdir.mkdir(parents=True)
    os.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(makeflow.formal, [])
    assert "No .sby spec found" in result.output

def test_clean_cancel(monkeypatch):
    monkeypatch.setattr(makeflow.click, "confirm", lambda *a, **k: False)
    runner = CliRunner()
    result = runner.invoke(makeflow.clean, [])
    assert "Clean canceled" in result.output

def test_clean_runs(monkeypatch):
    monkeypatch.setattr(makeflow.click, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(makeflow, "run_make", lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0})
    runner = CliRunner()
    result = runner.invoke(makeflow.clean, [])
    assert "Clean canceled" not in result.output

def test_check_tools(monkeypatch):
    # Patch tool descriptions and shutil.which to simulate both present and missing tools
    monkeypatch.setattr(makeflow, "shutil", shutil)
    from types import SimpleNamespace
    monkeypatch.setattr(sys.modules["saxoflow.tools"], "TOOL_DESCRIPTIONS", {"toolA": "A tool"})
    monkeypatch.setattr(shutil, "which", lambda x: "/usr/bin/" + x if x == "toolA" else None)
    runner = CliRunner()
    result = runner.invoke(makeflow.check_tools, [])
    assert "toolA" in result.output and "FOUND" in result.output

# ---- CLI: simulate, simulate_verilator (integration/dispatch) ---

def test_simulate_calls_sim_and_wave(monkeypatch):
    called = []
    monkeypatch.setattr(makeflow, "sim", mock.Mock())
    monkeypatch.setattr(makeflow, "wave", mock.Mock())
    runner = CliRunner()
    result = runner.invoke(makeflow.simulate, [])
    assert makeflow.sim.called
    assert makeflow.wave.called

def test_simulate_verilator_calls(monkeypatch):
    monkeypatch.setattr(makeflow, "sim_verilator", mock.Mock())
    monkeypatch.setattr(makeflow, "sim_verilator_run", mock.Mock())
    monkeypatch.setattr(makeflow, "wave_verilator", mock.Mock())
    runner = CliRunner()
    result = runner.invoke(makeflow.simulate_verilator, [])
    assert makeflow.sim_verilator.called
    assert makeflow.sim_verilator_run.called
    assert makeflow.wave_verilator.called

