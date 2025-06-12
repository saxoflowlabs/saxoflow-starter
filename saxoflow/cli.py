# saxoflow/cli.py

import click
from saxoflow.interactive_env import run_interactive_env
from saxoflow.installer.runner import install_tool, install_all
from saxoflow.init_project import init as init_project
from saxoflow.makeflow import sim, wave, formal, clean
from saxoflow.doctor import doctor  # <-- doctor is a click.command

@click.group()
def cli():
    """🧰 SaxoFlow Unified CLI (v0.3 Stable)"""
    pass

@cli.command("init-env")
@click.option('--headless', is_flag=True, help="Non-interactive default setup")
@click.option('--preset', type=click.Choice(["minimal", "full", "custom"]), help="Predefined selection")
def init_env_cmd(headless, preset):
    """Interactive environment setup"""
    run_interactive_env(headless=headless, preset=preset)
    click.echo("\n📝 Tool selection saved. You can now run: saxoflow install all")

@cli.command("install")
@click.argument("tools", nargs=-1)
def install(tools):
    """Install selected tool(s)"""
    if not tools or "all" in tools:
        install_all()
    else:
        for tool in tools:
            install_tool(tool)

@cli.command("init")
@click.argument("name")
def init_project_cmd(name):
    """Create new SaxoFlow project"""
    init_project.main(name=name)

# Inject directly all Makefile flow helpers
cli.add_command(sim)
cli.add_command(wave)
cli.add_command(formal)
cli.add_command(clean)

# ✅ Directly register doctor command here:
cli.add_command(doctor)
