# saxoflow/installer/runner.py

import subprocess
import json
from pathlib import Path
from saxoflow.tools.definitions import SCRIPT_TOOLS, APT_TOOLS

# Load saved user selection
def load_user_selection():
    try:
        with open(".saxoflow_tools.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# Install via APT package manager
def install_apt(tool):
    print(f"🔧 Installing {tool} via apt...")
    subprocess.run(["sudo", "apt", "install", "-y", tool], check=True)

# Install via shell script recipe
def install_script(tool):
    script_path = Path(SCRIPT_TOOLS[tool])
    if not script_path.exists():
        print(f"❌ Missing installer script: {script_path}")
        return
    print(f"🚀 Installing {tool} via {script_path}...")
    subprocess.run(["bash", str(script_path)], check=True)

# Install any tool (APT or Script or fail gracefully)
def install_tool(tool):
    if tool in APT_TOOLS:
        install_apt(tool)
    elif tool in SCRIPT_TOOLS:
        install_script(tool)
    else:
        print(f"⚠️ Skipping: No installer defined for '{tool}'")

# Full mode: install absolutely all known tools (use only if intentional)
def install_all():
    print("🚀 Installing ALL known tools...")
    full = APT_TOOLS + list(SCRIPT_TOOLS.keys())
    for tool in full:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            print(f"⚠️ Failed installing {tool}")

# User mode: only install based on saved interactive selection
def install_selected():
    selection = load_user_selection()
    if not selection:
        print("⚠️ No saved tool selection found. Run 'saxoflow init-env' first.")
        return

    print(f"🚀 Installing user-selected tools: {selection}")
    for tool in selection:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            print(f"⚠️ Failed installing {tool}")
