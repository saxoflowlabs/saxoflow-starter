"""
Tests for saxoflow.installer.runner module.

The installer runner dispatches installation routines based on user
selection, available presets and tool types.  The tests below ensure
that the dispatcher correctly chooses between apt and script installers,
persists tool paths to virtual environment activation scripts, and
performs selection logic for install modes.  System calls are
monkeypatched to avoid modifying the real environment.
"""

import json
import os
from pathlib import Path
from unittest import mock

import saxoflow.installer.runner as runner
import subprocess


def test_load_user_selection(tmp_path, monkeypatch):
    """load_user_selection returns an empty list when the config file does not exist."""
    monkeypatch.chdir(tmp_path)
    assert runner.load_user_selection() == []
    # Create a selection file and read it back
    data = ["yosys", "iverilog"]
    (tmp_path / ".saxoflow_tools.json").write_text(json.dumps(data))
    assert runner.load_user_selection() == data


def test_persist_tool_path(tmp_path, capsys):
    """persist_tool_path appends a PATH export line when missing."""
    # Set up a fake virtual environment activation script
    venv_bin = tmp_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)
    activate_file = venv_bin / "activate"
    activate_file.write_text("#!/bin/bash\n# existing content\n")
    # Change working dir to simulate project root
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
    finally:
        os.chdir(cwd)
    content = activate_file.read_text()
    # Expect that the new export line appears
    assert "export PATH=$HOME/.local/dummy/bin:$PATH" in content


def test_install_tool_dispatch(monkeypatch):
    """install_tool should delegate to apt or script installer based on tool lists."""
    calls = []
    monkeypatch.setattr(runner, "install_apt", lambda tool: calls.append(("apt", tool)))
    monkeypatch.setattr(runner, "install_script", lambda tool: calls.append(("script", tool)))
    # Choose one apt tool and one script tool from definitions
    from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS
    apt_tool = APT_TOOLS[0]
    script_tool = next(iter(SCRIPT_TOOLS))
    runner.install_tool(apt_tool)
    runner.install_tool(script_tool)
    assert ("apt", apt_tool) in calls
    assert ("script", script_tool) in calls


def test_install_all(monkeypatch):
    """install_all iterates through all tools and calls install_tool for each."""
    called = []
    monkeypatch.setattr(runner, "install_tool", lambda tool: called.append(tool))
    runner.install_all()
    from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS
    expected = APT_TOOLS + list(SCRIPT_TOOLS.keys())
    assert called == expected


def test_install_single_tool(monkeypatch, capsys):
    """install_single_tool prints messages on failure but still calls install_tool."""
    called = []
    def mock_install(tool):
        called.append(tool)
        raise subprocess.CalledProcessError(1, ["install"], "error")
    import subprocess
    monkeypatch.setattr(runner, "install_tool", mock_install)
    runner.install_single_tool("yosys")
    assert called == ["yosys"]