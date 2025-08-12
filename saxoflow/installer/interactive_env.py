# saxoflow/installer/interactive_env.py
"""
Interactive environment selection for SaxoFlow.

This module provides an interactive (and headless/preset) tool-selection
workflow used by `saxoflow init-env`. It writes the chosen tools to a JSON
file consumed by subsequent installation commands.

Key goals:
- Preserve existing behavior of `run_interactive_env(preset=None, headless=False)`.
- Add strong docstrings, type hints, and error handling.
- Keep unused helpers in-file (commented) for future reuse.
- Comply with PEP 8 and flake8.

Note
----
Per request, the "Agentic AI Extensions" prompt is commented out (not removed)
in the interactive flow. Presets that already include agentic AI tools will
still work unchanged.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import click
import questionary

from saxoflow.installer.presets import ALL_TOOL_GROUPS, PRESETS
from saxoflow.tools.definitions import TOOL_DESCRIPTIONS

# ---------------------------------------------------------------------------
# Constants & public API
# ---------------------------------------------------------------------------

TOOLS_FILE = Path(".saxoflow_tools.json")

__all__ = [
    "run_interactive_env",
    "dump_tool_selection",
    # "load_tool_selection",  # kept for reference; currently unused
]

# ---------------------------------------------------------------------------
# JSON persistence
# ---------------------------------------------------------------------------


def dump_tool_selection(selected: Sequence[str]) -> None:
    """Persist the selected tools to the project's tools file.

    Parameters
    ----------
    selected : Sequence[str]
        The list of tool identifiers to persist.

    Raises
    ------
    click.ClickException
        If the selection cannot be written to disk.
    """
    try:
        with TOOLS_FILE.open("w", encoding="utf-8") as f:
            json.dump(list(selected), f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
    except OSError as exc:  # IO error or permission issues
        raise click.ClickException(
            f"Failed to write tool selection to {TOOLS_FILE!s}: {exc}"
        ) from exc


# NOTE: This function is not used by the current flow, but it's useful for future
# features like "resume last selection" or "edit previous selection". We keep it
# commented for now to prevent unused-function lint warnings while documenting intent.
#
# def load_tool_selection() -> List[str]:
#     """Load a previously saved tool selection from disk.
#
#     Returns
#     -------
#     List[str]
#         A list of tool identifiers, or an empty list if no file exists.
#
#     Notes
#     -----
#     Currently unused. Retained for potential future features where the
#     interactive UI would seed default selections from previous runs.
#     """
#     try:
#         with TOOLS_FILE.open("r", encoding="utf-8") as f:
#             data = json.load(f)
#         if not isinstance(data, list):
#             # Defensive: unexpected content
#             return []
#         # Normalize to strings
#         return [str(x) for x in data]
#     except FileNotFoundError:
#         return []
#     except (OSError, json.JSONDecodeError):
#         # Corrupt or unreadable file; ignore gracefully.
#         return []


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _echo_usage_for_cool_cli_block() -> None:
    """Print guidance when interactive mode is blocked inside Cool CLI."""
    click.echo("⚠️  Interactive environment setup is not supported in SaxoFlow Cool CLI shell.")
    click.echo("\n[Usage] Please use one of the following supported commands:\n")
    click.echo("  saxoflow init-env --preset <preset>")
    click.echo("  saxoflow install")
    click.echo("  saxoflow install all")
    click.echo("\nSupported presets:")
    for pname in PRESETS:
        click.echo(f"  saxoflow init-env --preset {pname}")
    click.echo("\nTip: To see available presets, run: saxoflow init-env --help\n")


def _validate_preset(preset: str) -> List[str]:
    """Validate and resolve a preset to its tool list.

    Parameters
    ----------
    preset : str
        The preset name provided by the user.

    Returns
    -------
    List[str]
        The resolved list of tool identifiers.

    Raises
    ------
    click.ClickException
        If the preset is invalid.
    """
    if preset not in PRESETS:
        raise click.ClickException(f"❌ Invalid preset '{preset}'. Please check available presets.")
    resolved = PRESETS[preset]
    if not isinstance(resolved, Iterable):
        # TODO: If this occurs, it indicates a data integrity issue in presets.
        raise click.ClickException(f"Preset '{preset}' is malformed. Please report this bug.")
    tools = [str(t) for t in resolved]
    return tools


def _interactive_selection_flow() -> Optional[List[str]]:
    """Run the full interactive selection wizard.

    Returns
    -------
    Optional[List[str]]
        A list of selected tools or None if the user aborted.

    Notes
    -----
    Returns None when the user cancels any step.
    """
    target = questionary.select("🎯 Target device?", choices=["FPGA", "ASIC"]).ask()
    if target is None:
        click.echo("❌ Aborted by user.")
        return None

    verif = questionary.select("🧪 Verification strategy?", choices=["Simulation", "Formal"]).ask()
    if verif is None:
        click.echo("❌ Aborted by user.")
        return None

    selected: List[str] = []

    try:
        if questionary.confirm("📝 Install VSCode IDE?").ask():
            selected.extend(ALL_TOOL_GROUPS["ide"])

        # Verification tools
        if verif == "Simulation":
            sims = questionary.checkbox(
                "🧪 Select simulation tools:", choices=ALL_TOOL_GROUPS["simulation"]
            ).ask() or []
            selected.extend(sims)
        else:
            selected.extend(ALL_TOOL_GROUPS["formal"])

        base = questionary.checkbox(
            "🧱 Select waveform viewer & synthesis tools:", choices=ALL_TOOL_GROUPS["base"]
        ).ask() or []
        selected.extend(base)

        # Backend tools
        if target == "FPGA":
            fpgas = questionary.checkbox(
                "🧰 Select FPGA tools:", choices=ALL_TOOL_GROUPS["fpga"]
            ).ask() or []
            selected.extend(fpgas)
        else:
            asics = questionary.checkbox(
                "🏭 Select ASIC tools:", choices=ALL_TOOL_GROUPS["asic"]
            ).ask() or []
            selected.extend(asics)

        # ------------------------------------------------------------------
        # Agentic AI Extensions (commented out by request)
        # ------------------------------------------------------------------
        # if questionary.confirm("🤖 Enable Agentic AI Extensions?").ask():
        #     # NOTE: We intentionally keep this code for future re-enable.
        #     #       Interactive env does not offer AI extensions here.
        #     selected.extend(ALL_TOOL_GROUPS["agentic-ai"])
    except KeyError as exc:
        # Defensive: if ALL_TOOL_GROUPS lacks an expected key.
        raise click.ClickException(
            f"Installer configuration is missing a tool group: {exc}. "
            "Please verify saxoflow.installer.presets.ALL_TOOL_GROUPS."
        ) from exc

    return selected


def _print_final_summary(selected: Sequence[str]) -> None:
    """Print the final selection summary and next steps.

    Parameters
    ----------
    selected : Sequence[str]
        The list of selected tool identifiers.
    """
    click.echo("\n📦 Final tool selection:")
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "(no description)")
        click.echo(f"  - {tool}: {desc}")

    click.echo("\n✅ Saved selection. Next run:")
    click.echo("saxoflow install          # Install selected tools")
    click.echo("saxoflow install all      # Install all tools (⚠ advanced mode)")


def _dedupe_and_sort(items: Iterable[str]) -> List[str]:
    """Deduplicate and sort a sequence of string items.

    Parameters
    ----------
    items : Iterable[str]
        Items to normalize.

    Returns
    -------
    List[str]
        Sorted unique list.
    """
    return sorted(set(str(x) for x in items))


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_interactive_env(preset: Optional[str] = None, headless: bool = False) -> None:
    """Run SaxoFlow's interactive environment selection flow.

    Parameters
    ----------
    preset : Optional[str], default=None
        If provided, bypasses the wizard and uses the named preset.
    headless : bool, default=False
        If True and `preset` is not provided, selects a minimal default set.

    Behavior
    --------
    - Prints a banner line.
    - Blocks interactive mode when `SAXOFLOW_FORCE_HEADLESS=1` and no preset is provided,
      guiding users to use CLI flags instead.
    - Writes the final selection to `.saxoflow_tools.json`.
    - Echoes a recap and the next steps.

    Raises
    ------
    click.ClickException
        For malformed presets or I/O errors during save.
    """
    click.echo("🔧 SaxoFlow Pro Interactive Setup")

    # --- PATCHED: block interactive mode in Cool CLI ---
    in_cool_cli = os.environ.get("SAXOFLOW_FORCE_HEADLESS") == "1"
    if in_cool_cli and not preset:
        _echo_usage_for_cool_cli_block()
        return

    selected: Optional[List[str]] = None

    if preset:
        # Preset mode
        tools = _validate_preset(preset)
        selected = tools
        click.echo(f"✅ Preset '{preset}' selected: {selected}")
    elif headless:
        # Headless minimal mode
        try:
            selected = _validate_preset("minimal")
        except click.ClickException:
            # If 'minimal' is not defined for some reason, fallback to empty selection
            # and notify the user. This preserves backward compatibility while being safe.
            # TODO: Decide if 'minimal' should be mandatory in PRESETS.
            click.echo("⚠️  Headless mode requested but 'minimal' preset is missing. Selecting no tools.")
            selected = []
        else:
            click.echo("✅ Headless mode: minimal tools selected.")
    else:
        # Full interactive custom environment builder
        selected = _interactive_selection_flow()
        if selected is None:
            return  # user aborted

    # 🛑 Abort if custom mode and nothing selected
    is_custom_mode = not preset and not headless
    if is_custom_mode and (not selected or len(selected) == 0):
        click.echo("\n⚠️  No tools were selected. Aborting configuration.")
        return

    # Normalize selection
    selected = _dedupe_and_sort(selected or [])

    # Persist and print the final summary
    dump_tool_selection(selected)
    _print_final_summary(selected)
