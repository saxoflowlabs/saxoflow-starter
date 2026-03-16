from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.sim_agent

Hermetic coverage for:
- _pushd (cwd swap/restore, even on error)
- _capture_stdio (stdout/stderr redirect + restore)
- SimAgent.run:
    * import failure
    * project path missing
    * CLI success with <top>.vcd
    * CLI success with dump.vcd fallback
    * CLI non-zero exit
    * CLI zero exit but no VCD
    * CLI zero exit but empty VCD
    * cwd restoration after run
No network; filesystem restricted to tmp_path.
"""

import sys
import types
from pathlib import Path

import click
import pytest


def _fresh_module():
    """Reload SUT to avoid cross-test global state interference."""
    import importlib

    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.agents.sim_agent")
    )


def _install_fake_saxoflow_sim(monkeypatch, sim_cmd):
    """
    Install a fake 'saxoflow.makeflow.sim' Click command into sys.modules,
    so 'from saxoflow.makeflow import sim' resolves consistently.
    """
    pkg = types.ModuleType("saxoflow")
    pkg.__path__ = []  # mark as package
    makeflow = types.ModuleType("saxoflow.makeflow")
    makeflow.sim = sim_cmd

    monkeypatch.setitem(sys.modules, "saxoflow", pkg)
    monkeypatch.setitem(sys.modules, "saxoflow.makeflow", makeflow)


# -----------------------
# Context managers
# -----------------------

def test_pushd_restores_cwd_on_success_and_error(tmp_path):
    """
    _pushd: should change cwd when entered, and restore it after normal exit
    and when an exception occurs.
    """
    sut = _fresh_module()
    start = Path.cwd()

    target = tmp_path / "proj"
    target.mkdir()

    # Normal path
    with sut._pushd(target):
        assert Path.cwd() == target
    assert Path.cwd() == start

    # Error path
    with pytest.raises(RuntimeError):
        with sut._pushd(target):
            assert Path.cwd() == target
            raise RuntimeError("boom")
    assert Path.cwd() == start


def test_capture_stdio_redirects_and_restores():
    """
    _capture_stdio: should redirect stdout/stderr inside the context and restore
    them on exit.
    """
    sut = _fresh_module()

    before_out, before_err = sys.stdout, sys.stderr
    with sut._capture_stdio() as (out_buf, err_buf):
        # Printing inside the context writes to the buffers.
        print("hello-stdout")
        print("hello-stderr", file=sys.stderr)
        assert "hello-stdout" in out_buf.getvalue()
        assert "hello-stderr" in err_buf.getvalue()

    # After exit, original streams restored.
    assert sys.stdout is before_out
    assert sys.stderr is before_err


# -----------------------
# SimAgent.run scenarios
# -----------------------

def test_run_import_failure(monkeypatch, tmp_path):
    """
    SimAgent.run: if 'from saxoflow.makeflow import sim' fails, return a
    failed result with an informative error_message.
    """
    sut = _fresh_module()

    # Force import failure only for the target module.
    import builtins as _bi
    orig_import = _bi.__import__

    def fake_import(name, *args, **kwargs):
        if name == "saxoflow.makeflow":
            raise ImportError("no saxoflow.makeflow")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_bi, "__import__", fake_import)

    res = sut.SimAgent().run(str(tmp_path), "top")
    assert res["status"] == "failed"
    assert res["stage"] == "simulation"
    assert "Failed to import SaxoFlow sim entrypoint" in (res["error_message"] or "")


def test_run_project_path_missing(monkeypatch, tmp_path):
    """
    SimAgent.run: project path must exist; if not, return failed with message.
    Ensure import succeeds by installing a fake sim command.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        pass

    _install_fake_saxoflow_sim(monkeypatch, sim)

    missing = tmp_path / "does_not_exist"
    res = sut.SimAgent().run(str(missing), "top")
    assert res["status"] == "failed"
    assert "Project path does not exist" in (res["error_message"] or "")


def test_run_success_with_top_vcd(monkeypatch, tmp_path):
    """
    SimAgent.run: CLI exit_code == 0 and '<top>.vcd' exists with content -> success.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        p = Path("simulation/icarus")
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{tb}.vcd").write_text("VCD", encoding="utf-8")

    _install_fake_saxoflow_sim(monkeypatch, sim)

    proj = tmp_path / "proj"
    proj.mkdir()
    res = sut.SimAgent().run(str(proj), "top")
    assert res["status"] == "success"
    assert res["stage"] == "simulation"
    assert res["error_message"] is None


def test_run_success_with_dump_vcd_fallback(monkeypatch, tmp_path):
    """
    SimAgent.run: CLI exit_code == 0 and 'dump.vcd' exists with content -> success.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        p = Path("simulation/icarus")
        p.mkdir(parents=True, exist_ok=True)
        (p / "dump.vcd").write_text("VCD", encoding="utf-8")

    _install_fake_saxoflow_sim(monkeypatch, sim)

    proj = tmp_path / "proj2"
    proj.mkdir()
    res = sut.SimAgent().run(str(proj), "top")
    assert res["status"] == "success"
    assert res["stage"] == "simulation"
    assert res["error_message"] is None


def test_run_nonzero_exit_code(monkeypatch, tmp_path):
    """
    SimAgent.run: when CLI returns non-zero exit code -> failed with exit code in message.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        # Explicitly signal failure
        raise SystemExit(2)

    _install_fake_saxoflow_sim(monkeypatch, sim)

    proj = tmp_path / "proj3"
    proj.mkdir()
    res = sut.SimAgent().run(str(proj), "topmod")
    assert res["status"] == "failed"
    assert "exit code 2" in (res["error_message"] or "")


def test_run_no_vcd_produced(monkeypatch, tmp_path):
    """
    SimAgent.run: CLI succeeds (exit_code 0) but no VCD -> failed with guidance message.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        # Do not create any VCD file.
        p = Path("simulation/icarus")
        p.mkdir(parents=True, exist_ok=True)

    _install_fake_saxoflow_sim(monkeypatch, sim)

    proj = tmp_path / "proj4"
    proj.mkdir()
    res = sut.SimAgent().run(str(proj), "unit_top")
    assert res["status"] == "failed"
    assert "did not produce a VCD file" in (res["error_message"] or "")


def test_run_empty_vcd(monkeypatch, tmp_path):
    """
    SimAgent.run: CLI exit_code 0 but VCD of size 0 -> failed.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        p = Path("simulation/icarus")
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{tb}.vcd").write_bytes(b"")  # size 0

    _install_fake_saxoflow_sim(monkeypatch, sim)

    proj = tmp_path / "proj5"
    proj.mkdir()
    res = sut.SimAgent().run(str(proj), "core")
    assert res["status"] == "failed"
    assert "did not produce a VCD file" in (res["error_message"] or "")


def test_run_restores_cwd(monkeypatch, tmp_path):
    """
    SimAgent.run: regardless of outcome, cwd is restored after the call.
    """
    sut = _fresh_module()

    @click.command()
    @click.option("--tb", required=True)
    def sim(tb):  # noqa: D401
        # Succeed with a valid VCD
        p = Path("simulation/icarus")
        p.mkdir(parents=True, exist_ok=True)
        (p / f"{tb}.vcd").write_text("ok", encoding="utf-8")

    _install_fake_saxoflow_sim(monkeypatch, sim)

    start = Path.cwd()
    proj = tmp_path / "proj6"
    proj.mkdir()

    res = sut.SimAgent().run(str(proj), "top")
    assert res["status"] == "success"
    assert Path.cwd() == start
