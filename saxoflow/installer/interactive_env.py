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

    # --- PATCHED: block interactive mode in Cool CLI ---
    in_cool_cli = os.environ.get("SAXOFLOW_FORCE_HEADLESS") == "1"
    if in_cool_cli and not preset:
        click.echo("⚠️  Interactive environment setup is not supported in SaxoFlow Cool CLI shell.")
        click.echo("\n[Usage] Please use one of the following supported commands:\n")
        click.echo("  saxoflow init-env --preset <preset>")
        click.echo("  saxoflow install")
        click.echo("  saxoflow install all")
        click.echo("\nSupported presets:")
        for pname in PRESETS:
            click.echo(f"  saxoflow init-env --preset {pname}")
        click.echo("\nTip: To see available presets, run: saxoflow init-env --help\n")
        return

    # The rest of your function (unchanged)...
    selected = None
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
            sims = questionary.checkbox(
                "🧪 Select simulation tools:", choices=ALL_TOOL_GROUPS["simulation"]
            ).ask() or []
            selected.extend(sims)
        else:
            selected.extend(ALL_TOOL_GROUPS["formal"])

        base = questionary.checkbox(
            "🧱 Select waveform viewer & synthesis tools:", choices=ALL_TOOL_GROUPS["base"]
        ).ask() or []
        selected.extend(base)

        # Backend tools
        if target == "FPGA":
            fpgas = questionary.checkbox(
                "🧰 Select FPGA tools:", choices=ALL_TOOL_GROUPS["fpga"]
            ).ask() or []
            selected.extend(fpgas)
        else:
            asics = questionary.checkbox(
                "🏭 Select ASIC tools:", choices=ALL_TOOL_GROUPS["asic"]
            ).ask() or []
            selected.extend(asics)

        # AI extension
        if questionary.confirm("🤖 Enable Agentic AI Extensions?").ask():
            selected.extend(ALL_TOOL_GROUPS["agentic-ai"])

    # 🛑 Abort if custom mode and nothing selected
    if not preset and not headless and (not selected or len(selected) == 0):
        click.echo("\n⚠️  No tools were selected. Aborting configuration.")
        return

    # Deduplicate and sort only if selected is set
    selected = sorted(set(selected))

    dump_tool_selection(selected)

    click.echo("\n📦 Final tool selection:")
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "(no description)")
        click.echo(f"  - {tool}: {desc}")

    click.echo("\n✅ Saved selection. Next run:")
    click.echo("saxoflow install          # Install selected tools")
    click.echo("saxoflow install all      # Install all tools (⚠ advanced mode)")
