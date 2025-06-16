# saxoflow/doctor_tools.py — v2.5 adaptive flow+env analyzer

import shutil
import subprocess
import json
import os
from pathlib import Path

from saxoflow.tools.definitions import ALL_TOOLS, SCRIPT_TOOLS, APT_TOOLS

# Define Flow Profiles (vscode now always part of BASE)
FLOW_PROFILES = {
    "fpga": {
        "required": ["iverilog", "yosys", "gtkwave", "nextpnr", "openfpgaloader", "vscode"],
        "optional": ["verilator"]
    },
    "asic": {
        "required": ["iverilog", "yosys", "gtkwave", "openroad", "klayout", "magic", "netgen", "vscode"],
        "optional": ["verilator"]
    },
    "formal": {
        "required": ["iverilog", "yosys", "gtkwave", "symbiyosys", "vscode"],
        "optional": ["verilator"]
    },
    "minimal": {
        "required": ["iverilog", "yosys", "gtkwave", "vscode"],
        "optional": ["verilator"]
    }
}

# Load selected tools from user selection file
def load_user_selection():
    json_path = Path(".saxoflow_tools.json")
    if not json_path.exists():
        return []
    with open(json_path) as f:
        return json.load(f)

# Infer flow based on user selected tools
def infer_flow(selection):
    selection = set(selection)
    if "nextpnr" in selection:
        return "fpga"
    elif "openroad" in selection or "magic" in selection:
        return "asic"
    elif "symbiyosys" in selection:
        return "formal"
    else:
        return "minimal"

# Version detection logic (improved robust extractor)
def extract_version(tool, path):
    try:
        if tool == "iverilog":
            out = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
            for line in out.stdout.splitlines():
                if "Icarus Verilog version" in line:
                    return line.split("version")[1].split()[0]
        elif tool == "verilator":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip().split()[1]
        elif tool == "yosys":
            out = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip().split()[1]
        elif tool == "gtkwave":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip().split()[1]
        elif tool == "magic":
            out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        elif tool == "klayout":
            out = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip().split()[-1]
        elif tool == "openroad":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        elif tool == "symbiyosys":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        elif tool == "nextpnr":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        elif tool == "openfpgaloader":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            return out.stdout.strip()
        elif tool == "vscode":
            return "Installed"
        else:
            return "(unknown)"
    except:
        return "(parse error)"

# Main health scoring engine
def compute_health():
    user_selection = load_user_selection()
    flow = infer_flow(user_selection)

    profile = FLOW_PROFILES[flow]
    required = profile["required"]
    optional = profile["optional"]

    result = []
    ok = 0
    for tool in required:
        path = shutil.which(tool)
        if path:
            version = extract_version(tool, path)
            result.append((tool, True, path, version))
            ok += 1
        else:
            result.append((tool, False, None, None))

    opt_result = []
    for tool in optional:
        path = shutil.which(tool)
        if path:
            version = extract_version(tool, path)
            opt_result.append((tool, True, path, version))
        else:
            opt_result.append((tool, False, None, None))

    score = int(ok / len(required) * 100)
    return flow, score, result, opt_result

# === PATCH START: New v2.5 Environment Analyzer ===

# ✅ WSL Detection Logic
def detect_wsl():
    try:
        uname = os.uname().release.lower()
        if 'wsl' in uname:
            return True
        return False
    except AttributeError:
        return False

# ✅ PATH Analyzer Logic
def analyze_path():
    path_entries = os.getenv("PATH", "").split(":")
    win_paths = [p for p in path_entries if p.lower().startswith("/mnt/c/")]
    local_bin_present = any(str(Path.home() / ".local/bin") in p for p in path_entries)
    return {
        "total_entries": len(path_entries),
        "windows_entries": win_paths,
        "local_bin_present": local_bin_present
    }

# === PATCH END ===
