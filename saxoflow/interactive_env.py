import click
import questionary
import json
from collections import defaultdict
from pathlib import Path
from saxoflow.tools.definitions import TOOL_DESCRIPTIONS, ALL_TOOLS

# -----------------------
# Full tool groupings 
# (redundant in long-term, but kept for full CLI decoupling)
# -----------------------
SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["yosys", "gtkwave", "yosys_slang"]   # <-- PATCHED HERE
IDE_TOOLS = ["vscode"]

# -----------------------
# Preset modes (aligned to CLI presets)
# -----------------------
PRESETS = {
    "minimal": ["iverilog", "yosys", "gtkwave"],  # keep minimal as-is for simplicity
    "fpga": ["iverilog", "yosys", "gtkwave", "nextpnr", "openfpgaloader", "yosys_slang"],  # add slang to FPGA preset
    "asic": ["iverilog", "yosys", "gtkwave", "openroad", "klayout", "magic", "netgen", "yosys_slang"],  # add slang here too
    "formal": ["iverilog", "yosys", "gtkwave", "symbiyosys", "yosys_slang"],  # slang also useful for formal flows
    "full": SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + IDE_TOOLS  # fully automatic inclusion
}


# -----------------------
# Save tool selection
# -----------------------
def dump_tool_selection(selected):
    out_path = Path(".saxoflow_tools.json")
    with out_path.open("w") as f:
        json.dump(selected, f, indent=2)

# -----------------------
# Load prior selection (if needed elsewhere)
# -----------------------
def load_tool_selection():
    try:
        with open(".saxoflow_tools.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# -----------------------
# Main interactive env entry
# -----------------------
def run_interactive_env(preset=None, headless=False):
    click.echo("🔧 SaxoFlow Pro Interactive Setup")

    if preset:
        selected = PRESETS.get(preset, [])
        click.echo(f"✅ Preset '{preset}' selected: {selected}")

    elif headless:
        selected = PRESETS["minimal"]
        click.echo("✅ Headless mode: minimal tools selected.")

    else:
        target = questionary.select("🎯 Target device?", choices=["FPGA", "ASIC"]).ask()
        if target is None:
            click.echo("❌ Aborted by user."); return

        verif = questionary.select("🧪 Verification strategy?", choices=["Simulation", "Formal"]).ask()
        if verif is None:
            click.echo("❌ Aborted by user."); return

        selected = BASE_TOOLS.copy()

        if verif == "Simulation":
            sims = questionary.checkbox("🧪 Select simulation tools:", choices=SIM_TOOLS).ask() or []
            selected.extend(sims)
        else:
            selected.extend(FORMAL_TOOLS)

        if target == "FPGA":
            fpgas = questionary.checkbox("🧰 Select FPGA tools:", choices=FPGA_TOOLS).ask() or []
            selected.extend(fpgas)
        else:
            asics = questionary.checkbox("🏭 Select ASIC tools:", choices=ASIC_TOOLS).ask() or []
            selected.extend(asics)

        if questionary.confirm("📝 Install VSCode?").ask():
            selected.append("vscode")

    # Deduplicate and sanitize
    selected = sorted(list(set(selected)))

    dump_tool_selection(selected)
    click.echo("\n📦 Final tool selection:")
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "(no description)")
        click.echo(f"  - {tool}: {desc}")

    click.echo("\n✅ Saved selection. Next run:")
    click.echo("saxoflow install          # Install selected tools")
    click.echo("saxoflow install all      # Install all recipes (⚠ advanced)")
