# saxoflow/cli.py

import click
from saxoflow.interactive_env import run_interactive_env
from saxoflow.installer.runner import install_tool, install_all

@click.group()
def cli():
    """SaxoFlow unified CLI"""
    pass

@cli.command("init-env")
@click.option('--headless', is_flag=True, help="Run non-interactive minimal mode")
@click.option('--preset', type=click.Choice(["minimal", "full", "custom"]), help="Predefined install profile")
def init_env_cmd(headless, preset):
    """Interactive environment setup"""
    run_interactive_env(headless=headless, preset=preset)
    click.echo("\n📝 Tool selection saved. To install:")
    click.echo("saxoflow install all   # installs selected tools")

@cli.command("install")
@click.argument("tools", nargs=-1)
def install(tools):
    """Install selected tool(s)"""
    if not tools or "all" in tools:
        install_all()
    else:
        for tool in tools:
            install_tool(tool)
