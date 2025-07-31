import shutil
import subprocess
import json
import os
from pathlib import Path
import platform

from saxoflow.tools.definitions import ALL_TOOLS

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


def find_tool_binary(tool):
    # 1. Standard PATH search
    path = shutil.which(tool)
    if path:
        return path, True, tool
    # 2. Common .local/<tool>/bin/<tool>
    user_bin = Path.home() / ".local" / tool / "bin" / tool
    if user_bin.exists():
        return str(user_bin), False, tool
    # 3. Special case: nextpnr family
    if tool == "nextpnr":
        for variant in ["nextpnr-ice40", "nextpnr-ecp5", "nextpnr-xilinx"]:
            alt = shutil.which(variant)
            if alt:
                return alt, True, variant
        np_dir = Path.home() / ".local" / "nextpnr" / "bin"
        if np_dir.exists():
            for file in np_dir.glob("nextpnr*"):
                if file.is_file() and os.access(str(file), os.X_OK):
                    return str(file), False, file.name
    # 4. Special case: openfpgaloader (search both spellings)
    if tool == "openfpgaloader":
        for name in ["openfpgaloader", "openFPGALoader"]:
            path2 = shutil.which(name)
            if path2:
                return path2, True, tool
        for base in [Path.home() / ".local" / "bin", Path("/usr/bin"), Path("/usr/local/bin")]:
            for name in ["openfpgaloader", "openFPGALoader"]:
                candidate = base / name
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return str(candidate), False, tool
    return None, False, None


def extract_version(tool, path):
    import re
    if not path:
        return "(unknown)"
    try:
        def pick_version_iverilog(s):
            m = re.search(r"Icarus Verilog version ([\d\.]+(?:[^\)]*\))?)", s)
            if m:
                return m.group(1).strip()
            return None

        def pick_version_nextpnr(s):
            m = re.search(r"\(Version ([^)]+)\)", s)
            if m:
                return m.group(1).strip()
            return None

        def pick_version_gtkwave(s):
            m = re.search(r"GTKWave Analyzer v?([^\s]+)", s)
            if m:
                return m.group(1).strip()
            return None

        def pick_version_generic(s):
            m = re.search(r"(\d+\.\d+(?:[\w\.\-\+]*))", s)
            if m:
                return m.group(1).strip()
            return None

        if tool == "iverilog":
            out = subprocess.run([path, "-v"], capture_output=True, text=True, timeout=5)
            all_text = out.stdout + out.stderr
            v = pick_version_iverilog(all_text)
            if v:
                return v
            return pick_version_generic(all_text) or "(unknown)"
        elif tool.startswith("nextpnr"):
            for flag in ("--version", "-v", "--help"):
                try:
                    out = subprocess.run([path, flag], capture_output=True, text=True, timeout=5)
                    all_text = out.stdout + " " + out.stderr
                    v = pick_version_nextpnr(all_text)
                    if v:
                        return v
                except Exception:
                    continue
            return "(unknown)"
        elif tool == "gtkwave":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            all_text = out.stdout + " " + out.stderr
            v = pick_version_gtkwave(all_text)
            if v:
                return v
            return pick_version_generic(all_text) or "(unknown)"
        elif tool == "yosys":
            out = subprocess.run([path, "-V"], capture_output=True, text=True, timeout=5)
            all_text = out.stdout + " " + out.stderr
            v = pick_version_generic(all_text)
            if v:
                return v
            return "(unknown)"
        elif tool == "verilator":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            all_text = out.stdout + " " + out.stderr
            v = pick_version_generic(all_text)
            if v:
                return v
            return "(unknown)"
        elif tool == "openfpgaloader":
            for flag in ("--version", "-V"):
                try:
                    out = subprocess.run([path, flag], capture_output=True, text=True, timeout=5)
                    all_text = out.stdout + " " + out.stderr
                    v = pick_version_generic(all_text)
                    if v:
                        return v
                except Exception:
                    continue
            return "(unknown)"
        else:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            all_text = out.stdout + " " + out.stderr
            v = pick_version_generic(all_text)
            if v:
                return v
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
        path, in_path, variant = find_tool_binary(tool)
        version = extract_version(variant if variant else tool, path) if path else None
        if path:
            result.append((tool, True, path, version, in_path))
            ok += 1
        else:
            result.append((tool, False, None, None, False))
    opt_result = []
    for tool in optional:
        path, in_path, variant = find_tool_binary(tool)
        version = extract_version(variant if variant else tool, path) if path else None
        if path:
            opt_result.append((tool, True, path, version, in_path))
        else:
            opt_result.append((tool, False, None, None, False))
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
    # Build mapping: which tools are in each path entry
    path_tool_map = {}
    for tool in ALL_TOOLS:
        for p in paths:
            tp = Path(p) / tool
            if tp.exists() and os.access(tp, os.X_OK):
                if p not in path_tool_map:
                    path_tool_map[p] = []
                path_tool_map[p].append(tool)
    # Duplicates: show all associated tools for each duplicate path
    seen = set()
    duplicates = []
    for p in paths:
        if p in seen:
            assoc_tools = path_tool_map.get(p, [])
            duplicates.append((p, assoc_tools))
        seen.add(p)
    summary['path_duplicates'] = duplicates
    # Tool bins not in PATH, with context
    toolbins = [str(Path.home() / ".local" / t / "bin") for t in ALL_TOOLS]
    toolbin_map = {str(Path.home() / ".local" / t / "bin"): t for t in ALL_TOOLS}
    summary['bins_missing_in_path'] = [
        (tb, toolbin_map.get(tb)) for tb in toolbins
        if tb not in paths and os.path.isdir(tb)
    ]
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
        tips.append(
            "Not all required tools installed. Run `saxoflow diagnose repair` or `saxoflow diagnose repair-interactive`."
        )
    if not env["venv"]:
        tips.append("Virtual environment not active. Run `source .venv/bin/activate`.")
    if env["path_duplicates"]:
        for dup_path, tools in env["path_duplicates"]:
            if tools:
                tips.append(
                    f"Duplicate PATH entry: {dup_path} (used by: {', '.join(tools)}). Remove for cleaner environment."
                )
            else:
                tips.append(f"Duplicate PATH entry: {dup_path}. Remove for cleaner environment.")
        tips.append(
            "To clean PATH duplicates (advanced): export PATH=$(echo $PATH | tr ':' '\\n' | awk '!x[$0]++' | paste -sd:)"
        )
    if env["bins_missing_in_path"]:
        for tb, tool in env["bins_missing_in_path"]:
            if tool:
                tips.append(f"Tool bin not in PATH: {tb} (needed for: {tool}). Add this to your PATH.")
            else:
                tips.append(f"Tool bin not in PATH: {tb}. Add this to your PATH for best results.")
    if env["wsl"]:
        tips.append(
            "Detected WSL environment. Make sure Windows/WSL paths are set up correctly for tools and VSCode."
        )
    return {
        "env": env,
        "health": {"flow": flow, "score": score, "required": required, "optional": optional},
        "tips": tips
    }
