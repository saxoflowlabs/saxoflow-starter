# saxoflow/doctor.py — Doctor v2.6.2 Pro Auto-Repair Engine

import os
import sys
import subprocess
import json
import shutil
from pathlib import Path
import click

from saxoflow.tools.definitions import SCRIPT_TOOLS, APT_TOOLS, ALL_TOOLS, TOOL_DESCRIPTIONS
from saxoflow import doctor_tools  # ✅ Fully Flow-Aware Health Engine
from saxoflow.installer import runner  # ✅ New direct access to installer!

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ACTIVE = (os.getenv("VIRTUAL_ENV") is not None)

# -------------------- Logging utils
def log_ok(msg): click.echo(f"✅ {msg}")
def log_warn(msg): click.echo(f"⚠️ {msg}")
def log_fail(msg): click.echo(f"❌ {msg}")

@click.group()
def doctor():
    """SaxoFlow Environment Doctor"""

# 🔍 SUMMARY MODE — Full Flow-Aware Health Scan
@doctor.command("summary")
def doctor_summary():
    """Run full flow-sensitive system scan"""
    click.echo("🩺 SaxoFlow Doctor v2.6.2 Pro Health Scan\n")

    if VENV_ACTIVE:
        log_ok("Virtualenv detected")
    else:
        log_warn("Virtualenv NOT active")

    try:
        import saxoflow
        log_ok("SaxoFlow package import OK (v0.4.x)")
    except:
        log_fail("Cannot import saxoflow package!")

    flow, score, required, optional = doctor_tools.compute_health()

    click.echo(f"\n🎯 Flow detected: {flow.upper()} profile")
    click.echo(f"📊 Health score: {score}%\n")

    click.echo("🔧 Required Tools:")
    for tool, ok, path, version in required:
        if ok:
            log_ok(f"{tool} → {path} [{version}]")
        else:
            log_fail(f"{tool} missing!")

    click.echo("\n🧩 Optional Tools:")
    for tool, ok, path, version in optional:
        if ok:
            log_ok(f"{tool} → {path} [{version}]")
        else:
            log_warn(f"{tool} not installed (optional)")

# 🔍 ENVIRONMENT MODE — Print Environment Vars
@doctor.command("env")
def doctor_env():
    """Print environment info"""
    click.echo("\n🧬 Environment Info:")
    click.echo(f"VENV: {os.getenv('VIRTUAL_ENV')}")
    click.echo(f"PATH: {os.getenv('PATH')}")
    click.echo(f"Install Dir: {str(PROJECT_ROOT / 'tools-src')}")
    click.echo(f"WSL: {'Yes' if 'WSL' in os.uname().release else 'No'}")

# 🔧 FULL AUTO-REPAIR MODE
@doctor.command("repair")
def doctor_repair():
    """Automatically repair missing required tools"""
    click.echo("\n🔧 Starting Auto-Repair...\n")

    flow, score, required, optional = doctor_tools.compute_health()

    repaired_any = False

    for tool, ok, path, _ in required:
        if not ok:
            repaired_any = True
            click.echo(f"🚧 Installing missing: {tool}")
            try:
                runner.install_tool(tool)
                log_ok(f"{tool} successfully installed!")
            except subprocess.CalledProcessError:
                log_fail(f"Failed installing {tool} — manual fix may be needed.")

    if not repaired_any:
        log_ok("✅ All required tools already installed. No repair needed.")
