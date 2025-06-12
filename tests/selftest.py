# tests/selftest.py

import os
import subprocess
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def log(msg):
    print(f"[SELFTEST] {msg}")

def check_imports():
    try:
        import saxoflow
        from saxoflow import cli
        from saxoflow.installer import runner
        from saxoflow.tools import definitions
        from saxoflow import interactive_env
        log("✅ Python package imports successful")
    except Exception as e:
        log(f"❌ Import failed: {e}")
        sys.exit(1)

def check_cli():
    result = subprocess.run(
        [sys.executable, "-m", "saxoflow.cli", "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        log(f"❌ CLI failed: {result.stderr.decode()}")
        sys.exit(1)
    log("✅ CLI entry point works")

def check_tool_groups():
    from saxoflow.tools.definitions import ALL_TOOLS, SCRIPT_TOOLS

    missing = []
    for tool, script in SCRIPT_TOOLS.items():
        if not Path(script).exists():
            missing.append(tool)
    if missing:
        log(f"❌ Missing installer scripts: {missing}")
        sys.exit(1)

    log("✅ All installer recipes exist")

def simulate_json_write():
    dummy_selection = ["iverilog", "yosys", "gtkwave", "nextpnr", "vscode"]
    json_path = PROJECT_ROOT / ".saxoflow_tools.json"
    with open(json_path, "w") as f:
        json.dump(dummy_selection, f, indent=2)
    log(f"✅ Simulated .saxoflow_tools.json written")

    with open(json_path, "r") as f:
        readback = json.load(f)
    if readback != dummy_selection:
        log("❌ JSON file readback mismatch!")
        sys.exit(1)

    log("✅ JSON content verified")

def verify_recipe_dispatch():
    from saxoflow.installer import runner
    for tool in runner.SCRIPT_TOOLS.keys():
        script_path = Path(runner.SCRIPT_TOOLS[tool])
        if not script_path.exists():
            log(f"❌ Dispatch failure: missing {script_path}")
            sys.exit(1)
    log("✅ Recipe dispatch fully verified")

def check_env_selections():
    from saxoflow import interactive_env
    minimal = interactive_env.get_minimal_selection()
    full = interactive_env.get_full_selection()
    if not minimal or not full:
        log("❌ Preset selection returned empty list.")
        sys.exit(1)
    log("✅ Preset selection logic works")

def run_selftest():
    log("====== SaxoFlow SelfTest Started ======")
    check_imports()
    check_cli()
    check_tool_groups()
    simulate_json_write()
    verify_recipe_dispatch()
    check_env_selections()
    log("====== ALL TESTS PASSED SUCCESSFULLY ======")

if __name__ == "__main__":
    run_selftest()
