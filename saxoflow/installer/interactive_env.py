# saxoflow/installer/interactive_env.py
import os
import click
import questionary
import json
from pathlib import Path
from saxoflow.tools.definitions import TOOL_DESCRIPTIONS
from saxoflow.installer.presets import PRESETS, ALL_TOOL_GROUPS

def dump_tool_selection(selected):
    out_path = Path(".saxoflow_tools.json")
    with out_path.open("w") as f:
        json.dump(selected, f, indent=2)

def load_tool_selection():
    try:
        with open(".saxoflow_tools.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def run_interactive_env(preset=None, headless=False):
    click.echo("🔧 SaxoFlow Pro Interactive Setup")

    # Force fallback if run inside Cool CLI or testing shell
    if os.environ.get("SAXOFLOW_FORCE_HEADLESS") == "1":
        click.echo("⚠️  Running inside Cool CLI. Forcing headless mode.")
        headless = True

    if preset:
        if preset not in PRESETS:
            click.echo(f"❌ Invalid preset '{preset}'. Please check available presets.")
            return

        selected = PRESETS[preset]
        click.echo(f"✅ Preset '{preset}' selected: {selected}")

    elif headless:
        selected = PRESETS["minimal"]
        click.echo("✅ Headless mode: minimal tools selected.")

    else:
        # Full interactive custom environment builder
        target = questionary.select("🎯 Target device?", choices=["FPGA", "ASIC"]).ask()
        if target is None:
            click.echo("❌ Aborted by user.")
            return

        verif = questionary.select("🧪 Verification strategy?", choices=["Simulation", "Formal"]).ask()
        if verif is None:
            click.echo("❌ Aborted by user.")
            return

        selected = []

        if questionary.confirm("📝 Install VSCode IDE?").ask():
            selected.extend(ALL_TOOL_GROUPS["ide"])

        # Verification tools
        if verif == "Simulation":
            sims = questionary.checkbox("🧪 Select simulation tools:", choices=ALL_TOOL_GROUPS["simulation"]).ask() or []
            selected.extend(sims)
        else:
            selected.extend(ALL_TOOL_GROUPS["formal"])

        base = questionary.checkbox("🧱 Select waveform viewer & synthesis tools:", choices=ALL_TOOL_GROUPS["base"]).ask() or []
        selected.extend(base)

        # Backend tools
        if target == "FPGA":
            fpgas = questionary.checkbox("🧰 Select FPGA tools:", choices=ALL_TOOL_GROUPS["fpga"]).ask() or []
            selected.extend(fpgas)
        else:
            asics = questionary.checkbox("🏭 Select ASIC tools:", choices=ALL_TOOL_GROUPS["asic"]).ask() or []
            selected.extend(asics)
    
        # AI extension
        if questionary.confirm("🤖 Enable Agentic AI Extensions?").ask():
            selected.extend(ALL_TOOL_GROUPS["agentic-ai"])


    selected = sorted(set(selected))

    # 🛑 Abort if custom mode and nothing selected
    if not preset and not headless and not selected:
        click.echo("\n⚠️  No tools were selected. Aborting configuration.")
        return

    dump_tool_selection(selected)

    click.echo("\n📦 Final tool selection:")
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "(no description)")
        click.echo(f"  - {tool}: {desc}")

    click.echo("\n✅ Saved selection. Next run:")
    click.echo("saxoflow install          # Install selected tools")
    click.echo("saxoflow install all      # Install all tools (⚠ advanced mode)")
