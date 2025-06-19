# saxoflow/makeflow.py — v1.2 Makefile Task Wrappers (Pro Style)

import subprocess
import click
import shutil
from pathlib import Path

# --------------------------
# Shared Utils
# --------------------------

def require_makefile():
    if not Path("Makefile").exists():
        click.secho("❌ No Makefile found in this directory.", fg="red")
        raise click.Abort()

def run_make(target: str):
    click.secho(f"🛠️  make {target}", fg="blue")
    subprocess.run(["make", target], check=True)

# --------------------------
# Simulation Targets
# --------------------------

@click.command()
def sim():
    """Run simulation using Icarus Verilog (default backend)."""
    require_makefile()
    click.secho("🧪 Running Icarus Verilog simulation...", fg="cyan")
    run_make("sim")

@click.command()
def sim_verilator():
    """Run simulation using Verilator backend."""
    if not shutil.which("verilator"):
        click.secho("❌ Verilator not found in PATH. Please install it.", fg="red")
        raise click.Abort()
    require_makefile()
    click.secho("⚡ Running Verilator simulation...", fg="cyan")
    run_make("sim-verilator")

# --------------------------
# Waveform Viewer
# --------------------------

@click.command()
def wave():
    """Launch GTKWave viewer."""
    vcd_file = Path("dump.vcd")
    if not vcd_file.exists():
        click.secho("⚠️  dump.vcd not found — you may need to simulate first.", fg="yellow")
    click.secho("📈 Launching GTKWave...", fg="green")
    run_make("wave")

# --------------------------
# Formal Verification
# --------------------------

@click.command()
def formal():
    """Run formal verification using SymbiYosys."""
    sby_files = list(Path("formal").glob("*.sby"))
    if not sby_files:
        click.secho("⚠️  No .sby spec found in ./formal/", fg="yellow")
        raise click.Abort()
    click.secho("📐 Running formal verification via SymbiYosys...", fg="cyan")
    run_make("formal")

# --------------------------
# Clean Target
# --------------------------

@click.command()
def clean():
    """Clean all output and intermediate files."""
    if click.confirm("🧹 Clean all generated files and build artifacts?"):
        run_make("clean")
    else:
        click.echo("❎ Clean canceled.")

# --------------------------
# Tool Check
# --------------------------

@click.command()
def check_tools():
    """Check tool availability in PATH."""
    from saxoflow.tools import TOOL_DESCRIPTIONS

    click.echo("🔍 Checking installed tool availability:\n")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        path = shutil.which(tool)
        status = click.style("✅ FOUND  ", fg="green") if path else click.style("❌ MISSING", fg="red")
        click.echo(f"{tool.ljust(18)} {status} — {desc}")
