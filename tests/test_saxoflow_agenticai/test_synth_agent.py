from __future__ import annotations

"""Hermetic tests for saxoflow_agenticai.agents.synth_agent.

Key idea
--------
We do NOT run Yosys in tests. Instead we:
- inject a fake `saxoflow.makeflow.synth` Click command into `sys.modules`
- create fake synthesis artifacts under tmp_path
- assert SynthAgent returns a stable structured result
"""

import sys
import types
from pathlib import Path

import click
import pytest


def _fresh_module():
    """Reload SUT to avoid cross-test global state interference."""
    import importlib

    return importlib.reload(importlib.import_module("saxoflow_agenticai.agents.synth_agent"))


def _install_fake_saxoflow_synth(monkeypatch, synth_cmd):
    """Make `from saxoflow.makeflow import synth` resolve to our fake command."""
    pkg = types.ModuleType("saxoflow")
    pkg.__path__ = []
    makeflow = types.ModuleType("saxoflow.makeflow")
    makeflow.synth = synth_cmd

    monkeypatch.setitem(sys.modules, "saxoflow", pkg)
    monkeypatch.setitem(sys.modules, "saxoflow.makeflow", makeflow)


def test_run_import_failure(monkeypatch, tmp_path):
    sut = _fresh_module()

    import builtins as _bi

    orig_import = _bi.__import__

    def fake_import(name, *args, **kwargs):
        if name == "saxoflow.makeflow":
            raise ImportError("no saxoflow.makeflow")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_bi, "__import__", fake_import)

    res = sut.SynthAgent().run(str(tmp_path))
    assert res["status"] == "failed"
    assert res["stage"] == "synthesis"
    assert "Failed to import" in (res["error_message"] or "")


def test_run_project_path_missing(monkeypatch, tmp_path):
    sut = _fresh_module()

    @click.command()
    def synth():
        pass

    _install_fake_saxoflow_synth(monkeypatch, synth)

    missing = tmp_path / "does_not_exist"
    res = sut.SynthAgent().run(str(missing))
    assert res["status"] == "failed"
    assert "Project path does not exist" in (res["error_message"] or "")


def test_run_success_with_artifacts(monkeypatch, tmp_path):
    sut = _fresh_module()

    @click.command()
    def synth():
        rep = Path("synthesis/reports")
        out = Path("synthesis/out")
        rep.mkdir(parents=True, exist_ok=True)
        out.mkdir(parents=True, exist_ok=True)
        (rep / "area.rpt").write_text("ok", encoding="utf-8")
        (out / "netlist.json").write_text("{}", encoding="utf-8")

    _install_fake_saxoflow_synth(monkeypatch, synth)

    proj = tmp_path / "proj"
    proj.mkdir()
    res = sut.SynthAgent().run(str(proj))
    assert res["status"] == "success"
    assert res["stage"] == "synthesis"
    assert res["error_message"] is None


def test_run_nonzero_exit_code(monkeypatch, tmp_path):
    sut = _fresh_module()

    @click.command()
    def synth():
        raise SystemExit(3)

    _install_fake_saxoflow_synth(monkeypatch, synth)

    proj = tmp_path / "proj2"
    proj.mkdir()
    res = sut.SynthAgent().run(str(proj))
    assert res["status"] == "failed"
    assert "exit code 3" in (res["error_message"] or "")


def test_run_zero_exit_but_no_artifacts(monkeypatch, tmp_path):
    sut = _fresh_module()

    @click.command()
    def synth():
        (Path("synthesis/reports")).mkdir(parents=True, exist_ok=True)
        (Path("synthesis/out")).mkdir(parents=True, exist_ok=True)

    _install_fake_saxoflow_synth(monkeypatch, synth)

    proj = tmp_path / "proj3"
    proj.mkdir()
    res = sut.SynthAgent().run(str(proj))
    assert res["status"] == "failed"
    assert "no artifacts" in (res["error_message"] or "").lower()


def test_run_restores_cwd(monkeypatch, tmp_path):
    sut = _fresh_module()

    @click.command()
    def synth():
        out = Path("synthesis/out")
        out.mkdir(parents=True, exist_ok=True)
        (out / "netlist.json").write_text("{}", encoding="utf-8")

    _install_fake_saxoflow_synth(monkeypatch, synth)

    start = Path.cwd()
    proj = tmp_path / "proj4"
    proj.mkdir()

    res = sut.SynthAgent().run(str(proj))
    assert res["status"] == "success"
    assert Path.cwd() == start
