# saxoflow/doctor.py — SaxoFlow Pro Environment Doctor v4.x (Pro UX Edition)

import os
import shutil
import subprocess
import platform
from pathlib import Path
import click
import datetime
import sys

from packaging.version import parse as parse_version  # <-- Robust version parsing!

from saxoflow.tools.definitions import ALL_TOOLS, TOOL_DESCRIPTIONS, MIN_TOOL_VERSIONS
from saxoflow.installer import runner
from saxoflow import doctor_tools

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ACTIVE = os.getenv("VIRTUAL_ENV") is not None

DOCTOR_LOG_FILE = PROJECT_ROOT / "saxoflow_doctor_report.txt"

# --------------------------------------------
# 🧪 Logger Utilities
# --------------------------------------------
def log_ok(msg): click.secho(f"✅ {msg}", fg="green")
def log_warn(msg): click.secho(f"⚠️ {msg}", fg="yellow")
def log_fail(msg): click.secho(f"❌ {msg}", fg="red")
def log_tip(msg): click.secho(f"💡 {msg}", fg="blue")

# --------------------------------------------
# 🧠 Tool Checker Utility
# --------------------------------------------
def check_tool(tool_name, min_version=None):
    """Return (exists:bool, path:str, version:str or None, outdated:bool)"""
    try:
        result = subprocess.run([tool_name, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            return False, None, None, False
        output = result.stdout.strip().splitlines()[0]
        full_path = shutil.which(tool_name)
        # Version check (if requested)
        outdated = False
        version_num = None

        # Extract version: look for first field that looks like a version
        import re
        for part in output.split():
            if re.match(r"\d+(\.\d+)+", part):  # e.g., 0.54+15 or 3.12.3
                version_num = part
                break
        if min_version and version_num:
            try:
                # Use packaging.version for robust comparison
                if parse_version(version_num) < parse_version(min_version):
                    outdated = True
            except Exception:
                # If version cannot be parsed, log warning but do not crash
                log_warn(f"Could not parse version '{version_num}' for {tool_name}")
                outdated = False
        return True, full_path, output, outdated
    except FileNotFoundError:
        return False, None, None, False

# --------------------------------------------
# 🩺 Doctor CLI Group
# --------------------------------------------
@click.group()
def doctor():
    """🩺 SaxoFlow Pro Doctor - System Diagnosis & Repair"""
    pass

# --------------------------------------------
# 🔍 Summary Mode
# --------------------------------------------
@doctor.command("summary")
@click.option('--export', is_flag=True, help="Export report to a file for support or bug reports")
def doctor_summary(export):
    """Run full diagnostic health scan with dynamic analysis"""
    report_lines = []
    click.echo("🩺 SaxoFlow Doctor v4.x - Full Health Report\n")
    report_lines.append(f"Doctor run at {datetime.datetime.now()}")
    report_lines.append(f"Platform: {platform.platform()} ({platform.machine()})\n")

    # Environment info
    if VENV_ACTIVE:
        log_ok("Virtualenv detected")
        report_lines.append("Virtualenv: ACTIVE")
    else:
        log_warn("Virtualenv NOT active")
        report_lines.append("Virtualenv: NOT active")

    try:
        import saxoflow
        log_ok("SaxoFlow Python package import OK")
        report_lines.append("SaxoFlow Python import: OK")
    except ImportError:
        log_fail("Cannot import SaxoFlow Python package")
        report_lines.append("SaxoFlow Python import: FAIL")

    # Tool checks
    flow, score, required, optional = doctor_tools.compute_health()
    click.echo(f"\n🎯 Flow Profile: {flow.upper()}")
    click.echo(f"📊 Health Score: {score}%\n")

    # Check Python version
    py_version = sys.version.split()[0]
    min_py_version = "3.8"
    if parse_version(py_version) < parse_version(min_py_version):
        log_warn(f"Python {py_version} found. SaxoFlow recommends Python {min_py_version}+.")
        report_lines.append(f"Python version: {py_version} (OLD)")
    else:
        log_ok(f"Python {py_version} detected.")
        report_lines.append(f"Python version: {py_version}")

    click.echo("\n🔧 Required Tools:")
    report_lines.append("\nRequired tools:")
    for tool, ok, path, version in required:
        min_version = MIN_TOOL_VERSIONS.get(tool)
        exists, tool_path, tool_version, outdated = check_tool(tool, min_version)
        msg = f"{tool}: {tool_path or '(not found)'} — {tool_version or '(no version)'}"
        if ok and not outdated:
            log_ok(msg)
            report_lines.append("  OK: " + msg)
        elif ok and outdated:
            log_warn(f"{msg} (version too old, minimum {min_version})")
            log_tip(f"Run: saxoflow install {tool} to upgrade.")
            report_lines.append(f"  WARN: {msg} (OUTDATED; needs {min_version}+)")
        else:
            log_fail(f"{tool} missing")
            log_tip(f"Run: saxoflow install {tool}")
            report_lines.append("  MISSING: " + msg)

    click.echo("\n🧩 Optional Tools:")
    report_lines.append("\nOptional tools:")
    for tool, ok, path, version in optional:
        exists, tool_path, tool_version, _ = check_tool(tool)
        msg = f"{tool}: {tool_path or '(not found)'} — {tool_version or '(no version)'}"
        if ok:
            log_ok(msg)
            report_lines.append("  OK: " + msg)
        else:
            log_warn(f"{tool} not installed")
            report_lines.append("  NOT INSTALLED: " + msg)

    # VSCode extension check (if VSCode is present)
    code_path = shutil.which("code")
    if code_path:
        try:
            result = subprocess.run(
                ["code", "--list-extensions"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
            )
            exts = set(result.stdout.split())
            missing_exts = []
            required_exts = {"ms-vscode.cpptools", "mshr-hdl.veriloghdl"} # Example set
            for ext in required_exts:
                if ext not in exts:
                    missing_exts.append(ext)
            if missing_exts:
                log_warn(f"VSCode missing recommended extensions: {', '.join(missing_exts)}")
                log_tip("You can run: code --install-extension <ext>")
                report_lines.append("VSCode extensions: MISSING - " + ", ".join(missing_exts))
            else:
                log_ok("All recommended VSCode extensions installed")
                report_lines.append("VSCode extensions: OK")
        except Exception:
            log_warn("Could not check VSCode extensions")
            report_lines.append("VSCode extensions: Unknown (code check failed)")
    else:
        log_warn("VSCode not found in PATH")
        report_lines.append("VSCode: Not installed")

    # Path diagnostics
    click.echo()
    report_lines.append("\nPATH checks:")
    paths = os.getenv("PATH", "").split(":")
    seen = set()
    for p in paths:
        if p in seen:
            log_warn(f"Duplicate in PATH: {p}")
            report_lines.append(f"Duplicate in PATH: {p}")
        seen.add(p)
        # Warn if tool dirs are missing from PATH
    toolbins = [str(Path.home() / ".local" / t / "bin") for t in ALL_TOOLS]
    for tb in toolbins:
        if tb not in paths and os.path.isdir(tb):
            log_warn(f"Tool bin not in PATH: {tb}")
            log_tip(f"Add to PATH in your .bashrc: export PATH=\"{tb}:$PATH\"")
            report_lines.append(f"Tool bin not in PATH: {tb}")

    click.echo("\n🔍 For full troubleshooting see documentation or run with --export to create a log for support.")

    if score < 100:
        log_tip("Run `saxoflow doctor repair` to auto-install missing tools, or `saxoflow doctor repair-interactive` for selective repair.")

    # Optionally export
    if export:
        with open(DOCTOR_LOG_FILE, "w") as f:
            for line in report_lines:
                f.write(line + "\n")
        log_ok(f"Doctor report written to: {DOCTOR_LOG_FILE}")

# --------------------------------------------
# 🧬 Environment Info
# --------------------------------------------
@doctor.command("env")
def doctor_env():
    """Print system environment info"""
    click.echo("\n🧬 Environment Diagnostics:")
    click.echo(f"VIRTUAL_ENV: {os.getenv('VIRTUAL_ENV')}")
    click.echo(f"PATH: {os.getenv('PATH')}")
    click.echo(f"Project Root: {PROJECT_ROOT}")
    click.echo(f"Running on WSL: {'Yes' if 'WSL' in os.uname().release else 'No'}")
    click.echo(f"Python Executable: {sys.executable}")
    click.echo(f"Python Version: {platform.python_version()}")
    click.echo(f"Platform: {platform.platform()}")

# --------------------------------------------
# 🛠 Repair Mode (full auto)
# --------------------------------------------
@doctor.command("repair")
def doctor_repair():
    """Auto-install all missing required tools"""
    click.echo("\n🔧 Auto-Repair Starting...")

    flow, score, required, optional = doctor_tools.compute_health()
    repaired = False

    for tool, ok, _, _ in required:
        if not ok:
            click.echo(f"🚧 Installing: {tool}")
            try:
                runner.install_tool(tool)
                log_ok(f"{tool} installed")
                repaired = True
            except subprocess.CalledProcessError:
                log_fail(f"{tool} failed to install")
                log_tip(f"See logs above or run `saxoflow doctor export` for help.")

    if not repaired:
        log_ok("🎉 All required tools already installed")

# --------------------------------------------
# 🔧 Interactive Repair Mode (choose tools)
# --------------------------------------------
@doctor.command("repair-interactive")
def doctor_repair_interactive():
    """Interactively choose which missing tools to install"""
    import questionary
    flow, score, required, optional = doctor_tools.compute_health()
    missing_tools = [tool for tool, ok, _, _ in required if not ok]
    if not missing_tools:
        log_ok("All required tools already installed.")
        return
    chosen = questionary.checkbox("Select tools to repair/install:", choices=missing_tools).ask()
    if not chosen:
        log_warn("No tools selected. No action taken.")
        return
    for tool in chosen:
        click.echo(f"🚧 Installing: {tool}")
        try:
            runner.install_tool(tool)
            log_ok(f"{tool} installed")
        except subprocess.CalledProcessError:
            log_fail(f"{tool} failed to install")
            log_tip(f"See logs above or run `saxoflow doctor export` for help.")

# --------------------------------------------
# 🆘 Help & Support Command
# --------------------------------------------
@doctor.command("help")
def doctor_help():
    """Show support options and links"""
    click.echo("🆘 SaxoFlow Support")
    click.echo("If you need help, please:")
    click.echo("  - Visit the documentation: https://github.com/saxoflowlabs/saxoflow-starter/wiki")
    click.echo("  - Open an issue on GitHub: https://github.com/saxoflowlabs/saxoflow-starter/issues")
    click.echo("  - Join the community Discord: [insert link here]")
    click.echo("\nIf requested by support, run `saxoflow doctor summary --export` and attach the log file.")
