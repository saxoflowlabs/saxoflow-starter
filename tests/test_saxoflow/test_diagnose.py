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
import types
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
