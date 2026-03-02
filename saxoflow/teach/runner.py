# saxoflow/teach/runner.py
"""
Step command executor for the SaxoFlow tutoring subsystem.

Architecture contract
---------------------
- This module is the **only** place that executes shell commands in the
  tutoring system.
- Only commands declared in a step's ``CommandDef`` list are ever executed.
  The LLM never influences which command runs — it only explains.
- Execution output and exit code are always saved back to the
  :class:`~saxoflow.teach.session.TeachSession` after each run.
- Commands are executed inside *project_root* (working directory).

Python: 3.9+
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from saxoflow.teach.command_map import resolve_command
from saxoflow.teach.session import CommandDef, TeachSession

__all__ = ["run_step_commands", "RunResult"]

logger = logging.getLogger("saxoflow.teach.runner")

# Timeout in seconds for each command.
_DEFAULT_TIMEOUT = 120


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


@dataclass
class RunResult:
    """Result of executing one or more step commands.

    Attributes
    ----------
    command_str:
        The command string that was actually executed.
    stdout:
        Combined stdout + stderr output.
    exit_code:
        Process exit code (0 = success).
    timed_out:
        ``True`` if the process was killed due to timeout.
    resolved_wrapper:
        ``True`` if the SaxoFlow wrapper was used instead of native.
    """

    command_str: str
    stdout: str
    exit_code: int
    timed_out: bool = False
    resolved_wrapper: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_step_commands(
    session: TeachSession,
    project_root: Path,
    timeout: int = _DEFAULT_TIMEOUT,
    cmd_index: Optional[int] = None,
) -> List[RunResult]:
    """Execute the current step's declared commands (in order).

    The ``session.last_run_log``, ``session.last_run_exit_code``, and
    ``session.last_run_command`` are updated after every command.  If
    *cmd_index* is given, only that command (0-based) is executed.

    Parameters
    ----------
    session:
        Active :class:`~saxoflow.teach.session.TeachSession`.
    project_root:
        Working directory for command execution.
    timeout:
        Per-command timeout in seconds.
    cmd_index:
        If not ``None``, only the command at this index is run.

    Returns
    -------
    list[RunResult]
        One result per executed command.  Empty when the step has no
        commands.

    Raises
    ------
    ValueError
        When *cmd_index* is out of range.
    """
    step = session.current_step
    if step is None:
        logger.warning("run_step_commands: no current step")
        return []

    commands: List[CommandDef] = step.commands
    if not commands:
        logger.info("Step '%s' has no commands to run.", step.id)
        return []

    if cmd_index is not None:
        if cmd_index < 0 or cmd_index >= len(commands):
            raise ValueError(
                f"cmd_index {cmd_index} out of range for step '{step.id}' "
                f"(has {len(commands)} commands, 0-based)."
            )
        commands = [commands[cmd_index]]

    results: List[RunResult] = []
    for cmd_def in commands:
        result = _execute_single(cmd_def, project_root, timeout)
        # Persist last run info back into session
        session.last_run_log = result.stdout
        session.last_run_exit_code = result.exit_code
        session.last_run_command = result.command_str
        results.append(result)

        if result.exit_code != 0:
            logger.warning(
                "Command exited with code %d: %s", result.exit_code, result.command_str
            )
            # Stop on first failure — do not cascade errors
            break

    return results


# ---------------------------------------------------------------------------
# Internal execution
# ---------------------------------------------------------------------------


def _execute_single(
    cmd_def: CommandDef,
    project_root: Path,
    timeout: int,
) -> RunResult:
    """Resolve and execute one :class:`CommandDef`.

    Returns a :class:`RunResult` regardless of whether the command
    succeeded or failed.
    """
    resolved = resolve_command(cmd_def)

    if not resolved.is_available:
        logger.warning(
            "Command not available on PATH: %s", resolved.command_str
        )
        return RunResult(
            command_str=resolved.command_str,
            stdout=f"Error: '{resolved.command_str.split()[0]}' not found on PATH.\n"
                   f"Hint: check saxoflow diagnose or install the required tool.",
            exit_code=127,
            resolved_wrapper=resolved.is_wrapper,
        )

    cmd_str = resolved.command_str
    logger.debug("Executing: %s (cwd=%s)", cmd_str, project_root)

    try:
        args = shlex.split(cmd_str, posix=True)
    except ValueError as exc:
        logger.error("shlex parse error for command %r: %s", cmd_str, exc)
        args = cmd_str.split()

    try:
        proc = subprocess.run(
            args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return RunResult(
            command_str=cmd_str,
            stdout=(proc.stdout + proc.stderr).strip(),
            exit_code=proc.returncode,
            resolved_wrapper=resolved.is_wrapper,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", timeout, cmd_str)
        return RunResult(
            command_str=cmd_str,
            stdout=f"Timed out after {timeout} seconds.",
            exit_code=-1,
            timed_out=True,
            resolved_wrapper=resolved.is_wrapper,
        )
    except FileNotFoundError:
        return RunResult(
            command_str=cmd_str,
            stdout=f"Error: executable not found: {args[0]}",
            exit_code=127,
            resolved_wrapper=resolved.is_wrapper,
        )
    except OSError as exc:
        logger.error("OS error executing %r: %s", cmd_str, exc)
        return RunResult(
            command_str=cmd_str,
            stdout=f"OS error: {exc}",
            exit_code=1,
            resolved_wrapper=resolved.is_wrapper,
        )
