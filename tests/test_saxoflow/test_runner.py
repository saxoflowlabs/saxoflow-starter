"""
Tests for saxoflow.installer.runner module.

Hermetic guarantees:
- No real subprocess calls (all patched).
- No writes outside tmp_path (cwd and files patched).
- Tool lists are patched where needed for deterministic assertions.

Covered behaviors:
- Selection persistence loading (OK / missing / corrupt).
- PATH persistence to venv activate (present / duplicate / missing venv).
- Version probing for multiple tools + fallback + timeout/OSError.
- install_apt: already-installed shortcut vs. apt install + VSCode tip.
- install_script: already-installed shortcut, missing script, happy path,
  and special-case 'yosys' extra PATH for 'slang'.
- Dispatcher (install_tool), bulk (install_all), selected (install_selected),
  and single tool (install_single_tool) with graceful error handling.
"""

from __future__ import annotations

import builtins
import json
import os
import subprocess
from pathlib import Path
from typing import List

import pytest

import saxoflow.installer.runner as runner


# ---------------------------------------------------------------------------
# load_user_selection
# ---------------------------------------------------------------------------

def test_load_user_selection_missing_and_ok(tmp_path, monkeypatch):
    """Returns [] when file missing; returns decoded list when present."""
    monkeypatch.chdir(tmp_path)

    # Missing -> []
    assert runner.load_user_selection() == []

    # Valid JSON list
    data = ["yosys", "iverilog"]
    (tmp_path / ".saxoflow_tools.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    assert runner.load_user_selection() == data


def test_load_user_selection_corrupt_returns_empty(tmp_path, monkeypatch):
    """Corrupt JSON should be swallowed and return []."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".saxoflow_tools.json").write_text("{not-json}", encoding="utf-8")
    assert runner.load_user_selection() == []


# ---------------------------------------------------------------------------
# persist_tool_path
# ---------------------------------------------------------------------------

def test_persist_tool_path_appends_once_and_not_duplicate(tmp_path, monkeypatch):
    """Appends an export line when missing; does not duplicate on second call."""
    # Arrange a fake project venv activate file
    vbin = tmp_path / ".venv" / "bin"
    vbin.mkdir(parents=True, exist_ok=True)
    activate = vbin / "activate"
    activate.write_text("#!/bin/sh\n", encoding="utf-8")

    # Work from tmp_path so relative VENV_ACTIVATE is used
    monkeypatch.chdir(tmp_path)

    # First append -> success message printed once
    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m))
    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")

    # Second append -> no new message / duplicate
    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")

    content = activate.read_text(encoding="utf-8")
    assert content.count("export PATH=$HOME/.local/dummy/bin:$PATH") == 1
    assert any("path added to virtual environment" in m for m in msgs)


def test_persist_tool_path_no_venv_prints_warning(tmp_path, monkeypatch, capsys):
    """If venv activate not found, prints a warning and returns."""
    monkeypatch.chdir(tmp_path)
    runner.persist_tool_path("toolx", "$HOME/.local/toolx/bin")
    out = capsys.readouterr().out
    assert "Virtual environment not found" in out


# ---------------------------------------------------------------------------
# is_apt_installed / is_script_installed
# ---------------------------------------------------------------------------

def test_is_apt_installed_true_false(monkeypatch):
    """dpkg rc==0 -> True; rc!=0 -> False."""
    class R:
        def __init__(self, rc): self.returncode = rc

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: R(0),
        raising=True,
    )
    assert runner.is_apt_installed("pkg")

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: R(1),
        raising=True,
    )
    assert not runner.is_apt_installed("pkg")


def test_is_script_installed_uses_home(tmp_path, monkeypatch):
    """Presence of ~/.local/<tool>/bin controls detection result."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)
    tool = "abc"

    path = tmp_path / ".local" / tool / "bin"
    path.mkdir(parents=True)
    assert runner.is_script_installed(tool)

    # Remove and test false
    path.rmdir()
    assert not runner.is_script_installed(tool)


# ---------------------------------------------------------------------------
# get_version_info
# ---------------------------------------------------------------------------

def test_get_version_info_variants_and_fallback(monkeypatch):
    """Recognizes tool-specific lines and falls back to regex when needed."""
    def fake_run(cmd, stdout, stderr, text, timeout, check=False):
        class Out:
            def __init__(self, s): self.stdout = s
        exe = cmd[0]
        if "iverilog" in exe:
            return Out("Icarus Verilog version 12.0 (stable)")
        if "gtkwave" in exe:
            return Out("GTKWave Analyzer v3.3.100")
        if "magic" in exe:
            return Out("Magic 8.3.209 (Linux)")
        if "netgen" in exe:
            return Out("Netgen 1.5.176")
        if "openfpgaloader" in exe:
            return Out("openFPGALoader v0.10.0")
        if "klayout" in exe:
            return Out("KLayout 0.27.10")
        return Out("SomeTool v1.2.3")  # generic fallback

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    assert "Icarus Verilog version" in runner.get_version_info("iverilog", "iverilog")
    assert "GTKWave Analyzer" in runner.get_version_info("gtkwave", "gtkwave")
    assert "Magic" in runner.get_version_info("magic", "magic")
    assert "Netgen" in runner.get_version_info("netgen", "netgen")
    assert "openFPGALoader" in runner.get_version_info(
        "openfpgaloader", "openfpgaloader"
    )
    assert "KLayout" in runner.get_version_info("klayout", "klayout")
    assert "v1.2.3" in runner.get_version_info("any", "any-exe")


def test_get_version_info_unknown_and_timeout(monkeypatch):
    """None path or subprocess timeout → '(version unknown)'."""
    assert runner.get_version_info("x", None) == "(version unknown)"

    def raises(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["t"], timeout=5)

    monkeypatch.setattr(subprocess, "run", raises, raising=True)
    assert runner.get_version_info("x", "x-exe") == "(version unknown)"


# ---------------------------------------------------------------------------
# install_apt
# ---------------------------------------------------------------------------

def test_install_apt_already_installed(monkeypatch):
    """When already installed, prints status and does not invoke apt."""
    monkeypatch.setattr(runner, "is_apt_installed", lambda _t: True, raising=True)
    monkeypatch.setattr(runner, "shutil_which", lambda t: f"/usr/bin/{t}", raising=True)
    monkeypatch.setattr(runner, "get_version_info", lambda t, p: "v1.0", raising=True)

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)

    runner.install_apt("yosys")
    assert any("already installed" in m for m in msgs)
    assert not any("Installing yosys via apt" in m for m in msgs)


def test_install_apt_runs_apt_and_code_tip(monkeypatch):
    """Non-installed -> calls apt. 'code' prints extra tip."""
    monkeypatch.setattr(runner, "is_apt_installed", lambda _t: False, raising=True)
    called = []

    def fake_run(cmd, check=True):
        called.append(tuple(cmd))
        return None

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)

    runner.install_apt("yosys")
    assert any("Installing yosys via apt" in m for m in msgs)
    assert ("sudo", "apt", "install", "-y", "yosys") in called

    msgs.clear()
    runner.install_apt("code")
    assert any("Tip: You can run VSCode" in m for m in msgs)


# ---------------------------------------------------------------------------
# install_script
# ---------------------------------------------------------------------------

def test_install_script_already_installed(monkeypatch, tmp_path):
    """Prints already-installed and returns without running script."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: True, raising=True)
    monkeypatch.setattr(runner, "shutil_which", lambda t: str(tmp_path / t), raising=True)
    monkeypatch.setattr(runner, "get_version_info", lambda t, p: "v2.0", raising=True)

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)

    # Ensure key exists so lookups succeed (value not used in this branch)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"mytool": "installer.sh"}, raising=True)
    runner.install_script("mytool")
    assert any("already installed" in m for m in msgs)


def test_install_script_missing_script(monkeypatch, tmp_path):
    """If installer script path does not exist, prints error and returns."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: False, raising=True)
    # Map to a non-existent path
    monkeypatch.setattr(
        runner, "SCRIPT_TOOLS", {"notool": str(tmp_path / "no.sh")}, raising=True
    )

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)
    runner.install_script("notool")
    assert any("Missing installer script" in m for m in msgs)


def test_install_script_runs_and_persists(monkeypatch, tmp_path):
    """Runs bash on script and persists PATH once (generic tool)."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: False, raising=True)

    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"oktool": str(script)}, raising=True)

    called = {"bash": False, "persist": []}

    def fake_run(cmd, check=True):
        if cmd[:1] == ["bash"]:
            called["bash"] = True
        return None

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)
    monkeypatch.setattr(
        runner,
        "persist_tool_path",
        lambda tool, path: called["persist"].append((tool, path)),
        raising=True,
    )

    runner.install_script("oktool")
    assert called["bash"] is True
    assert called["persist"] == [("oktool", "$HOME/.local/oktool/bin")]


def test_install_script_yosys_persists_slang_also(monkeypatch, tmp_path):
    """Special-case: installing 'yosys' also persists '$HOME/.local/slang/bin'."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: False, raising=True)

    script = tmp_path / "ys.sh"
    script.write_text("echo hi\n", encoding="utf-8")
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"yosys": str(script)}, raising=True)

    persists: List[tuple] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(
        runner,
        "persist_tool_path",
        lambda tool, path: persists.append((tool, path)),
        raising=True,
    )

    runner.install_script("yosys")
    assert ("yosys", "$HOME/.local/yosys/bin") in persists
    assert ("slang", "$HOME/.local/slang/bin") in persists


# ---------------------------------------------------------------------------
# Dispatcher & orchestration
# ---------------------------------------------------------------------------

def test_install_tool_dispatch_and_unknown(monkeypatch):
    """Dispatches to apt/script; unknown tool prints a skip message."""
    calls: List[tuple] = []
    monkeypatch.setattr(runner, "install_apt", lambda t: calls.append(("apt", t)))
    monkeypatch.setattr(
        runner, "install_script", lambda t: calls.append(("script", t))
    )
    # Deterministic tool lists
    monkeypatch.setattr(runner, "APT_TOOLS", ["a1"], raising=True)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"s1": "/p.sh"}, raising=True)

    runner.install_tool("a1")
    runner.install_tool("s1")

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m))
    runner.install_tool("unknown-x")

    assert ("apt", "a1") in calls and ("script", "s1") in calls
    assert any("No installer defined for 'unknown-x'" in m for m in msgs)


def test_install_all_iterates_and_handles_errors(monkeypatch):
    """Calls install_tool for each and prints a failure on exceptions."""
    monkeypatch.setattr(runner, "APT_TOOLS", ["t1"], raising=True)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"t2": "/s.sh"}, raising=True)

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)

    def maybe_fail(tool):
        # Fail for 't2', succeed for 't1'
        if tool == "t2":
            raise subprocess.CalledProcessError(1, ["x"])
        return None

    monkeypatch.setattr(runner, "install_tool", maybe_fail, raising=True)

    runner.install_all()
    assert any("Installing ALL known tools" in m for m in msgs)
    assert any("Failed installing t2" in m for m in msgs)


def test_install_selected_empty_and_ok(monkeypatch):
    """When selection is empty, prints guidance; otherwise installs each tool."""
    # Empty selection
    monkeypatch.setattr(runner, "load_user_selection", lambda: [], raising=True)
    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)
    runner.install_selected()
    assert any("No saved tool selection" in m for m in msgs)

    # Non-empty selection
    msgs.clear()
    seq: List[str] = []
    monkeypatch.setattr(
        runner, "load_user_selection", lambda: ["a", "b"], raising=True
    )
    monkeypatch.setattr(runner, "install_tool", lambda t: seq.append(t), raising=True)
    runner.install_selected()
    assert seq == ["a", "b"]
    assert any("Installing user-selected tools: ['a', 'b']" in m for m in msgs)


def test_install_single_tool_handles_error(monkeypatch):
    """install_single_tool prints a failure message on CalledProcessError."""
    def boom(_t):
        raise subprocess.CalledProcessError(1, ["cmd"], "err")

    monkeypatch.setattr(runner, "install_tool", boom, raising=True)

    msgs: List[str] = []
    monkeypatch.setattr(builtins, "print", lambda m: msgs.append(m), raising=True)

    runner.install_single_tool("zzz")
    assert any("Failed to install zzz" in m for m in msgs)
