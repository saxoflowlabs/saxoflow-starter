import subprocess
import click
import questionary
import shutil
import logging
import json
from collections import defaultdict
from pathlib import Path
from saxoflow.tools import TOOL_DESCRIPTIONS

# ---------------------- #
# Tool Groups
# ---------------------- #
SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["yosys", "gtkwave"]
IDE_TOOLS = ["vscode"]

# Tools that require scripts
SCRIPT_TOOLS = {
    "verilator": "scripts/install_verilator.sh",
    "openroad": "scripts/install_openroad.sh",
    "vscode": "scripts/install_vscode.sh",
    "nextpnr": "scripts/install_nextpnr.sh",
    "symbiyosys": "scripts/install_symbiyosys.sh"
}

# Logging
logging.basicConfig(
    filename="saxoflow-install.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

def dump_tool_selection(selected):
    out_path = Path(".saxoflow_tools.json")
    with out_path.open("w") as f:
        json.dump(selected, f, indent=2)
    logging.info(f"Selected tools: {selected}")

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

def install_apt_tools(tools):
    if tools:
        click.echo("\n📦 Installing APT tools...")
        try:
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y"] + tools, check=True)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ APT install failed: {e}")
            logging.error(f"APT failed: {e}")

def install_script_tools(selected):
    for tool, script in SCRIPT_TOOLS.items():
        if tool in selected:
            if shutil.which(tool):
                click.echo(f"✅ {tool} already installed, skipping...")
                continue

            if tool == "openroad":
                click.confirm("⚠️ OpenROAD takes 15–30 mins. Continue?", abort=True)

            if tool == "symbiyosys":
                click.echo("ℹ️ symbiyosys will be built from source and requires yosys.")

            click.echo(f"⚙️ Installing {tool} via {script}...")
            logging.info(f"Running {script}")
            try:
                subprocess.run(["bash", script], check=True)
            except subprocess.CalledProcessError as e:
                click.echo(f"❌ Script failed for {tool}: {e}")
                logging.error(f"{tool} script failed: {e}")

@click.command()
@click.option('--headless', is_flag=True, help="Run without prompts (default: minimal FPGA + iverilog + vscode)")
@click.option('--preset', type=click.Choice(["minimal", "full", "custom"]), help="Predefined tool selections")
def init_env(headless, preset):
    """Interactive or preset-based environment setup."""
    click.echo("🔧 SaxoFlow Environment Setup")

    if preset == "minimal" or headless:
        selected = ["iverilog"] + BASE_TOOLS + ["nextpnr", "vscode"]
    elif preset == "full":
        selected = SIM_TOOLS + FORMAL_TOOLS + BASE_TOOLS + FPGA_TOOLS + ASIC_TOOLS + IDE_TOOLS
    else:
        target = questionary.select("🎯 What is your target device?", choices=["FPGA", "ASIC"]).ask()
        verif_strategy = questionary.select(
            "🧠 What is your verification strategy?",
            choices=["Simulation-Based Verification", "Formal Verification"]
        ).ask()

        if verif_strategy == "Simulation-Based Verification":
            selected_verif = questionary.checkbox(
                "🧪 Select simulation tools:",
                choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in SIM_TOOLS]
            ).ask()
            selected_verif = [t.split(" — ")[0] for t in selected_verif]
        else:
            selected_verif = FORMAL_TOOLS

        vscode_choice = questionary.confirm("📝 Do you want to install VSCode as your RTL editing IDE?").ask()

        if target == "FPGA":
            selected_extra = questionary.checkbox(
                "🧰 Select FPGA tools:",
                choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in FPGA_TOOLS]
            ).ask()
        else:
            selected_extra = questionary.checkbox(
                "🏭 Select ASIC tools:",
                choices=[f"{t} — {TOOL_DESCRIPTIONS[t]}" for t in ASIC_TOOLS]
            ).ask()

        selected_extra = [t.split(" — ")[0] for t in selected_extra]
        if vscode_choice:
            selected_extra.append("vscode")

        selected = selected_verif + BASE_TOOLS + selected_extra

    # Remove duplicates
    selected = list(dict.fromkeys(selected))

    if not selected:
        click.echo("⚠️ No tools selected. Aborting.")
        return

    dump_tool_selection(selected)
    display_summary(selected)

    if not headless and not preset:
        click.confirm("\n➡️ Proceed with installation?", abort=True)

    install_apt_tools([t for t in selected if t not in SCRIPT_TOOLS])
    install_script_tools(selected)

    click.echo("\n✅ SaxoFlow environment setup complete!")
    logging.info("Environment setup complete.")
    click.echo("🌟 SaxoFlow is now ready for RTL design and verification!")
    click.echo("👉 Next step: Start with 'saxoflow init my_project' and explore the flow.")

@click.command(name="target-device")
def target_device():
    """Alias for init-env."""
    init_env()
