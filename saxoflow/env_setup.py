import subprocess
import click
import questionary
import shutil
import logging
import json
from collections import defaultdict
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
    "vscode": "scripts/install_vscode.sh"
}

# Logging setup
logging.basicConfig(
    filename="saxoflow-install.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)

@click.command()
@click.option('--headless', is_flag=True, help="Run without prompts (default: minimal FPGA + iverilog + vscode)")
@click.option('--preset', type=click.Choice(["minimal", "full", "custom"]), help="Predefined tool selections")
def init_env(headless, preset):
    """Interactive or preset-based environment setup."""
    click.echo("🔧 SaxoFlow Environment Setup")

    # ---- Preset/Headless Selections ---- #
    if preset == "minimal" or headless:
        target = "FPGA"
        selected_verif = ["iverilog"]
        selected_extra = ["nextpnr", "vscode"]
        selected = selected_verif + BASE_TOOLS + selected_extra

    elif preset == "full":
        selected = SIM_TOOLS + FORMAL_TOOLS + BASE_TOOLS + FPGA_TOOLS + ASIC_TOOLS + IDE_TOOLS

    else:
        # Interactive Custom Mode
        target = questionary.select(
            "🎯 What is your target device?",
            choices=["FPGA", "ASIC"]
        ).ask()

        verif_strategy = questionary.select(
            "🧠 What is your verification strategy?",
            choices=["Simulation-Based Verification", "Formal Verification"]
        ).ask()

        if verif_strategy == "Simulation-Based Verification":
            selected_verif = questionary.checkbox(
                "🧪 Select simulation tools:",
                choices=SIM_TOOLS
            ).ask()
        else:
            selected_verif = FORMAL_TOOLS

        if target == "FPGA":
            selected_extra = questionary.checkbox(
                "🧰 Select FPGA tools:",
                choices=FPGA_TOOLS + IDE_TOOLS
            ).ask()
        else:
            selected_extra = questionary.checkbox(
                "🏭 Select ASIC tools:",
                choices=ASIC_TOOLS + IDE_TOOLS
            ).ask()

        selected = selected_verif + BASE_TOOLS + selected_extra

    # Remove duplicates
    selected = list(dict.fromkeys(selected))

    if not selected:
        click.echo("⚠️ No tools selected. Aborting.")
        return

    # Export selected tools
    logging.info(f"Selected tools: {selected}")
    with open(".saxoflow_tools.json", "w") as f:
        json.dump(selected, f, indent=2)

    # Display grouped summary
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

    if not headless and not preset:
        click.confirm("\n➡️ Proceed with installation?", abort=True)

    # ---- APT Installation ---- #
    apt_tools = [t for t in selected if t not in SCRIPT_TOOLS]
    if apt_tools:
        click.echo("\n📦 Installing APT tools...")
        try:
            subprocess.run(["sudo", "apt", "update"], check=True)
            subprocess.run(["sudo", "apt", "install", "-y"] + apt_tools, check=True)
        except subprocess.CalledProcessError as e:
            click.echo(f"❌ APT install failed: {e}")
            logging.error(f"APT failed: {e}")
            return

    # ---- Script-based Tools ---- #
    for tool, script in SCRIPT_TOOLS.items():
        if tool in selected:
            if shutil.which(tool):
                click.echo(f"✅ {tool} already installed, skipping...")
                continue

            if tool == "openroad" and not headless and preset != "full":
                click.confirm("⚠️ OpenROAD takes 15–30 mins. Continue?", abort=True)

            click.echo(f"⚙️ Installing {tool} via {script}...")
            logging.info(f"Running {script}")
            try:
                subprocess.run(["bash", script], check=True)
            except subprocess.CalledProcessError as e:
                click.echo(f"❌ Script failed for {tool}: {e}")
                logging.error(f"{tool} script failed: {e}")

    click.echo("\n✅ SaxoFlow environment setup complete!")
    logging.info("Environment setup complete.")

@click.command(name="target-device")
def target_device():
    """Alias for init-env."""
    init_env()
