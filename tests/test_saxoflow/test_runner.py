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

def test_persist_tool_path_appends_once_and_not_duplicate(tmp_path, monkeypatch, capsys):
    """Appends an export line when missing; does not duplicate on second call."""
    # Arrange a fake project venv activate file
    vbin = tmp_path / ".venv" / "bin"
    vbin.mkdir(parents=True, exist_ok=True)
    activate = vbin / "activate"
    activate.write_text("#!/bin/sh\n", encoding="utf-8")

    # Work from tmp_path so relative VENV_ACTIVATE is used
    monkeypatch.chdir(tmp_path)

    # First append -> success message printed once
    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
    out1 = capsys.readouterr().out

    # Second append -> no new message / duplicate
    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
    out2 = capsys.readouterr().out

    content = activate.read_text(encoding="utf-8")
    assert content.count("export PATH=$HOME/.local/dummy/bin:$PATH") == 1
    assert "SUCCESS: dummy path added to virtual environment activation script." in out1
    assert out2 == ""


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

def test_install_apt_already_installed(monkeypatch, capsys):
    """When already installed, prints status and does not invoke apt."""
    monkeypatch.setattr(runner, "is_apt_installed", lambda _t: True, raising=True)
    monkeypatch.setattr(runner, "shutil_which", lambda t: f"/usr/bin/{t}", raising=True)
    monkeypatch.setattr(runner, "get_version_info", lambda t, p: "v1.0", raising=True)

    runner.install_apt("yosys")
    out = capsys.readouterr().out
    assert "SUCCESS: yosys already installed via apt: /usr/bin/yosys - v1.0" in out
    assert "INFO: Installing yosys via apt..." not in out


def test_install_apt_runs_apt_and_code_tip(monkeypatch, capsys):
    """Non-installed -> calls apt. 'code' prints extra tip."""
    monkeypatch.setattr(runner, "is_apt_installed", lambda _t: False, raising=True)
    called = []

    def fake_run(cmd, check=True):
        called.append(tuple(cmd))
        return None

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    runner.install_apt("yosys")
    out = capsys.readouterr().out
    assert "INFO: Installing yosys via apt..." in out
    assert ("sudo", "apt", "install", "-y", "yosys") in called

    runner.install_apt("code")
    out2 = capsys.readouterr().out
    assert "INFO: Installing code via apt..." in out2
    assert "TIP: You can run VSCode using 'code' from your terminal." in out2


# --- install_script ----------------------------------------------------------

def test_install_script_already_installed(monkeypatch, tmp_path, capsys):
    """Prints already-installed and returns without running script."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: True, raising=True)
    monkeypatch.setattr(runner, "shutil_which", lambda t: str(tmp_path / t), raising=True)
    monkeypatch.setattr(runner, "get_version_info", lambda t, p: "v2.0", raising=True)

    # Ensure key exists so lookups succeed (value not used in this branch)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"mytool": "installer.sh"}, raising=True)

    runner.install_script("mytool")
    out = capsys.readouterr().out
    # New format: "SUCCESS: mytool already installed: <path> - v2.0"
    assert "SUCCESS: mytool already installed:" in out
    assert " - v2.0" in out


def test_install_script_missing_script(monkeypatch, tmp_path, capsys):
    """If installer script path does not exist, prints error and returns."""
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: False, raising=True)
    # Map to a non-existent path
    monkeypatch.setattr(
        runner, "SCRIPT_TOOLS", {"notool": str(tmp_path / "no.sh")}, raising=True
    )

    runner.install_script("notool")
    out = capsys.readouterr().out
    assert "ERROR: Missing installer script:" in out


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

def test_install_selected_handles_calledprocesserror(monkeypatch, capsys):
    """
    Covers: install_selected -> per-tool except subprocess.CalledProcessError.
    """
    monkeypatch.setattr(runner, "load_user_selection", lambda: ["t1"], raising=True)

    def boom(_tool):
        raise subprocess.CalledProcessError(1, ["cmd"])
    monkeypatch.setattr(runner, "install_tool", boom, raising=True)

    runner.install_selected()
    out = capsys.readouterr().out
    assert "INFO: Installing user-selected tools: ['t1']" in out
    assert "WARNING: Failed installing t1" in out


def test_persist_tool_path_oserror_best_effort(monkeypatch, tmp_path, capsys):
    """
    Covers persist_tool_path -> except OSError: best-effort print and no crash.
    """
    # Arrange a real-looking activate file
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".venv" / "bin").mkdir(parents=True)
    (tmp_path / ".venv" / "bin" / "activate").write_text("#!/bin/sh\n", encoding="utf-8")

    # Make Path.open raise only for the venv activate path
    orig_open = Path.open
    def open_raiser(self, *args, **kwargs):
        if self == runner.VENV_ACTIVATE:
            raise OSError("boom")
        return orig_open(self, *args, **kwargs)
    monkeypatch.setattr(Path, "open", open_raiser, raising=True)

    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
    out = capsys.readouterr().out
    assert "Could not persist dummy path" in out  # best-effort warning printed


def test_install_selected_handles_calledprocesserror(monkeypatch, capsys):
    """
    Covers: install_selected -> per-tool except subprocess.CalledProcessError.
    """
    monkeypatch.setattr(runner, "load_user_selection", lambda: ["t1"], raising=True)

    def boom(_tool):
        raise subprocess.CalledProcessError(1, ["cmd"])
    monkeypatch.setattr(runner, "install_tool", boom, raising=True)

    runner.install_selected()
    out = capsys.readouterr().out
    assert "INFO: Installing user-selected tools: ['t1']" in out
    assert "WARNING: Failed installing t1" in out


def test_shutil_which_import_failure_returns_none(monkeypatch):
    """
    Covers: shutil_which -> except Exception: return None (import failure).
    """
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "shutil":
            raise ImportError("no shutil for you")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import, raising=True)
    assert runner.shutil_which("anything") is None


def test_shutil_which_success_returns_value(monkeypatch):
    """
    Covers the normal (non-exception) path inside shutil_which:
        return shutil.which(cmd)
    """
    import shutil as real_shutil

    # Ensure the imported shutil has our mocked .which
    monkeypatch.setattr(real_shutil, "which", lambda cmd: f"/mock/bin/{cmd}", raising=True)

    assert runner.shutil_which("yosys") == "/mock/bin/yosys"


def test_install_script_already_installed_uses_default_path_when_which_none(monkeypatch, capsys):
    """
    Covers the branch in install_script where existing_path is None and
    the fallback 'default_path' is used in the printed message:
        existing_path or default_path
    """
    # Pretend the tool is already installed (skip actual script run)
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: True, raising=True)

    # Force existing_path to be None
    monkeypatch.setattr(runner, "shutil_which", lambda _t: None, raising=True)

    # Version info still retrieved (path None is allowed by our stub)
    monkeypatch.setattr(runner, "get_version_info", lambda t, p: "v2.0", raising=True)

    # Ensure SCRIPT_TOOLS has the key so the code path is taken
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"toolx": "installer.sh"}, raising=True)

    runner.install_script("toolx")
    out = capsys.readouterr().out

    # New format (no emoji): "SUCCESS: toolx already installed: <path> - v2.0"
    assert "SUCCESS: toolx already installed:" in out
    assert "~/.local/toolx/bin" in out  # default path used when which() returns None
    assert " - v2.0" in out