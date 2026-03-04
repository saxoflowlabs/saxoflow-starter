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

import logging
import os
import shlex
import subprocess
from typing import List, Union

logger = logging.getLogger("cool_cli.app")

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from .banner import print_banner
from .completers import HybridShellCompleter
from .constants import AGENTIC_COMMANDS, CUSTOM_PROMPT_HTML, SHELL_COMMANDS
from .editors import is_blocking_editor_command
from .panels import agent_panel, ai_panel, output_panel, user_input_panel, welcome_panel
from .shell import is_unix_command, process_command, requires_raw_tty
from .state import console, conversation_history
from . import state as _state  # for teach_session read at call time
from .bootstrap import ensure_first_run_setup
from .messages import error as msg_error, warning as msg_warning


# =============================================================================
# Utilities
# =============================================================================

def ai_buddy_interactive(user_input, history):
    from .agentic import ai_buddy_interactive as _abi 
    return _abi(user_input, history)


def _clear_terminal() -> None:
    """Clear the terminal screen (Windows and POSIX)."""
    os.system("cls" if os.name == "nt" else "clear")  # noqa: S605


def _goodbye() -> Text:
    """Return the standard goodbye message as cyan Text."""
    return Text(
        "\nUntil next time, may your timing constraints always be met "
        "and your logic always latch-free.\n",
        style="cyan",
    )


def _is_saxoflow_install(cmd: str) -> bool:
    """Return True when *cmd* is a 'saxoflow install <tool>' invocation."""
    try:
        parts = shlex.split(cmd) if cmd else []
    except ValueError:
        return False
    return len(parts) >= 3 and parts[0] == "saxoflow" and parts[1] == "install"


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
        # Teach / tutoring
        "teach", "teach start", "teach list", "teach index", "teach status",
        "teach next", "teach prev", "teach back", "teach run", "teach check",
        "teach ask", "teach invoke-agent", "teach quit",
        # Shell
        "cd", *SHELL_COMMANDS.keys(), "nano", "vim", "vi", "micro", "code", "subl", "gedit",
    ]
    return HybridShellCompleter(commands=commands)


def _render_history(panel_width: int) -> None:
    """Reprint the conversation history as panels."""
    for entry in conversation_history:
        user_text = entry.get("user", "")
        # Skip the user bubble for auto-shown entries (e.g. first content chunk
        # displayed immediately after 'teach start' with no user input).
        if user_text:
            upanel = user_input_panel(user_text, width=panel_width)
            console.print(upanel)

        assistant_msg = entry.get("assistant")
        panel_type = entry.get("panel", "ai")

        if not assistant_msg:
            console.print("")
            continue

        # If we stored a direct renderable (Panel, Group, or anything else
        # that is not a plain string/Text/Markdown), print it without wrapping.
        if not isinstance(assistant_msg, (str, Text, Markdown)):
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
    # Direct renderables (Panel, Group, etc.) are printed without extra wrapping.
    if not isinstance(renderable, (str, Text, Markdown)):
        console.print(user_input_panel(user_input, width=panel_width))
        console.print(renderable)
        console.print("")
        conversation_history.append(
            {"user": user_input, "assistant": renderable, "panel": panel_kind}
        )
        return

    console.print(user_input_panel(user_input, width=panel_width))

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
        stdout_pipe = getattr(subprocess, "PIPE", None)
        stderr_pipe = getattr(subprocess, "PIPE", None)

        popen_kwargs = {"text": True}
        if stdout_pipe is not None:
            popen_kwargs["stdout"] = stdout_pipe
        if stderr_pipe is not None:
            popen_kwargs["stderr"] = stderr_pipe

        proc = subprocess.Popen(  # noqa: S603
            ["python3", "-m", "saxoflow_agenticai.cli"] + parts,
            **popen_kwargs,
        )
        stdout, stderr = proc.communicate()
    except FileNotFoundError as exc:
        # was: Text(f"[❌] Failed to run agentic command: {exc}", style="bold red")
        return msg_error(f"Failed to run agentic command: {exc}")
    except Exception as exc:  # noqa: BLE001
        # was: Text(f"[❌] Unexpected error running agentic command: {exc}", style="bold red")
        return msg_error(f"Unexpected error running agentic command: {exc}")

    output = (stdout or "") + (stderr or "")
    if proc.returncode != 0:
        # was: Text(f"[❌] Error in `{command_line}`\n\n{output}", style="bold red")
        return msg_error(f"Error in `{command_line}`\n\n{output}")

    # was: Text(output or f"[⚠] No output from `{command_line}` command.", style="white")
    if output:
        return Text(output, style="white")
    return msg_warning(f"No output from `{command_line}` command.")


# =============================================================================
# Teach-mode handler
# =============================================================================

def _handle_teach_input(
    user_input: str,
    first_token: str,
    session,
    panel_width: int,
) -> str:
    """Route one turn of input when a teach session is active.

    Returns ``"quit"`` when the user typed ``quit`` inside teach mode so
    the caller knows to tear down the session; returns ``""`` otherwise.
    """
    try:
        from saxoflow.teach._tui_bridge import handle_input as _teach_handle  # noqa: PLC0415
    except ImportError as exc:
        console.print(Text(f"[teach] Bridge module not available: {exc}", style="red"))
        return ""

    llm = getattr(_state, "_teach_llm", None)
    panel = _teach_handle(user_input, session, llm=llm)
    _print_and_record(user_input, panel, "output", panel_width)

    if first_token == "quit":
        return "quit"
    return ""


# =============================================================================
# In-process teach-start (must run inside TUI so _state.teach_session is set
# in the correct process — not in a captured subprocess)
# =============================================================================

def _start_teach_session_inproc(parts: List[str], panel_width: int) -> None:
    """Start a teach session in the running TUI process.

    Called by the main loop whenever the user types
    ``saxoflow teach start <pack_id>``.
    Runs the pack-loading and LLM-initialisation logic directly here (no
    subprocess) so that ``_state.teach_session`` is bound to the parent TUI
    process and the teach-mode routing guard activates immediately.
    """
    from pathlib import Path  # noqa: PLC0415
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.session import TeachSession  # noqa: PLC0415
    from saxoflow.teach.indexer import DocIndex  # noqa: PLC0415
    from .panels import tutor_panel  # noqa: PLC0415

    # parts: ["saxoflow", "teach", "start", pack_id, ...optional flags...]
    if len(parts) < 4:
        console.print(user_input_panel(" ".join(parts), width=panel_width))
        console.print(tutor_panel(
            Text("Usage: saxoflow teach start <pack_id>", style="yellow"),
            width=panel_width,
        ))
        console.print("")
        return

    pack_id = parts[3]
    # Simple flag extraction (--provider / --model)
    provider = None
    model = None
    for i, tok in enumerate(parts[4:], start=4):
        if tok == "--provider" and i + 1 < len(parts):
            provider = parts[i + 1]
        elif tok == "--model" and i + 1 < len(parts):
            model = parts[i + 1]

    packs_path = Path("packs")
    pack_path = packs_path / pack_id
    lines: List[str] = []

    # --- Load pack -----------------------------------------------------------
    try:
        pack = load_pack(pack_path)
    except (FileNotFoundError, PackLoadError) as exc:
        console.print(user_input_panel(" ".join(parts), width=panel_width))
        console.print(tutor_panel(
            Text(f"Error loading pack '{pack_id}': {exc}", style="red"),
            width=panel_width,
        ))
        console.print("")
        return

    # --- Index ---------------------------------------------------------------
    idx = DocIndex(pack)
    try:
        idx.load_or_build()
        if idx.chunk_count == 0:
            lines.append(
                f"No document chunks found. "
                f"Add a PDF to packs/{pack_id}/docs/ and run "
                f"'saxoflow teach index {pack_id}' to enable "
                "document-grounded tutoring.  Continuing without context."
            )
        else:
            lines.append(f"Index ready: {idx.chunk_count} chunks.")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Warning: could not load index ({exc}). Running without context.")

    # --- LLM -----------------------------------------------------------------
    llm = None
    try:
        from saxoflow_agenticai.core.model_selector import ModelSelector  # noqa: PLC0415
        llm = ModelSelector.get_model(
            agent_type="tutor", provider=provider, model_name=model
        )
        lines.append(f"LLM ready: {type(llm).__name__}")
    except Exception as exc:  # noqa: BLE001
        lines.append(
            f"LLM unavailable ({exc}). "
            "Set an API key (e.g. OPENAI_API_KEY) to enable AI explanations."
        )

    # --- Session -------------------------------------------------------------
    session = TeachSession(pack=pack)
    if not session.load_progress():
        lines.append("No saved progress — starting from step 1.")

    # Bind into TUI state (this is why we must run in-process!)
    _state.teach_session = session
    _state._teach_llm = llm  # type: ignore[attr-defined]

    step = session.current_step
    step_title = step.title if step else "(all steps complete)"
    lines.append(f"")
    lines.append(f"Pack:  {pack.name}")
    lines.append(f"Step:  {session.current_step_index + 1} / {session.total_steps} — {step_title}")
    lines.append("")
    lines.append("Commands: run · next · back · hint · status · agents · quit  |  or type any question")

    content = Text("\n".join(lines), style="white")
    user_cmd = " ".join(parts)
    console.print(user_input_panel(user_cmd, width=panel_width))
    console.print(tutor_panel(content, width=panel_width))
    console.print("")
    conversation_history.append(
        {"user": user_cmd, "assistant": "\n".join(lines), "panel": "output"}
    )

    # Load and display the first content chunk for the opening step
    try:
        from saxoflow.teach._tui_bridge import prepare_step_for_display  # noqa: PLC0415
        first_panel = prepare_step_for_display(session)
        console.print(first_panel)
        console.print("")
        conversation_history.append(
            {"user": "", "assistant": first_panel, "panel": "output"}
        )
    except Exception as _exc:  # noqa: BLE001
        logger.debug("Could not load first content chunk: %s", _exc)


def main() -> None:
    """Run the interactive SaxoFlow CLI session."""
    # ✅ Run first-run provider key setup before anything else
    ensure_first_run_setup(console)

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
        # 1) Built-ins (split to preserve spec: quit/exit never recorded)
        # ---------------------------------------------------------------------
        if first_token in {"quit", "exit"}:
            try:
                process_command(user_input)  # optional cleanup
            except Exception:
                pass
            console.print(_goodbye())
            break

        if first_token == "clear":
            try:
                process_command(user_input)  # optional side-effects
            except Exception:
                pass
            conversation_history.clear()
            console.clear()
            continue  # next loop will show banner

        if first_token == "help" or user_input in {"init-env --help", "init-env help"}:
            result = process_command(user_input)
            if isinstance(result, Panel):
                _print_and_record(user_input, result, "panel", panel_width)
            else:
                _print_and_record(user_input, result, "output", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 1b) Teach-mode routing guard
        #     When a teach session is active, all non-built-in input is
        #     handled by _tui_bridge.  Shell/agentic/AI-buddy routing below
        #     is skipped.  The guard is placed AFTER built-ins so that
        #     quit/exit/clear/help continue to function normally.
        # ---------------------------------------------------------------------
        if _state.teach_session is not None:
            # Allow standard Unix/shell commands to execute directly even in
            # teach mode so students can explore the workspace freely alongside
            # the tutorial (ls, cat, pwd, etc. just work).
            if is_unix_command(user_input) or user_input.startswith("!"):
                if _is_saxoflow_install(user_input):
                    # Print user panel BEFORE the subprocess runs so it appears first.
                    console.print(user_input_panel(user_input, width=panel_width))
                    console.print("")
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    if not (isinstance(renderable, Text) and not renderable.plain.strip()):
                        console.print(renderable)
                        console.print("")
                    conversation_history.append({"user": user_input, "assistant": renderable or Text(""), "panel": "output"})
                elif requires_raw_tty(user_input):
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(user_input, renderable, "output", panel_width)
                else:
                    with console.status("[cyan]Running...", spinner="aesthetic"):
                        renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(user_input, renderable, "output", panel_width)
                # Capture plain text output into the session terminal_log so the
                # TutorAgent can see recent shell activity (cat, ll, cat file, etc.)
                try:
                    from rich.text import Text as _RT  # noqa: PLC0415
                    from rich.panel import Panel as _RP  # noqa: PLC0415
                    _r = renderable
                    if isinstance(_r, _RT):
                        _plain = _r.plain
                    elif isinstance(_r, _RP) and isinstance(_r.renderable, _RT):
                        _plain = _r.renderable.plain
                    else:
                        _plain = str(_r)
                    if _plain and _plain.strip():
                        _state.teach_session.add_terminal_entry(user_input, _plain.strip())
                except Exception:  # noqa: BLE001
                    pass
                # If the typed command matches the current pending step command,
                # advance the command cursor so the student doesn't have to use 'run'.
                try:
                    from saxoflow.teach._tui_bridge import record_manual_command as _rmc  # noqa: PLC0415
                    _auto = _rmc(user_input, _state.teach_session)
                    if _auto is not None:
                        console.print(_auto)
                        console.print("")
                        conversation_history.append({"user": "", "assistant": _auto, "panel": "output"})
                except Exception:  # noqa: BLE001
                    pass
                continue

            teach_result = _handle_teach_input(
                user_input, first_token, _state.teach_session, panel_width
            )
            if teach_result == "quit":
                _state.teach_session = None
                console.print(Text("Exited tutor mode.", style="cyan"))
            continue

        # ---------------------------------------------------------------------
        # 1c) In-process saxoflow-teach-start interceptor
        #     Must run here (not as a subprocess) so _state.teach_session is
        #     bound in this process and the teach guard above activates.
        # ---------------------------------------------------------------------
        _cmd_parts = shlex.split(user_input) if user_input else []
        if (
            len(_cmd_parts) >= 3
            and _cmd_parts[0] == "saxoflow"
            and _cmd_parts[1] == "teach"
            and _cmd_parts[2] == "start"
        ):
            _start_teach_session_inproc(_cmd_parts, panel_width)
            continue

        # ---------------------------------------------------------------------
        # 2) Shell/editor commands → Output panel
        # ---------------------------------------------------------------------
        is_cli_command = user_input.startswith("!") or is_unix_command(user_input)

        if is_cli_command:
            # Blocking editors should always return to the CLI after closing.
            if is_blocking_editor_command(user_input):
                renderable = process_command(user_input)
                _print_and_record(user_input, renderable, "output", panel_width)
            else:
                if _is_saxoflow_install(user_input):
                    # Print user panel BEFORE the subprocess so it appears first in terminal.
                    console.print(user_input_panel(user_input, width=panel_width))
                    console.print("")
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    if not (isinstance(renderable, Text) and not renderable.plain.strip()):
                        console.print(renderable)
                        console.print("")
                    conversation_history.append({"user": user_input, "assistant": renderable or Text(""), "panel": "output"})
                # 🔧 FIX: Skip spinner for interactive/raw-TTY commands (e.g., saxoflow init-env)
                elif requires_raw_tty(user_input):
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(user_input, renderable, "output", panel_width)
                else:
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
