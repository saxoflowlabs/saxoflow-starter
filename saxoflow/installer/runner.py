# saxoflow/installer/runner.py

import subprocess
from pathlib import Path
from saxoflow.tools.definitions import SCRIPT_TOOLS, ALL_TOOLS

def install_tool(tool):
    if tool not in SCRIPT_TOOLS:
        raise ValueError(f"❌ No installer defined for tool '{tool}'.")
    
    script_path = Path(SCRIPT_TOOLS[tool])
    if not script_path.exists():
        raise FileNotFoundError(f"❌ Installer script not found: {script_path}")

    print(f"🚀 Installing {tool} via {script_path} ...")
    subprocess.run(["bash", str(script_path)], check=True)

def install_all():
    for tool in SCRIPT_TOOLS.keys():
        try:
            install_tool(tool)
        except subprocess.CalledProcessError as e:
            print(f"⚠️ Failed installing {tool}: {e}")
