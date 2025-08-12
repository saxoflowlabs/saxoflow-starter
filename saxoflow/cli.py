# saxoflow/cli.py
"""
SaxoFlow Unified CLI.

This module defines the top-level Click-based command-line interface that ties
together:
- Environment initialization (interactive presets)
- Tool installation flows
- Diagnose utilities
- Project build/simulation/formal/synthesis commands
- Agentic AI command group (delegated to saxoflow_agenticai.cli)

Design goals
------------
- Preserve existing behavior and command names.
- Keep per-area concerns modular by importing sub-CLIs and runners.
- Provide clear help/usage strings that derive from the actual configuration
  (PRESETS, APT_TOOLS, SCRIPT_TOOLS) to avoid drift.
- Add defensive error handling to avoid hard crashes from subprocess layers.

Notes
-----
- If Agentic AI presets are disabled in `presets.py`, they simply won't appear
  in the computed list of valid presets. The CLI remains stable.
- Runner functions are expected to be provided by `saxoflow.installer.runner`.
"""

from __future__ import annotations

import sys
from typing import Iterable, List, Optional

import click

# Interactive environment builder (handles headless/preset logic internally).
from saxoflow.installer.interactive_env import run_interactive_env

# Orchestration functions for installing tools/presets/selections.
from saxoflow.installer import runner

# Preset definitions (single source of truth for groups and preset names).
from saxoflow.installer.presets import PRESETS

# Low-level tool maps used to validate single-tool installations.
from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS

# Project scaffolding command (import BEFORE registering it below).
# Fix for NameError: ensure `unit` is defined when we add it to the CLI.
from saxoflow.unit_project import unit

# Per-stage commands from makeflow (simulation, formal, synth, etc.).
from saxoflow.makeflow import (
    check_tools,
    clean,
    formal,
    sim,
    sim_verilator,
    sim_verilator_run,
    simulate,
    simulate_verilator,
    synth,
    wave,
    wave_verilator,
)

# Diagnose command group (full CLI exposed under "diagnose").
from saxoflow import diagnose

# Agentic AI top-level command group (mounted under "agenticai").
# Made optional so the core CLI still loads if this extra module isn't installed.
try:
    from saxoflow_agenticai.cli import cli as agenticai_cli  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    agenticai_cli = None
    # NOTE: Keeping this silent to avoid noisy imports in environments without
    # Agentic AI installed. Uncomment below if you prefer an info message.
    # click.echo("ℹ️ Agentic AI CLI not available; module not installed.")


def _sorted_unique(items: Iterable[str]) -> List[str]:
    """Return a sorted, de-duplicated list of strings.

    Parameters
    ----------
    items
        A collection of strings.

    Returns
    -------
    list of str
        Sorted unique strings.

    Notes
    -----
    Helper used to render deterministic help messages.
    """
    return sorted({str(x) for x in items})


@click.group()
def cli() -> None:
    """
    🧰 SaxoFlow Unified CLI v1 Professional Edition

    A unified interface for:
    - Managing EDA toolchains and environment presets
    - Project builds (simulation, waveforms, formal, synthesis)
    - Health checks/diagnose
    - Agentic AI workflows (mounted under `agenticai`)

    Tip: Run commands from your project root for best results.
    """


# 1️⃣ Environment Initialization (Interactive + Presets)
@cli.command("init-env")
@click.option(
    "--preset",
    type=click.Choice(list(PRESETS.keys())),
    help="Initialize with a predefined preset.",
)
@click.option(
    "--headless",
    is_flag=True,
    help="Run without user prompts (uses 'minimal' preset if available).",
)
def init_env_cmd(preset: Optional[str], headless: bool) -> None:
    """Configure the environment interactively or via a preset."""
    # Defers detailed logic to interactive_env.run_interactive_env
    # which already handles Cool CLI restrictions and edge cases.
    run_interactive_env(preset=preset, headless=headless)


# 2️⃣ Tool Installation Dispatcher
@cli.command("install")
@click.argument("mode", required=False, default="selected")
def install(mode: str) -> None:
    """
    Install EDA toolchains.

    Modes
    -----
    selected
        Install tools from last init-env selection.
    all
        Install all available tools.
    <preset>
        Install from preset (e.g., minimal, fpga, asic, formal, ...).
    <tool>
        Install a specific tool by name (e.g., iverilog, yosys, ...).

    Notes
    -----
    - Preset names and tool names are derived from current configuration
      to avoid documentation drift.
    """
    valid_presets = list(PRESETS.keys())
    valid_tools = _sorted_unique(list(APT_TOOLS) + list(SCRIPT_TOOLS.keys()))

    try:
        if mode == "selected":
            runner.install_selected()
        elif mode == "all":
            runner.install_all()
        elif mode in valid_presets:
            # Delegates to runner to install the preset's tools.
            runner.install_preset(mode)
        elif mode in valid_tools:
            runner.install_single_tool(mode)
        else:
            _print_install_usage(valid_presets, valid_tools)
    except Exception as exc:  # Defensive catch-all to avoid crashing the CLI
        # TODO: Consider more granular exception handling once runner surfaces
        # specific error types (e.g., network errors, permissions).
        click.echo(f"❌ Installation error: {exc}", err=True)
        # Preserve non-zero exit to signal failure to calling shells/CI.
        sys.exit(1)


def _print_install_usage(
    valid_presets: Iterable[str],
    valid_tools: Iterable[str],
) -> None:
    """Print a helpful usage message for `saxoflow install`.

    Parameters
    ----------
    valid_presets
        The preset names currently supported by the system.
    valid_tools
        The tool names supported by the installer layer.
    """
    presets_csv = ", ".join(_sorted_unique(valid_presets))
    tools_csv = ", ".join(_sorted_unique(valid_tools))

    click.echo("❌ Invalid install mode or tool.")
    click.echo("Valid usage:")
    click.echo("  saxoflow install selected")
    click.echo("  saxoflow install all")
    if presets_csv:
        click.echo(f"  saxoflow install <preset>    → {presets_csv}")
    if tools_csv:
        click.echo(f"  saxoflow install <tool>      → {tools_csv}")


# 3️⃣ Attach Full diagnose CLI Group
cli.add_command(diagnose.diagnose, name="diagnose")

# 4️⃣ Project Build System Commands (use from project root)
cli.add_command(unit)  # `unit` is safely imported above now
cli.add_command(sim)
cli.add_command(sim_verilator)
cli.add_command(sim_verilator_run)
cli.add_command(wave)
cli.add_command(wave_verilator)
cli.add_command(simulate)
cli.add_command(simulate_verilator)
cli.add_command(formal)
cli.add_command(synth)
cli.add_command(clean)
cli.add_command(check_tools)

# 5️⃣ Agentic AI command group (optional)
if agenticai_cli is not None:
    cli.add_command(agenticai_cli, name="agenticai")
# else:
#     # Unused, kept for reference:
#     # If you want a visible hint when Agentic AI isn't installed,
#     # uncomment the block below.
#     # click.echo("ℹ️ Agentic AI CLI not available; module not installed.")

# Friendly tip for users if run directly
if __name__ == "__main__":
    # Keeping the gentle tip commented out to reduce noise during direct runs.
    # It can be re-enabled if desired:
    # click.echo("💡 Run all SaxoFlow commands from your project root, e.g., 'saxoflow sim'")
    cli()
