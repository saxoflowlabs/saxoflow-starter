# saxoflow/doctor_tools.py — v3.1 Pro Diagnostics Engine (with robust version parsing)

import shutil
import subprocess
import json
import os
from pathlib import Path
import platform

from packaging.version import parse as parse_version  # <--- Add this import

from saxoflow.tools.definitions import ALL_TOOLS, SCRIPT_TOOLS, APT_TOOLS, MIN_TOOL_VERSIONS

# --- Configurable Profiles (extendable for new flows) ---
FLOW_PROFILES = {
    "fpga": {
        "required": ["iverilog", "yosys", "gtkwave", "nextpnr", "openfpgaloader"],
        "optional": ["verilator", "vivado", "vscode"]
    },
    "asic": {
        "required": ["verilator", "yosys", "gtkwave", "openroad", "klayout", "magic", "netgen"],
        "optional": ["iverilog", "vscode"]
    },
    "formal": {
        "required": ["yosys", "gtkwave", "symbiyosys"],
        "optional": ["iverilog", "vscode"]
    },
    "minimal": {
        "required": ["iverilog", "yosys", "gtkwave"],
        "optional": ["verilator", "vscode"]
    }
}

def tool_details(tool):
    DETAILS = {
        "yosys": "Synthesizer, required for all flows.",
        "iverilog": "Simulation (FPGA/minimal), optional for ASIC.",
        "verilator": "Fast SystemVerilog simulator (ASIC/formal/FPGA).",
        "gtkwave": "Waveform viewer, used across all flows.",
        "nextpnr": "FPGA place-and-route tool.",
        "openfpgaloader": "FPGA programmer, e.g. for Lattice boards.",
        "vivado": "Proprietary FPGA toolchain (optional).",
        "vscode": "Recommended IDE integration.",
        "openroad": "Digital ASIC P&R.",
        "klayout": "Layout viewer for ASIC.",
        "magic": "ASIC layout editor.",
        "netgen": "LVS/DRC for ASIC.",
        "symbiyosys": "Formal property verification."
    }
    return DETAILS.get(tool, "")

def load_user_selection():
    json_path = Path(".saxoflow_tools.json")
    if not json_path.exists():
        return []
    try:
        with open(json_path) as f:
            return json.load(f)
    except Exception:
        return []

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

def extract_version(tool, path):
    import re
    try:
        if tool == "iverilog":
            out = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
            for line in out.stdout.splitlines():
                if "Icarus Verilog version" in line:
                    # Look for first version-like token
                    for part in line.split():
                        if re.match(r"\d+(\.\d+)+", part):
                            return part
        elif tool == "verilator":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            # Verilator x.y or x.y.z
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "yosys":
            out = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
            # Yosys x.y+z
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "gtkwave":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "magic":
            out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "klayout":
            out = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "openroad":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "symbiyosys":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "nextpnr":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "openfpgaloader":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "vivado":
            out = subprocess.run([path, "-version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        elif tool == "vscode":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            for part in out.stdout.strip().split():
                if re.match(r"\d+(\.\d+)+", part):
                    return part
        return "(unknown)"
    except Exception as e:
        return f"(parse error: {e})"

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
        # 🔧 Allow fallback for nextpnr → nextpnr-ice40 etc
        if tool == "nextpnr" and not path:
            path = shutil.which("nextpnr-ice40")
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
    score = int(ok / len(required) * 100) if required else 100
    return flow, score, result, opt_result

def analyze_env():
    summary = {}
    summary['platform'] = platform.platform()
    summary['python_version'] = platform.python_version()
    summary['venv'] = os.getenv("VIRTUAL_ENV")
    summary['wsl'] = detect_wsl()
    summary['path'] = os.getenv("PATH", "")
    summary['project_root'] = str(Path.cwd())
    summary['user'] = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
    summary['home'] = str(Path.home())
    paths = summary['path'].split(":")
    duplicates = [p for i, p in enumerate(paths) if p in paths[:i]]
    summary['path_duplicates'] = duplicates
    toolbins = [str(Path.home() / ".local" / t / "bin") for t in ALL_TOOLS]
    summary['bins_missing_in_path'] = [tb for tb in toolbins if tb not in paths and os.path.isdir(tb)]
    return summary

def detect_wsl():
    try:
        if "WSL" in platform.uname().release:
            return True
        if os.path.exists("/proc/version"):
            with open("/proc/version") as f:
                if "Microsoft" in f.read():
                    return True
        return False
    except Exception:
        return False

def analyze_path():
    path_entries = os.getenv("PATH", "").split(":")
    win_paths = [p for p in path_entries if p.lower().startswith("/mnt/c/")]
    local_bin_present = any(str(Path.home() / ".local/bin") in p for p in path_entries)
    return {
        "total_entries": len(path_entries),
        "windows_entries": win_paths,
        "local_bin_present": local_bin_present
    }

def pro_diagnostics():
    env = analyze_env()
    flow, score, required, optional = compute_health()
    tips = []
    if score < 100:
        tips.append("Not all required tools installed. Run `saxoflow doctor repair` or `saxoflow doctor repair-interactive`.")
    if not env["venv"]:
        tips.append("Virtual environment not active. Run `source .venv/bin/activate`.")
    if env["path_duplicates"]:
        tips.append(f"Duplicate entries in PATH: {env['path_duplicates']}")
    if env["bins_missing_in_path"]:
        tips.append(f"Tool bins not in PATH: {env['bins_missing_in_path']}. Add these to your PATH for best results.")
    if env["wsl"]:
        tips.append("Detected WSL environment. Make sure Windows/WSL paths are set up correctly for tools and VSCode.")
    return {
        "env": env,
        "health": {"flow": flow, "score": score, "required": required, "optional": optional},
        "tips": tips
    }
