# """
# Tests for saxoflow.installer.runner module.

# The installer runner dispatches installation routines based on user
# selection, available presets and tool types.  The tests below ensure
# that the dispatcher correctly chooses between apt and script installers,
# persists tool paths to virtual environment activation scripts, and
# performs selection logic for install modes.  System calls are
# monkeypatched to avoid modifying the real environment.
# """

# import json
# import os
# import builtins
# import sys
# import saxoflow.installer.runner as runner
# import subprocess
# from pathlib import Path
# from unittest import mock


# def test_load_user_selection(tmp_path, monkeypatch):
#     """load_user_selection returns an empty list when the config file does not exist."""
#     monkeypatch.chdir(tmp_path)
#     assert runner.load_user_selection() == []
#     # Create a selection file and read it back
#     data = ["yosys", "iverilog"]
#     (tmp_path / ".saxoflow_tools.json").write_text(json.dumps(data))
#     assert runner.load_user_selection() == data


# def test_persist_tool_path(tmp_path, capsys):
#     """persist_tool_path appends a PATH export line when missing."""
#     # Set up a fake virtual environment activation script
#     venv_bin = tmp_path / ".venv" / "bin"
#     venv_bin.mkdir(parents=True, exist_ok=True)
#     activate_file = venv_bin / "activate"
#     activate_file.write_text("#!/bin/bash\n# existing content\n")
#     # Change working dir to simulate project root
#     cwd = os.getcwd()
#     os.chdir(tmp_path)
#     try:
#         runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
#     finally:
#         os.chdir(cwd)
#     content = activate_file.read_text()
#     # Expect that the new export line appears
#     assert "export PATH=$HOME/.local/dummy/bin:$PATH" in content


# def test_install_tool_dispatch(monkeypatch):
#     """install_tool should delegate to apt or script installer based on tool lists."""
#     calls = []
#     monkeypatch.setattr(runner, "install_apt", lambda tool: calls.append(("apt", tool)))
#     monkeypatch.setattr(runner, "install_script", lambda tool: calls.append(("script", tool)))
#     # Choose one apt tool and one script tool from definitions
#     from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS
#     apt_tool = APT_TOOLS[0]
#     script_tool = next(iter(SCRIPT_TOOLS))
#     runner.install_tool(apt_tool)
#     runner.install_tool(script_tool)
#     assert ("apt", apt_tool) in calls
#     assert ("script", script_tool) in calls


# def test_install_all(monkeypatch):
#     """install_all iterates through all tools and calls install_tool for each."""
#     called = []
#     monkeypatch.setattr(runner, "install_tool", lambda tool: called.append(tool))
#     runner.install_all()
#     from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS
#     expected = APT_TOOLS + list(SCRIPT_TOOLS.keys())
#     assert called == expected


# def test_install_single_tool(monkeypatch, capsys):
#     """install_single_tool prints messages on failure but still calls install_tool."""
#     called = []
#     def mock_install(tool):
#         called.append(tool)
#         raise subprocess.CalledProcessError(1, ["install"], "error")
#     import subprocess
#     monkeypatch.setattr(runner, "install_tool", mock_install)
#     runner.install_single_tool("yosys")
#     assert called == ["yosys"]


# def test_is_apt_installed_true_false(monkeypatch):
#     # True if dpkg returns 0, False otherwise
#     class FakeResult:
#         def __init__(self, rc): self.returncode = rc
#     monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult(0))
#     assert runner.is_apt_installed("foo")
#     monkeypatch.setattr(subprocess, "run", lambda *a, **k: FakeResult(1))
#     assert not runner.is_apt_installed("foo")


# def test_is_script_installed(tmp_path, monkeypatch):
#     # Directory exists -> True; not exists -> False
#     monkeypatch.setattr(Path, "home", lambda: tmp_path)
#     tool = "dummytool"
#     (tmp_path / ".local" / tool / "bin").mkdir(parents=True)
#     assert runner.is_script_installed(tool)
#     shutil = sys.modules["shutil"]
#     (tmp_path / ".local" / tool / "bin").rmdir()
#     assert not runner.is_script_installed(tool)


# def test_prompt_reinstall_yes_no(monkeypatch):
#     monkeypatch.setattr(builtins, "input", lambda _: "y")
#     assert runner.prompt_reinstall("yosys", "1.0") is True
#     monkeypatch.setattr(builtins, "input", lambda _: "n")
#     assert runner.prompt_reinstall("yosys", "1.0") is False


# def test_get_version_info_variants(monkeypatch):
#     # Should recognize output for several tools, default fallback
#     def fake_run(cmd, stdout, stderr, text, timeout):
#         class Fake:
#             def __init__(self, out): self.stdout = out
#         # For different tools
#         if "iverilog" in cmd[0]:
#             return Fake("Icarus Verilog version 12.0 (stable)")
#         if "gtkwave" in cmd[0]:
#             return Fake("GTKWave Analyzer v3.3.100")
#         if "magic" in cmd[0]:
#             return Fake("Magic 8.3.209 (Linux)")
#         if "netgen" in cmd[0]:
#             return Fake("Netgen 1.5.176")
#         if "openfpgaloader" in cmd[0]:
#             return Fake("openFPGALoader v0.10.0")
#         if "klayout" in cmd[0]:
#             return Fake("KLayout 0.27.10")
#         return Fake("SomeTool v1.2.3")
#     monkeypatch.setattr(subprocess, "run", fake_run)
#     # Try each tool
#     assert "Icarus Verilog version" in runner.get_version_info("iverilog", "iverilog")
#     assert "GTKWave Analyzer" in runner.get_version_info("gtkwave", "gtkwave")
#     assert "Magic" in runner.get_version_info("magic", "magic")
#     assert "Netgen" in runner.get_version_info("netgen", "netgen")
#     assert "openFPGALoader" in runner.get_version_info("openfpgaloader", "openfpgaloader")
#     assert "KLayout" in runner.get_version_info("klayout", "klayout")
#     # Fallback to regex
#     assert "SomeTool v1.2.3" in runner.get_version_info("dummy", "dummy")


# def test_install_apt_already_installed(monkeypatch):
#     # Simulate already installed, should print and return (not call apt)
#     monkeypatch.setattr(runner, "is_apt_installed", lambda t: True)
#     monkeypatch.setattr(runner, "get_version_info", lambda t, p: "Version 1.0")
#     monkeypatch.setattr(runner.shutil, "which", lambda t: "/usr/bin/" + t)
#     called = []
#     monkeypatch.setattr(builtins, "print", lambda msg: called.append(msg))
#     runner.install_apt("yosys")
#     assert any("already installed" in m for m in called)


# def test_install_apt_runs_apt(monkeypatch):
#     # Simulate not installed; should run apt
#     monkeypatch.setattr(runner, "is_apt_installed", lambda t: False)
#     monkeypatch.setattr(subprocess, "run", lambda cmd, check=None: None)
#     called = []
#     monkeypatch.setattr(builtins, "print", lambda msg: called.append(msg))
#     runner.install_apt("yosys")
#     assert any("Installing yosys via apt" in m for m in called)


# def test_install_script_already_installed(monkeypatch, tmp_path):
#     # Should print already installed and not run script
#     monkeypatch.setattr(runner, "is_script_installed", lambda t: True)
#     monkeypatch.setattr(runner.shutil, "which", lambda t: str(tmp_path / "fakebin"))
#     monkeypatch.setattr(runner, "get_version_info", lambda t, p: "Version 2.0")
#     called = []
#     monkeypatch.setattr(builtins, "print", lambda msg: called.append(msg))
#     runner.SCRIPT_TOOLS["mytool"] = "dummy_installer.sh"
#     runner.install_script("mytool")
#     assert any("already installed" in m for m in called)


# def test_install_script_missing_script(monkeypatch):
#     # Should print error if installer script missing
#     monkeypatch.setattr(runner, "is_script_installed", lambda t: False)
#     runner.SCRIPT_TOOLS["notool"] = "notfound.sh"
#     monkeypatch.setattr(Path, "exists", lambda self: False)
#     called = []
#     monkeypatch.setattr(builtins, "print", lambda msg: called.append(msg))
#     runner.install_script("notool")
#     assert any("Missing installer script" in m for m in called)


# def test_install_script_runs_script(monkeypatch, tmp_path):
#     # Should run the script if not installed and script exists
#     monkeypatch.setattr(runner, "is_script_installed", lambda t: False)
#     script = tmp_path / "ok.sh"
#     script.write_text("echo hi")
#     runner.SCRIPT_TOOLS["oktool"] = str(script)
#     monkeypatch.setattr(Path, "exists", lambda self: True)
#     monkeypatch.setattr(subprocess, "run", lambda *a, **k: None)
#     monkeypatch.setattr(runner, "persist_tool_path", lambda *a, **k: None)
#     called = []
#     monkeypatch.setattr(builtins, "print", lambda msg: called.append(msg))
#     runner.install_script("oktool")
#     assert any("Installing oktool via" in m for m in called)


# def test_install_selected(monkeypatch, tmp_path):
#     # Should call install_tool for each selected
#     sel = ["yosys", "iverilog"]
#     monkeypatch.setattr(runner, "load_user_selection", lambda: sel)
#     called = []
#     monkeypatch.setattr(runner, "install_tool", lambda t: called.append(t))
#     runner.install_selected()
#     assert called == sel

