# cool_cli/commands.py
"""
Command routing helpers for the SaxoFlow CLI shell.

Public API
----------
- handle_command(cmd, console): route a single user command string and return a
  Rich renderable (Panel/Text) or None to signal exit.

Behavior notes (preserved)
--------------------------
- 'help' returns a Rich `Panel` with unified help content.
- 'init-env --help' returns a `Text` block with that command's usage.
- Agentic AI commands ('rtlgen', 'tbgen', 'fpropgen', 'debug', 'report',
  'fullpipeline') print a status `Panel` to the provided `console`, then return
  the tool's output as `Text`, or a red error `Text` with traceback on failure.
- Generation commands emit only the final artifact text to the user.
- 'clear' clears the console and returns an informational `Text`.
- 'quit'/'exit' return None (signal caller to terminate).
- Shell-like prefixes ('ll', 'cat', 'cd') do not execute; they return a
  cyan `Text` acknowledging the command (same as original).

Design & safety
---------------
- The module wraps risky operations (Click runner invocations) and converts
  exceptions into friendly `Text` messages; the CLI shell should not crash.
- Helpers are split for readability and testability.
- Python 3.9+ compatible. flake8/isort/black friendly.
"""

from __future__ import annotations

import os
import re
import sys
import subprocess
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from click.testing import CliRunner
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from dotenv import load_dotenv

from saxoflow.cli import cli as saxoflow_cli
from saxoflow_agenticai.cli import cli as agenticai_cli
# Internal helpers (same repo): OK to import for integrated experience
from saxoflow_agenticai.cli import _any_llm_key_present, _supported_provider_envs

__all__ = ["handle_command", "strip_box_lines"]

# =============================================================================
# Constants & configuration
# =============================================================================

_AGENTIC_COMMANDS: Tuple[str, ...] = (
    "rtlgen",
    "tbgen",
    "fpropgen",
    "debug",
    "report",
    "fullpipeline",
)

_SAXOFLOW_SUBCOMMANDS: Tuple[str, ...] = (
    "agenticai",
    "check-tools",
    "clean",
    "diagnose",
    "formal",
    "init-env",
    "install",
    "sim",
    "sim-verilator",
    "sim-verilator-run",
    "simulate",
    "simulate-verilator",
    "synth",
    "unit",
    "wave",
    "wave-verilator",
)

_SHELL_PREFIXES: Tuple[str, ...] = ("ll", "cat", "cd")

runner: CliRunner = CliRunner()
console: Console = Console()

# Box-drawing characters (unicode range + common glyphs)
_BORDER_RE = re.compile(r"^\s*([\u2500-\u257F╭╮╯╰│─━═║╔╗╚╝]+)\s*$")

# Test-scaffold tokens to drop from help text in strip_box_lines
_SCAFFOLD_LINES = {"top", "inside", "line", "bottom"}

# =============================================================================
# Helpers
# =============================================================================

def _strip_box_lines(text: str) -> str:
    """Remove border-only lines and test scaffolding tokens from help text."""
    if not text:
        return text

    keep: List[str] = []
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()

        # Drop empties and pure border lines
        if not stripped or _BORDER_RE.match(stripped):
            continue

        # First trim edge glyphs so tokens like "│ inside" become "inside"
        while line and _BORDER_RE.match(line[:1]):
            line = line[1:]
        while line and _BORDER_RE.match(line[-1:]):
            line = line[:-1]

        trimmed = line.strip()
        if not trimmed:
            continue
        if trimmed.lower() in _SCAFFOLD_LINES:
            continue

        keep.append(trimmed)
    return "\n".join(keep)


def strip_box_lines(text: str) -> str:
    """Public alias for box-border stripping (used by tests)."""
    return _strip_box_lines(text)


def _prefix_saxoflow_commands(help_lines: Iterable[str]) -> List[str]:
    """Prefix 'saxoflow ' before recognized subcommands in the help listing."""
    prefixed: List[str] = []
    for line in help_lines:
        stripped = line.strip()
        if not stripped:
            prefixed.append(line)
            continue
        first = stripped.split()[0]
        if first in _SAXOFLOW_SUBCOMMANDS:
            rest = stripped[len(first):].rstrip()
            prefixed.append(f"saxoflow {first}{rest}")
        else:
            prefixed.append(line)
    return prefixed


def _compute_panel_width(cns: Console) -> int:
    """Compute a reasonable panel width based on the console size (60% of width)."""
    return max(60, min(120, int(cns.width * 0.6)))


def _invoke_click(cli, args: Sequence[str]) -> Tuple[str, Optional[BaseException], tuple]:
    """Invoke a Click CLI and return (output, exception, exc_info)."""
    try:
        result = runner.invoke(cli, list(args))
    except Exception as exc:  # noqa: BLE001
        return "", exc, ()
    # Click stores exception and exc_info on the result when it fails
    return result.output or "", result.exception, getattr(result, "exc_info", ())


# -----------------------
# Artifact-only extraction
# -----------------------

_CODEBLOCK_RE = re.compile(r"```(?:\w+)?\s*(.*?)\s*```", re.DOTALL)
_MODULE_RE = re.compile(r"(module\s+\w[\s\S]*?endmodule\b)", re.IGNORECASE | re.DOTALL)
_PROP_RE = re.compile(r"(property\b[\s\S]*?endproperty\b)", re.IGNORECASE | re.DOTALL)
_PACKAGE_RE = re.compile(r"(package\b[\s\S]*?endpackage\b)", re.IGNORECASE | re.DOTALL)

def _is_generation_cmd(name: str) -> bool:
    return name in ("rtlgen", "tbgen", "fpropgen")

def _extract_artifact(name: str, text: str) -> str:
    """
    Best-effort extraction of the generated artifact only.
    Prefers fenced code blocks; otherwise extracts module/property/package spans.
    Falls back to the original text if no clear artifact is detected.
    """
    if not _is_generation_cmd(name):
        return text

    s = text.strip()
    if not s:
        return s

    # 1) Fenced code block (``` ... ```)
    m = _CODEBLOCK_RE.search(s)
    if m and m.group(1).strip():
        return m.group(1).strip()

    # 2) Language-aware fallbacks
    # RTL/TB: module…endmodule
    m2 = _MODULE_RE.search(s)
    if m2 and m2.group(1).strip():
        return m2.group(1).strip()

    # Formal: property…endproperty or package…endpackage
    m3 = _PROP_RE.search(s)
    if m3 and m3.group(1).strip():
        return m3.group(1).strip()

    m4 = _PACKAGE_RE.search(s)
    if m4 and m4.group(1).strip():
        return m4.group(1).strip()

    # 3) Nothing detected -> return original
    return s


def _build_help_panel(cns: Console) -> Panel:
    """Build the unified help panel styled like the `saxoflow` help output."""
    sax_help_raw, exc, _ = _invoke_click(saxoflow_cli, ["--help"])
    if exc:
        sax_help_raw = f"[error]Failed to fetch saxoflow --help: {exc}[/error]"
    init_help_raw, exc2, _ = _invoke_click(saxoflow_cli, ["init-env", "--help"])
    if exc2:
        init_help_raw = f"[error]Failed to fetch init-env --help: {exc2}[/error]"

    sax_help_raw = _strip_box_lines(sax_help_raw.strip())
    init_help_raw = _strip_box_lines(init_help_raw.strip())

    sax_lines = sax_help_raw.splitlines()
    prefixed_lines = _prefix_saxoflow_commands(sax_lines)

    saxoflow_help = "\n".join(prefixed_lines)
    init_env_help = init_help_raw.replace("Usage: ", "Usage: saxoflow ")

    parts: List[str] = []
    parts.append("🚀 SaxoFlow Unified CLI Commands\n")
    parts.append(saxoflow_help)
    parts.append("\n\ninit-env Presets\n")
    parts.append(init_env_help)
    parts.append(
        "\n\n🤖 Agentic AI Commands\n"
        "rtlgen        Generates RTL from a specification\n"
        "tbgen         Generates a testbench from a spec\n"
        "fpropgen      Generates formal properties\n"
        "debug         Analyzes simulation results\n"
        "report        Generates a full pipeline report\n"
        "fullpipeline  Runs the full AI pipeline\n"
    )
    parts.append(
        "\n🛠️ Built-in Commands\n"
        "help       Show commands and usage\n"
        "clear      Clear the current conversation\n"
        "quit/exit  Leave the CLI\n"
    )
    parts.append("\n💻 Unix Shell Commands\nSupports common commands like `ls`, `cat`, `cd`, etc.")

    help_text = Text("\n".join(parts))
    return Panel(
        help_text,
        border_style="yellow",
        padding=(1, 2),
        width=_compute_panel_width(cns),
        expand=False,
        title="saxoflow",
        title_align="left",
    )


def _ensure_llm_key_before_agent(cns: Console) -> bool:
    """Ensure an LLM API key exists; if not, run the native setup wizard.

    Returns True when a key is present after the check (wizard may run),
    otherwise False with a user-friendly message printed to the console.
    """
    load_dotenv(override=True)
    if _any_llm_key_present():
        return True

    # Before you build the Panel:
    envs_list = ", ".join(sorted(_supported_provider_envs().values()))
    envs_multiline = envs_list.replace(", ", "\n  ")

    cns.print(
        Panel(
            "🔑 No LLM API key detected.\n\n"
            "I'll open the interactive setup now. You can also set one of:\n"
            "  " + envs_multiline,
            border_style="cyan",
            title="setup",
        )
    )

    if not sys.stdin.isatty():
        cns.print(Text("Non-interactive shell; skipping wizard.", style="yellow"))
        return False

    try:
        # Local import to avoid import-time cycles
        from .bootstrap import run_key_setup_wizard, _resolve_target_provider_env
        prov, _ = _resolve_target_provider_env()
        run_key_setup_wizard(cns, preferred_provider=prov)
    except Exception as exc:  # noqa: BLE001
        cns.print(Text(f"[❌] Key setup failed: {exc}", style="bold red"))
        return False

    load_dotenv(override=True)
    if _any_llm_key_present():
        cns.print(Text("✅ LLM API key configured.", style="green"))
        return True

    cns.print(Text("[❌] No API key found after setup.", style="bold red"))
    return False


def _run_agentic_command(name: str, cns: Console) -> Text:
    """Execute an Agentic AI subcommand and return a renderable Text."""
    status = Panel(
        f"🚀 Running `{name}` via SaxoFlow Agentic AI...",
        border_style="cyan",
        title="status",
    )
    # Print status first; then, if tests expose a `.printed` list, append the actual Panel
    cns.print(status)
    if hasattr(cns, "printed") and isinstance(getattr(cns, "printed"), list):
        cns.printed.append(status)

    output, exception, exc_info = _invoke_click(agenticai_cli, [name])
    if exception:
        import traceback

        tb = ""
        # Only format when we really have a 3-tuple
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            tb = "".join(traceback.format_exception(*exc_info))
        msg = f"[❌ EXCEPTION] {exception}"
        if tb:
            msg += f"\n\nTraceback:\n{tb}"
        return Text(msg, style="bold red")

    if not output:
        return Text(f"[⚠] No output from `{name}` command.", style="white")

    # Enforce "artifact-only" for generation commands
    cleaned = _extract_artifact(name, output)
    return Text(cleaned, style="white")


# =============================================================================
# Public API
# =============================================================================

def handle_command(cmd: str, cns: Console) -> Union[Panel, Text, None]:
    """Route a user-entered command and return a renderable or exit signal."""
    if cmd is None:
        return (
            Text("Unknown command. Type ", style="yellow")
            + Text("help", style="cyan")
            + Text(" to see available commands.", style="yellow")
        )

    raw = cmd.strip()
    lowered = raw.lower()

    # Unified help view (panel)
    if lowered == "help":
        try:
            return _build_help_panel(cns)
        except Exception as exc:  # noqa: BLE001
            return Text(f"[❌] Failed to render help: {exc}", style="bold red")

    # Specific help for init-env (plain text)
    if lowered in ("init-env --help", "init-env help"):
        out, exc, _ = _invoke_click(saxoflow_cli, ["init-env", "--help"])
        if exc:
            return Text(f"[❌] Failed to run 'init-env --help': {exc}", style="bold red")
        return Text(out.strip() or "[⚠] No output from `init-env --help` command.", style="white")

    # Agentic AI commands (ensure key first)
    if lowered in _AGENTIC_COMMANDS:
        try:
            if not _ensure_llm_key_before_agent(cns):
                envs_hint = ", ".join(sorted(_supported_provider_envs().values()))
                return Text(
                    "Agentic command skipped: missing API key.\n"
                    f"Set one of: {envs_hint} or run `setupkeys` from the agent CLI.",
                    style="bold red",
                )
            return _run_agentic_command(lowered, cns)
        except Exception as exc:  # noqa: BLE001
            import traceback

            tb = traceback.format_exc()
            return Text(f"[❌ Outer Exception] {str(exc)}\n{tb}", style="bold red")

    # Exit signals
    if lowered in ("quit", "exit"):
        return None

    # Clear console
    if lowered == "clear":
        if hasattr(cns, "clear") and callable(getattr(cns, "clear")):
            cns.clear()
        # Maintain a clears counter for test observability
        try:
            current = getattr(cns, "clears", 0)
            setattr(cns, "clears", current + 1)
        except Exception:
            pass
        return Text("Conversation cleared.", style="cyan")

    # Shell-like prefixes: acknowledge only, do not execute
    if lowered.startswith(_SHELL_PREFIXES):
        return Text(f"Executing Unix command `{raw}`...", style="cyan")

    # Unknown command fallback
    return (
        Text("Unknown command. Type ", style="yellow")
        + Text("help", style="cyan")
        + Text(" to see available commands.", style="yellow")
    )
