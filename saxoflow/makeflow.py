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
    click.echo("🔧 Running Icarus Verilog simulation...")
    subprocess.run(["make", "sim"])

@click.command()
def sim_verilator():
    """Run simulation using Verilator."""
    if not Path("Makefile").exists():
        click.echo("❌ Makefile not found in current directory.")
        return
    click.echo("🔧 Running Verilator simulation...")
    subprocess.run(["make", "sim-verilator"])

@click.command()
def wave():
    """Launch GTKWave viewer."""
    if not Path("dump.vcd").exists():
        click.echo("⚠️ Warning: dump.vcd not found. Did you run simulation?")
    else:
        click.echo("📈 Launching GTKWave...")
    subprocess.run(["make", "wave"])

@click.command()
def formal():
    """Run formal verification using SymbiYosys."""
    sby_files = list(Path("formal").glob("*.sby"))
    if not sby_files:
        click.echo("⚠️ No .sby spec found in ./formal/")
        return
    click.echo("📐 Running formal verification...")
    subprocess.run(["make", "formal"])

@click.command()
def clean():
    """Clean build and output directories."""
    if click.confirm("🧹 Clean all generated files and build artifacts?"):
        subprocess.run(["make", "clean"])
    else:
        click.echo("❎ Clean canceled.")

@click.command()
def check_tools():
    """Check installed tools and report missing ones."""
    from saxoflow.tools import TOOL_DESCRIPTIONS

    click.echo("🔍 Checking tool availability...\n")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        path = shutil.which(tool)
        status = "✅ FOUND " if path else "❌ MISSING"
        click.echo(f"{tool.ljust(18)} {status} — {desc}")
