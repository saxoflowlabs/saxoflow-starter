import subprocess
import json
import shutil
from pathlib import Path
from saxoflow.tools.definitions import SCRIPT_TOOLS, APT_TOOLS

def load_user_selection():
    try:
        with open(".saxoflow_tools.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def persist_tool_path(tool_name: str, bin_path: str):
    activate_file = Path(".venv/bin/activate")
    export_line = f'export PATH={bin_path}:$PATH'
    if activate_file.exists():
        with open(activate_file, "r+") as f:
            contents = f.read()
            if bin_path not in contents:
                f.write(f'\n# Added by SaxoFlow for {tool_name}\n{export_line}\n')
                print(f"✅ {tool_name} path added to virtual environment activation script.")
    else:
        print(f"⚠  Virtual environment not found — could not persist {tool_name} path.")

def prompt_reinstall(tool, version_info):
    response = input(f"🔁 {tool} is already installed ({version_info}). Reinstall anyway? [y/N]: ").strip().lower()
    return response == "y"

def is_apt_installed(package):
    result = subprocess.run(["dpkg", "-s", package], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0

def is_script_installed(tool):
    user_home = Path.home()
    install_dir = user_home / ".local" / tool / "bin"
    return install_dir.exists()

def get_version_info(tool, path):
    import re
    try:
        version_cmd = [path, "--version"]
        if tool == "iverilog":
            version_cmd = [path, "-v"]
        out = subprocess.run(version_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=5)
        output = out.stdout.strip()
        for line in output.splitlines():
            if tool == "gtkwave" and "GTKWave Analyzer v" in line:
                return line.strip()
            elif tool == "iverilog" and "Icarus Verilog version" in line:
                return line.strip()
            elif tool == "klayout" and "KLayout" in line:
                return line.strip()
            elif tool == "magic" and "Magic" in line:
                return line.strip()
            elif tool == "netgen" and "Netgen" in line:
                return line.strip()
            elif tool == "openfpgaloader" and "openFPGALoader" in line:
                return line.strip()
        for line in output.splitlines():
            if re.search(r"\d+\.\d+", line):
                return line.strip()
    except Exception:
        pass
    return "(version unknown)"

def install_apt(tool):
    if is_apt_installed(tool):
        tool_path = shutil.which(tool)
        version_info = get_version_info(tool, tool_path) if tool_path else "(version unknown)"
        print(f"✅ {tool} already installed via apt: {tool_path} — {version_info}")
        return  # Skip reinstall prompt
    print(f"🔧 Installing {tool} via apt...")
    subprocess.run(["sudo", "apt", "install", "-y", tool], check=True)
    if tool == "code":
        print("💡 Tip: You can run VSCode using 'code' from your terminal.")

def install_script(tool):
    tool_key = tool.lower()
    if is_script_installed(tool_key):
        existing_path = shutil.which(tool_key)
        version_info = get_version_info(tool_key, existing_path) if existing_path else "(version unknown)"
        print(f"✅ {tool} already installed: {existing_path or f'~/.local/{tool_key}/bin'} — {version_info}")
        return  # Skip reinstall prompt
    script_path = Path(SCRIPT_TOOLS[tool])
    if not script_path.exists():
        print(f"❌ Missing installer script: {script_path}")
        return
    print(f"🚀 Installing {tool} via {script_path}...")
    subprocess.run(["bash", str(script_path)], check=True)
    bin_path_map = {
        "verilator": "$HOME/.local/verilator/bin",
        "openroad": "$HOME/.local/openroad/bin",
        "nextpnr": "$HOME/.local/nextpnr/bin",
        "symbiyosys": "$HOME/.local/sby/bin",
        "vivado": "$HOME/.local/vivado/bin",
        "yosys": "$HOME/.local/yosys/bin",
    }
    persist_tool_path(tool.capitalize(), bin_path_map.get(tool, f"$HOME/.local/{tool}/bin"))
    if tool == "yosys":
        persist_tool_path("Slang", "$HOME/.local/slang/bin")


# def install_apt(tool):
#     if is_apt_installed(tool):
#         tool_path = shutil.which(tool)
#         version_info = get_version_info(tool, tool_path) if tool_path else "(version unknown)"
#         print(f"✅ {tool} already installed via apt: {tool_path} — {version_info}")
#         if not prompt_reinstall(tool, version_info):
#             return
#     print(f"🔧 Installing {tool} via apt...")
#     subprocess.run(["sudo", "apt", "install", "-y", tool], check=True)
#     if tool == "code":
#         print("💡 Tip: You can run VSCode using 'code' from your terminal.")

# def install_script(tool):
#     tool_key = tool.lower()
#     if is_script_installed(tool_key):
#         existing_path = shutil.which(tool_key)
#         version_info = get_version_info(tool_key, existing_path) if existing_path else "(version unknown)"
#         print(f"✅ {tool} already installed: {existing_path or f'~/.local/{tool_key}/bin'} — {version_info}")
#         if not prompt_reinstall(tool, version_info):
#             return
#     script_path = Path(SCRIPT_TOOLS[tool])
#     if not script_path.exists():
#         print(f"❌ Missing installer script: {script_path}")
#         return
#     print(f"🚀 Installing {tool} via {script_path}...")
#     subprocess.run(["bash", str(script_path)], check=True)
#     bin_path_map = {
#         "verilator": "$HOME/.local/verilator/bin",
#         "openroad": "$HOME/.local/openroad/bin",
#         "nextpnr": "$HOME/.local/nextpnr/bin",
#         "symbiyosys": "$HOME/.local/sby/bin",
#         "vivado": "$HOME/.local/vivado/bin",
#         "yosys": "$HOME/.local/yosys/bin",
#     }
#     persist_tool_path(tool.capitalize(), bin_path_map.get(tool, f"$HOME/.local/{tool}/bin"))
#     if tool == "yosys":
#         persist_tool_path("Slang", "$HOME/.local/slang/bin")

def install_tool(tool):
    if tool in APT_TOOLS:
        install_apt(tool)
    elif tool in SCRIPT_TOOLS:
        install_script(tool)
    else:
        print(f"⚠ Skipping: No installer defined for '{tool}'")

def install_all():
    print("🚀 Installing ALL known tools...")
    full = APT_TOOLS + list(SCRIPT_TOOLS.keys())
    for tool in full:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            print(f"⚠ Failed installing {tool}")

def install_selected():
    selection = load_user_selection()
    if not selection:
        print("⚠ No saved tool selection found. Run 'saxoflow init-env' first.")
        return
    print(f"🚀 Installing user-selected tools: {selection}")
    for tool in selection:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            print(f"⚠ Failed installing {tool}")

def install_single_tool(tool):
    print(f"🚀 Installing tool: {tool}")
    try:
        install_tool(tool)
    except subprocess.CalledProcessError:
        print(f"❌ Failed to install {tool}")
