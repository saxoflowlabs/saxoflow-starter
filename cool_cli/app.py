# cool_cli/app.py
"""
Interactive SaxoFlow CLI application entrypoint.

Responsibilities
----------------
- Render banner and welcome tips.
- Manage an interactive prompt session with fuzzy completion.
- Route user input to:
  1) Built-in commands (help/quit/exit/clear and init-env help variants).
  2) Agentic AI commands (rtlgen/tbgen/fpropgen/report/etc.) via subprocess.
  3) Shell/editor commands (prefixed with "!" or recognized UNIX commands).
  4) AI Buddy (conversational assistant & review/action orchestration).

Behavior-preserving notes
-------------------------
- Input/output text, panel styling, and routing precedence remain unchanged.
- Console history rendering is preserved.
- Subprocess invocation for agentic commands remains the same; now guarded
  with exceptions so the TUI does not crash.
- The `clear` command now also clears the in-memory conversation history and
  skips recording a history entry, so the banner/welcome view returns on the
  next loop.

Python 3.9+ compatible.
"""

from __future__ import annotations

import shlex
import subprocess
from typing import List, Optional, Union

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

from .agentic import ai_buddy_interactive
from .banner import print_banner
from .completers import HybridShellCompleter
from .constants import AGENTIC_COMMANDS, CUSTOM_PROMPT_HTML, SHELL_COMMANDS
from .editors import is_blocking_editor_command
from .panels import agent_panel, ai_panel, output_panel, user_input_panel, welcome_panel
from .shell import is_unix_command, process_command
from .state import console, conversation_history


# =============================================================================
# Utilities
# =============================================================================

def _clear_terminal() -> None:
    """Clear the terminal screen (Windows and POSIX)."""
    # NOTE: Using os.system for simplicity; upstream UX relies on a full clear.
    import os
    os.system("cls" if os.name == "nt" else "clear")  # noqa: S605


def _goodbye() -> Text:
    """Return the standard goodbye message as cyan Text."""
    return Text(
        "\nUntil next time, may your timing constraints always be met "
        "and your logic always latch-free.\n",
        style="cyan",
    )


def _show_opening_look(panel_width: int) -> None:
    """Print initial banner and welcome tips."""
    welcome_text = (
        "Welcome to SaxoFlow CLI! Take your first step toward mastering "
        "digital design and verification."
    )
    tips = Text(
        "Tips for getting started:\n"
        "1. Ask questions, generate RTL/testbenches, or run simple commands.\n"
        "2. Try shell commands like 'ls' or design commands like 'rtlgen'.\n"
        "3. Type 'help' to see available commands.\n"
        "4. Type 'quit' or 'exit' to leave the CLI.\n",
        style="yellow",
    )
    print_banner(console)
    console.print(welcome_panel(welcome_text, panel_width=panel_width))
    console.print(tips)
    console.print("")


def _build_completer() -> HybridShellCompleter:
    """Create the fuzzy command/path completer."""
    commands: List[str] = [
        # Built-ins
        "help", "quit", "exit", "simulate", "synth", "ai", "clear",
        # Agentic
        "rtlgen", "tbgen", "fpropgen", "report", "rtlreview", "tbreview",
        "fpropreview", "debug", "sim", "fullpipeline",
        # Utilities
        "attach", "save", "load", "export", "stats", "system", "models", "set",
        # Shell
        "cd", *SHELL_COMMANDS.keys(), "nano", "vim", "vi", "micro", "code", "subl", "gedit",
    ]
    return HybridShellCompleter(commands=commands)


def _render_history(panel_width: int) -> None:
    """Reprint the conversation history as panels."""
    for entry in conversation_history:
        upanel = user_input_panel(entry.get("user", ""), width=panel_width)
        console.print(upanel)

        assistant_msg = entry.get("assistant")
        panel_type = entry.get("panel", "ai")

        if not assistant_msg:
            console.print("")
            continue

        # If we stored a raw Panel (e.g., from `help`), just print it.
        if isinstance(assistant_msg, Panel):
            console.print(assistant_msg)
            console.print("")
            continue

        assistant_renderable = (
            Text(assistant_msg) if isinstance(assistant_msg, str) else assistant_msg
        )

        if panel_type == "output":
            op = output_panel(assistant_renderable, border_style="white", width=panel_width)
        elif panel_type == "agent":
            op = agent_panel(assistant_renderable, width=panel_width)
        else:
            op = ai_panel(assistant_renderable, width=panel_width)
        console.print(op)
        console.print("")


def _print_and_record(
    user_input: str,
    renderable: Union[str, Text, Markdown, Panel],
    panel_kind: str,
    panel_width: int,
) -> None:
    """Print the user input panel + renderable panel, and append to history.

    Args:
        user_input: The original command the user entered.
        renderable: The assistant output (string, Text/Markdown, or Panel).
        panel_kind: One of {'ai', 'agent', 'output', 'panel'} to control styling.
        panel_width: Target panel width for layout consistency.
    """
    console.print(user_input_panel(user_input, width=panel_width))

    if isinstance(renderable, Panel):
        panel = renderable
    else:
        if panel_kind == "output":
            panel = output_panel(renderable, border_style="white", width=panel_width)
        elif panel_kind == "agent":
            panel = agent_panel(renderable, width=panel_width)
        else:
            panel = ai_panel(renderable, width=panel_width)

    console.print(panel)
    console.print("")
    conversation_history.append(
        {"user": user_input, "assistant": renderable, "panel": panel_kind}
    )


def _run_agentic_subprocess(command_line: str) -> Union[Text, Markdown]:
    """Execute an agentic CLI command via subprocess and return its output.

    Args:
        command_line: Full user input string (e.g., 'rtlgen --arg val').

    Returns:
        Text|Markdown: Output wrapped as a Rich renderable (Text for now).

    Notes:
        - Matches original behavior: uses `python3 -m saxoflow_agenticai.cli`.
        - Combines stdout + stderr.
        - Non-zero return codes produce a red error Text.
    """
    parts = shlex.split(command_line)
    try:
        proc = subprocess.Popen(  # noqa: S603
            ["python3", "-m", "saxoflow_agenticai.cli"] + parts,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate()
    except FileNotFoundError as exc:
        # Python or environment not found — surface a helpful error.
        return Text(f"[❌] Failed to run agentic command: {exc}", style="bold red")
    except Exception as exc:  # noqa: BLE001
        # Broad guard to keep the TUI resilient.
        return Text(f"[❌] Unexpected error running agentic command: {exc}", style="bold red")

    output = (stdout or "") + (stderr or "")
    if proc.returncode != 0:
        return Text(f"[❌] Error in `{command_line}`\n\n{output}", style="bold red")

    return Text(output or f"[⚠] No output from `{command_line}` command.", style="white")


# =============================================================================
# Main loop
# =============================================================================

def main() -> None:
    """Run the interactive SaxoFlow CLI session."""
    cli_history = InMemoryHistory()
    session = PromptSession(completer=_build_completer(), history=cli_history)

    # Panel width: keep existing ratio to preserve layout/UX.
    panel_width = int(console.width * 0.8)
    custom_prompt = HTML(CUSTOM_PROMPT_HTML)

    while True:
        _clear_terminal()

        if not conversation_history:
            _show_opening_look(panel_width)
        else:
            _render_history(panel_width)

        try:
            user_input = session.prompt(custom_prompt)
        except (EOFError, KeyboardInterrupt):
            console.print(_goodbye())
            break

        user_input = (user_input or "").strip()
        if not user_input:
            continue

        first_token = user_input.split(maxsplit=1)[0].lower()

        # ---------------------------------------------------------------------
        # 1) Built-ins FIRST so they don't fall into the AI path.
        # ---------------------------------------------------------------------
        if first_token in {"help", "quit", "exit", "clear"} or user_input in {
            "init-env --help", "init-env help"
        }:
            result = process_command(user_input)
            if result is None:  # quit/exit
                console.print(_goodbye())
                break

            # SPECIAL-CASE: 'clear' should reset history and re-show banner next loop.
            if first_token == "clear":
                # Do not record a history entry; just clear and redraw next tick.
                conversation_history.clear()
                console.clear()
                # Jump to the next loop; since history is empty, banner will show.
                continue

            if isinstance(result, Panel):
                # Print help panel directly (yellow border, full content).
                _print_and_record(user_input, result, "panel", panel_width)
            else:
                # Print as an output panel.
                _print_and_record(user_input, result, "output", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 2) Shell/editor commands → Output panel
        # ---------------------------------------------------------------------
        is_cli_command = user_input.startswith("!") or is_unix_command(user_input)

        if is_cli_command:
            if is_blocking_editor_command(user_input):
                # Blocking editors should return to the CLI after closing.
                renderable = process_command(user_input)
                _print_and_record(user_input, renderable, "output", panel_width)
            else:
                # Non-blocking/normal shell commands
                with console.status("[cyan]Loading...", spinner="aesthetic"):
                    renderable = process_command(user_input)
                if renderable is None:
                    console.print(_goodbye())
                    break
                _print_and_record(user_input, renderable, "output", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 3) Agentic AI commands → Agent panel
        # ---------------------------------------------------------------------
        if first_token in AGENTIC_COMMANDS:
            with console.status("[magenta]Agentic AI running...", spinner="clock"):
                renderable = _run_agentic_subprocess(user_input)
            _print_and_record(user_input, renderable, "agent", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 4) AI Buddy → AI panel
        # ---------------------------------------------------------------------
        with console.status("[cyan]Thinking...", spinner="dots"):
            assistant_response = ai_buddy_interactive(user_input, conversation_history)
        _print_and_record(user_input, assistant_response, "ai", panel_width)


if __name__ == "__main__":  # pragma: no cover
    main()
