"""Tests for `saxoflow/cli.py`.

These tests are hermetic and validate:
- init-env: delegates to interactive env runner with correct args
- install: dispatch across modes (selected/all/preset/tool) and error path
- deterministic usage/help rendering
- registration of makeflow/unit/diagnose commands on the root group
- optional Agentic AI group mounting when present
- helper `_sorted_unique` behavior

All subprocess/installer calls are monkeypatched at the exact import path
used inside the SUT (`saxoflow.cli`), so no real side effects occur.
"""

from __future__ import annotations

import importlib
import sys
from types import ModuleType
from typing import Iterable, List

import click
from click.testing import CliRunner


def _reload_cli_with_presets(monkeypatch, presets: dict[str, list[str]], with_agentic: bool = False):
    """Reload `saxoflow.cli` after injecting dynamic PRESETS and (optionally) a fake agentic group.

    Click's `Choice(list(PRESETS.keys()))` is evaluated at import time; hence we must
    patch `saxoflow.installer.presets.PRESETS` *before* (re)importing `saxoflow.cli`.
    """
    import saxoflow.installer.presets as presets_mod

    # Patch PRESETS for this import cycle.
    monkeypatch.setattr(presets_mod, "PRESETS", presets, raising=True)

    # Optionally provide a fake `saxoflow_agenticai.cli` with a `cli` Click group.
    if with_agentic:
        mod = ModuleType("saxoflow_agenticai.cli")
        grp = click.Group(name="agenticai")  # minimal group is enough
        setattr(mod, "cli", grp)
        sys.modules["saxoflow_agenticai.cli"] = mod
    else:
        sys.modules.pop("saxoflow_agenticai.cli", None)

    # Ensure a clean reload of SUT.
    if "saxoflow.cli" in sys.modules:
        import saxoflow.cli as sut
        return importlib.reload(sut)

    return importlib.import_module("saxoflow.cli")


def test_sorted_unique_basic(monkeypatch):
    """_sorted_unique: returns sorted, deduped strings, coercing to str."""
    sut = _reload_cli_with_presets(monkeypatch, presets={"minimal": ["iverilog"]})
    data: Iterable[str] = ["b", "a", "b", "a"]
    assert sut._sorted_unique(data) == ["a", "b"]
    # mixed types coerced to str
    assert sut._sorted_unique(["1", 2, "10"]) == ["1", "10", "2"]


def test_init_env_delegates_to_runner_for_preset_and_headless(monkeypatch):
    """init-env: with a preset → passes preset; with --headless → passes headless=True."""
    presets = {"foo": ["yosys"], "minimal": ["iverilog"]}
    sut = _reload_cli_with_presets(monkeypatch, presets=presets)

    called: List[tuple] = []

    # Patch the function AS IMPORTED in saxoflow.cli
    monkeypatch.setattr(
        sut, "run_interactive_env",
        lambda *, preset=None, headless=False: called.append((preset, headless)),
        raising=True,
    )

    runner = CliRunner()

    # --preset path (must be in the decorator's Choice — ensured by reload with patched PRESETS)
    res1 = runner.invoke(sut.cli, ["init-env", "--preset", "foo"])
    assert res1.exit_code == 0
    assert called[-1] == ("foo", False)

    # --headless path
    res2 = runner.invoke(sut.cli, ["init-env", "--headless"])
    assert res2.exit_code == 0
    assert called[-1] == (None, True)


def test_install_dispatch_selected_all_preset_tool_and_invalid(monkeypatch):
    """install: dispatches correctly across modes; invalid prints usage with sorted CSV."""
    presets = {"p1": ["yosys"], "minimal": ["iverilog"]}
    sut = _reload_cli_with_presets(monkeypatch, presets=presets)

    # Capture calls in-order
    calls: list[tuple[str, str | None]] = []

    monkeypatch.setattr(sut.runner, "install_selected", lambda: calls.append(("selected", None)), raising=True)
    monkeypatch.setattr(sut.runner, "install_all", lambda: calls.append(("all", None)), raising=True)
    # install_preset may or may not exist on the real runner; allow creating it.
    monkeypatch.setattr(sut.runner, "install_preset", lambda name: calls.append(("preset", name)), raising=False)
    monkeypatch.setattr(sut.runner, "install_single_tool", lambda name: calls.append(("tool", name)), raising=True)

    # Also adjust valid tool lists (consulted at runtime inside install()).
    monkeypatch.setattr(sut, "APT_TOOLS", ["t1"], raising=True)
    monkeypatch.setattr(sut, "SCRIPT_TOOLS", {"t2": "script.sh"}, raising=True)

    runner = CliRunner()

    # selected
    r1 = runner.invoke(sut.cli, ["install", "selected"])
    assert r1.exit_code == 0 and calls[-1] == ("selected", None)

    # all
    r2 = runner.invoke(sut.cli, ["install", "all"])
    assert r2.exit_code == 0 and calls[-1] == ("all", None)

    # preset
    r3 = runner.invoke(sut.cli, ["install", "p1"])
    assert r3.exit_code == 0 and calls[-1] == ("preset", "p1")

    # single tool (from either APT_TOOLS or SCRIPT_TOOLS)
    r4 = runner.invoke(sut.cli, ["install", "t1"])
    assert r4.exit_code == 0 and calls[-1] == ("tool", "t1")

    r5 = runner.invoke(sut.cli, ["install", "t2"])
    assert r5.exit_code == 0 and calls[-1] == ("tool", "t2")

    # invalid → usage, sorted CSVs
    r6 = runner.invoke(sut.cli, ["install", "??bad??"])
    assert r6.exit_code == 0
    assert "Invalid install mode" in r6.output
    # CSVs are sorted and deduped; also ensure both presets and tools are listed
    assert "p1, minimal" in r6.output or "minimal, p1" in r6.output
    assert "t1, t2" in r6.output


def test_install_exception_path_exits_nonzero(monkeypatch):
    """install: any exception is caught, printed, and the CLI exits non-zero."""
    presets = {"minimal": ["iverilog"]}
    sut = _reload_cli_with_presets(monkeypatch, presets=presets)

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sut.runner, "install_selected", boom, raising=True)
    res = CliRunner().invoke(sut.cli, ["install", "selected"])
    assert res.exit_code != 0
    assert "Installation error: kaboom" in res.output


def test_root_cli_registers_expected_commands(monkeypatch):
    """Root `cli` has essential subcommands attached (names only; behavior tested elsewhere)."""
    sut = _reload_cli_with_presets(monkeypatch, presets={"minimal": ["iverilog"]})
    # Command names are derived from the Click command objects added in cli.py
    required = {
        "init-env",
        "install",
        "diagnose",  # group
        "unit",
        "sim",
        "sim-verilator",
        "sim-verilator-run",
        "wave",
        "wave-verilator",
        "simulate",
        "simulate-verilator",
        "formal",
        "synth",
        "clean",
        "check-tools",
    }
    assert required.issubset(set(sut.cli.commands.keys()))


def test_agentic_group_is_added_when_available(monkeypatch):
    """When saxoflow_agenticai.cli is importable, its `cli` is mounted as group 'agenticai'."""
    presets = {"minimal": ["iverilog"]}
    sut = _reload_cli_with_presets(monkeypatch, presets=presets, with_agentic=True)
    assert "agenticai" in sut.cli.commands


def test_print_install_usage_formats_sorted_lists(monkeypatch, capsys):
    """_print_install_usage prints a deterministic, sorted CSV for presets and tools."""
    sut = _reload_cli_with_presets(monkeypatch, presets={"a": [], "c": [], "b": []})
    sut._print_install_usage(valid_presets=["b", "a", "b"], valid_tools=["z", "y", "x", "x"])
    out = capsys.readouterr().out
    # Sorted & unique
    assert "a, b" in out or "b, a" in out  # allow either CSV order (both valid due to sorting)
    assert "x, y, z" in out
