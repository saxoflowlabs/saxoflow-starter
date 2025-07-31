"""
Unit tests for saxoflow.diagnose_tools.

These tests exercise the helper functions that underpin the `saxoflow diagnose`
command group.  Since these helpers touch the operating system and may search
for binaries on the real PATH, many tests monkeypatch or simulate the
environment to ensure deterministic behaviour.  When functions execute
subprocesses (for version detection) the tests substitute simple scripts to
avoid invoking real EDA tools.
"""

import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import saxoflow.diagnose_tools as dt


def test_infer_flow():
    """infer_flow should detect profile based on installed tools."""
    assert dt.infer_flow(["nextpnr"]) == "fpga"
    assert dt.infer_flow(["openroad", "magic"]) == "asic"
    assert dt.infer_flow(["symbiyosys"]) == "formal"
    # Anything else defaults to minimal
    assert dt.infer_flow(["iverilog"]) == "minimal"


def test_find_tool_binary_none(tmp_path):
    """find_tool_binary returns (None, False, None) when binary not found."""
    # Use a bogus tool name unlikely to exist
    path, in_path, variant = dt.find_tool_binary("nonexistent_tool")
    assert path is None and in_path is False and variant is None


def test_extract_version_generic(tmp_path):
    """extract_version should parse a simple version string from a fake binary output."""
    # Create a dummy script that prints version information
    dummy = tmp_path / "dummy_tool"
    dummy.write_text("#!/bin/sh\necho 'dummy tool version 1.2.3'\n")
    dummy.chmod(dummy.stat().st_mode | stat.S_IXUSR)

    # monkeypatch subprocess.run to call our script instead of real tool
    with mock.patch("subprocess.run") as mrun:
        class Result:
            def __init__(self, stdout="", stderr=""):
                self.stdout = stdout
                self.stderr = stderr
        mrun.return_value = Result(stdout="dummy tool version 1.2.3\n", stderr="")
        version = dt.extract_version("dummy_tool", str(dummy))
        assert version == "1.2.3"


def test_analyze_env_detects_duplicates(monkeypatch):
    """analyze_env detects duplicate PATH entries and tools missing from PATH."""
    # Create a fake environment with duplicates
    fake_home = tempfile.gettempdir()
    dup_path = "/usr/local/bin"
    path = f"{dup_path}:{dup_path}:/bin"
    monkeypatch.setenv("PATH", path)
    # Provide fake user directories containing tool bin directories to trigger bins_missing_in_path
    # Simulate one of the tool directories existing in home
    for tool in dt.ALL_TOOLS[:2]:
        tdir = Path(fake_home) / ".local" / tool / "bin"
        tdir.mkdir(parents=True, exist_ok=True)
    env_info = dt.analyze_env()
    # There should be one duplicate entry and at least two bins missing in PATH
    assert env_info["path_duplicates"], "Expected at least one duplicate PATH entry"
    assert env_info["bins_missing_in_path"], "Expected some tool bins missing from PATH"


def test_detect_wsl(monkeypatch):
    """detect_wsl should return a boolean without throwing."""
    # Simulate WSL by patching platform.uname().release
    with mock.patch("platform.uname") as muname:
        class U:
            release = "5.4.72-microsoft-standard-WSL2"
        muname.return_value = U
        assert dt.detect_wsl() is True
    # Now simulate non-WSL
    with mock.patch("platform.uname") as muname:
        class U2:
            release = "linux"
        muname.return_value = U2
        assert dt.detect_wsl() is False


def test_analyze_path(monkeypatch):
    """analyze_path returns counts of PATH entries and flags Windows paths/local bin."""
    monkeypatch.setenv("PATH", "/mnt/c/Windows/System32:/usr/bin:" + str(Path.home() / ".local/bin"))
    result = dt.analyze_path()
    assert result["total_entries"] >= 3
    assert result["windows_entries"], "Should detect at least one Windows path"
    assert result["local_bin_present"] is True


def test_is_no_action_feedback(monkeypatch):
    """is_no_action_feedback returns True for various synonyms of no issues."""
    # Typical patterns
    assert dt.pro_diagnostics  # ensure function imported (not executed here)
    from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator
    assert AgentFeedbackCoordinator.is_no_action_feedback("No major issues found")
    assert AgentFeedbackCoordinator.is_no_action_feedback("looks good")
    assert AgentFeedbackCoordinator.is_no_action_feedback("Naming: None\nLogic: None")
    assert not AgentFeedbackCoordinator.is_no_action_feedback("Syntax Issues: something broken")