"""
Integrated tests for saxoflow.makeflow.

Goals
-----
- Preserve current CLI behavior (happy paths + errors).
- Keep tests hermetic (tmp cwd, no real subprocess/network).
- Exercise both line and branch coverage, including prompts and output listing.

Conventions
-----------
- Use _chdir() to isolate cwd changes.
- Use _touch_text() to create files with parents.
- Patch using the import path used inside the SUT.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import List
from unittest import mock

import click
import pytest
from click.testing import CliRunner

import saxoflow.makeflow as makeflow


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _chdir(path: Path):
    """Context manager to temporarily change working directory."""
    class _Ctx:
        def __enter__(self):
            self._old = Path.cwd()
            os.chdir(path)
            return path

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self._old)
    return _Ctx()


def _touch_text(path: Path, content: str = "") -> Path:
    """Create file with parents and write text content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


# Back-compat helper name used by a few original tests
def touch(p: Path):
    """Alias to match original tests' helper name."""
    _touch_text(p, "// testbench")


# ---------------------------------------------------------------------------
# require_makefile
# ---------------------------------------------------------------------------

def test_require_makefile_raises(tmp_path):
    """require_makefile should abort (click.Abort) when Makefile is missing."""
    with _chdir(tmp_path):
        with pytest.raises(click.Abort):
            makeflow.require_makefile()


def test_require_makefile_ok(tmp_path):
    """require_makefile should pass silently when Makefile exists."""
    _touch_text(tmp_path / "Makefile", "all:\n\t@true\n")
    with _chdir(tmp_path):
        makeflow.require_makefile()  # no exception


# ---------------------------------------------------------------------------
# run_make
# ---------------------------------------------------------------------------

def test_run_make_invokes_subprocess(monkeypatch):
    """run_make should call subprocess.run and return stdout/stderr/rc."""
    received_cmd = {"cmd": None}

    def fake_run(cmd, capture_output, text):
        class Result:
            stdout = "ok"
            stderr = ""
            returncode = 0

        received_cmd["cmd"] = cmd
        return Result()

    monkeypatch.setattr(makeflow.subprocess, "run", fake_run)
    result = makeflow.run_make("sim-icarus", extra_vars={"TOP_TB": "tb"})
    assert received_cmd["cmd"][:2] == ["make", "sim-icarus"]
    assert result == {"stdout": "ok", "stderr": "", "returncode": 0}


def test_run_make_extra_vars_in_cmd(monkeypatch):
    """run_make should include VAR=VALUE args when extra_vars provided."""
    captured: List[str] = []

    def fake_run(cmd, capture_output, text):
        captured.extend(cmd)

        class R:
            stdout, stderr, returncode = "ok", "", 0

        return R()

    monkeypatch.setattr(makeflow.subprocess, "run", fake_run)
    res = makeflow.run_make("target-x", extra_vars={"A": "1", "B": "z"})
    assert captured[:2] == ["make", "target-x"]
    assert "A=1" in captured and "B=z" in captured
    assert res == {"stdout": "ok", "stderr": "", "returncode": 0}


# ---------------------------------------------------------------------------
# check_x_display (unused helper retained)
# ---------------------------------------------------------------------------

def test_check_x_display_false_true(monkeypatch):
    """check_x_display returns False when DISPLAY unset, True when set."""
    monkeypatch.delenv("DISPLAY", raising=False)
    assert makeflow.check_x_display() is False
    monkeypatch.setenv("DISPLAY", ":0")
    assert makeflow.check_x_display() is True


# ---------------------------------------------------------------------------
# CLI: sim
# ---------------------------------------------------------------------------

def test_sim_no_testbenches(tmp_path):
    """sim should warn when no TBs exist."""
    _touch_text(tmp_path / "Makefile", "all:")
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, [])
    assert "No testbenches" in result.output


def test_sim_one_testbench(tmp_path, monkeypatch):
    """sim should autodetect the single TB and run make."""
    _touch_text(tmp_path / "Makefile", "all:")
    touch(tmp_path / "source/tb/verilog/tb1.v")
    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda t, extra_vars=None: {"stdout": "s", "stderr": "", "returncode": 0},
    )
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, [])
    assert "Running Icarus Verilog simulation" in result.output


def test_sim_multiple_testbenches_user_select(tmp_path, monkeypatch):
    """sim should prompt when multiple TBs exist and honor the choice."""
    _touch_text(tmp_path / "Makefile", "all:")
    touch(tmp_path / "source/tb/verilog/tb1.v")
    touch(tmp_path / "source/tb/verilog/tb2.v")
    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda t, extra_vars=None: {"stdout": "", "stderr": "", "returncode": 0},
    )
    monkeypatch.setattr(makeflow.click, "prompt", lambda msg, type=int, default=1: 2)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, [])
    assert "Multiple testbenches found" in result.output
    assert "tb2.v" in result.output or "tb1.v" in result.output


def test_sim_tb_argument_not_found(tmp_path):
    """sim --tb should print not-found message when missing."""
    _touch_text(tmp_path / "Makefile", "all:")
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, ["--tb", "nonexistent"])
    assert "not found in any source/tb/" in result.output


def test_sim_tb_argument_found(tmp_path, monkeypatch):
    """sim --tb should run when the named TB exists."""
    _touch_text(tmp_path / "Makefile", "all:")
    touch(tmp_path / "source/tb/verilog/mytb.v")
    monkeypatch.setattr(
        makeflow,
        "run_make",
        lambda t, extra_vars=None: {"stdout": "", "stderr": "", "returncode": 0},
    )
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, ["--tb", "mytb"])
    assert "Running Icarus Verilog simulation" in result.output


def test_sim_multiple_invalid_choice(tmp_path, monkeypatch):
    """Invalid index should raise during list indexing → CLI non-zero exit."""
    _touch_text(tmp_path / "Makefile", "all:")
    _touch_text(tmp_path / "source/tb/verilog/a.v")
    _touch_text(tmp_path / "source/tb/verilog/b.v")
    monkeypatch.setattr(makeflow.click, "prompt", lambda *a, **k: 999)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim, [])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI: sim_verilator
# ---------------------------------------------------------------------------

def test_sim_verilator_missing_tool(tmp_path, monkeypatch):
    """sim_verilator should abort when verilator is not in PATH."""
    _touch_text(tmp_path / "Makefile", "all:")
    with _chdir(tmp_path):
        monkeypatch.setattr(makeflow.shutil, "which", lambda name: None)
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator, [])
    assert "Verilator not found in PATH" in result.output


def test_sim_verilator_no_testbenches(tmp_path, monkeypatch):
    """sim_verilator should warn when no TBs exist."""
    _touch_text(tmp_path / "Makefile", "all:")
    with _chdir(tmp_path):
        monkeypatch.setattr(makeflow.shutil, "which", lambda name: "/usr/bin/verilator")
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator, [])
    assert "No testbenches" in result.output


def test_sim_verilator_happy_outputs(tmp_path, monkeypatch):
    """Verilator present, TB found, obj_dir exists -> outputs printed."""
    _touch_text(tmp_path / "Makefile", "all:")
    tb = _touch_text(tmp_path / "source/tb/verilog/mytb.v", "// tb")

    monkeypatch.setattr(makeflow.shutil, "which", lambda name: "/usr/bin/verilator")
    monkeypatch.setattr(
        makeflow, "run_make", lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0}
    )
    obj_dir = tmp_path / "simulation/verilator/obj_dir"
    _touch_text(obj_dir / "Vmytb", "")
    _touch_text(obj_dir / "dump.vcd", "")

    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator, ["--tb", tb.stem])
    assert result.exit_code == 0
    assert "Running Verilator build" in result.output
    assert "Outputs (simulation/verilator/obj_dir)" in result.output


# ---------------------------------------------------------------------------
# CLI: sim_verilator_run
# ---------------------------------------------------------------------------

def test_sim_verilator_run_no_binaries(tmp_path):
    """sim_verilator_run should warn when obj_dir has no V* binaries."""
    (tmp_path / "simulation/verilator/obj_dir").mkdir(parents=True)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator_run, [])
    assert "No Verilator simulation executable found" in result.output


def test_sim_verilator_run_missing_exe(tmp_path):
    """sim_verilator_run --tb should warn if the named exe is missing."""
    (tmp_path / "simulation/verilator/obj_dir").mkdir(parents=True)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator_run, ["--tb", "nope"])
    assert "not found. Did you build it with sim-verilator" in result.output


def test_sim_verilator_run_tb_and_vcd(tmp_path, monkeypatch):
    """With --tb, executable exists and VCD present -> run & print VCD."""
    bin_dir = tmp_path / "simulation/verilator/obj_dir"
    bin_dir.mkdir(parents=True)
    exe = _touch_text(bin_dir / "Vcore", "")
    _touch_text(bin_dir / "dump.vcd", "")

    ran = {"cmd": None}
    monkeypatch.setattr(
        makeflow.subprocess, "run", lambda cmd, check=True: ran.update(cmd=tuple(cmd))
    )

    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator_run, ["--tb", "core"])
    assert result.exit_code == 0
    # PRODUCTION uses a relative path; normalize to absolute for comparison.
    assert Path(ran["cmd"][0]).resolve() == exe.resolve()
    assert "VCD output" in result.output


def test_sim_verilator_run_autodetect_newest(tmp_path, monkeypatch):
    """Autodetect chooses newest V* executable by mtime."""
    bin_dir = tmp_path / "simulation/verilator/obj_dir"
    bin_dir.mkdir(parents=True)

    old = _touch_text(bin_dir / "Vold", "")
    new = _touch_text(bin_dir / "Vnew", "")

    now = time.time()
    os.utime(old, (now - 100, now - 100))
    os.utime(new, (now, now))

    recorded = []
    monkeypatch.setattr(
        makeflow.subprocess, "run", lambda cmd, check=True: recorded.append(tuple(cmd))
    )

    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.sim_verilator_run, [])
    assert result.exit_code == 0
    assert recorded and Path(recorded[0][0]).name == "Vnew"


# ---------------------------------------------------------------------------
# CLI: wave
# ---------------------------------------------------------------------------

def test_wave_no_vcd(tmp_path):
    """wave should report if no VCD files are present."""
    (tmp_path / "simulation/icarus").mkdir(parents=True)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.wave, [])
    assert "No VCD files found" in result.output


def test_wave_select_from_multiple(tmp_path, monkeypatch):
    """wave should prompt when multiple VCDs exist."""
    vcd_dir = tmp_path / "simulation/icarus"
    vcd_dir.mkdir(parents=True)
    (vcd_dir / "foo.vcd").write_text("", encoding="utf-8")
    (vcd_dir / "bar.vcd").write_text("", encoding="utf-8")
    monkeypatch.setattr(makeflow.click, "prompt", lambda *a, **k: 2)
    monkeypatch.setattr(makeflow.subprocess, "run", lambda cmd: None)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.wave, [])
    assert "Multiple VCD files found" in result.output


def test_wave_explicit_missing_or_ok(tmp_path, monkeypatch):
    """Explicit VCD missing prints warning; on present spawns gtkwave."""
    vcd = tmp_path / "simulation/icarus/out.vcd"
    vcd.parent.mkdir(parents=True, exist_ok=True)

    # Missing
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.wave, [str(vcd)])
    assert "not found" in result.output

    # Present
    vcd.write_text("", encoding="utf-8")
    called = {"cmd": None}
    monkeypatch.setattr(makeflow.subprocess, "run", lambda cmd: called.update(cmd=tuple(cmd)))
    with _chdir(tmp_path):
        result = runner.invoke(makeflow.wave, [str(vcd)])
    assert "Launching GTKWave" in result.output
    assert called["cmd"] == ("gtkwave", str(vcd))


def test_wave_multiple_invalid_choice(tmp_path, monkeypatch):
    """Invalid index from prompt should bubble (IndexError) → non-zero exit."""
    vdir = tmp_path / "simulation/icarus"
    vdir.mkdir(parents=True)
    _touch_text(vdir / "a.vcd")
    _touch_text(vdir / "b.vcd")
    monkeypatch.setattr(makeflow.click, "prompt", lambda *a, **k: 999)  # out-of-range
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.wave, [])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI: wave_verilator
# ---------------------------------------------------------------------------

def test_wave_verilator_explicit_missing_or_ok(tmp_path, monkeypatch):
    """Explicit verilator VCD missing vs present behavior."""
    vcd = tmp_path / "simulation/verilator/obj_dir/dump.vcd"
    vcd.parent.mkdir(parents=True, exist_ok=True)

    # Missing
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.wave_verilator, [str(vcd)])
    assert "not found" in result.output

    # Present
    vcd.write_text("", encoding="utf-8")
    called = {"cmd": None}
    monkeypatch.setattr(makeflow.subprocess, "run", lambda cmd: called.update(cmd=tuple(cmd)))
    with _chdir(tmp_path):
        result = runner.invoke(makeflow.wave_verilator, [str(vcd)])
    assert "Launching GTKWave" in result.output
    assert called["cmd"] == ("gtkwave", str(vcd))


# ---------------------------------------------------------------------------
# CLI: synth
# ---------------------------------------------------------------------------

def test_synth_missing_script(tmp_path):
    """synth should abort when synth.ys is missing."""
    _touch_text(tmp_path / "Makefile", "all:")
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.synth, [])
    assert "synthesis/scripts/synth.ys not found" in result.output


def test_synth_happy_outputs(tmp_path, monkeypatch):
    """synth: script exists, Makefile exists, reports/out files listed."""
    _touch_text(tmp_path / "Makefile", "all:")
    _touch_text(tmp_path / "synthesis/scripts/synth.ys", "# ys")
    _touch_text(tmp_path / "synthesis/reports/r.txt", "r")
    _touch_text(tmp_path / "synthesis/out/o.txt", "o")
    monkeypatch.setattr(
        makeflow, "run_make", lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0}
    )
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.synth, [])
    assert result.exit_code == 0
    assert "Running Yosys synthesis" in result.output
    assert "Synthesis outputs" in result.output


# ---------------------------------------------------------------------------
# CLI: formal
# ---------------------------------------------------------------------------

def test_formal_no_sby(tmp_path):
    """formal should abort when no .sby specs are found."""
    (tmp_path / "formal/scripts").mkdir(parents=True)
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.formal, [])
    assert "No .sby spec found" in result.output


def test_formal_happy_outputs(tmp_path, monkeypatch):
    """formal: .sby exists, and reports/out collected."""
    _touch_text(tmp_path / "formal/scripts/prop.sby", "sby")
    _touch_text(tmp_path / "formal/reports/r.txt", "r")
    _touch_text(tmp_path / "formal/out/o.txt", "o")
    monkeypatch.setattr(
        makeflow, "run_make", lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0}
    )
    with _chdir(tmp_path):
        runner = CliRunner()
        result = runner.invoke(makeflow.formal, [])
    assert result.exit_code == 0
    assert "Running formal verification" in result.output
    assert "Formal outputs" in result.output


# ---------------------------------------------------------------------------
# CLI: clean
# ---------------------------------------------------------------------------

def test_clean_cancel(monkeypatch):
    """clean should exit early when the user declines."""
    monkeypatch.setattr(makeflow.click, "confirm", lambda *a, **k: False)
    runner = CliRunner()
    result = runner.invoke(makeflow.clean, [])
    assert "Clean canceled" in result.output


def test_clean_runs(monkeypatch):
    """clean should invoke make when the user confirms."""
    monkeypatch.setattr(makeflow.click, "confirm", lambda *a, **k: True)
    monkeypatch.setattr(
        makeflow, "run_make", lambda *a, **k: {"stdout": "", "stderr": "", "returncode": 0}
    )
    runner = CliRunner()
    result = runner.invoke(makeflow.clean, [])
    assert "Clean canceled" not in result.output


# ---------------------------------------------------------------------------
# CLI: check_tools
# ---------------------------------------------------------------------------

def test_check_tools(monkeypatch):
    """check_tools should show 'FOUND' when which() returns a path."""
    import types

    fake_tools_mod = types.ModuleType("saxoflow.tools")
    fake_tools_mod.TOOL_DESCRIPTIONS = {"toolA": "A tool"}
    monkeypatch.setitem(sys.modules, "saxoflow.tools", fake_tools_mod)

    # toolA present, others missing
    monkeypatch.setattr(
        makeflow.shutil, "which", lambda x: "/usr/bin/" + x if x == "toolA" else None
    )
    runner = CliRunner()
    result = runner.invoke(makeflow.check_tools, [])
    assert "toolA" in result.output and "FOUND" in result.output


def test_check_tools_missing_format(monkeypatch):
    """Ensure missing tool prints 'MISSING' status with description."""
    import types

    fake_tools_mod = types.ModuleType("saxoflow.tools")
    fake_tools_mod.TOOL_DESCRIPTIONS = {"t1": "Tool One", "t2": "Tool Two"}
    monkeypatch.setitem(sys.modules, "saxoflow.tools", fake_tools_mod)

    # Missing both
    monkeypatch.setattr(makeflow.shutil, "which", lambda name: None)

    runner = CliRunner()
    result = runner.invoke(makeflow.check_tools, [])
    assert "t1" in result.output and "MISSING" in result.output
    assert "t2" in result.output and "MISSING" in result.output


# ---------------------------------------------------------------------------
# CLI: simulate, simulate_verilator (dispatch)
# ---------------------------------------------------------------------------

def test_simulate_calls_sim_and_wave(monkeypatch):
    """simulate should dispatch to sim and wave in sequence."""
    monkeypatch.setattr(makeflow, "sim", mock.Mock())
    monkeypatch.setattr(makeflow, "wave", mock.Mock())
    runner = CliRunner()
    _ = runner.invoke(makeflow.simulate, [])
    assert makeflow.sim.called
    assert makeflow.wave.called


def test_simulate_verilator_calls(monkeypatch):
    """simulate_verilator should dispatch to build/run/view steps."""
    monkeypatch.setattr(makeflow, "sim_verilator", mock.Mock())
    monkeypatch.setattr(makeflow, "sim_verilator_run", mock.Mock())
    monkeypatch.setattr(makeflow, "wave_verilator", mock.Mock())
    runner = CliRunner()
    _ = runner.invoke(makeflow.simulate_verilator, [])
    assert makeflow.sim_verilator.called
    assert makeflow.sim_verilator_run.called
    assert makeflow.wave_verilator.called
