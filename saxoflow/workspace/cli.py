"""CLI bindings for the M2 workspace contract."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .lockfiles import write_lockfiles
from .migrate import load_legacy_selection, migrate_legacy_workspace, sync_workspace_selection
from .schema import load_project_data, workspace_paths
from .validate import format_validation_report, validate_workspace


@click.group("workspace")
def workspace_group() -> None:
    """Manage SaxoFlow workspace contracts and lockfiles."""


@workspace_group.command("init")
@click.option("--name", default=None, help="Workspace name override (defaults to cwd name).")
def workspace_init(name: str | None) -> None:
    """Initialize `.saxoflow` project metadata and placeholder lockfiles."""
    root = Path.cwd()
    created_files = sync_workspace_selection(
        root,
        load_legacy_selection(root),
        project_name=name or root.name,
    )
    click.secho("SUCCESS: Workspace contract initialized.", fg="green")
    for file_path in created_files:
        click.echo(f"  - {file_path}")


@workspace_group.command("migrate")
@click.option("--no-backup", is_flag=True, help="Skip backup of legacy .saxoflow_tools.json.")
def workspace_migrate(no_backup: bool) -> None:
    """Migrate legacy workspace state into `.saxoflow` contract files."""
    result = migrate_legacy_workspace(Path.cwd(), backup=not no_backup)
    click.secho("SUCCESS: Workspace migration completed.", fg="green")
    if result.backup_file:
        click.echo(f"Backup: {result.backup_file}")
    if result.selected_tools:
        click.echo(f"Migrated tools: {', '.join(result.selected_tools)}")
    for file_path in result.created_files:
        click.echo(f"  - {file_path}")


@workspace_group.command("lock")
def workspace_lock() -> None:
    """Regenerate workspace lockfiles from `project.yaml`."""
    project_data = load_project_data(Path.cwd())
    if project_data is None:
        click.secho("ERROR: Missing .saxoflow/project.yaml. Run 'saxoflow workspace init' first.", fg="red")
        sys.exit(1)

    toolchain_path, models_path = write_lockfiles(Path.cwd(), project_data)
    click.secho("SUCCESS: Workspace lockfiles refreshed.", fg="green")
    click.echo(f"  - {toolchain_path}")
    click.echo(f"  - {models_path}")


@workspace_group.command("validate")
def workspace_validate() -> None:
    """Validate workspace contract structure and lockfile consistency."""
    result = validate_workspace(Path.cwd())
    click.echo(format_validation_report(result))
    paths = workspace_paths(Path.cwd())
    click.echo(f"Project file: {paths.project_file}")
    click.echo(f"Toolchain lock: {paths.toolchain_lock_file}")
    click.echo(f"Models lock: {paths.models_lock_file}")
    if not result.is_valid:
        sys.exit(1)