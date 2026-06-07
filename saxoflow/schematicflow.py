"""Render Yosys JSON netlists as SVG schematics with NetlistSVG."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Sequence

import click

DEFAULT_INPUT = "synthesis/out/synthesized.json"
DEFAULT_OUTPUT = "synthesis/reports/schematic.svg"


def _project_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _resolve_path(root: Path, raw_path: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    return expanded if expanded.is_absolute() else root / expanded


def find_netlistsvg() -> Optional[str]:
    """Find NetlistSVG in PATH or SaxoFlow's managed user prefix."""
    found = shutil.which("netlistsvg")
    if found:
        return found

    managed = Path.home() / ".local/netlistsvg/bin/netlistsvg"
    if managed.is_file() and os.access(str(managed), os.X_OK):
        return str(managed)
    return None


def _is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        if "microsoft" in platform.uname().release.lower():
            return True
        return "microsoft" in Path("/proc/version").read_text(
            encoding="utf-8",
            errors="ignore",
        ).lower()
    except OSError:
        return False


def _viewer_commands(path: Path) -> list[list[str]]:
    """Return viewer commands in platform-appropriate priority order."""
    absolute = str(path.resolve())
    commands: list[list[str]] = []

    if _is_wsl():
        wslview = shutil.which("wslview")
        if wslview:
            commands.append([wslview, absolute])

        wslpath = shutil.which("wslpath")
        if wslpath:
            try:
                converted = subprocess.run(
                    [wslpath, "-w", absolute],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                windows_path = converted.stdout.strip()
            except (OSError, subprocess.TimeoutExpired):
                windows_path = ""

            if windows_path:
                cmd = shutil.which("cmd.exe")
                if cmd:
                    commands.append(
                        [cmd, "/C", "start", "", windows_path]
                    )
                explorer = shutil.which("explorer.exe")
                if explorer:
                    commands.append([explorer, windows_path])

    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        commands.append([xdg_open, absolute])
    for viewer in ("eog", "feh", "display", "evince"):
        binary = shutil.which(viewer)
        if binary:
            commands.append([binary, absolute])
    mac_open = shutil.which("open")
    if mac_open:
        commands.append([mac_open, absolute])
    return commands


def open_schematic(path: Path, *, missing_ok: bool = False) -> bool:
    """Open an SVG using the desktop viewer available to this environment."""
    if not path.is_file():
        raise click.UsageError(f"Schematic SVG not found: {path}")

    commands = _viewer_commands(path)
    if not commands:
        message = (
            "No desktop viewer was found. Under WSL, install `wslu` for "
            "`wslview` or ensure Windows interop is enabled."
        )
        if missing_ok:
            click.secho(f"WARNING: {message}", fg="yellow")
            return False
        raise click.ClickException(message)

    for command in commands:
        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            continue
        click.secho(
            f"SUCCESS: Opened schematic with {Path(command[0]).name}.",
            fg="green",
        )
        return True

    message = "Could not launch any available schematic viewer."
    if missing_ok:
        click.secho(f"WARNING: {message}", fg="yellow")
        return False
    raise click.ClickException(message)


def _validate_json_netlist(path: Path) -> None:
    if not path.is_file():
        raise click.UsageError(f"Yosys JSON netlist not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.UsageError(f"Invalid Yosys JSON netlist {path}: {exc}") from exc
    if not isinstance(payload.get("modules"), dict) or not payload["modules"]:
        raise click.UsageError(
            f"Yosys JSON netlist contains no modules: {path}"
        )


def render_schematic(
    *,
    root: Path,
    input_path: Path,
    output_path: Path,
    skin_path: Optional[Path] = None,
    timeout: int = 120,
    missing_ok: bool = False,
    open_viewer: bool = False,
) -> bool:
    """Render one JSON netlist and return whether an SVG was produced."""
    binary = find_netlistsvg()
    if not binary:
        message = (
            "NetlistSVG is not installed. Run "
            "`saxoflow install netlistsvg` to enable schematic generation."
        )
        if missing_ok:
            click.secho(f"WARNING: {message}", fg="yellow")
            return False
        raise click.UsageError(message)

    _validate_json_netlist(input_path)
    if skin_path and not skin_path.is_file():
        raise click.UsageError(f"NetlistSVG skin file not found: {skin_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    command = [
        binary,
        _project_path(input_path, root),
        "-o",
        _project_path(output_path, root),
    ]
    if skin_path:
        command.extend(["--skin", _project_path(skin_path, root)])

    click.secho(
        "INFO: Rendering synthesized schematic with NetlistSVG...",
        fg="cyan",
    )
    click.echo(" ".join(command))
    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        message = f"NetlistSVG timed out after {timeout} seconds."
        if missing_ok:
            click.secho(f"WARNING: {message}", fg="yellow")
            return False
        raise click.ClickException(message)
    except OSError as exc:
        message = f"Could not execute NetlistSVG: {exc}"
        if missing_ok:
            click.secho(f"WARNING: {message}", fg="yellow")
            return False
        raise click.ClickException(message) from exc

    output = "\n".join(
        part.strip()
        for part in (result.stdout, result.stderr)
        if part.strip()
    )
    if output:
        click.echo(output)
    if result.returncode != 0 or not output_path.is_file():
        message = (
            f"NetlistSVG failed with exit code {result.returncode}."
            if result.returncode
            else "NetlistSVG completed without creating an SVG."
        )
        if missing_ok:
            click.secho(f"WARNING: {message}", fg="yellow")
            return False
        raise click.ClickException(message)

    click.secho(
        f"SUCCESS: Schematic written to {_project_path(output_path, root)}",
        fg="green",
    )
    if open_viewer:
        open_schematic(output_path, missing_ok=missing_ok)
    return True


@click.command("schematic")
@click.option(
    "--input",
    "input_spec",
    default=DEFAULT_INPUT,
    show_default=True,
    metavar="FILE",
    help="Yosys JSON netlist to render.",
)
@click.option(
    "--output",
    "output_spec",
    default=DEFAULT_OUTPUT,
    show_default=True,
    metavar="FILE",
    help="Destination SVG file.",
)
@click.option(
    "--skin",
    "skin_spec",
    type=click.Path(dir_okay=False, path_type=str),
    help="Optional NetlistSVG skin file.",
)
@click.option(
    "--timeout",
    type=click.IntRange(min=1),
    default=120,
    show_default=True,
    metavar="SECONDS",
    help="Maximum rendering time.",
)
@click.option(
    "--open/--no-open",
    "open_viewer",
    default=True,
    show_default=True,
    help="Open the generated SVG in the desktop viewer.",
)
def schematic(
    input_spec: str,
    output_spec: str,
    skin_spec: Optional[str],
    timeout: int,
    open_viewer: bool,
) -> None:
    """Render a Yosys JSON netlist as an SVG schematic."""
    root = Path.cwd()
    if not (root / "Makefile").is_file():
        raise click.UsageError(
            "No Makefile found. Run `saxoflow schematic` from a unit root."
        )

    input_path = _resolve_path(root, input_spec)
    output_path = _resolve_path(root, output_spec)
    skin_path = _resolve_path(root, skin_spec) if skin_spec else None
    render_schematic(
        root=root,
        input_path=input_path,
        output_path=output_path,
        skin_path=skin_path,
        timeout=timeout,
        open_viewer=open_viewer,
    )


__all__: Sequence[str] = (
    "schematic",
    "render_schematic",
    "find_netlistsvg",
    "open_schematic",
)
