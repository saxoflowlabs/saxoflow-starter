import click
from pathlib import Path
import shutil
import sys

PROJECT_STRUCTURE = [
    "source/specification",
    "source/rtl/verilog",
    "source/rtl/vhdl",
    "source/rtl/systemverilog",
    "simulation/icarus",
    "simulation/verilator",
    "synthesis/src",
    "synthesis/scripts",
    "synthesis/reports",
    "synthesis/out",
    "formal/src",
    "formal/scripts",
    "formal/reports",
    "formal/out",
    "constraints",
    "pnr"
]

@click.command()
@click.argument("name", required=True)
def unit(name):
    """📁 Create a new SaxoFlow professional project structure."""
    root = Path(name)

    if root.exists():
        click.secho("❗ Project folder already exists. Aborting.", fg="red")
        sys.exit(1)

    click.secho(f"📂 Initializing project: {name}", fg="green")
    root.mkdir(parents=True)

    # Create subdirectories and add .gitkeep
    for sub in PROJECT_STRUCTURE:
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    # Copy base Makefile template if available
    template_path = Path(__file__).parent.parent / "templates" / "Makefile"
    if template_path.exists():
        shutil.copy(template_path, root / "Makefile")
        click.secho("✅ Makefile template added.", fg="cyan")
    else:
        click.secho("⚠️ Makefile template not found. Please add one manually.", fg="yellow")

    # Final summary
    click.secho("🎉 Project initialized successfully!", fg="green", bold=True)
    click.secho(f"👉 Next: cd {name} && make sim-icarus", fg="blue")
