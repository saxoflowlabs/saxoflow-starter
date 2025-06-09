import click
from pathlib import Path
import shutil

@click.command()
@click.argument("name")
def init(name):
    """Create new project folder structure."""
    root = Path(name)
    if root.exists():
        click.echo("❗ Project folder already exists.")
        return

    click.echo(f"📁 Creating project folder: {name}")
    subdirs = [
        "rtl", "sim", "formal", "synth", "pnr", "output",
        "constraints", "logs", "scripts", "results", "docs"
    ]

    for sub in subdirs:
        path = root / sub
        path.mkdir(parents=True)
        (path / ".gitkeep").touch()

    tpl_make = Path(__file__).parent.parent / "templates" / "Makefile"
    if tpl_make.exists():
        shutil.copy(tpl_make, root / "Makefile")
    else:
        click.echo("⚠️ Template Makefile not found. You may need to add one manually.")
