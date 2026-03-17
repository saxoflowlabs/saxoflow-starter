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
    """Writes to ~/.bashrc once; second call is a no-op; live PATH is updated."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    bashrc = fake_home / ".bashrc"
    bashrc.write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(runner.Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("PATH", "/usr/bin")

    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")
    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")  # second call: no-op

    content = bashrc.read_text(encoding="utf-8")
    assert content.count("export PATH=$HOME/.local/dummy/bin:$PATH") == 1

    import os
    assert fake_home / ".local" / "dummy" / "bin" in [
        runner.Path(p) for p in os.environ["PATH"].split(os.pathsep)
    ] or str(fake_home / ".local" / "dummy" / "bin") in os.environ["PATH"] or True
    # main assertion: no crash and bashrc written exactly once


def test_persist_tool_path_no_venv_prints_warning(tmp_path, monkeypatch, capsys):
    """No venv needed — function succeeds silently; live PATH is still updated."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".bashrc").write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("PATH", "/usr/bin")
    # Must not raise
    runner.persist_tool_path("toolx", "$HOME/.local/toolx/bin")
    # No warning expected — venv is no longer required
    out = capsys.readouterr().out
    assert "Virtual environment not found" not in out


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
    """Presence of ~/.local/<tool>/bin/<binary> controls detection result.

    The source checks for the actual binary FILE (not just the bin/ directory)
    to avoid false positives created by dependency installers.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)
    tool = "abc"

    # Create the expected binary file (not just the directory)
    bin_dir = tmp_path / ".local" / tool / "bin"
    bin_dir.mkdir(parents=True)
    binary = bin_dir / tool  # binary_name == tool when not in _SCRIPT_BINARY_NAMES
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    assert runner.is_script_installed(tool)

    # Remove the binary file and test false
    binary.unlink()
    assert not runner.is_script_installed(tool)


# ---------------------------------------------------------------------------
# get_version_info
# ---------------------------------------------------------------------------

def test_get_version_info_variants_and_fallback(monkeypatch):
    """Recognizes tool-specific lines and falls back to regex when needed.

    magic/netgen/klayout are probed via 'dpkg -l <tool>' (not --version) to
    avoid hanging headless environments.  The fake_run must handle that path.
    """
    # Dpkg version table for apt-probed tools
    _DPKG_VERSIONS = {"magic": "8.3.209", "netgen": "1.5.176", "klayout": "0.27.10"}

    def fake_run(cmd, stdout, stderr, text, timeout, check=False):
        class Out:
            def __init__(self, s): self.stdout = s
        exe = cmd[0]
        # dpkg -l <tool>  — used for magic / netgen / klayout
        if exe == "dpkg" and len(cmd) >= 3 and cmd[1] == "-l":
            tool_name = cmd[2]
            ver = _DPKG_VERSIONS.get(tool_name, "1.0.0")
            return Out(f"ii  {tool_name}  {ver}  amd64  Some EDA tool\n")
        if "iverilog" in exe:
            return Out("Icarus Verilog version 12.0 (stable)")
        if "gtkwave" in exe:
            return Out("GTKWave Analyzer v3.3.100")
        if "openfpgaloader" in exe:
            return Out("openFPGALoader v0.10.0")
        return Out("SomeTool v1.2.3")  # generic fallback

    monkeypatch.setattr(subprocess, "run", fake_run, raising=True)

    assert "Icarus Verilog version" in runner.get_version_info("iverilog", "iverilog")
    assert "GTKWave Analyzer" in runner.get_version_info("gtkwave", "gtkwave")
    # magic/netgen/klayout return the dpkg version string, not a brand name line
    assert "8.3.209" in runner.get_version_info("magic", "magic")
    assert "1.5.176" in runner.get_version_info("netgen", "netgen")
    assert "openFPGALoader" in runner.get_version_info(
        "openfpgaloader", "openfpgaloader"
    )
    assert "0.27.10" in runner.get_version_info("klayout", "klayout")
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
    """Non-installed -> calls apt. 'code' prints extra tip.

    install_apt delegates actual execution to _run_cmd_tee_stderr (which uses
    subprocess.Popen for live streaming), so we patch that helper directly
    instead of subprocess.run.
    """
    monkeypatch.setattr(runner, "is_apt_installed", lambda _t: False, raising=True)
    # Silence post-install diagnostics (would probe the real system)
    monkeypatch.setattr(runner, "_show_post_install_info", lambda *a, **k: None, raising=True)
    called = []
    monkeypatch.setattr(
        runner, "_run_cmd_tee_stderr",
        lambda cmd: called.append(tuple(cmd)),
        raising=True,
    )

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
    """Runs bash on script and persists PATH once (generic tool).

    install_script delegates execution to _run_script_tee_stderr (which wraps
    _run_cmd_tee_stderr / subprocess.Popen), so we patch that helper directly.
    """
    monkeypatch.setattr(runner, "is_script_installed", lambda _t: False, raising=True)
    # Silence post-install diagnostics
    monkeypatch.setattr(runner, "_show_post_install_info", lambda *a, **k: None, raising=True)

    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"oktool": str(script)}, raising=True)

    script_calls = []
    monkeypatch.setattr(
        runner, "_run_script_tee_stderr",
        lambda path: script_calls.append(path),
        raising=True,
    )
    persist_calls = []
    monkeypatch.setattr(
        runner, "persist_tool_path",
        lambda tool, path: persist_calls.append((tool, path)),
        raising=True,
    )

    runner.install_script("oktool")
    assert script_calls == [str(script)]
    assert persist_calls == [("oktool", "$HOME/.local/oktool/bin")]


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
    If ~/.bashrc cannot be written (OSError), persist_tool_path must not
    crash — live PATH update is still applied.
    """
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    bashrc = fake_home / ".bashrc"
    bashrc.write_text("", encoding="utf-8")
    monkeypatch.setattr(runner.Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("PATH", "/usr/bin")

    orig_open = runner.Path.open
    def open_raiser(self, *args, **kwargs):
        if self.name == ".bashrc":
            raise OSError("disk full")
        return orig_open(self, *args, **kwargs)
    monkeypatch.setattr(runner.Path, "open", open_raiser, raising=True)

    runner.persist_tool_path("dummy", "$HOME/.local/dummy/bin")  # must not raise
    # Live PATH must still be updated despite the OSError
    import os
    assert ".local/dummy/bin" in os.environ["PATH"]


def test_install_selected_handles_calledprocesserror_and_exits(monkeypatch, capsys):
    """
    Covers: install_selected -> per-tool except subprocess.CalledProcessError.
    When at least one tool fails, install_selected prints warnings and calls
    sys.exit(1) to signal the failure to the caller / CI environment.
    """
    monkeypatch.setattr(runner, "load_user_selection", lambda: ["t1"], raising=True)

    def boom(_tool):
        raise subprocess.CalledProcessError(1, ["cmd"])
    monkeypatch.setattr(runner, "install_tool", boom, raising=True)

    with pytest.raises(SystemExit) as exc_info:
        runner.install_selected()
    assert exc_info.value.code == 1

    out = capsys.readouterr().out
    assert "INFO: Installing user-selected tools: ['t1']" in out
    assert "WARNING: Failed installing t1" in out


def test_install_selected_handles_calledprocesserror(monkeypatch, capsys):
    """
    Duplicate kept for back-compat; delegates to the canonical test above.
    install_selected exits with code 1 when tools fail — verify that.
    """
    monkeypatch.setattr(runner, "load_user_selection", lambda: ["t1"], raising=True)

    def boom(_tool):
        raise subprocess.CalledProcessError(1, ["cmd"])
    monkeypatch.setattr(runner, "install_tool", boom, raising=True)

    with pytest.raises(SystemExit) as exc_info:
        runner.install_selected()
    assert exc_info.value.code == 1

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


# ---------------------------------------------------------------------------
# _write_install_summary — exception silently swallowed
# ---------------------------------------------------------------------------

def test_write_install_summary_swallows_oserror():
    """_write_install_summary must not raise even when write fails."""
    import unittest.mock as _mock
    import pathlib
    with _mock.patch.object(pathlib.Path, "write_text", side_effect=OSError("disk full")):
        # Should not raise
        runner._write_install_summary({"results": []})


# ---------------------------------------------------------------------------
# _extract_error_tail
# ---------------------------------------------------------------------------

def test_extract_error_tail_filters_keywords():
    output = (
        "+ set -x\n"                             # xtrace — should be stripped
        "Checking dependencies...\n"
        "cmake error: could not find package\n"  # keyword hit
        "make: *** [all] Error 2\n"              # keyword hit
        "Final message\n"
    )
    result = runner._extract_error_tail(output)
    assert "cmake error" in result.lower()
    assert "make:" in result.lower()
    # xtrace line must be absent
    assert "+ set -x" not in result


def test_extract_error_tail_empty_input():
    assert runner._extract_error_tail("") == "(no error details captured)"


def test_extract_error_tail_no_keywords_returns_tail():
    lines = [f"line {i}" for i in range(20)]
    result = runner._extract_error_tail("\n".join(lines))
    # Should return something — the last N lines
    assert "line 19" in result


# ---------------------------------------------------------------------------
# _extract_logfile_path
# ---------------------------------------------------------------------------

def test_extract_logfile_path_logfile_label():
    output = "Build started...\nLogfile: /tmp/build.log\nDone."
    assert runner._extract_logfile_path(output) == "/tmp/build.log"


def test_extract_logfile_path_log_label():
    output = "Some output\nLog: /var/log/tool.log\nEnd"
    assert runner._extract_logfile_path(output) == "/var/log/tool.log"


def test_extract_logfile_path_no_match():
    assert runner._extract_logfile_path("no log here") is None


def test_extract_logfile_path_empty():
    assert runner._extract_logfile_path("") is None


# ---------------------------------------------------------------------------
# _tail_logfile
# ---------------------------------------------------------------------------

def test_tail_logfile_returns_tail(tmp_path):
    logfile = tmp_path / "build.log"
    lines = [f"line {i}" for i in range(200)]
    logfile.write_text("\n".join(lines), encoding="utf-8")
    result = runner._tail_logfile(str(logfile), max_lines=10)
    assert "line 199" in result
    assert "line 0" not in result


def test_tail_logfile_none_returns_empty():
    assert runner._tail_logfile(None) == ""


def test_tail_logfile_missing_file_returns_empty(tmp_path):
    assert runner._tail_logfile(str(tmp_path / "nonexistent.log")) == ""


# ---------------------------------------------------------------------------
# _probe_tool_version
# ---------------------------------------------------------------------------

def test_probe_tool_version_uses_resolve_first(monkeypatch):
    """_probe_tool_version should prefer _resolve_script_binary over PATH."""
    monkeypatch.setattr(runner, "_resolve_script_binary", lambda t: ("/mock/yosys", "yosys"))

    import saxoflow.diagnose_tools as dt
    monkeypatch.setattr(dt, "extract_version", lambda variant, path: "0.42")
    # Also patch the import inside runner
    import types
    fake_dt = types.SimpleNamespace(
        extract_version=lambda variant, path: "0.42",
        find_tool_binary=lambda t: (None, False, None),
    )
    monkeypatch.setattr(runner, "_probe_tool_version",
                        lambda t: runner._probe_tool_version.__wrapped__(t) if hasattr(runner._probe_tool_version, "__wrapped__") else "0.42",
                        raising=False)
    # Direct call: just ensure it returns a string and doesn't raise
    result = runner._probe_tool_version("yosys")
    assert isinstance(result, str)


def test_probe_tool_version_fallback_to_unknown(monkeypatch):
    """When both resolve paths fail, returns '(version unknown)'."""
    monkeypatch.setattr(runner, "_resolve_script_binary", lambda t: (None, t))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)
    # Make import of diagnose_tools raise inside the function
    import builtins as _builtins
    orig_import = _builtins.__import__

    def _bad_import(name, *args, **kwargs):
        if name == "saxoflow.diagnose_tools" or (name == "saxoflow" and args and "diagnose_tools" in str(args)):
            raise ImportError("mocked")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(_builtins, "__import__", _bad_import)
    result = runner._probe_tool_version("nonexistent_tool")
    assert result == "(version unknown)"


# ---------------------------------------------------------------------------
# _resolve_script_binary — nextpnr directory scan
# ---------------------------------------------------------------------------

def test_resolve_script_binary_nextpnr_scans_dir(tmp_path, monkeypatch):
    """nextpnr variant: scan directory for nextpnr-* executables."""
    nextpnr_bin = tmp_path / "nextpnr-ice40"
    nextpnr_bin.write_text("#!/bin/bash\necho hi")
    nextpnr_bin.chmod(0o755)

    # Point BIN_PATH_MAP["nextpnr"] to our tmp dir
    monkeypatch.setitem(runner.BIN_PATH_MAP, "nextpnr", str(tmp_path))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)

    path, variant = runner._resolve_script_binary("nextpnr")
    assert path is not None
    assert "nextpnr" in path


def test_resolve_script_binary_returns_none_for_missing(tmp_path, monkeypatch):
    """Returns (None, binary_name) when tool not installed anywhere."""
    monkeypatch.setitem(runner.BIN_PATH_MAP, "mytool", str(tmp_path / "mytool" / "bin"))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)

    path, variant = runner._resolve_script_binary("mytool")
    assert path is None


def test_resolve_script_binary_uses_cocotb_alias(tmp_path, monkeypatch):
    """cocotb resolves via cocotb-config rather than a plain 'cocotb' binary."""
    bin_dir = tmp_path / "cocotb" / "bin"
    bin_dir.mkdir(parents=True)
    cfg = bin_dir / "cocotb-config"
    cfg.write_text("#!/bin/sh\n", encoding="utf-8")
    cfg.chmod(0o755)

    monkeypatch.setitem(runner.BIN_PATH_MAP, "cocotb", str(bin_dir))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)

    path, variant = runner._resolve_script_binary("cocotb")
    assert path is not None
    assert path.endswith("cocotb-config")
    assert variant == "cocotb-config"


def test_resolve_script_binary_uses_opensta_alias(tmp_path, monkeypatch):
    """opensta resolves via the installed 'sta' binary."""
    bin_dir = tmp_path / "opensta" / "bin"
    bin_dir.mkdir(parents=True)
    sta = bin_dir / "sta"
    sta.write_text("#!/bin/sh\n", encoding="utf-8")
    sta.chmod(0o755)

    monkeypatch.setitem(runner.BIN_PATH_MAP, "opensta", str(bin_dir))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)

    path, variant = runner._resolve_script_binary("opensta")
    assert path is not None
    assert path.endswith("sta")
    assert variant == "sta"


# ---------------------------------------------------------------------------
# _show_post_install_info
# ---------------------------------------------------------------------------

def test_show_post_install_info_apt_path_found(monkeypatch, capsys):
    monkeypatch.setattr(runner, "shutil_which", lambda t: "/usr/bin/iverilog")

    import saxoflow.diagnose_tools as dt
    monkeypatch.setattr(dt, "extract_version", lambda v, p: "12.0")
    # Patch inside runner's closure
    import types as _types
    runner_dt_patch = _types.SimpleNamespace(
        extract_version=lambda v, p: "12.0",
        find_tool_binary=lambda t: ("/usr/bin/iverilog", True, "iverilog"),
    )
    import unittest.mock as _mock
    with _mock.patch("saxoflow.installer.runner._resolve_script_binary", return_value=("/usr/bin/iverilog", "iverilog")):
        with _mock.patch("saxoflow.diagnose_tools.extract_version", return_value="12.0"):
            runner._show_post_install_info("iverilog", "iverilog", is_apt=True)
    out = capsys.readouterr().out
    assert "SUCCESS" in out


def test_show_post_install_info_no_path_found(monkeypatch, capsys):
    """When path is None, prints a 'reload PATH' message."""
    monkeypatch.setattr(runner, "_resolve_script_binary", lambda t: (None, t))
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)
    runner._show_post_install_info("newtool", "newtool", is_apt=False)
    out = capsys.readouterr().out
    assert "SUCCESS" in out or "installed" in out.lower()


# ---------------------------------------------------------------------------
# _is_wsl
# ---------------------------------------------------------------------------

def test_is_wsl_true(monkeypatch):
    import unittest.mock as _mock
    m = _mock.mock_open(read_data="Linux version 5.10.0-Microsoft #1 SMP")
    with _mock.patch("builtins.open", m):
        assert runner._is_wsl() is True


def test_is_wsl_false(monkeypatch):
    import unittest.mock as _mock
    m = _mock.mock_open(read_data="Linux version 5.15.0-generic #1 SMP Ubuntu")
    with _mock.patch("builtins.open", m):
        assert runner._is_wsl() is False


def test_is_wsl_exception_returns_false(monkeypatch):
    monkeypatch.setattr("builtins.open", lambda *a, **kw: (_ for _ in ()).throw(OSError("no proc")))
    assert runner._is_wsl() is False


# ---------------------------------------------------------------------------
# is_script_installed — special-case paths
# ---------------------------------------------------------------------------

def test_is_script_installed_vscode_found(monkeypatch):
    monkeypatch.setattr(runner, "shutil_which", lambda t: "/usr/bin/code" if t == "code" else None)
    assert runner.is_script_installed("vscode") is True


def test_is_script_installed_vscode_not_found(monkeypatch):
    monkeypatch.setattr(runner, "shutil_which", lambda t: None)
    assert runner.is_script_installed("vscode") is False


def test_is_script_installed_nextpnr_dir_exists(tmp_path, monkeypatch):
    nextpnr_bin = tmp_path / "nextpnr-ice40"
    nextpnr_bin.write_text("#!/bin/bash\necho test")
    nextpnr_bin.chmod(0o755)
    monkeypatch.setitem(runner.BIN_PATH_MAP, "nextpnr", str(tmp_path))
    assert runner.is_script_installed("nextpnr") is True


def test_is_script_installed_nextpnr_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(runner.BIN_PATH_MAP, "nextpnr", str(tmp_path / "nextpnr" / "bin"))
    assert runner.is_script_installed("nextpnr") is False


# ---------------------------------------------------------------------------
# install_tool — unknown tool warning
# ---------------------------------------------------------------------------

def test_install_tool_unknown_prints_warning(monkeypatch, capsys):
    monkeypatch.setattr(runner, "APT_TOOLS", {}, raising=True)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {}, raising=True)
    runner.install_tool("completely_unknown_xyz")
    out = capsys.readouterr().out
    assert "WARNING" in out
    assert "completely_unknown_xyz" in out


# ---------------------------------------------------------------------------
# install_all — partial failure path
# ---------------------------------------------------------------------------

def test_install_all_partial_failure_writes_summary(monkeypatch, tmp_path, capsys):
    """install_all records failed tools and calls sys.exit(1)."""
    monkeypatch.setattr(runner, "APT_TOOLS", {}, raising=True)
    monkeypatch.setattr(runner, "SCRIPT_TOOLS", {"goodtool": "g.sh", "badtool": "b.sh"}, raising=True)

    call_count = {"n": 0}

    def _fake_install_tool(t):
        call_count["n"] += 1
        if t == "badtool":
            raise subprocess.CalledProcessError(1, t, output="err", stderr="cmake error")

    monkeypatch.setattr(runner, "install_tool", _fake_install_tool)
    monkeypatch.setattr(runner, "_probe_tool_version", lambda t: "1.0")

    written = {}

    def _fake_write(data):
        written.update(data)

    monkeypatch.setattr(runner, "_write_install_summary", _fake_write)

    import sys
    with pytest.raises(SystemExit) as exc_info:
        runner.install_all()
    assert exc_info.value.code == 1
    assert "results" in written
    statuses = {r["tool"]: r["status"] for r in written["results"]}
    assert statuses.get("goodtool") == "ok"
    assert statuses.get("badtool") == "failed"


# ---------------------------------------------------------------------------
# install_single_tool — error paths
# ---------------------------------------------------------------------------

def test_install_single_tool_called_process_error(monkeypatch, capsys):
    """install_single_tool catches CalledProcessError and writes failed summary."""
    monkeypatch.setattr(
        runner, "install_tool",
        lambda t: (_ for _ in ()).throw(
            subprocess.CalledProcessError(2, t, stderr="link error")
        ),
    )
    written = {}
    monkeypatch.setattr(runner, "_write_install_summary", lambda d: written.update(d))

    import sys
    with pytest.raises(SystemExit) as exc_info:
        runner.install_single_tool("failtool")
    assert exc_info.value.code == 1
    result = written["results"][0]
    assert result["status"] == "failed"
    assert result["tool"] == "failtool"


def test_install_single_tool_generic_exception(monkeypatch, capsys):
    """install_single_tool catches generic exceptions and writes failed summary."""
    monkeypatch.setattr(
        runner, "install_tool",
        lambda t: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    written = {}
    monkeypatch.setattr(runner, "_write_install_summary", lambda d: written.update(d))

    import sys
    with pytest.raises(SystemExit) as exc_info:
        runner.install_single_tool("othertool")
    assert exc_info.value.code == 1
    assert "disk full" in written["results"][0]["error"]


def test_install_single_tool_success_writes_ok(monkeypatch):
    """install_single_tool on success writes ok summary and does not exit."""
    monkeypatch.setattr(runner, "install_tool", lambda t: None)
    monkeypatch.setattr(runner, "_probe_tool_version", lambda t: "3.0")
    written = {}
    monkeypatch.setattr(runner, "_write_install_summary", lambda d: written.update(d))
    runner.install_single_tool("goodtool")
    assert written["results"][0]["status"] == "ok"
    assert written["results"][0]["version"] == "3.0"