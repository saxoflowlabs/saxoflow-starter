# saxoflow/cli.py

import click
from saxoflow.installer.interactive_env import run_interactive_env
from saxoflow.installer import runner
from saxoflow.installer.presets import PRESETS
from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS
from saxoflow.unit_project import unit

# Import per-stage commands from makeflow
from saxoflow.makeflow import (
    sim, sim_verilator, sim_verilator_run,
    wave, wave_verilator,
    simulate, simulate_verilator,  
    formal, synth, clean, check_tools
)
from saxoflow import diagnose  # Full  diagnose group
from saxoflow_agenticai.cli import cli as agenticai_cli # Import agentic AI CLI

@click.group()
def cli():
    """
    🧰 SaxoFlow Unified CLI v1 Professional Edition
    This CLI provides a unified interface for managing EDA toolchains,
    project builds, and AI-assisted workflows.
    """
    pass

# 1️⃣ Environment Initialization (Interactive + Presets)
@cli.command("init-env")
@click.option('--preset', type=click.Choice(list(PRESETS.keys())), help="Initialize with a predefined preset")
@click.option('--headless', is_flag=True, help="Run without user prompts")
def init_env_cmd(preset, headless):
    """Interactive environment configuration"""
    run_interactive_env(preset=preset, headless=headless)

# 2️⃣ Tool Installation Dispatcher
@cli.command("install")
@click.argument("mode", required=False, default="selected")
def install(mode):
    """
    Install EDA toolchains.

    Modes:
      selected       Install tools from last init-env selection
      all            Install all available tools
      <preset>       Install from preset: minimal, fpga, asic, formal, agentic-ai
      <tool>         Install individual tool: iverilog, yosys, etc.
    """
    valid_presets = PRESETS.keys()
    valid_tools = list(APT_TOOLS) + list(SCRIPT_TOOLS.keys())

    if mode == "selected":
        runner.install_selected()
    elif mode == "all":
        runner.install_all()
    elif mode in valid_presets:
        runner.install_preset(mode)
    elif mode in valid_tools:
        runner.install_single_tool(mode)
    else:
        click.echo("❌ Invalid install mode or tool.")
        click.echo("Valid usage:")
        click.echo("  saxoflow install selected")
        click.echo("  saxoflow install all")
        click.echo(f"  saxoflow install <preset>    → {', '.join(valid_presets)}")
        click.echo(f"  saxoflow install <tool>      → {', '.join(valid_tools)}")

# 3️⃣ Attach Full diagnose CLI Group
cli.add_command(diagnose.diagnose, name="diagnose")

# 4️⃣ Project Build System Commands (use from project root)
cli.add_command(unit)
cli.add_command(sim)
cli.add_command(sim_verilator)
cli.add_command(sim_verilator_run)
cli.add_command(wave)
cli.add_command(wave_verilator)
cli.add_command(simulate)         
cli.add_command(simulate_verilator) 
cli.add_command(formal)
cli.add_command(synth)
cli.add_command(clean)
cli.add_command(check_tools)

# 5️⃣ Agentic AI command group
cli.add_command(agenticai_cli, name="agenticai")


# Friendly tip for users if run directly
if __name__ == "__main__":
    # click.echo("💡 Run all SaxoFlow commands from your project root, e.g., 'saxoflow sim'")
    cli()
