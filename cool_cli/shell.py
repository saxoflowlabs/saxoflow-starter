# cool_cli/shell.py
"""
Shell dispatch helpers for the SaxoFlow Cool CLI.

Public API
----------
- is_unix_command(cmd) -> bool
- run_shell_command(command) -> str
- dispatch_input(prompt) -> rich.text.Text
- process_command(cmd) -> rich.text.Text | rich.panel.Panel | None
- requires_raw_tty(cmd) -> bool   # Lets the app disable spinners for interactive commands

Design & Safety
---------------
- Mirrors original behavior for aliases (ls/ll/etc.), 'cd', generic PATH
  commands, and 'saxoflow …' passthrough.
- Converts all operational errors to friendly textual messages
  (the top-level CLI shouldn't crash).
- Uses ``subprocess.Popen`` where cancellation (Ctrl-C) needs a graceful path.
- Keeps some historical/unused constructs commented for reference.

Python: 3.9+
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

from rich.panel import Panel
from rich.text import Text

from .agentic import run_quick_action
# ⬇️ Import the key guard so free-text paths trigger the setup wizard if needed
from .commands import handle_command, _ensure_llm_key_before_agent
from .constants import (
    BLOCKING_EDITORS,
    NONBLOCKING_EDITORS,
    SHELL_COMMANDS,
)
from .editors import handle_terminal_editor
from .state import console
from .panels import saxoflow_panel  # ✅ Reuse the canonical SaxoFlow panel
# NEW: centralized, emoji-free message helpers for consistent coloring
from .messages import error as msg_error, warning as msg_warning, info as msg_info

__all__ = [
    "is_unix_command",
    "run_shell_command",
    "dispatch_input",
    "process_command",
    "requires_raw_tty",
]

# =============================================================================
# Internal helpers
# =============================================================================

# Keep this in sync with commands._AGENTIC_COMMANDS
_AGENTIC_COMMANDS: Tuple[str, ...] = (
    "rtlgen",
    "tbgen",
    "fpropgen",
    "debug",
    "report",
    "fullpipeline",
)

# --------- Artifact-only extraction (for saxoflow passthrough paths) ----------

_CODEBLOCK_RE = re.compile(r"```(?:\w+)?\s*(.*?)\s*```", re.DOTALL)
_MODULE_RE = re.compile(r"(module\s+\w[\s\S]*?endmodule\b)", re.IGNORECASE | re.DOTALL)
_PROP_RE = re.compile(r"(property\b[\s\S]*?endproperty\b)", re.IGNORECASE | re.DOTALL)
_PACKAGE_RE = re.compile(r"(package\b[\s\S]*?endpackage\b)", re.IGNORECASE | re.DOTALL)

_GEN_CMDS: Tuple[str, ...] = ("rtlgen", "tbgen", "fpropgen")


def _extract_artifact_text(text: str) -> str:
    """Best-effort extraction of the generated artifact only."""
    s = (text or "").strip()
    if not s:
        return s
    m = _CODEBLOCK_RE.search(s)
    if m and m.group(1).strip():
        return m.group(1).strip()
    m2 = _MODULE_RE.search(s)
    if m2 and m2.group(1).strip():
        return m2.group(1).strip()
    m3 = _PROP_RE.search(s)
    if m3 and m3.group(1).strip():
        return m3.group(1).strip()
    m4 = _PACKAGE_RE.search(s)
    if m4 and m4.group(1).strip():
        return m4.group(1).strip()
    return s


def _is_agentic_generation_passthrough(parts: Sequence[str]) -> bool:
    """True if: saxoflow agenticai <rtlgen|tbgen|fpropgen> …"""
    if not parts or parts[0] != "saxoflow":
        return False
    return len(parts) >= 3 and parts[1] == "agenticai" and parts[2] in _GEN_CMDS


def _is_interactive_init_env_cmd(parts: Sequence[str]) -> bool:
    """
    True for: 'saxoflow init-env' with NO '--preset' and NO '--headless'.
    This command must inherit the real TTY so the wizard can render & read keys.
    """
    if not parts or parts[0] != "saxoflow":
        return False
    if len(parts) < 2 or parts[1] != "init-env":
        return False
    tail = parts[2:]
    has_preset = any(arg == "--preset" or arg.startswith("--preset=") for arg in tail)
    has_headless = any(arg == "--headless" for arg in tail)
    return not has_preset and not has_headless


def _safe_split(command: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """Safely split a command string with shlex."""
    try:
        tokens = shlex.split(command)
        return (tokens or None), None
    except ValueError as exc:
        # Keep string return type; callers normalize to colored output.
        return None, f"[error] {exc}"


def _editor_hint_set() -> Tuple[str, ...]:
    """Return the union of blocking and non-blocking editor names."""
    return (*BLOCKING_EDITORS, *NONBLOCKING_EDITORS)


def _change_directory(target: str) -> str:
    """Change the working directory, preserving original messaging."""
    try:
        t = (target or "").strip()
        dest = os.path.expanduser(t) if t.startswith("~") else t
        os.chdir(dest)
        return f"Changed directory to {os.getcwd()}"
    except Exception as exc:  # noqa: BLE001
        return f"[error] {exc}"


def _run_subprocess_run(parts: Sequence[str]) -> str:
    """Run a command synchronously with subprocess.run and return combined output."""
    try:
        result = subprocess.run(parts, capture_output=True, text=True)  # noqa: S603
        return (result.stdout or "") + (result.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"[error] Failed to run saxoflow CLI: {exc}"


def _run_subprocess_popen(cmd: Sequence[str]) -> str:
    """Run a command via Popen, supporting Ctrl-C cancellation semantics."""
    try:
        pipe = getattr(subprocess, "PIPE", None)
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=pipe,
            stderr=pipe,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate()
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                proc.kill()
            return "[Interrupted] Command cancelled by user."
        return ((stdout or "") + (stderr or "")).rstrip()
    except Exception as exc:  # noqa: BLE001
        return f"[error] {exc}"


def _read_tools_file() -> List[str]:
    """Best-effort read of the selection file written by init-env."""
    path = Path(".saxoflow_tools.json")
    if not path.exists():
        return []
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        return []


def _summary_panel() -> Panel:
    """
    Build a friendly recap panel after the interactive wizard exits,
    and render it with the standard SaxoFlow panel style.
    """
    tools = _read_tools_file()
    if not tools:
        renderable = Text.from_markup(
            "[yellow]No saved tool selection found.[/yellow]\n\n"
            "Run [bold]saxoflow init-env[/bold] to choose tools."
        )
    else:
        # ASCII bullets to avoid double-width glyphs
        bullet_lines = "\n".join(f"* {t}" for t in tools)
        renderable = Text.from_markup(
            "[bold cyan]You selected these tools to install:[/bold cyan]\n\n"
            f"{bullet_lines}\n\n"
            "[yellow]Next:[/yellow] run [bold]saxoflow install[/bold] to download and set them up."
        )

    # ✅ Reuse the canonical SaxoFlow panel (yellow border, left-aligned title)
    return saxoflow_panel(renderable, fit=True)


# ------------- NEW: real-shell detection & fallback (bash -lc) ---------------

# Common built-ins we may want to allow (non-interactive usage)
_SHELL_BUILTINS: Tuple[str, ...] = (
    "export", "alias", "unalias", "set", "unset", "source", ".", "type", "hash", "ulimit",
)

# Tokens that indicate we need a real shell to interpret the line
_SHELL_META: Tuple[str, ...] = ("|", ">", "<", "&&", "||", ";", "*", "$", "~", "`", "(", ")", "{", "}")

def _needs_real_shell(raw: str) -> bool:
    """Return True if the command line needs a shell (pipes, redirects, globs, vars, builtins)."""
    s = (raw or "").strip()
    if not s:
        return False
    first = s.split()[0]
    if first in _SHELL_BUILTINS:
        return True
    return any(tok in s for tok in _SHELL_META)


def _run_via_bash(raw: str) -> str:
    """Execute a command line via `bash -lc` and return combined output."""
    try:
        proc = subprocess.run(["bash", "-lc", raw], capture_output=True, text=True)  # noqa: S603
        return (proc.stdout or "") + (proc.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"[error] {exc}"


# =============================================================================
# Public API
# =============================================================================

def requires_raw_tty(cmd: str) -> bool:
    """
    Return True if the command should run without the app's status spinner
    (i.e., needs an unwrapped, raw TTY). This avoids persistent 'Loading…'
    lines when interactive UIs run under a Rich status context.
    """
    raw = (cmd or "").strip()
    parts, _ = _safe_split(raw)
    parts = parts or []

    # Interactive init-env must inherit the real TTY
    if _is_interactive_init_env_cmd(parts):
        return True

    # saxoflow install <tool> can run for tens of minutes; stream live output
    if len(parts) >= 3 and parts[0] == "saxoflow" and parts[1] == "install":
        return True

    # Direct editor invocation (nano/vim/vi/micro/code/subl/gedit…)
    if parts and parts[0] in _editor_hint_set():
        return True

    # Shell-escape path: inspect what's after '!'
    if raw.startswith("!"):
        after = raw[1:].strip()
        sparts, _ = _safe_split(after)
        sparts = sparts or []

        # Editors via '!' → interactive
        if sparts and sparts[0] in _editor_hint_set():
            return True

        # 'saxoflow init-env' via '!' → interactive
        if _is_interactive_init_env_cmd(sparts):
            return True

        # Non-blocking shell commands like '!ls' can show a spinner
        return False

    # Default: spinner is fine
    return False


def is_unix_command(cmd: str) -> bool:
    """Return True when *cmd* looks like a shell command that should execute directly.

    Recognises:
    - ``!`` shell-escape prefix
    - Lines that need a real shell (pipes, redirects, shell built-ins, etc.)
    - Aliases from SHELL_COMMANDS (ls, ll, pwd, …)
    - The ``cd`` built-in
    - Any executable resolved by shutil.which (e.g. ``git``, ``head``)
    - Relative-path invocations: ``./binary``, ``../sibling/binary``
    - Absolute-path invocations: ``/usr/bin/tool``
    """
    stripped = (cmd or "").strip()
    if not stripped:
        return False
    if stripped.startswith("!"):
        return True
    if _needs_real_shell(stripped):
        return True
    first = stripped.split()[0]
    return (
        first in SHELL_COMMANDS
        or first == "cd"
        or shutil.which(first) is not None
        or first.startswith("./")
        or first.startswith("../")
        or first.startswith("/")
    )


def run_shell_command(command: str) -> str:
    """Execute a shell command safely; handle aliases, cd, PATH, saxoflow, and shell meta/builtins."""
    parts, err = _safe_split(command)
    if err:
        return err
    if not parts:
        return ""

    raw_line = command.strip()
    # If the user typed shell meta or a builtin, use bash -lc directly.
    if _needs_real_shell(raw_line):
        return _run_via_bash(raw_line)

    cmd_name, args = parts[0], parts[1:]

    # Aliases
    if cmd_name in SHELL_COMMANDS:
        base_cmd = list(SHELL_COMMANDS[cmd_name])
        if cmd_name in ("ls", "ll"):
            extra_opts = [arg for arg in args if arg.startswith("-")]
            path_args = [arg for arg in args if not arg.startswith("-")]
            cmd = base_cmd + extra_opts + path_args
        else:
            cmd = base_cmd

    # Built-in 'cd'
    elif cmd_name == "cd":
        target = args[0] if args else os.path.expanduser("~")
        return _change_directory(target)

    # Saxoflow passthrough
    elif cmd_name == "saxoflow":
        if _is_interactive_init_env_cmd(parts):
            # Inherit stdio (no capture) so the wizard can draw properly.
            try:
                subprocess.run(parts, check=False)  # noqa: S603
            except Exception as exc:  # noqa: BLE001
                return f"[error] Failed to run saxoflow CLI: {exc}"
            # After wizard exits, show recap:
            console.print(_summary_panel())
            return ""
        # install: stream live so user can see progress (can take many minutes).
        if len(parts) >= 3 and parts[1] == "install":
            tool_name = parts[2]
            console.print(
                Panel(
                    f"[bold cyan]Installing [white]{tool_name}[/white]...[/bold cyan]\n"
                    "[dim]Output streams below. This may take several minutes.[/dim]",
                    title="[bold cyan]installer[/bold cyan]",
                    title_align="left",
                    border_style="cyan",
                )
            )
            try:
                subprocess.run(parts, check=False)  # noqa: S603
            except Exception as exc:  # noqa: BLE001
                return f"[error] Failed to run saxoflow install: {exc}"
            return ""
        # All other saxoflow calls: captured output is fine.
        raw_output = _run_subprocess_run(parts)
        if _is_agentic_generation_passthrough(parts):
            return _extract_artifact_text(raw_output)
        return raw_output

    # PATH-resolved commands (or relative/absolute path executables like ./binary)
    else:
        if shutil.which(cmd_name) is None and not cmd_name.startswith(("./", "../", "/")):
            return f"[error] Unsupported shell command: {cmd_name}"
        cmd = parts

    return _run_subprocess_popen(cmd)


def dispatch_input(prompt: str) -> Text:
    """Dispatch one user input line outside of the full TUI session."""
    prompt = (prompt or "").strip()
    first_word = prompt.split(maxsplit=1)[0] if prompt else ""

    # Agentic AI commands: route through commands.handle_command
    if first_word in _AGENTIC_COMMANDS:
        result = handle_command(prompt, console)
        if isinstance(result, Text):
            return result
        return Text(str(result), no_wrap=False)

    # Editors: treat natively (blocking & non-blocking)
    if first_word in set(_editor_hint_set()):
        result = handle_terminal_editor(prompt)
        if isinstance(result, str):
            return Text(result, no_wrap=False)
        return result

    # Shell escape
    if prompt.startswith("!"):
        shell_cmd = prompt[1:].strip()
        # Editors via '!' → hand over to the editor handler for raw TTY
        sparts, _ = _safe_split(shell_cmd)
        sparts = sparts or []
        if sparts and sparts[0] in _editor_hint_set():
            result = handle_terminal_editor(shell_cmd)
            if isinstance(result, str):
                return Text(result, no_wrap=False)
            return result
        # All other cases: run via a real shell to support pipes/globs/etc.
        out = _run_via_bash(shell_cmd)
        if out.startswith("[error]"):
            return msg_error(out.replace("[error]", "").strip())
        return Text(out, no_wrap=False, style="white")

    if not first_word:
        return Text("", no_wrap=False)

    if is_unix_command(prompt):
        out = run_shell_command(prompt)
        if out.startswith("[error]"):
            return msg_error(out.replace("[error]", "").strip())
        if out.startswith("[Interrupted]"):
            return msg_warning("Command cancelled by user.")
        return Text(out, no_wrap=False, style="white")

    # ⬇️ Ensure an LLM key exists for free-text agentic/chat paths
    if not _ensure_llm_key_before_agent(console):
        return Text(
            "Agent action cancelled: no LLM API key configured.",
            no_wrap=False,
            style="bold red",
        )

    quick = run_quick_action(prompt)
    if quick is not None:
        return Text(quick, no_wrap=False)

    return Text(
        "I'm sorry, I didn't understand your request. "
        "Try design commands like 'rtlgen', 'tbgen', 'fpropgen' or 'report', "
        "or simple shell commands like 'ls', 'pwd', 'date'.",
        no_wrap=False,
    )


def process_command(cmd: str) -> Union[Text, Panel, None]:
    """Process a CLI-style command line and return a renderable or None."""
    cmd = (cmd or "").strip()
    if not cmd:
        return Text("")

    parts, err = _safe_split(cmd)
    if err:
        # Normalize to fully colored error text
        return msg_error(err.replace("[error]", "").strip())
    parts = parts or []

    # 'cd' (built-in) — only for plain 'cd <path>' without shell metacharacters.
    # Compound lines like 'cd dir && ./binary' are handled by _needs_real_shell below.
    if parts and parts[0] == "cd" and not _needs_real_shell(cmd):
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        msg = _change_directory(target)
        if msg.startswith("[error]"):
            return msg_error(msg.replace("[error]", "").strip())
        # Keep success style cyan (Cool CLI branding)
        return Text(msg, style="cyan")

    # Agentic AI commands: delegate early (ensures API-key setup flow)
    if parts and parts[0] in _AGENTIC_COMMANDS:
        return handle_command(cmd, console)

    # Editors (native)
    first_word = parts[0] if parts else ""
    if first_word in set(_editor_hint_set()):
        return handle_terminal_editor(cmd)

    # Shell escape
    if cmd.startswith("!"):
        shell_cmd = cmd[1:].strip()
        # Editors via '!' → use editor handler
        sparts, _ = _safe_split(shell_cmd)
        sparts = sparts or []
        if sparts and sparts[0] in _editor_hint_set():
            return handle_terminal_editor(shell_cmd)
        # Others → real shell
        out = _run_via_bash(shell_cmd)
        if out.startswith("[error]"):
            return msg_error(out.replace("[error]", "").strip())
        return Text(out, style="white")

    # saxoflow passthrough
    if cmd.startswith("saxoflow"):
        sparts = shlex.split(cmd)

        # Interactive init-env → inherit stdio; then show recap.
        if _is_interactive_init_env_cmd(sparts):
            try:
                subprocess.run(sparts, check=False)  # noqa: S603
            except Exception as exc:  # noqa: BLE001
                return msg_error(f"Failed to run saxoflow CLI: {exc}")
            return _summary_panel()

        # install commands: stream output live so the user can see progress.
        # These can run for a very long time (e.g. OpenROAD build from source).
        if len(sparts) >= 3 and sparts[1] == "install":
            tool_name = sparts[2]
            console.print(
                Panel(
                    f"[bold cyan]Installing [white]{tool_name}[/white]...[/bold cyan]\n"
                    "[dim]Output streams below. This may take several minutes.[/dim]",
                    title="[bold cyan]installer[/bold cyan]",
                    title_align="left",
                    border_style="cyan",
                )
            )
            try:
                result = subprocess.run(sparts, check=False)  # noqa: S603

                # Read per-tool result summary written by runner.py
                install_summary = None
                try:
                    import json as _json
                    from pathlib import Path as _Path
                    _result_path = _Path("/tmp/saxoflow_install_result.json")
                    if _result_path.exists():
                        install_summary = _json.loads(_result_path.read_text(encoding="utf-8"))
                        _result_path.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass

                # If no result file was written, the tool name was unrecognised (cli.py
                # calls sys.exit(1) before runner writes anything).
                if install_summary is None and result.returncode != 0:
                    return msg_error(
                        f"'{tool_name}' is not a supported tool or preset. "
                        f"Run 'saxoflow init-env' to see and select supported tools."
                    )

                if install_summary is not None:
                    results = install_summary.get("results", [])
                    ok_tools = [r for r in results if r.get("status") == "ok"]
                    failed_tools = [r for r in results if r.get("status") == "failed"]

                    lines = []
                    for r in ok_tools:
                        ver = r.get("version", "")
                        if ver and ver != "(version unknown)":
                            suffix = f"  {ver} \u2013 installed successfully"
                        else:
                            suffix = "  installed successfully"
                        lines.append(f"[bold green]\u2713 {r['tool']}[/bold green][dim]{suffix}[/dim]")
                    for r in failed_tools:
                        err = r.get("error", "see terminal output above")
                        lines.append(f"[bold red]\u2717 {r['tool']}[/bold red]")
                        # err may be pipe-separated key error lines — show each on its own line
                        for err_line in err.split(" | "):
                            err_line = err_line.strip()
                            if err_line:
                                lines.append(f"  [dim red]{err_line}[/dim red]")

                    if failed_tools:
                        lines.append("")
                        lines.append(
                            "[dim]Run [bold]saxoflow diagnose summary[/bold] for a full "
                            "environment health check, or retry the failed tool individually.[/dim]"
                        )
                        border = "yellow"
                        title = "[bold yellow]installer[/bold yellow]"
                    else:
                        border = "green"
                        title = "[bold green]installer[/bold green]"

                    return Panel("\n".join(lines), title=title, title_align="left", border_style=border)

                # Fallback: no result file but exit code 0 (should not normally occur)
                return Panel(
                    f"[bold green]\u2713 [white]{tool_name}[/white] installation completed successfully.[/bold green]",
                    title="[bold green]installer[/bold green]",
                    title_align="left",
                    border_style="green",
                )
            except Exception as exc:  # noqa: BLE001
                return msg_error(f"Failed to run saxoflow install: {exc}")

        # All other saxoflow commands → captured output in headless mode.
        env = os.environ.copy()
        env["SAXOFLOW_FORCE_HEADLESS"] = "1"
        try:
            result = subprocess.run(  # noqa: S603
                sparts,
                capture_output=True,
                text=True,
                env=env,
            )
            combined = (result.stdout or "") + (result.stderr or "")
            if _is_agentic_generation_passthrough(sparts):
                combined = _extract_artifact_text(combined)
            return Text(combined, style="white")
        except Exception as exc:  # noqa: BLE001
            return msg_error(f"Failed to run saxoflow CLI: {exc}")

    # If the full line clearly needs a real shell (pipes, redirects, globs...), run via bash.
    if _needs_real_shell(cmd):
        out = _run_via_bash(cmd)
        if out.startswith("[error]"):
            return msg_error(out.replace("[error]", "").strip())
        return Text(out, style="white")

    # Generic supported commands
    if parts and (
        parts[0] in SHELL_COMMANDS
        or shutil.which(parts[0])
        or parts[0].startswith(("./", "../", "/"))
    ):
        out = run_shell_command(cmd)
        if out.startswith("[error]"):
            return msg_error(out.replace("[error]", "").strip())
        if out.startswith("[Interrupted]"):
            return msg_warning("Command cancelled by user.")
        return Text(out, style="white")

    # Fallback: high-level commands (help, etc.) handled by commands module
    return handle_command(cmd, console)


# Back-compat shim for legacy import path `coolcli.shell:main`.
try:
    from .app import main as main  # noqa: F401
except Exception:  # pragma: no cover - hit only if package is broken
    pass
