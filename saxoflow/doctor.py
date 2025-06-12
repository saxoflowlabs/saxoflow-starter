# saxoflow/doctor.py

import os
import sys
import subprocess
import json
from pathlib import Path
import shutil
import click

from saxoflow.tools.definitions import SCRIPT_TOOLS, ALL_TOOLS, TOOL_DESCRIPTIONS

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_ACTIVE = (os.getenv("VIRTUAL_ENV") is not None)

def log_ok(msg):
    click.echo(f"✅ {msg}")

def log_warn(msg):
    click.echo(f"⚠️ {msg}")

def log_fail(msg):
    click.echo(f"❌ {msg}")

def check_venv():
    if VENV_ACTIVE:
        log_ok("Virtual environment detected.")
    else:
        log_warn("Virtual environment NOT active — you may want to activate '.venv'.")

def check_python_package():
    try:
        import saxoflow
        log_ok(f"SaxoFlow package version: {saxoflow.__version__}")
    except Exception as e:
        log_fail(f"Cannot import saxoflow: {e}")

def check_scripts_exist():
    missing = []
    for tool, script in SCRIPT_TOOLS.items():
        path = PROJECT_ROOT / script
        if not path.exists():
            missing.append(script)
    if missing:
        log_fail(f"Missing install scripts: {missing}")
    else:
        log_ok("All installer scripts found.")

def check_json_selection():
    json_path = PROJECT_ROOT / ".saxoflow_tools.json"
    if json_path.exists():
        try:
            with open(json_path) as f:
                data = json.load(f)
            log_ok(f"Tool selection file found: {data}")
        except Exception as e:
            log_fail(f"Error parsing .saxoflow_tools.json: {e}")
    else:
        log_warn("No .saxoflow_tools.json found yet.")

def check_tool_binaries():
    click.echo("\n🔍 Tool binary availability:")
    for tool in ALL_TOOLS:
        path = shutil.which(tool)
        if path:
            log_ok(f"{tool} found at {path}")
        else:
            log_warn(f"{tool} not found on PATH")

@click.command()
def doctor():
    """Run full SaxoFlow environment health check"""
    click.echo("🩺 Running SaxoFlow Environment Doctor...\n")
    check_venv()
    check_python_package()
    check_scripts_exist()
    check_json_selection()
    check_tool_binaries()
    click.echo("\n🎯 Diagnostics complete.")
