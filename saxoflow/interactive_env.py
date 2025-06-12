# saxoflow/interactive_env.py

import click
import questionary
import json
from collections import defaultdict
from pathlib import Path
from saxoflow.tools.definitions import TOOL_DESCRIPTIONS

# ------------------- Tool groups -------------------

SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["yosys", "gtkwave"]
IDE_TOOLS = ["vscode"]

# ------------------- Logic functions -------------------

def dump_tool_selection(selected):
    out_path = Path(".saxoflow_tools.json")
    with out_path.open("w") as f:
        json.dump(selected, f, indent=2)

def display_summary(selected):
    click.echo("\n📦 Tools selected:")
    buckets = defaultdict(list)
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "")
        stage = desc.split("]")[0].strip("[")
        buckets[stage].append((tool, desc))
    for stage in sorted(buckets):
        click.echo(f"\n🔹 {stage} Tools:")
        for tool, desc in buckets[stage]:
            click.echo(f"  - {tool}: {desc}")

def run_interactive_env(headless=False, preset=None):
    click.echo("🔧 SaxoFlow Environment Setup")

    if preset == "minimal" or headless:
        selected = ["iverilog"] + BASE_TOOLS + ["nextpnr", "vscode"]
    elif preset == "full":
        selected = SIM_TOOLS + FORMAL_TOOLS + BASE_TOOLS + FPGA_TOOLS + ASIC_TOOLS + IDE_TOOLS
    else:
        target = questionary.select("🎯 Target device?", choices=["FPGA", "ASIC"]).ask()
        verif_strategy = questionary.select("🧠 Verification strategy?", choices=["Simulation-Based Verification", "Formal Verification"]).ask()

        if verif_strategy == "Simulation-Based Verification":
            selected_verif = questionary.checkbox("🧪 Select simulation tools:", choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in SIM_TOOLS]).ask()
            selected_verif = [t.split(" — ")[0] for t in selected_verif]
        else:
            selected_verif = FORMAL_TOOLS

        vscode_choice = questionary.confirm("📝 Install VSCode IDE?").ask()

        if target == "FPGA":
            selected_extra = questionary.checkbox("🧰 Select FPGA tools:", choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in FPGA_TOOLS]).ask()
        else:
            selected_extra = questionary.checkbox("🏭 Select ASIC tools:", choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in ASIC_TOOLS]).ask()

        selected_extra = [t.split(" — ")[0] for t in selected_extra]
        if vscode_choice:
            selected_extra.append("vscode")

        selected = selected_verif + BASE_TOOLS + selected_extra

    selected = list(dict.fromkeys(selected))

    if not selected:
        click.echo("⚠️ No tools selected. Aborting.")
        return

    dump_tool_selection(selected)
    display_summary(selected)

    click.confirm("\n➡️ Confirm selection?", abort=True)

    click.echo("\n✅ Tool selection complete. Now run:")
    click.echo("saxoflow install <tool> or saxoflow install all")

# ------------------- Click CLI entry point -------------------

@click.command()
@click.option('--headless', is_flag=True)
@click.option('--preset', type=click.Choice(["minimal", "full", "custom"]))
def init_env(headless, preset):
    run_interactive_env(headless, preset)
