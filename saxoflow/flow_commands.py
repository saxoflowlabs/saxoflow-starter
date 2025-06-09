import subprocess
import click
import shutil
from pathlib import Path

@click.command()
def sim():
    """Run simulation using Icarus Verilog."""
    if not Path("Makefile").exists():
        click.echo("❌ Makefile not found in current directory.")
        return
    subprocess.run(["make", "sim"])

@click.command()
def sim_verilator():
    """Run simulation using Verilator."""
    if not Path("Makefile").exists():
        click.echo("❌ Makefile not found in current directory.")
        return
    subprocess.run(["make", "sim-verilator"])

@click.command()
def wave():
    """Launch GTKWave."""
    if not Path("dump.vcd").exists():
        click.echo("⚠️ Warning: dump.vcd not found. Make sure simulation was run first.")
    subprocess.run(["make", "wave"])

@click.command()
def formal():
    """Run formal verification with SymbiYosys."""
    if not list(Path("formal").glob("*.sby")):
        click.echo("⚠️ No .sby formal verification spec found in ./formal/")
        return
    subprocess.run(["make", "formal"])

@click.command()
def clean():
    """Clean build artifacts."""
    click.confirm("🧹 Confirm clean build artifacts?", abort=True)
    subprocess.run(["make", "clean"])

@click.command()
def check_tools():
    """Check if required tools are installed."""
    from saxoflow.tools import TOOL_DESCRIPTIONS

    click.echo("🔍 Checking installed tools:\n")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        result = shutil.which(tool)
        status = "✅ FOUND" if result else "❌ MISSING"
        click.echo(f"{tool.ljust(16)} {status} - {desc}")
