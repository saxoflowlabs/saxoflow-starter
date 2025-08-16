# cool_cli/shell.py
"""
Shell dispatch helpers for the SaxoFlow Cool CLI.

Public API
----------
- is_unix_command(cmd) -> bool
- run_shell_command(command) -> str
- dispatch_input(prompt) -> rich.text.Text
- process_command(cmd) -> rich.text.Text | rich.panel.Panel | None

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
from typing import Iterable, List, Optional, Sequence, Tuple, Union

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

__all__ = ["is_unix_command", "run_shell_command", "dispatch_input", "process_command"]

# -----------------------------------------------------------------------------
# Unused-but-kept imports/ideas (for historical context)
# -----------------------------------------------------------------------------
# from .editors import is_blocking_editor_command  # UNUSED: callers should import directly.
# _EDITOR_HINT_SET = {"nano", "vim", "vi", "micro", "code", "subl", "gedit"}  # superseded by constants


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
    """
    Best-effort extraction of the generated artifact only.
    Prefers fenced code blocks; otherwise falls back to module/property/package spans.
    """
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
    """
    Return True if tokens look like: saxoflow agenticai <rtlgen|tbgen|fpropgen> ...
    """
    if not parts or parts[0] != "saxoflow":
        return False
    if len(parts) >= 3 and parts[1] == "agenticai" and parts[2] in _GEN_CMDS:
        return True
    return False


def _safe_split(command: str) -> Tuple[Optional[List[str]], Optional[str]]:
    """Safely split a command string with shlex."""
    try:
        tokens = shlex.split(command)
        return (tokens or None), None
    except ValueError as exc:
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


# =============================================================================
# Public API
# =============================================================================

def is_unix_command(cmd: str) -> bool:
    """Return True if the first token is a supported alias, 'cd', or on PATH."""
    stripped = (cmd or "").strip()
    if not stripped:
        return False
    if stripped.startswith("!"):
        stripped = stripped[1:].strip()
    first = stripped.split()[0]
    return first in SHELL_COMMANDS or first == "cd" or shutil.which(first) is not None


def run_shell_command(command: str) -> str:
    """Execute a shell command safely; handle aliases, cd, PATH, and saxoflow."""
    parts, err = _safe_split(command)
    if err:
        return err
    if not parts:
        return ""

    cmd_name, args = parts[0], parts[1:]

    # Aliases
    if cmd_name in SHELL_COMMANDS:
        base_cmd = list(SHELL_COMMANDS[cmd_name])
        if cmd_name in ("ls", "ll"):
            extra_opts = [arg for arg in args if arg.startswith("-")]
            cmd = base_cmd + extra_opts
        else:
            cmd = base_cmd

    # Built-in 'cd'
    elif cmd_name == "cd":
        target = args[0] if args else os.path.expanduser("~")
        return _change_directory(target)

    # Saxoflow passthrough
    elif cmd_name == "saxoflow":
        raw_output = _run_subprocess_run(parts)
        # If this is an agentic generation, return artifact-only text
        if _is_agentic_generation_passthrough(parts):
            return _extract_artifact_text(raw_output)
        return raw_output

    # PATH-resolved commands
    else:
        if shutil.which(cmd_name) is None:
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
        result = handle_terminal_editor(shell_cmd)
        if isinstance(result, str):
            return Text(result, no_wrap=False)
        return result

    if not first_word:
        return Text("", no_wrap=False)

    if is_unix_command(prompt):
        return Text(run_shell_command(prompt), no_wrap=False)

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
        return Text(err, style="red")
    parts = parts or []

    # 'cd' (built-in)
    if parts and parts[0] == "cd":
        target = parts[1] if len(parts) > 1 else os.path.expanduser("~")
        return Text(_change_directory(target), style="cyan" if os.path.isdir(os.getcwd()) else "red")

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
        return handle_terminal_editor(shell_cmd)

    # Special case: saxoflow init-env (no preset) — preserved text
    if cmd == "saxoflow init-env":
        msg = (
            "⚠️  Interactive environment setup is not supported in SaxoFlow Cool CLI shell.\n"
            "[Usage] Please use one of the following supported commands:\n"
            "   saxoflow init-env --preset <preset>\n"
            "   saxoflow install\n"
            "   saxoflow install all\n\n"
            "Tip: To see available presets, run: saxoflow init-env --help\n"
        )
        return Text(msg, style="yellow")

    # saxoflow passthrough with forced headless env
    if cmd.startswith("saxoflow"):
        env = os.environ.copy()
        env["SAXOFLOW_FORCE_HEADLESS"] = "1"
        try:
            sparts = shlex.split(cmd)
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
            return Text(f"[error] Failed to run saxoflow CLI: {exc}", style="red")

    # Generic supported commands
    if parts and (parts[0] in SHELL_COMMANDS or shutil.which(parts[0])):
        return Text(run_shell_command(cmd), style="white")

    # Fallback: high-level commands (help, etc.) handled by commands module
    return handle_command(cmd, console)


# Back-compat shim for legacy import path `coolcli.shell:main`.
# Re-export the new entrypoint without touching the earlier __all__.
try:
    from .app import main as main  # noqa: F401
except Exception:  # pragma: no cover - hit only if package is broken
    pass
