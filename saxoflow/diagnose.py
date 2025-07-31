import os
import shutil
import subprocess
import platform
from pathlib import Path
import click
import datetime
import sys

from packaging.version import parse as parse_version

from saxoflow.tools.definitions import TOOL_DESCRIPTIONS, MIN_TOOL_VERSIONS
from saxoflow.installer import runner
from saxoflow import diagnose_tools

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ACTIVE = os.getenv("VIRTUAL_ENV") is not None

DIAGNOSE_LOG_FILE = PROJECT_ROOT / "saxoflow_diagnose_report.txt"


# --------------------------------------------
# 🩺  diagnose CLI Group (define first!)
# --------------------------------------------
@click.group()
def diagnose():
    """🩺 SaxoFlow Pro diagnose - System Diagnosis & Repair"""
    pass


# --------------------------------------------
# 🧪 Logger Utilities
# --------------------------------------------
def log_ok(msg):
    click.secho(f"✅ {msg}", fg="green")


def log_warn(msg):
    click.secho(f"⚠️ {msg}", fg="yellow")


def log_fail(msg):
    click.secho(f"❌ {msg}", fg="red")


def log_tip(msg):
    click.secho(f"💡 {msg}", fg="blue")


# --------------------------------------------
# 🔍 Summary Mode
# --------------------------------------------
@diagnose.command("summary")
@click.option('--export', is_flag=True, help="Export report to a file for support or bug reports")
def diagnose_summary(export):
    """Run full diagnostic health scan with dynamic analysis"""
    report_lines = []
    click.echo("🩺 SaxoFlow diagnose v4.x - Full Health Report\n")
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
        import saxoflow
        log_ok("SaxoFlow Python package import OK")
        report_lines.append("SaxoFlow Python import: OK")
    except ImportError:
        log_fail("Cannot import SaxoFlow Python package")
        report_lines.append("SaxoFlow Python import: FAIL")

    # Tool checks
    flow, score, required, optional = diagnose_tools.compute_health()
    click.echo(f"\n🎯 Flow Profile: {flow.upper()}")
    click.echo(f"📊 Health Score: {score}%\n")

    # Check Python version
    py_version = sys.version.split()[0]
    min_py_version = "3.8"
    if parse_version(py_version) < parse_version(min_py_version):
        log_warn(f"Python {py_version} found. SaxoFlow recommends Python {min_py_version}+. Upgrade if possible.")
        report_lines.append(f"Python version: {py_version} (OLD)")
    else:
        log_ok(f"Python {py_version} detected.")
        report_lines.append(f"Python version: {py_version}")

    click.echo("\n🔧 Required Tools:")
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
                    outdated = False
            msg = f"{tool}: {path} — {version}"
            if not in_path:
                log_warn(f"{tool} found at {path} but not in PATH")
                log_tip(f"Add to PATH in your .bashrc: export PATH=\"{os.path.dirname(path)}:$PATH\"")
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
            report_lines.append(f"  MISSING: {tool}: (not found) — (no version)")

    click.echo("\n🧩 Optional Tools:")
    report_lines.append("\nOptional tools:")
    for tool, ok, path, version, in_path in optional:
        if ok:
            msg = f"{tool}: {path} — {version}"
            if not in_path:
                log_warn(f"{tool} found at {path} but not in PATH")
                log_tip(f"Add to PATH in your .bashrc: export PATH=\"{os.path.dirname(path)}:$PATH\"")
                report_lines.append(f"  FOUND_NOT_IN_PATH: {msg}")
            else:
                log_ok(msg)
                report_lines.append("  OK: " + msg)
        else:
            log_warn(f"{tool} not installed")
            log_tip(f"You can install with: saxoflow install {tool}")
            report_lines.append(f"  NOT INSTALLED: {tool}: (not found) — (no version)")

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
            required_exts = {"ms-vscode.cpptools", "mshr-hdl.veriloghdl"}
            for ext in required_exts:
                if ext not in exts:
                    missing_exts.append(ext)
            if missing_exts:
                log_warn(f"VSCode missing recommended extensions: {', '.join(missing_exts)}")
                for ext in missing_exts:
                    log_tip(f"Run: code --install-extension {ext}")
                report_lines.append("VSCode extensions: MISSING - " + ", ".join(missing_exts))
            else:
                log_ok("All recommended VSCode extensions installed")
                report_lines.append("VSCode extensions: OK")
        except Exception:
            log_warn("Could not check VSCode extensions")
            report_lines.append("VSCode extensions: Unknown (code check failed)")
    else:
        log_warn("VSCode not found in PATH")
        log_tip("To enable integrated IDE features, install VSCode from https://code.visualstudio.com/")
        report_lines.append("VSCode: Not installed")

    # Path diagnostics — User-friendly Reporting (NEW: context aware)
    click.echo()
    report_lines.append("\nPATH checks:")
    env_info = diagnose_tools.analyze_env()
    # 1. Duplicates
    for dup_path, tools in env_info['path_duplicates']:
        if tools:
            log_warn(f"Duplicate in PATH: {dup_path} (used by {tools})")
            log_tip(
                f"This is a bin directory for {tools}. Having duplicates can slow down shell startup or confuse which binary runs."
            )
        else:
            log_warn(f"Duplicate in PATH: {dup_path}")
            log_tip("Having duplicate PATH entries can slow down shell startup or confuse which binary runs.")
        log_tip("Remove duplicate PATH entries in your ~/.bashrc or ~/.profile.")
        if tools:
            report_lines.append(f"Duplicate in PATH: {dup_path} (tool: {tools})")
        else:
            report_lines.append(f"Duplicate in PATH: {dup_path}")

    if env_info['path_duplicates']:
        log_tip(
            "💡 Duplicate PATH entries usually happen if you install the same tool multiple times, add the same export line in .bashrc/.zshrc more than once, or if automated scripts add redundant paths."
        )
        log_tip("💡 To professionally clean up your PATH, run: saxoflow diagnose clean-path")
        log_tip("To auto-clean all duplicates (advanced):")
        log_tip("export PATH=$(echo $PATH | tr ':' '\\n' | awk '!x[$0]++' | paste -sd:)")
        report_lines.append("PATH has duplicates. See above for cleanup instructions.")

    # 2. Tool bins missing from PATH (with tool name & desc)
    for tb, tool in env_info['bins_missing_in_path']:
        if tool:
            log_warn(f"Tool bin not in PATH: {tb} ({tool})")
            log_tip(f"Add to PATH in your .bashrc: export PATH=\"{tb}:$PATH\"")
            desc = TOOL_DESCRIPTIONS.get(tool, "")
            if desc:
                log_tip(f"{tool}: {desc}")
            report_lines.append(f"Tool bin not in PATH: {tb} ({tool})")
        else:
            log_warn(f"Tool bin not in PATH: {tb}")
            log_tip(f"Add to PATH in your .bashrc: export PATH=\"{tb}:$PATH\"")
            report_lines.append(f"Tool bin not in PATH: {tb}")

    click.echo("\n🔍 For full troubleshooting see documentation or run with --export to create a log for support.")

    if score < 100:
        log_tip("Run `saxoflow diagnose repair` to auto-install missing tools, or `saxoflow diagnose repair-interactive` for selective repair.")

    # Optionally export
    if export:
        with open(DIAGNOSE_LOG_FILE, "w") as f:
            for line in report_lines:
                f.write(line + "\n")
        log_ok(f"diagnose report written to: {DIAGNOSE_LOG_FILE}")

    # --- Add summary footer if actionable issues found ---
    issues = 0
    for tool, ok, path, version, in_path in required:
        if not ok or not in_path:
            issues += 1
    for tool, ok, path, version, in_path in optional:
        if not ok or not in_path:
            issues += 1
    issues += len(env_info['path_duplicates'])
    issues += len(env_info['bins_missing_in_path'])
    if issues:
        click.echo(f"\n🚦 SaxoFlow diagnose found {issues} actionable issue(s). See above for recommendations.\n")
    else:
        click.echo("\n✅ No major issues detected. You're good to go!\n")


# --------------------------------------------
# 🧬 Environment Info
# --------------------------------------------
@diagnose.command("env")
def diagnose_env():
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
@diagnose.command("repair")
def diagnose_repair():
    """Auto-install all missing required tools"""
    click.echo("\n🔧 Auto-Repair Starting...")

    flow, score, required, optional = diagnose_tools.compute_health()
    repaired = False

    for tool, ok, _, _, _ in required:
        if not ok:
            click.echo(f"🚧 Installing: {tool}")
            try:
                runner.install_tool(tool)
                log_ok(f"{tool} installed")
                repaired = True
            except subprocess.CalledProcessError:
                log_fail(f"{tool} failed to install")
                log_tip(f"See logs above or run `saxoflow diagnose export` for help.")

    if not repaired:
        log_ok("🎉 All required tools already installed")


# --------------------------------------------
# 🔧 Interactive Repair Mode (choose tools)
# --------------------------------------------
@diagnose.command("repair-interactive")
def diagnose_repair_interactive():
    """Interactively choose which missing tools to install"""
    import questionary
    flow, score, required, optional = diagnose_tools.compute_health()
    missing_tools = [tool for tool, ok, _, _, _ in required if not ok]
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
            log_tip(f"See logs above or run `saxoflow diagnose export` for help.")


# --------------------------------------------
# 🧹 Professional PATH Clean Command (NEW)
# --------------------------------------------
@diagnose.command("clean-path")
@click.option(
    "--shell",
    default="bash",
    type=click.Choice(["bash", "zsh"], case_sensitive=False),
    help="Shell config file to clean: bash (.bashrc) or zsh (.zshrc)"
)
def diagnose_clean_path(shell):
    """
    Interactively clean duplicate PATH entries from your shell config file (with backup & full transparency).

    - This command only edits ~/.bashrc or ~/.zshrc if you agree.
    - It will show you exactly what changes will be made.
    - Always makes a backup as ~/.bashrc.bak or ~/.zshrc.bak before editing.
    """
    import shutil as pyshutil
    home = str(Path.home())
    config_file = f"{home}/.bashrc" if shell == "bash" else f"{home}/.zshrc"

    click.echo(f"\n🔍 Scanning your PATH for duplicates as seen by this shell...")
    path = os.environ.get("PATH", "")
    paths = path.split(":")
    seen, duplicates = set(), []
    for p in paths:
        if p in seen:
            duplicates.append(p)
        seen.add(p)

    if not duplicates:
        click.secho("✅ No duplicate PATH entries detected! Your PATH is clean.", fg="green")
        return

    click.secho(f"\n⚠️  Found {len(duplicates)} duplicate PATH entries:", fg="yellow")
    for p in duplicates:
        click.echo(f"  {p}")

    click.echo(
        "\n💡 Duplicates happen if you install the same tool multiple times, add the same export line in .bashrc/.zshrc more than once, or if automated scripts add redundant paths."
    )

    click.echo(f"\nWe'll attempt to clean up duplicates in {config_file}.")
    backup = f"{config_file}.bak"
    pyshutil.copy(config_file, backup)
    click.echo(f"🛡️  Backup created: {backup}")

    # Parse and de-duplicate export PATH lines only
    cleaned_lines = []
    export_path_lines = []
    with open(config_file, "r") as f:
        lines = f.readlines()
    for line in lines:
        if "export PATH=" in line and not line.strip().startswith("#"):
            export_path_lines.append(line)
        else:
            cleaned_lines.append(line)

    # Only keep one unique export PATH=... line (or none, if none exist)
    if export_path_lines:
        cleaned_lines.append(export_path_lines[-1])  # Keep only the last occurrence
        click.secho("\nThe following duplicate export PATH lines will be removed:", fg="yellow")
        for line in export_path_lines[:-1]:
            click.echo(f"  {line.strip()}")

    # Show preview
    click.echo("\n--- Cleaned config preview ---")
    preview = "".join(cleaned_lines[-10:]) if len(cleaned_lines) > 10 else "".join(cleaned_lines)
    click.echo(preview + "\n--- End Preview ---")

    if not click.confirm("Proceed to update your config file (remove above redundant export PATH lines)?", default=False):
        click.secho("Aborted. No changes made. You may clean manually if you wish.", fg="red")
        return

    with open(config_file, "w") as f:
        f.writelines(cleaned_lines)

    click.secho(
        f"✅ Clean complete! Your shell config was updated. Open a new terminal for changes to take effect.",
        fg="green"
    )
    click.echo("If you have custom tool setups, verify manually that all needed paths are still present.")


# --------------------------------------------
# 🆘 Help & Support Command
# --------------------------------------------
@diagnose.command("help")
def diagnose_help():
    """Show support options and links"""
    click.echo("🆘 SaxoFlow Support")
    click.echo("If you need help, please:")
    click.echo("  - Visit the documentation: https://github.com/saxoflowlabs/saxoflow-starter/wiki")
    click.echo("  - Open an issue on GitHub: https://github.com/saxoflowlabs/saxoflow-starter/issues")
    click.echo("  - Join the community Discord: [insert link here]")
    click.echo("\nIf requested by support, run `saxoflow diagnose summary --export` and attach the log file.")
