# saxoflow/init_project.py — v1.2 Pro Project Bootstrapper

import click
from pathlib import Path
import shutil
import sys

PROJECT_STRUCTURE = [
    "rtl", "sim", "formal", "synth", "pnr", "constraints", "logs", "scripts", "spec"
]

@click.command()
@click.argument("name", required=True)
def init(name):
    """📁 Create a new SaxoFlow-compatible project structure."""
    root = Path(name)

    if root.exists():
        click.secho("❗ Project folder already exists. Aborting.", fg="red")
        sys.exit(1)

    click.secho(f"📂 Initializing project: {name}", fg="green")
    root.mkdir(parents=True)

    # Create subdirectories and add .gitkeep
    for sub in PROJECT_STRUCTURE:
        path = root / sub
        path.mkdir(parents=True)
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
    click.secho(f"👉 Next: cd {name} && make sim", fg="blue")
