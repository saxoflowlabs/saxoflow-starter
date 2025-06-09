import click
from pathlib import Path
import shutil

@click.command()
@click.argument("name")
def init(name):
    """Create a new SaxoFlow project directory structure."""
    root = Path(name)

    # Check if folder exists
    if root.exists():
        click.echo("❗ Project folder already exists.")
        return

    click.echo(f"📁 Creating SaxoFlow project: {name}")
    
    # Define standard project layout
    subdirs = [
        "rtl",            # RTL sources
        "sim",            # Testbenches and test vectors
        "formal",         # Formal verification specs
        "synth",          # Synthesized netlists
        "pnr",            # Place & Route outputs
        "output",         # General output files (bitstreams, GDS, etc.)
        "constraints",    # Timing / placement constraints (SDC, XDC, etc.)
        "logs",           # Log files from tools
        "scripts",        # Project-specific scripts
        "results",        # Reports, metrics
        "docs"            # Documentation
    ]

    for sub in subdirs:
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    # Copy template Makefile if exists
    tpl_make = Path(__file__).parent.parent / "templates" / "Makefile"
    if tpl_make.exists():
        shutil.copy(tpl_make, root / "Makefile")
        click.echo("✅ Template Makefile added.")
    else:
        click.echo("⚠️ Template Makefile not found. You may need to add one manually.")

    click.echo("🎉 Project initialized successfully!")
    click.echo(f"👉 Next: cd {name} && make sim  # or use saxoflow commands")
