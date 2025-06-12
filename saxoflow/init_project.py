import click
from pathlib import Path
import shutil

@click.command()
@click.argument("name", required=True)
def init(name):
    """Create a new SaxoFlow project directory structure."""
    root = Path(name)

    if root.exists():
        click.echo("❗ Project folder already exists.")
        return

    click.echo(f"📁 Creating SaxoFlow project: {name}")

    subdirs = [
        "rtl", "sim", "formal", "synth", "pnr",
        "output", "constraints", "logs", "scripts",
        "results", "docs"
    ]

    for sub in subdirs:
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    # Simple Makefile copy (keep your old method for now)
    tpl_make = Path(__file__).parent.parent / "templates" / "Makefile"
    if tpl_make.exists():
        shutil.copy(tpl_make, root / "Makefile")
        click.echo("✅ Template Makefile added.")
    else:
        click.echo("⚠️ Template Makefile not found. You may need to add one manually.")

    click.echo("🎉 Project initialized successfully!")
    click.echo(f"👉 Next: cd {name} && make sim  # or use saxoflow commands")
