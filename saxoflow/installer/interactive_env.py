# saxoflow/installer/interactive_env.py
from __future__ import annotations

import json
import os
import sys
import subprocess
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


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _echo_usage_for_cool_cli_block() -> None:
    """Print guidance when interactive mode is blocked inside Cool CLI.

    This runs only on the rare error path where launching the child
    interactive process fails. Keep it minimal and informative.
    """
    click.secho(
        "WARNING: Interactive environment setup is not supported in SaxoFlow Cool CLI shell.",
        fg="yellow",
    )
    click.secho("\nUsage:\n", fg="cyan")
    click.secho("  saxoflow init-env --preset <preset>", fg="cyan")
    click.secho("  saxoflow install", fg="cyan")
    click.secho("  saxoflow install all", fg="cyan")
    click.secho("\nSupported presets:", fg="cyan")
    for pname in PRESETS:
        click.secho(f"  saxoflow init-env --preset {pname}", fg="cyan")
    click.secho(
        "\nTIP: To see available presets, run: saxoflow init-env --help\n",
        fg="cyan",
    )


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
        raise click.ClickException(
            f"ERROR: Invalid preset '{preset}'. Please check available presets."
        )
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
    target = questionary.select("Target device?", choices=["FPGA", "ASIC"]).ask()
    if target is None:
        click.secho("ERROR: Aborted by user.", fg="red")
        return None

    # Removed emoji for consistent ASCII-only prompts
    verif = questionary.select("Verification strategy?", choices=["Simulation", "Formal"]).ask()
    if verif is None:
        click.secho("ERROR: Aborted by user.", fg="red")
        return None

    selected: List[str] = []

    try:
        if questionary.confirm("Install VSCode IDE?").ask():
            selected.extend(ALL_TOOL_GROUPS["ide"])

        # NEW: Optional dependency/source manager (Bender)
        if questionary.confirm("Add Bender (HDL dependency manager)?").ask():
            # We directly add the tool key since Bender is script-managed and
            # described in TOOL_DESCRIPTIONS; no preset/group change required.
            selected.append("bender")

        # Verification tools
        if verif == "Simulation":
            sims = questionary.checkbox(
                "Select simulation tools:", choices=ALL_TOOL_GROUPS["simulation"]
            ).ask() or []
            selected.extend(sims)
        else:
            selected.extend(ALL_TOOL_GROUPS["formal"])

        base = questionary.checkbox(
            "Select waveform viewer & synthesis tools:", choices=ALL_TOOL_GROUPS["base"]
        ).ask() or []
        selected.extend(base)

        # Backend tools
        if target == "FPGA":
            fpgas = questionary.checkbox(
                "Select FPGA tools:", choices=ALL_TOOL_GROUPS["fpga"]
            ).ask() or []
            selected.extend(fpgas)
        else:
            asics = questionary.checkbox(
                "Select ASIC tools:", choices=ALL_TOOL_GROUPS["asic"]
            ).ask() or []
            selected.extend(asics)

        # ------------------------------------------------------------------
        # Agentic AI Extensions (commented out by request)
        # ------------------------------------------------------------------
        # if questionary.confirm("Enable Agentic AI Extensions?").ask():
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
    click.secho("\nFinal tool selection:", fg="cyan")
    for tool in selected:
        desc = TOOL_DESCRIPTIONS.get(tool, "(no description)")
        click.echo(f"  - {tool}: {desc}")

    click.secho("\nSUCCESS: Saved selection.", fg="green")
    click.secho("TIP: Next, run:  saxoflow install        # Install the selected tools", fg="cyan")
    click.echo("    Or:        saxoflow install all    # Install everything (advanced)")


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
    - If called from the Cool CLI (SAXOFLOW_FORCE_HEADLESS=1) *and* no preset/headless
      is specified, we spawn a subprocess that runs the same wizard with a clean
      event loop (no prompt-toolkit conflicts).
    - Writes the final selection to `.saxoflow_tools.json`.
    - Echoes a recap and the next steps.

    Raises
    ------
    click.ClickException
        For malformed presets or I/O errors during save.
    """
    click.secho("SaxoFlow Pro Interactive Setup", fg="cyan")

    # --- Conflict-free path when inside Cool CLI shell ---
    in_cool_cli = os.environ.get("SAXOFLOW_FORCE_HEADLESS") == "1"
    is_child = os.environ.get("SAXOFLOW_INTERACTIVE_SUBPROC") == "1"

    if in_cool_cli and not preset and not headless and not is_child:
        # Spawn a clean child process to run the interactive wizard.
        env = os.environ.copy()
        env.pop("SAXOFLOW_FORCE_HEADLESS", None)          # allow interactive in child
        env["SAXOFLOW_INTERACTIVE_SUBPROC"] = "1"         # prevent recursion
        try:
            subprocess.run(
                [sys.executable, "-W", "ignore:::runpy", "-m", "saxoflow.installer.interactive_env"],
                check=True,
                env=env,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            click.secho(
                f"ERROR: Failed to launch interactive setup in a subprocess: {exc}",
                fg="red",
            )
            _echo_usage_for_cool_cli_block()
        return

    # --- Normal, in-process behavior below ---
    selected: Optional[List[str]] = None

    if preset:
        # Preset mode
        tools = _validate_preset(preset)
        selected = tools
        click.secho(f"Preset '{preset}' selected: {selected}", fg="cyan")
    elif headless:
        # Headless minimal mode
        try:
            selected = _validate_preset("minimal")
        except click.ClickException:
            # If 'minimal' is not defined for some reason, fallback to empty selection
            # and notify the user. This preserves backward compatibility while being safe.
            # TODO: Decide if 'minimal' should be mandatory in PRESETS.
            click.secho(
                "WARNING: Headless mode requested but 'minimal' preset is missing. Selecting no tools.",
                fg="yellow",
            )
            selected = []
        else:
            click.secho("Headless mode: minimal tools selected.", fg="cyan")
    else:
        # Full interactive custom environment builder
        selected = _interactive_selection_flow()
        if selected is None:
            return  # user aborted

    # Abort if custom mode and nothing selected
    is_custom_mode = not preset and not headless
    if is_custom_mode and (not selected or len(selected) == 0):
        click.secho("\nWARNING: No tools were selected. Aborting configuration.", fg="yellow")
        return

    # Normalize selection
    selected = _dedupe_and_sort(selected or [])

    # Persist and print the final summary
    dump_tool_selection(selected)
    _print_final_summary(selected)


# Allow: python -m saxoflow.installer.interactive_env
def _main() -> None:  # pragma: no cover
    run_interactive_env(preset=None, headless=False)


if __name__ == "__main__":  # pragma: no cover
    _main()
