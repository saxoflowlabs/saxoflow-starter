# saxoflow/diagnose.py
"""
SaxoFlow Diagnose CLI.

This module defines the `diagnose` Click command group and related subcommands
used to assess and repair the user's environment.

Features
--------
- Summary scan (`saxoflow diagnose summary`) with flow-aware tool checks,
  PATH analysis, VS Code extension hints, and optional export to a log file.
- Environment dump (`saxoflow diagnose env`) with key runtime facts.
- Auto-repair (`saxoflow diagnose repair`) to install missing required tools.
- Interactive repair (`saxoflow diagnose repair-interactive`) to pick tools.
- PATH cleaner (`saxoflow diagnose clean-path`) to remove duplicate PATH lines.
- Help (`saxoflow diagnose help`) with support pointers.

Design goals
------------
- Preserve the existing CLI command names and output behavior for used parts.
- Provide clear docstrings, type hints, and small, testable helpers.
- Add defensive error handling (file IO, subprocess timeouts, missing files).
- Keep printing UX (colors) and behavior stable (no emojis).
"""

from __future__ import annotations

import datetime
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

import click
from packaging.version import parse as parse_version

from saxoflow.installer import runner
from saxoflow.tools.definitions import MIN_TOOL_VERSIONS, TOOL_DESCRIPTIONS
from saxoflow import diagnose_tools  # env health & path analysis utilities

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ACTIVE = os.getenv("VIRTUAL_ENV") is not None  # kept for status output
DIAGNOSE_LOG_FILE = PROJECT_ROOT / "saxoflow_diagnose_report.txt"

__all__ = [
    "diagnose",
    "diagnose_summary",
    "diagnose_env",
    "diagnose_repair",
    "diagnose_repair_interactive",
    "diagnose_clean_path",
    "diagnose_help",
]

# ---------------------------------------------------------------------------
# CLI Group
# ---------------------------------------------------------------------------


@click.group()
def diagnose() -> None:
    """SaxoFlow Pro diagnose — System Diagnosis & Repair."""
    # No-op: group container for subcommands
    return


# ---------------------------------------------------------------------------
# Logging helpers (colors only; no emojis)
# ---------------------------------------------------------------------------


def log_ok(msg: str) -> None:
    """Print a green SUCCESS message."""
    click.secho(f"SUCCESS: {msg}", fg="green")


def log_warn(msg: str) -> None:
    """Print a yellow WARNING message."""
    click.secho(f"WARNING: {msg}", fg="yellow")


def log_fail(msg: str) -> None:
    """Print a red ERROR message."""
    click.secho(f"ERROR: {msg}", fg="red")


def log_tip(msg: str) -> None:
    """Print a cyan TIP message."""
    click.secho(f"TIP: {msg}", fg="cyan")


# ---------------------------------------------------------------------------
# VS Code helper
# ---------------------------------------------------------------------------


def _check_vscode_extensions(code_path: str) -> Tuple[bool, List[str]]:
    """Check for recommended VS Code extensions.

    Parameters
    ----------
    code_path
        Path to the VS Code `code` executable (assumed to be in PATH).

    Returns
    -------
    (ok, missing)
        ok
            True if all recommended extensions are present, False otherwise.
        missing
            List of missing extension identifiers (empty if none).
    """
    # Keep original behavior: silent failure -> unknown result.
    try:
        result = subprocess.run(
            [code_path, "--list-extensions"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
        exts = set(result.stdout.split())
        required_exts = {"ms-vscode.cpptools", "mshr-hdl.veriloghdl"}
        missing = sorted([ext for ext in required_exts if ext not in exts])
        return (len(missing) == 0), missing
    except Exception:
        return False, []  # unknown


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


@diagnose.command("summary")
@click.option(
    "--export",
    is_flag=True,
    help="Export report to a file for support or bug reports.",
)
def diagnose_summary(export: bool) -> None:
    """Run full diagnostic health scan with dynamic analysis."""
    report_lines: List[str] = []

    click.secho("INFO: SaxoFlow diagnose v4.x - Full Health Report", fg="cyan")
    click.echo()
    report_lines.append(f"diagnose run at {datetime.datetime.now()}")
    report_lines.append(f"Platform: {platform.platform()} ({platform.machine()})\n")

    # Environment info
    if VENV_ACTIVE:
        log_ok("Virtualenv detected")
        report_lines.append("Virtualenv: ACTIVE")
    else:
        log_warn("Virtualenv NOT active")
        log_tip("Activate your virtualenv with: source .venv/bin/activate")
        report_lines.append("Virtualenv: NOT active")

    try:
        import saxoflow  # noqa: F401  # import check only
        log_ok("SaxoFlow Python package import OK")
        report_lines.append("SaxoFlow Python import: OK")
    except ImportError:
        log_fail("Cannot import SaxoFlow Python package")
        report_lines.append("SaxoFlow Python import: FAIL")

    # Tool checks
    flow, score, required, optional = diagnose_tools.compute_health()
    click.echo(f"\nFlow Profile: {flow.upper()}")
    click.echo(f"Health Score: {score}%\n")

    # Check Python version (keep existing threshold for compatibility)
    py_version = sys.version.split()[0]
    min_py_version = "3.8"  # TODO: Align with official 3.9+ policy after audit.
    if parse_version(py_version) < parse_version(min_py_version):
        log_warn(
            "Python "
            f"{py_version} found. SaxoFlow recommends Python {min_py_version}+."
            " Upgrade if possible."
        )
        report_lines.append(f"Python version: {py_version} (OLD)")
    else:
        log_ok(f"Python {py_version} detected.")
        report_lines.append(f"Python version: {py_version}")

    # Required tools
    click.secho("\nRequired Tools:", fg="cyan")
    report_lines.append("\nRequired tools:")
    for tool, ok, path, version, in_path in required:
        min_version = MIN_TOOL_VERSIONS.get(tool)
        if ok:
            outdated = False
            if min_version and version and version not in ("(unknown)", None):
                try:
                    if parse_version(str(version)) < parse_version(min_version):
                        outdated = True
                except Exception:
                    # Best-effort only; if parse fails, treat as not outdated.
                    outdated = False

            msg = f"{tool}: {path} - {version}"
            if not in_path:
                log_warn(f"{tool} found at {path} but not in PATH")
                log_tip(
                    'Add to PATH in your .bashrc: export PATH="'
                    f'{os.path.dirname(path)}:$PATH"'
                )
                report_lines.append(f"  FOUND_NOT_IN_PATH: {msg}")
            elif not outdated:
                log_ok(msg)
                report_lines.append("  OK: " + msg)
            else:
                log_warn(f"{msg} (version too old, minimum {min_version})")
                log_tip(f"Run: saxoflow install {tool} to upgrade.")
                report_lines.append(f"  WARN: {msg} (OUTDATED; needs {min_version}+)")

        else:
            log_fail(f"{tool} missing")
            log_tip(f"Run: saxoflow install {tool}")
            report_lines.append(f"  MISSING: {tool}: (not found) - (no version)")

    # Optional tools
    click.secho("\nOptional Tools:", fg="cyan")
    report_lines.append("\nOptional tools:")
    for tool, ok, path, version, in_path in optional:
        if ok:
            msg = f"{tool}: {path} - {version}"
            if not in_path:
                log_warn(f"{tool} found at {path} but not in PATH")
                log_tip(
                    'Add to PATH in your .bashrc: export PATH="'
                    f'{os.path.dirname(path)}:$PATH"'
                )
                report_lines.append(f"  FOUND_NOT_IN_PATH: {msg}")
            else:
                log_ok(msg)
                report_lines.append("  OK: " + msg)
        else:
            log_warn(f"{tool} not installed")
            log_tip(f"You can install with: saxoflow install {tool}")
            report_lines.append(
                f"  NOT INSTALLED: {tool}: (not found) - (no version)"
            )

    # VS Code extension check
    code_path = shutil.which("code")
    if code_path:
        ok, missing = _check_vscode_extensions(code_path)
        if ok:
            log_ok("All recommended VSCode extensions installed")
            report_lines.append("VSCode extensions: OK")
        elif missing:
            log_warn(
                "VSCode missing recommended extensions: "
                + ", ".join(missing)
            )
            for ext in missing:
                log_tip(f"Run: code --install-extension {ext}")
            report_lines.append("VSCode extensions: MISSING - " + ", ".join(missing))
        else:
            log_warn("Could not check VSCode extensions")
            report_lines.append("VSCode extensions: Unknown (code check failed)")
    else:
        log_warn("VSCode not found in PATH")
        log_tip(
            "To enable integrated IDE features, install VSCode from "
            "https://code.visualstudio.com/"
        )
        report_lines.append("VSCode: Not installed")

    # Path diagnostics — User-friendly Reporting
    click.echo()
    report_lines.append("\nPATH checks:")
    env_info = diagnose_tools.analyze_env()

    # 1) Duplicates
    for dup_path, tools in env_info["path_duplicates"]:
        if tools:
            log_warn(f"Duplicate in PATH: {dup_path} (used by {tools})")
            log_tip(
                "This is a bin directory for "
                f"{tools}. Having duplicates can slow down shell startup "
                "or confuse which binary runs."
            )
        else:
            log_warn(f"Duplicate in PATH: {dup_path}")
            log_tip(
                "Having duplicate PATH entries can slow down shell startup "
                "or confuse which binary runs."
            )
        log_tip("Remove duplicate PATH entries in your ~/.bashrc or ~/.profile.")
        if tools:
            report_lines.append(f"Duplicate in PATH: {dup_path} (tool: {tools})")
        else:
            report_lines.append(f"Duplicate in PATH: {dup_path}")

    if env_info["path_duplicates"]:
        log_tip(
            "Duplicate PATH entries usually happen if you install the same "
            "tool multiple times, add the same export line in .bashrc/.zshrc "
            "more than once, or if automated scripts add redundant paths."
        )
        log_tip("To professionally clean up your PATH, run: saxoflow diagnose clean-path")
        log_tip(
            r"To auto-clean all duplicates (advanced): "
            r"export PATH=$(echo $PATH | tr ':' '\n' | awk '!x[$0]++' | paste -sd:)"
        )
        report_lines.append("PATH has duplicates. See above for cleanup instructions.")

    # 2) Tool bins missing from PATH (with tool name & desc)
    for tb, tool in env_info["bins_missing_in_path"]:
        if tool:
            log_warn(f"Tool bin not in PATH: {tb} ({tool})")
            log_tip(f'Add to PATH in your .bashrc: export PATH="{tb}:$PATH"')
            desc = TOOL_DESCRIPTIONS.get(tool, "")
            if desc:
                log_tip(f"{tool}: {desc}")
            report_lines.append(f"Tool bin not in PATH: {tb} ({tool})")
        else:
            log_warn(f"Tool bin not in PATH: {tb}")
            log_tip(f'Add to PATH in your .bashrc: export PATH="{tb}:$PATH"')
            report_lines.append(f"Tool bin not in PATH: {tb}")

    click.secho(
        "\nINFO: For full troubleshooting see documentation or run with --export to "
        "create a log for support.",
        fg="cyan",
    )

    if score < 100:
        log_tip(
            "Run `saxoflow diagnose repair` to auto-install missing tools, or "
            "`saxoflow diagnose repair-interactive` for selective repair."
        )

    # Optional export
    if export:
        try:
            with open(DIAGNOSE_LOG_FILE, "w", encoding="utf-8") as f:
                for line in report_lines:
                    f.write(line + "\n")
            log_ok(f"diagnose report written to: {DIAGNOSE_LOG_FILE}")
        except OSError as exc:
            log_fail(f"Failed to write report file: {exc}")

    # Summary footer if actionable issues found
    issues = 0
    for _, ok_req, _, _, in_path_req in required:
        if not ok_req or not in_path_req:
            issues += 1
    for _, ok_opt, _, _, in_path_opt in optional:
        if not ok_opt or not in_path_opt:
            issues += 1
    issues += len(env_info["path_duplicates"])
    issues += len(env_info["bins_missing_in_path"])

    if issues:
        click.secho(
            f"\nINFO: SaxoFlow diagnose found {issues} actionable issue(s). "
            "See above for recommendations.\n",
            fg="cyan",
        )
    else:
        click.secho("\nSUCCESS: No major issues detected. You're good to go!\n", fg="green")


# ---------------------------------------------------------------------------
# Environment Info
# ---------------------------------------------------------------------------


@diagnose.command("env")
def diagnose_env() -> None:
    """Print system environment info."""
    click.secho("\nEnvironment Diagnostics:", fg="cyan")
    click.secho(f"VIRTUAL_ENV: {os.getenv('VIRTUAL_ENV')}", fg="cyan")
    click.secho(f"PATH: {os.getenv('PATH')}", fg="cyan")
    click.secho(f"Project Root: {PROJECT_ROOT}", fg="cyan")
    # Use platform.uname for wider compatibility.
    running_wsl = "Yes" if diagnose_tools.detect_wsl() else "No"
    click.secho(f"Running on WSL: {running_wsl}", fg="cyan")
    click.secho(f"Python Executable: {sys.executable}", fg="cyan")
    click.secho(f"Python Version: {platform.python_version()}", fg="cyan")
    click.secho(f"Platform: {platform.platform()}", fg="cyan")


# ---------------------------------------------------------------------------
# Repair Mode (full auto)
# ---------------------------------------------------------------------------


@diagnose.command("repair")
def diagnose_repair() -> None:
    """Auto-install all missing required tools."""
    click.secho("\nINFO: Auto-Repair Starting...", fg="cyan")

    flow, score, required, _optional = diagnose_tools.compute_health()
    repaired = False

    for tool, ok, _, _, _ in required:
        if not ok:
            click.secho(f"Installing: {tool}", fg="cyan")
            try:
                runner.install_tool(tool)
                log_ok(f"{tool} installed")
                repaired = True
            except subprocess.CalledProcessError:
                log_fail(f"{tool} failed to install")
                log_tip("See logs above or run `saxoflow diagnose export` for help.")

    if not repaired:
        log_ok("All required tools already installed.")


# ---------------------------------------------------------------------------
# Interactive Repair Mode (choose tools)
# ---------------------------------------------------------------------------


@diagnose.command("repair-interactive")
def diagnose_repair_interactive() -> None:
    """Interactively choose which missing tools to install."""
    import questionary  # local import to keep CLI startup light

    flow, score, required, _optional = diagnose_tools.compute_health()
    missing_tools = [tool for tool, ok, _, _, _ in required if not ok]
    if not missing_tools:
        log_ok("All required tools already installed.")
        return

    chosen = questionary.checkbox(
        "Select tools to repair/install:", choices=missing_tools
    ).ask()
    if not chosen:
        log_warn("No tools selected. No action taken.")
        return

    for tool in chosen:
        click.secho(f"Installing: {tool}", fg="cyan")
        try:
            runner.install_tool(tool)
            log_ok(f"{tool} installed")
        except subprocess.CalledProcessError:
            log_fail(f"{tool} failed to install")
            log_tip("See logs above or run `saxoflow diagnose export` for help.")


# ---------------------------------------------------------------------------
# Professional PATH Clean Command
# ---------------------------------------------------------------------------


@diagnose.command("clean-path")
@click.option(
    "--shell",
    default="bash",
    type=click.Choice(["bash", "zsh"], case_sensitive=False),
    help="Shell config file to clean: bash (.bashrc) or zsh (.zshrc).",
)
def diagnose_clean_path(shell: str) -> None:
    """
    Interactively clean duplicate PATH entries from your shell config
    file (with backup & full transparency).

    - This command only edits ~/.bashrc or ~/.zshrc if you agree.
    - It will show you exactly what changes will be made.
    - Always makes a backup as ~/.bashrc.bak or ~/.zshrc.bak before editing.
    """
    import shutil as pyshutil  # local alias to avoid name clash in this scope

    home = str(Path.home())
    config_file = f"{home}/.bashrc" if shell.lower() == "bash" else f"{home}/.zshrc"

    if not Path(config_file).exists():
        log_warn(f"Shell config not found: {config_file}")
        log_tip("Nothing to do. Create the file first if you want to manage PATH there.")
        return

    click.secho("\nINFO: Scanning your PATH for duplicates as seen by this shell...", fg="cyan")
    path = os.environ.get("PATH", "")
    paths = path.split(":")
    seen: set = set()
    duplicates: List[str] = []
    for p in paths:
        if p in seen:
            duplicates.append(p)
        seen.add(p)

    if not duplicates:
        click.secho("SUCCESS: No duplicate PATH entries detected! Your PATH is clean.", fg="green")
        return

    click.secho(f"\nWARNING: Found {len(duplicates)} duplicate PATH entries:", fg="yellow")
    for p in duplicates:
        click.secho(f"  {p}", fg="cyan")

    click.secho(
        "TIP: Duplicates happen if you install the same tool multiple times, add the same "
        "export line in .bashrc/.zshrc more than once, or if automated scripts add "
        "redundant paths.",
        fg="cyan",
    )

    click.secho(f"\nWe'll attempt to clean up duplicates in {config_file}.", fg="cyan")
    backup = f"{config_file}.bak"
    try:
        pyshutil.copy(config_file, backup)
        click.secho(f"Backup created: {backup}", fg="cyan")
    except OSError as exc:
        log_fail(f"Failed to create backup: {exc}")
        return

    # Parse and de-duplicate export PATH lines only
    cleaned_lines: List[str] = []
    export_path_lines: List[str] = []
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError as exc:
        log_fail(f"Failed to read {config_file}: {exc}")
        return

    for line in lines:
        if "export PATH=" in line and not line.strip().startswith("#"):
            export_path_lines.append(line)
        else:
            cleaned_lines.append(line)

    # Only keep one unique export PATH=... line (or none, if none exist)
    if export_path_lines:
        cleaned_lines.append(export_path_lines[-1])  # Keep only the last occurrence
        click.secho(
            "\nThe following duplicate export PATH lines will be removed:",
            fg="yellow",
        )
        for line in export_path_lines[:-1]:
            click.secho(f"  {line.strip()}", fg="cyan")

    # Show preview
    click.secho("\n--- Cleaned config preview ---", fg="cyan")
    preview = "".join(cleaned_lines[-10:]) if len(cleaned_lines) > 10 else "".join(cleaned_lines)
    click.secho(preview + "\n--- End Preview ---", fg="cyan")

    if not click.confirm(
        "Proceed to update your config file (remove above redundant export PATH lines)?",
        default=False,
    ):
        click.secho("ERROR: Aborted. No changes made. You may clean manually if you wish.", fg="red")
        return

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            f.writelines(cleaned_lines)
    except OSError as exc:
        log_fail(f"Failed to write {config_file}: {exc}")
        return

    click.secho(
        "SUCCESS: Clean complete! Your shell config was updated. Open a new terminal for changes to take effect.",
        fg="green",
    )
    click.secho(
        "If you have custom tool setups, verify manually that all needed paths are still present.",
        fg="cyan",
    )


# ---------------------------------------------------------------------------
# Help & Support
# ---------------------------------------------------------------------------


@diagnose.command("help")
def diagnose_help() -> None:
    """Show support options and links."""
    click.secho("SaxoFlow Support", fg="cyan")
    click.secho("If you need help, please:", fg="cyan")
    click.secho(
        "  - Visit the documentation: https://github.com/saxoflowlabs/saxoflow-starter/wiki",
        fg="cyan",
    )
    click.secho(
        "  - Open an issue on GitHub: https://github.com/saxoflowlabs/saxoflow-starter/issues",
        fg="cyan",
    )
    click.secho("  - Join the community Discord: [insert link here]", fg="cyan")
    click.secho(
        "\nIf requested by support, run `saxoflow diagnose summary --export` and attach the log file.",
        fg="cyan",
    )
