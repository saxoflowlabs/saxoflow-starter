"""
Tests for saxoflow.installer.interactive_env.

These tests are fully hermetic:
- They never touch real network or external processes.
- Files are written only under tmp_path and via a patched TOOLS_FILE.
- Interactive prompts (questionary) are replaced with deterministic stubs.

Coverage goals:
- dump_tool_selection: success + OSError path
- _validate_preset: valid + invalid preset
- _dedupe_and_sort: normalization behavior
- _interactive_selection_flow: happy path + early abort + missing group error
- run_interactive_env: preset mode, headless (with/without 'minimal'),
  Cool CLI block env var, interactive no-selection path (custom mode)
- _print_final_summary: description mapping and fallback
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Iterable, List

import click
import pytest
from click.testing import CliRunner

import saxoflow.installer.interactive_env as sut


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _answers_iter(*values):
    """Yield answers in order for questionary.*().ask() calls."""
    it = iter(values)

    def factory(*_a, **_k):
        return SimpleNamespace(ask=lambda: next(it))
    return factory


def _set_minimal_groups(monkeypatch):
    """Patch minimal, consistent tool groups and descriptions for tests."""
    groups = {
        "ide": ["vscode"],
        "simulation": ["iverilog", "verilator"],
        "formal": ["symbiyosys"],
        "base": ["gtkwave", "yosys"],
        "fpga": ["nextpnr"],
        "asic": ["openroad"],
    }
    monkeypatch.setattr(sut, "ALL_TOOL_GROUPS", groups, raising=True)
    monkeypatch.setattr(
        sut, "TOOL_DESCRIPTIONS",
        {
            "vscode": "IDE",
            "iverilog": "Icarus",
            "verilator": "Verilator",
            "symbiyosys": "SBY",
            "gtkwave": "GTKWave",
            "yosys": "Yosys",
            "nextpnr": "NextPNR",
            "openroad": "OpenROAD",
        },
        raising=True,
    )
    return groups


# ---------------------------------------------------------------------------
# dump_tool_selection
# ---------------------------------------------------------------------------

def test_dump_tool_selection_writes_unicode(tmp_path, monkeypatch):
    """dump_tool_selection should write JSON with ensure_ascii=False (unicode preserved)."""
    out = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out, raising=True)

    data = ["yosys", "µtb", "α"]
    sut.dump_tool_selection(data)

    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == data  # exact preservation, including unicode


def test_dump_tool_selection_raises_click_on_oserror(tmp_path, monkeypatch):
    """dump_tool_selection should raise ClickException on OSError (parent dir missing)."""
    bad = tmp_path / "nope" / "tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", bad, raising=True)

    with pytest.raises(click.ClickException):
        sut.dump_tool_selection(["a", "b"])


# ---------------------------------------------------------------------------
# _validate_preset
# ---------------------------------------------------------------------------

def test_validate_preset_ok_and_invalid(monkeypatch):
    """_validate_preset returns the list for valid preset and raises for invalid."""
    monkeypatch.setattr(sut, "PRESETS", {"basic": ["yosys", "iverilog"]}, raising=True)

    assert sut._validate_preset("basic") == ["yosys", "iverilog"]
    with pytest.raises(click.ClickException):
        sut._validate_preset("nope")


# ---------------------------------------------------------------------------
# _dedupe_and_sort
# ---------------------------------------------------------------------------

def test_dedupe_and_sort_behavior():
    """_dedupe_and_sort should remove duplicates and sort ascending."""
    assert sut._dedupe_and_sort(["b", "a", "b", "a", "c"]) == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _interactive_selection_flow
# ---------------------------------------------------------------------------

def test_interactive_selection_flow_happy(monkeypatch):
    """Full custom wizard path with selections → returns combined list."""
    _set_minimal_groups(monkeypatch)

    # Calls in order:
    # select(target), select(verif), confirm(IDE), checkbox(sim/base/fpga)
    monkeypatch.setattr(
        sut.questionary, "select",
        _answers_iter("FPGA", "Simulation"), raising=True
    )
    monkeypatch.setattr(
        sut.questionary, "confirm",
        _answers_iter(True), raising=True
    )
    monkeypatch.setattr(
        sut.questionary, "checkbox",
        _answers_iter(["iverilog"], ["gtkwave"], ["nextpnr"]), raising=True
    )

    selected = sut._interactive_selection_flow()
    # IDE added because confirm=True; then sim/base/fpga picks
    assert selected == ["vscode", "iverilog", "gtkwave", "nextpnr"]


def test_interactive_selection_flow_aborted(monkeypatch, capsys):
    """If the user aborts the first select, flow returns None and prints message."""
    _set_minimal_groups(monkeypatch)
    # First select returns None -> abort
    monkeypatch.setattr(sut.questionary, "select", _answers_iter(None), raising=True)

    out = sut._interactive_selection_flow()
    captured = capsys.readouterr().out
    assert out is None
    assert "Aborted by user" in captured


def test_interactive_selection_flow_missing_group_raises(monkeypatch):
    """If ALL_TOOL_GROUPS lacks a required key, ClickException is raised."""
    groups = _set_minimal_groups(monkeypatch)
    # Remove 'base' to trip KeyError inside flow
    broken = dict(groups)
    broken.pop("base")
    monkeypatch.setattr(sut, "ALL_TOOL_GROUPS", broken, raising=True)

    # Provide minimal path to reach the missing 'base' step
    monkeypatch.setattr(
        sut.questionary, "select",
        _answers_iter("FPGA", "Simulation"), raising=True
    )
    monkeypatch.setattr(sut.questionary, "confirm", _answers_iter(False), raising=True)
    monkeypatch.setattr(
        sut.questionary, "checkbox",
        _answers_iter(["iverilog"], []), raising=True
    )

    with pytest.raises(click.ClickException):
        sut._interactive_selection_flow()


# ---------------------------------------------------------------------------
# _print_final_summary
# ---------------------------------------------------------------------------

def test_print_final_summary_uses_descriptions(capsys, monkeypatch):
    """_print_final_summary falls back to '(no description)' when missing."""
    monkeypatch.setattr(
        sut, "TOOL_DESCRIPTIONS",
        {"a": "Tool A"},  # 'b' intentionally missing
        raising=True,
    )
    sut._print_final_summary(["a", "b"])
    out = capsys.readouterr().out
    assert "Tool A" in out
    assert "(no description)" in out


# ---------------------------------------------------------------------------
# run_interactive_env
# ---------------------------------------------------------------------------

def test_run_interactive_env_preset_mode(tmp_path, monkeypatch, capsys):
    """Preset mode: validates, normalizes, persists, and prints preset message."""
    _set_minimal_groups(monkeypatch)
    monkeypatch.setattr(
        sut, "PRESETS",
        {"basic": ["yosys", "yosys", "iverilog"], "minimal": ["yosys"]},
        raising=True,
    )
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    saved = {"val": None}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda sel: saved.update(val=list(sel)), raising=True)
    monkeypatch.setattr(sut, "_print_final_summary", lambda sel: None, raising=True)

    sut.run_interactive_env(preset="basic", headless=False)

    # Dedupe+sort should occur before save
    assert saved["val"] == ["iverilog", "yosys"]
    assert "Preset 'basic' selected" in capsys.readouterr().out


def test_run_interactive_env_headless_minimal_present(tmp_path, monkeypatch):
    """Headless=True: picks 'minimal' when defined, persists normalized list."""
    _set_minimal_groups(monkeypatch)
    monkeypatch.setattr(sut, "PRESETS", {"minimal": ["yosys", "yosys"]}, raising=True)
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    saved = {"val": None}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda sel: saved.update(val=list(sel)), raising=True)
    monkeypatch.setattr(sut, "_print_final_summary", lambda sel: None, raising=True)

    sut.run_interactive_env(headless=True)
    assert saved["val"] == ["yosys"]


def test_run_interactive_env_headless_minimal_missing(tmp_path, monkeypatch, capsys):
    """Headless=True: if 'minimal' missing, warns and persists empty selection."""
    _set_minimal_groups(monkeypatch)
    monkeypatch.setattr(sut, "PRESETS", {"other": ["yosys"]}, raising=True)
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    saved = {"val": None}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda sel: saved.update(val=list(sel)), raising=True)
    monkeypatch.setattr(sut, "_print_final_summary", lambda sel: None, raising=True)

    sut.run_interactive_env(headless=True)
    out = capsys.readouterr().out
    assert "Headless mode requested" in out
    assert saved["val"] == []


def test_run_interactive_env_cool_cli_blocked(monkeypatch, tmp_path, capsys):
    """When SAXOFLOW_FORCE_HEADLESS=1 and no preset, interactive is blocked."""
    monkeypatch.setenv("SAXOFLOW_FORCE_HEADLESS", "1")
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    called = {"saved": False}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda _sel: called.update(saved=True), raising=True)

    sut.run_interactive_env(preset=None, headless=False)
    out = capsys.readouterr().out
    assert "Interactive environment setup is not supported" in out
    assert called["saved"] is False  # no persistence

    monkeypatch.delenv("SAXOFLOW_FORCE_HEADLESS", raising=False)


def test_run_interactive_env_interactive_custom_no_selection(tmp_path, monkeypatch, capsys):
    """Custom mode with no selections → prints warning and returns (no save)."""
    _set_minimal_groups(monkeypatch)
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    # Target=FPGA, Verif=Simulation, IDE=False, sim=[], base=[], fpga=[]
    monkeypatch.setattr(
        sut.questionary, "select",
        _answers_iter("FPGA", "Simulation"), raising=True
    )
    monkeypatch.setattr(sut.questionary, "confirm", _answers_iter(False), raising=True)
    monkeypatch.setattr(
        sut.questionary, "checkbox",
        _answers_iter([], [], []), raising=True
    )

    saved = {"called": False}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda _sel: saved.update(called=True), raising=True)

    sut.run_interactive_env(preset=None, headless=False)
    out = capsys.readouterr().out
    assert "No tools were selected. Aborting" in out
    assert saved["called"] is False  # nothing persisted


def test_run_interactive_env_interactive_success_persists(tmp_path, monkeypatch):
    """Custom mode with selections → persists deduped/sorted list and prints summary."""
    _set_minimal_groups(monkeypatch)
    out_file = tmp_path / ".saxoflow_tools.json"
    monkeypatch.setattr(sut, "TOOLS_FILE", out_file, raising=True)

    # Pick verif=formal (auto adds 'formal' group), IDE False, base=[], asic=[]
    monkeypatch.setattr(
        sut.questionary, "select",
        _answers_iter("ASIC", "Formal"), raising=True
    )
    monkeypatch.setattr(sut.questionary, "confirm", _answers_iter(False), raising=True)
    monkeypatch.setattr(
        sut.questionary, "checkbox",
        _answers_iter([], []),  # base=[], asic=[]
        raising=True,
    )

    saved = {"val": None}
    monkeypatch.setattr(sut, "dump_tool_selection", lambda sel: saved.update(val=list(sel)), raising=True)
    monkeypatch.setattr(sut, "_print_final_summary", lambda sel: None, raising=True)

    sut.run_interactive_env(preset=None, headless=False)
    # Only 'formal' tools included (symbiyosys)
    assert saved["val"] == ["symbiyosys"]
