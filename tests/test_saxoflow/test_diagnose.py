"""
Integrated tests for the saxoflow.diagnose Click command group.

This file merges the original smoke tests with extended, branch-covering tests:
- VSCode extension checks (OK / missing / error)
- `summary --export` + VSCode-not-found
- `repair` (missing tools vs none missing)
- `repair-interactive` (none missing / user abort / user selects tools)
- `clean-path` (config missing / no duplicates / duplicates abort / duplicates apply)

All external effects (subprocess, filesystem, env, questionary) are patched.
Tests use CliRunner and are fully hermetic.
"""

from __future__ import annotations

import io
import os
import sys
import subprocess
import types
import pytest
import builtins
import shutil
from pathlib import Path
from typing import List

from click.testing import CliRunner

import saxoflow.diagnose as diag


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_health(required, optional=("vscode", False, None, None, False)):
    """Build a compute_health-compatible tuple for diagnose_tools."""
    req = list(required)
    opt = [("verilator", True, "/usr/bin/verilator", "5.0", True), optional]
    return ("minimal", 50, req, opt)


def _patch_questionary(monkeypatch, chosen: list[str] | None):
    """
    Provide a stub 'questionary' module with checkbox().ask() -> chosen.
    """
    mod = types.SimpleNamespace()
    mod.checkbox = lambda *a, **k: types.SimpleNamespace(ask=lambda: chosen)
    monkeypatch.setitem(__import__("sys").modules, "questionary", mod)


# ---------------------------------------------------------------------------
# Original smoke tests
# ---------------------------------------------------------------------------

def test_diagnose_summary_cli(monkeypatch):
    """diagnose summary prints a health score and missing tool status."""
    # Monkeypatch compute_health and analyze_env
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: (
                "minimal",
                50,
                [
                    ("yosys", True, "/usr/bin/yosys", "0.27", True),
                    ("iverilog", False, None, None, False),
                ],
                [
                    ("verilator", True, "/usr/bin/verilator", "5.0", True),
                    ("vscode", False, None, None, False),
                ],
            ),
            analyze_env=lambda: {"path_duplicates": [], "bins_missing_in_path": []},
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["summary"])
    assert result.exit_code == 0
    out = result.output.lower()
    assert "health score" in out
    assert "50%" in out
    assert "iverilog missing" in out


def test_diagnose_env_cli():
    """diagnose env prints environment variables without errors."""
    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["env"])
    assert result.exit_code == 0
    assert "VIRTUAL_ENV" in result.output


def test_diagnose_help_cli():
    """diagnose help prints support links."""
    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["help"])
    assert result.exit_code == 0
    out = result.output
    assert "Support" in out
    assert "documentation" in out.lower()


# ---------------------------------------------------------------------------
# _check_vscode_extensions unit-level tests
# ---------------------------------------------------------------------------

def test_check_vscode_extensions_ok_missing_error(monkeypatch):
    """
    _check_vscode_extensions returns:
      - (True, []) when all present
      - (False, [missing...]) when some missing
      - (False, []) on subprocess error
    """
    # OK: returns both required extensions
    def _run_ok(*_a, **_k):
        class R:
            stdout = "ms-vscode.cpptools\nmshr-hdl.veriloghdl\n"
            stderr = ""
            returncode = 0
        return R()
    monkeypatch.setattr(diag.subprocess, "run", _run_ok)
    assert diag._check_vscode_extensions("code") == (True, [])

    # Missing one
    def _run_missing(*_a, **_k):
        class R:
            stdout = "ms-vscode.cpptools\n"
            stderr = ""
            returncode = 0
        return R()
    monkeypatch.setattr(diag.subprocess, "run", _run_missing)
    ok, missing = diag._check_vscode_extensions("code")
    assert ok is False and "mshr-hdl.veriloghdl" in missing

    # Error path
    def _run_raises(*_a, **_k):
        raise OSError("boom")
    monkeypatch.setattr(diag.subprocess, "run", _run_raises)
    assert diag._check_vscode_extensions("code") == (False, [])


# ---------------------------------------------------------------------------
# diagnose summary export & VSCode presence branches
# ---------------------------------------------------------------------------

def test_diagnose_summary_export_and_vscode_not_found(monkeypatch, tmp_path):
    """
    diagnose summary --export writes to DIAGNOSE_LOG_FILE and warns when VSCode
    is not in PATH.
    """
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [
                    ("yosys", True, "/usr/bin/yosys", "0.27", True),
                    ("iverilog", False, None, None, False),
                ]
            ),
            analyze_env=lambda: {"path_duplicates": [], "bins_missing_in_path": []},
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )

    # VSCode not found
    monkeypatch.setattr(diag.shutil, "which", lambda _c: None)

    # Redirect export file
    monkeypatch.setattr(diag, "DIAGNOSE_LOG_FILE", tmp_path / "report.txt")

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["summary", "--export"])
    assert result.exit_code == 0
    assert "VSCode not found in PATH" in result.output
    assert (tmp_path / "report.txt").exists()


def test_diagnose_summary_vscode_ok(monkeypatch):
    """diagnose summary prints 'All recommended VSCode extensions installed' when check passes."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [("yosys", True, "/usr/bin/yosys", "0.27", True)]
            ),
            analyze_env=lambda: {"path_duplicates": [], "bins_missing_in_path": []},
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )

    # code present + subprocess returns both extensions
    monkeypatch.setattr(diag.shutil, "which", lambda _c: "/usr/bin/code")

    def _run_ok(*_a, **_k):
        class R:
            stdout = "ms-vscode.cpptools\nmshr-hdl.veriloghdl\n"
            stderr = ""
            returncode = 0
        return R()
    monkeypatch.setattr(diag.subprocess, "run", _run_ok)

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["summary"])
    assert result.exit_code == 0
    assert "All recommended VSCode extensions installed" in result.output


# ---------------------------------------------------------------------------
# diagnose repair (auto)
# ---------------------------------------------------------------------------

def test_diagnose_repair_installs_missing(monkeypatch):
    """diagnose repair invokes runner.install_tool for each missing required tool."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [
                    ("iverilog", False, None, None, False),
                    ("yosys", True, "/usr/bin/yosys", "0.27", True),
                ]
            )
        ),
        raising=True,
    )

    called: List[str] = []
    monkeypatch.setattr(diag.runner, "install_tool", lambda tool: called.append(tool))

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["repair"])
    assert result.exit_code == 0
    assert called == ["iverilog"]


def test_diagnose_repair_no_missing(monkeypatch):
    """diagnose repair prints 'All required tools already installed' when none are missing."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [("iverilog", True, "/usr/bin/iverilog", "12.0", True)]
            )
        ),
        raising=True,
    )

    calls = []
    monkeypatch.setattr(diag.runner, "install_tool", lambda tool: calls.append(tool))

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["repair"])
    assert result.exit_code == 0
    assert calls == []
    assert "All required tools already installed" in result.output


# ---------------------------------------------------------------------------
# diagnose repair-interactive
# ---------------------------------------------------------------------------

def test_diagnose_repair_interactive_none_missing(monkeypatch):
    """repair-interactive early-exits when nothing is missing."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [("yosys", True, "/usr/bin/yosys", "0.27", True)]
            )
        ),
        raising=True,
    )
    _patch_questionary(monkeypatch, chosen=["whatever"])  # should not be used

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["repair-interactive"])
    assert result.exit_code == 0
    assert "already installed" in result.output


def test_diagnose_repair_interactive_user_aborts(monkeypatch):
    """repair-interactive prints 'No tools selected' when user selects none."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [("iverilog", False, None, None, False)]
            )
        ),
        raising=True,
    )
    _patch_questionary(monkeypatch, chosen=[])  # user selects nothing

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["repair-interactive"])
    assert result.exit_code == 0
    assert "No tools selected" in result.output


def test_diagnose_repair_interactive_installs_selection(monkeypatch):
    """repair-interactive installs exactly the selected tools."""
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: _mock_health(
                [
                    ("iverilog", False, None, None, False),
                    ("yosys", False, None, None, False),
                ]
            )
        ),
        raising=True,
    )
    _patch_questionary(monkeypatch, chosen=["iverilog"])

    installed: List[str] = []
    monkeypatch.setattr(diag.runner, "install_tool", lambda tool: installed.append(tool))

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["repair-interactive"])
    assert result.exit_code == 0
    assert installed == ["iverilog"]


# ---------------------------------------------------------------------------
# diagnose clean-path
# ---------------------------------------------------------------------------

def test_diagnose_clean_path_config_missing(monkeypatch, tmp_path):
    """clean-path warns if ~/.bashrc does not exist."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["clean-path", "--shell", "bash"])
    assert result.exit_code == 0
    assert "Shell config not found" in result.output


def test_diagnose_clean_path_no_duplicates(monkeypatch, tmp_path):
    """clean-path prints 'PATH is clean' if no duplicate PATH entries are found."""
    monkeypatch.setenv("PATH", "/usr/bin:/bin:/sbin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc = tmp_path / ".bashrc"
    rc.write_text("# sample\nexport PATH=/usr/bin:$PATH\n")

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["clean-path", "--shell", "bash"])
    assert result.exit_code == 0
    assert "No duplicate PATH entries detected" in result.output


def test_diagnose_clean_path_with_duplicates_abort(monkeypatch, tmp_path):
    """
    clean-path shows preview and aborts when user declines;
    backup is created and file remains unchanged.
    """
    monkeypatch.setenv("PATH", "/a:/b:/b:/c:/a")  # duplicates: /b and /a
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc = tmp_path / ".bashrc"
    original = "# sample\nexport PATH=/x:$PATH\nexport PATH=/y:$PATH\n"
    rc.write_text(original)

    # Decline confirmation
    monkeypatch.setattr(diag.click, "confirm", lambda *a, **k: False)

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["clean-path", "--shell", "bash"])
    assert result.exit_code == 0
    assert (tmp_path / ".bashrc.bak").exists()
    assert rc.read_text() == original
    assert "Aborted. No changes made" in result.output


def test_diagnose_clean_path_with_duplicates_apply(monkeypatch, tmp_path):
    """
    clean-path writes a cleaned file (keeps only the last export PATH line)
    when user confirms.
    """
    monkeypatch.setenv("PATH", "/a:/b:/b:/c:/a")  # duplicates present
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc = tmp_path / ".bashrc"
    rc.write_text(
        "# hdr\n"
        "export PATH=/first:$PATH\n"
        "echo keepme\n"
        "export PATH=/second:$PATH\n"  # only this one should remain
    )

    # Accept confirmation
    monkeypatch.setattr(diag.click, "confirm", lambda *a, **k: True)

    runner = CliRunner()
    result = runner.invoke(diag.diagnose, ["clean-path", "--shell", "bash"])
    assert result.exit_code == 0
    cleaned = rc.read_text()
    assert "export PATH=/second:$PATH" in cleaned
    assert "export PATH=/first:$PATH" not in cleaned
    assert (tmp_path / ".bashrc.bak").exists()
    assert "Clean complete!" in result.output


def test_summary_covers_env_import_pyver_and_tool_branches(monkeypatch):
    # Force "virtualenv NOT active"
    monkeypatch.setattr(diag, "VENV_ACTIVE", False, raising=True)

    # Make "import saxoflow" fail inside summary()
    real_import = __import__
    def fake_import(name, *a, **k):
        if name == "saxoflow" and k.get("level", 0) == 0:
            raise ImportError("blocked")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", fake_import, raising=True)

    # Force "old" Python branch
    monkeypatch.setattr(diag.sys, "version", "3.7.9 (custom)")

    # Required tools variations:
    #  - tA: present, NOT in PATH
    #  - tB: present, up-to-date
    #  - tC: present, parse_version(version) raises -> not outdated
    #  - tD: present, outdated
    monkeypatch.setattr(diag, "MIN_TOOL_VERSIONS", {
        "tB": "5.0",
        "tC": "1.0",
        "tD": "1.0",
    }, raising=True)

    real_parse = diag.parse_version
    def pv(s):
        if str(s) == "badver":
            raise ValueError("boom")  # hit except: outdated=False
        return real_parse(str(s))
    monkeypatch.setattr(diag, "parse_version", pv, raising=True)

    req = [
        ("tA", True, "/opt/tA/bin/tA", "1.0", False),
        ("tB", True, "/usr/bin/tB", "5.0", True),
        ("tC", True, "/usr/bin/tC", "badver", True),
        ("tD", True, "/usr/bin/tD", "0.5", True),
    ]
    opt = [
        ("opt1", True, "/opt/opt1", "1.0", False),  # optional not-in-PATH branch
    ]

    env_info = {
        "path_duplicates": [("/dupTools", ["yosys"]), ("/dupNoTools", [])],
        "bins_missing_in_path": [("/tb_with_tool", "tbin"), ("/tb_no_tool", None)],
    }

    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 50, req, opt),
            analyze_env=lambda: env_info,
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )

    # VSCode present but the check errors -> "Could not check VSCode extensions"
    monkeypatch.setattr(diag.shutil, "which", lambda _c: "/usr/bin/code")
    def run_raises(*_a, **_k):  # _check_vscode_extensions catches this
        raise OSError("fail")
    monkeypatch.setattr(diag.subprocess, "run", run_raises)

    out = CliRunner().invoke(diag.diagnose, ["summary"]).output

    assert "Virtualenv NOT active" in out
    assert "Cannot import SaxoFlow Python package" in out
    assert "SaxoFlow recommends Python 3.8+" in out

    # Required tools formatting changed to "tool: path - version"
    assert "tA found at /opt/tA/bin/tA but not in PATH" in out
    assert "tB: /usr/bin/tB - 5.0" in out   # updated formatting (hyphen, not em dash)
    assert "(version too old, minimum 1.0)" in out  # tD outdated

    # Optional not-in-PATH message still present
    assert "opt1 found at /opt/opt1 but not in PATH" in out

    # VSCode extensions unknown branch
    assert "Could not check VSCode extensions" in out

    # PATH duplicate messages (with & without tool listing)
    assert "Duplicate in PATH: /dupTools (used by ['yosys'])" in out
    assert "Duplicate in PATH: /dupNoTools" in out

    # The extra tips block after any duplicates:
    assert "To auto-clean all duplicates (advanced)" in out

    # Bins missing (tool present vs None)
    assert "Tool bin not in PATH: /tb_with_tool (tbin)" in out
    assert "Tool bin not in PATH: /tb_no_tool" in out



def test_summary_export_file_write_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 100, [], []),
            analyze_env=lambda: {"path_duplicates": [], "bins_missing_in_path": []},
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )
    monkeypatch.setattr(diag.shutil, "which", lambda _c: None)
    monkeypatch.setattr(diag, "DIAGNOSE_LOG_FILE", tmp_path / "report.txt")
    # Make open() for writing fail
    def open_raises(*_a, **_k):
        raise OSError("nope")
    monkeypatch.setattr(builtins, "open", open_raises, raising=True)

    out = CliRunner().invoke(diag.diagnose, ["summary", "--export"]).output
    assert "Failed to write report file" in out


def test_summary_no_issues_detected_branch(monkeypatch):
    req = [("yosys", True, "/usr/bin/yosys", "0.27", True)]
    opt = [("verilator", True, "/usr/bin/verilator", "5.0", True)]
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 100, req, opt),
            analyze_env=lambda: {"path_duplicates": [], "bins_missing_in_path": []},
            pro_diagnostics=lambda: {"health": {"formal": {}}, "env": {}, "tips": []},
        ),
        raising=True,
    )
    monkeypatch.setattr(diag.shutil, "which", lambda _c: None)

    out = CliRunner().invoke(diag.diagnose, ["summary"]).output
    assert "No major issues detected. You're good to go!" in out


def test_repair_calledprocesserror_logs_failure(monkeypatch):
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 50, [("iverilog", False, None, None, False)], [])
        ),
        raising=True,
    )
    def boom(_tool):
        raise subprocess.CalledProcessError(1, "cmd")
    monkeypatch.setattr(diag.runner, "install_tool", boom, raising=True)

    out = CliRunner().invoke(diag.diagnose, ["repair"]).output
    assert "failed to install" in out
    assert "diagnose export" in out  # tip line


def test_repair_interactive_calledprocesserror_logs_failure(monkeypatch):
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 50, [("iverilog", False, None, None, False)], [])
        ),
        raising=True,
    )
    # Simulate user selecting 'iverilog'
    mod = types.SimpleNamespace()
    mod.checkbox = lambda *a, **k: types.SimpleNamespace(ask=lambda: ["iverilog"])
    monkeypatch.setitem(sys.modules, "questionary", mod)

    def boom(_tool):
        raise subprocess.CalledProcessError(1, "cmd")
    monkeypatch.setattr(diag.runner, "install_tool", boom, raising=True)

    out = CliRunner().invoke(diag.diagnose, ["repair-interactive"]).output
    assert "failed to install" in out
    assert "diagnose export" in out


def test_clean_path_backup_copy_failure(monkeypatch, tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("export PATH=/x:$PATH\n")
    monkeypatch.setenv("PATH", "/a:/b:/a")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Ensure the function imports *this* fake shutil
    fake_shutil = types.SimpleNamespace(copy=lambda *_: (_ for _ in ()).throw(OSError("copy fail")))
    monkeypatch.setitem(sys.modules, "shutil", fake_shutil)

    out = CliRunner().invoke(diag.diagnose, ["clean-path", "--shell", "bash"]).output
    assert "Failed to create backup" in out


def test_clean_path_read_failure(monkeypatch, tmp_path):
    rc = tmp_path / ".bashrc"
    rc.write_text("export PATH=/x:$PATH\n")
    monkeypatch.setenv("PATH", "/a:/b:/a")  # ensure duplicates so we reach the read stage
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    # Bypass backup so we don't trigger file reads there
    monkeypatch.setattr(shutil, "copy", lambda *a, **k: None)

    # Fail only the read of the config during parsing
    real_open = builtins.open
    def open_failing(path, mode="r", **kw):
        if "r" in mode:
            raise OSError("read fail")
        return real_open(path, mode, **kw)

    monkeypatch.setattr(builtins, "open", open_failing, raising=True)

    out = CliRunner().invoke(diag.diagnose, ["clean-path", "--shell", "bash"]).output
    assert "Failed to read" in out


def test_clean_path_write_failure(monkeypatch, tmp_path):
    # Duplicate PATH so we go through full flow
    monkeypatch.setenv("PATH", "/a:/b:/b:/a")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    rc = tmp_path / ".bashrc"
    rc.write_text("export PATH=/x:$PATH\nexport PATH=/y:$PATH\n")

    # Auto-confirm to reach the write branch
    monkeypatch.setattr(diag.click, "confirm", lambda *a, **k: True)

    # Bypass backup so it doesn't use open() in that step
    monkeypatch.setattr(shutil, "copy", lambda *a, **k: None)

    # Let reads succeed but make the write fail
    real_open = builtins.open
    def open_rw(path, mode="r", **kw):
        if "w" in mode:
            raise OSError("write fail")
        return real_open(path, mode, **kw)

    monkeypatch.setattr(builtins, "open", open_rw, raising=True)

    out = CliRunner().invoke(diag.diagnose, ["clean-path", "--shell", "bash"]).output
    assert "Failed to write" in out


def test_summary_bins_missing_prints_tool_description(monkeypatch):
    """
    Covers: if desc: log_tip(f"{tool}: {desc}")
    by ensuring TOOL_DESCRIPTIONS has an entry for the missing-bin tool.
    """
    # Health doesn't matter for this branch; keep it simple.
    monkeypatch.setattr(
        diag,
        "diagnose_tools",
        types.SimpleNamespace(
            compute_health=lambda: ("minimal", 100, [], []),
            analyze_env=lambda: {
                "path_duplicates": [],
                "bins_missing_in_path": [("/fake/tool/bin", "tbin")],
            },
        ),
        raising=True,
    )

    # Ensure VSCode branch doesn't interfere
    monkeypatch.setattr(diag.shutil, "which", lambda _c: None, raising=True)

    # Provide a description so the 'if desc:' path is taken
    monkeypatch.setattr(
        diag,
        "TOOL_DESCRIPTIONS",
        {"tbin": "Helpful tool description"},
        raising=True,
    )

    out = CliRunner().invoke(diag.diagnose, ["summary"]).output
    # The warning about the missing bin
    assert "Tool bin not in PATH: /fake/tool/bin (tbin)" in out
    # The follow-up tip that prints the description (the uncovered line)
    assert "tbin: Helpful tool description" in out


def test_clean_path_lists_removed_export_lines_and_shows_preview(monkeypatch, tmp_path):
    """
    Covers the branch:
        if export_path_lines:
            cleaned_lines.append(export_path_lines[-1])
            click.secho("The following duplicate export PATH lines will be removed:", ...)
            for line in export_path_lines[:-1]: click.echo(...)
    and the preview banner that immediately follows.
    """
    # Ensure duplicates so the command proceeds past early exit
    monkeypatch.setenv("PATH", "/a:/b:/b:/a")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    rc = tmp_path / ".bashrc"
    rc.write_text(
        "# header\n"
        "export PATH=/first:$PATH\n"
        "# commented export PATH=should_not_be_picked\n"
        "export PATH=/second:$PATH\n"
        "export PATH=/third:$PATH\n"  # this is the one that should be kept
    )

    # Decline confirmation so no file write is attempted
    monkeypatch.setattr(diag.click, "confirm", lambda *a, **k: False)

    out = CliRunner().invoke(diag.diagnose, ["clean-path", "--shell", "bash"]).output

    # The notice about duplicate export PATH lines to be removed
    assert "The following duplicate export PATH lines will be removed:" in out
    # It should list the first two export lines (keep only the last one)
    assert "  export PATH=/first:$PATH" in out
    assert "  export PATH=/second:$PATH" in out
    # And it should always show the preview banner right after that block
    assert "--- Cleaned config preview ---" in out
    # Sanity: the kept (last) export line appears in the preview text
    assert "export PATH=/third:$PATH" in out
    # We declined the confirmation
    assert "Aborted. No changes made" in out
