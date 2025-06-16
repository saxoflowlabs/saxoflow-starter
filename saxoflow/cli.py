# saxoflow/cli.py

import click
from saxoflow.interactive_env import run_interactive_env
from saxoflow.installer import runner
from saxoflow.makeflow import sim, wave, formal, clean
from saxoflow import doctor  # ✅ Doctor v2 group import

@click.group()
def cli():
    """🧰 SaxoFlow Unified CLI v0.4.2 Pro-Stable"""
    pass

# 1️⃣ Interactive Environment Setup
@cli.command("init-env")
@click.option('--preset', type=click.Choice(["minimal", "fpga", "asic", "formal", "full"]))
@click.option('--headless', is_flag=True)  # ✅ correctly closed quotes
def init_env_cmd(preset, headless):
    """Interactive environment configuration"""
    run_interactive_env(preset=preset, headless=headless)

# 2️⃣ Install Logic (selected/all)
@cli.command("install")
@click.argument("mode", required=False, default="selected")
def install(mode):
    """Install EDA toolchains"""
    if mode == "selected":
        runner.install_selected()
    elif mode == "all":
        runner.install_all()
    else:
        click.echo("❌ Invalid mode. Usage: saxoflow install [selected|all]")

# 3️⃣ Attach full Doctor group
cli.add_command(doctor.doctor, name="doctor")

# 4️⃣ Build System Commands
cli.add_command(sim)
cli.add_command(wave)
cli.add_command(formal)
cli.add_command(clean)
