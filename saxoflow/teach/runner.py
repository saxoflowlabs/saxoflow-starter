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

# Shell metacharacters that require executing via bash -c rather than execvp.
_SHELL_METACHAR = frozenset(["&&", "||", "|", ";", ">", "<", "$(", "`", "cd ", "export ", "source "])


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
        if cmd_def.background:
            result = _execute_background(cmd_def, project_root, session=session)
        else:
            result = _execute_single(cmd_def, project_root, timeout, session=session)
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


def _execute_background(
    cmd_def: CommandDef,
    project_root: Path,
    session=None,
) -> RunResult:
    """Launch a GUI command in the background without waiting for it to exit.

    Used for tools like GTKWave that block until the user closes the window.
    No stdout is captured.  The runner records exit_code=0 optimistically so
    the step can continue.
    """
    resolved = resolve_command(cmd_def)
    cmd_str = resolved.command_str
    needs_shell = any(m in cmd_str for m in _SHELL_METACHAR)

    if not needs_shell and not resolved.is_available:
        return RunResult(
            command_str=cmd_str,
            stdout=f"Error: '{cmd_str.split()[0]}' not found on PATH.",
            exit_code=127,
            resolved_wrapper=resolved.is_wrapper,
        )

    logger.debug("Launching background: %s (cwd=%s)", cmd_str, project_root)

    effective_cwd = str(project_root)
    if session is not None:
        _sess_cwd = getattr(session, "cwd", "")
        if _sess_cwd:
            _candidate = Path(str(project_root)) / _sess_cwd
            if _candidate.exists():
                effective_cwd = str(_candidate)

    try:
        if needs_shell:
            proc = subprocess.Popen(
                cmd_str,
                cwd=effective_cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                shell=True,
                executable="/bin/bash",
            )
        else:
            try:
                args = shlex.split(cmd_str, posix=True)
            except ValueError:
                args = cmd_str.split()
            proc = subprocess.Popen(
                args,
                cwd=effective_cwd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return RunResult(
            command_str=cmd_str,
            stdout="[Launched in background — interact with the window that opened]",
            exit_code=0,
            resolved_wrapper=resolved.is_wrapper,
        )
    except FileNotFoundError:
        return RunResult(
            command_str=cmd_str,
            stdout=f"Error: executable not found: {cmd_str.split()[0]}",
            exit_code=127,
            resolved_wrapper=resolved.is_wrapper,
        )
    except OSError as exc:
        return RunResult(
            command_str=cmd_str,
            stdout=f"OS error launching background process: {exc}",
            exit_code=1,
            resolved_wrapper=resolved.is_wrapper,
        )


def _execute_single(
    cmd_def: CommandDef,
    project_root: Path,
    timeout: int,
    session=None,
) -> RunResult:
    """Resolve and execute one :class:`CommandDef`.

    Returns a :class:`RunResult` regardless of whether the command
    succeeded or failed.

    Parameters
    ----------
    cmd_def:
        The command definition to execute.
    project_root:
        Base working directory.  If *session* has a non-empty ``cwd``
        attribute the effective directory is ``project_root / session.cwd``.
    timeout:
        Per-command timeout in seconds.
    session:
        Optional active :class:`~saxoflow.teach.session.TeachSession`.
        Used to read/update the effective working directory when the
        command contains ``cd``.
    """
    resolved = resolve_command(cmd_def)
    cmd_str = resolved.command_str
    logger.debug("Executing: %s (cwd=%s)", cmd_str, project_root)

    needs_shell = any(m in cmd_str for m in _SHELL_METACHAR)

    # For commands that require a shell (cd, &&, pipes, etc.) skip the
    # PATH availability check: the shell handles built-ins and PATH itself.
    if not needs_shell and not resolved.is_available:
        logger.warning("Command not available on PATH: %s", cmd_str)
        return RunResult(
            command_str=cmd_str,
            stdout=(
                f"Error: '{cmd_str.split()[0]}' not found on PATH.\n"
                f"Hint: check saxoflow diagnose or install the required tool."
            ),
            exit_code=127,
            resolved_wrapper=resolved.is_wrapper,
        )

    # Compute effective working directory from session.cwd (relative to project_root).
    effective_cwd = str(project_root)
    if session is not None:
        _sess_cwd = getattr(session, "cwd", "")
        if _sess_cwd:
            _candidate = Path(str(project_root)) / _sess_cwd
            if _candidate.exists():
                effective_cwd = str(_candidate)

    args: list = []  # populated in non-shell branch; used in error handler
    try:
        if needs_shell:
            # Append a sentinel to capture the post-execution working directory
            # and persist it back into session.cwd so subsequent commands start
            # from wherever 'cd' left us.
            _pwd_sentinel = "SAXOFLOW_CWD"
            wrapped_cmd = f'{cmd_str}; echo "{_pwd_sentinel}:$(pwd)"'
            proc = subprocess.run(
                wrapped_cmd,
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True,
                executable="/bin/bash",
            )
            raw_out = (proc.stdout + proc.stderr).strip()
            # Extract sentinel and update session.cwd
            new_cwd: Optional[str] = None
            filtered: list = []
            for _ln in raw_out.splitlines():
                if _ln.startswith(f"{_pwd_sentinel}:"):
                    new_cwd = _ln[len(f"{_pwd_sentinel}:"):]
                else:
                    filtered.append(_ln)
            output = "\n".join(filtered).strip()
            if new_cwd and session is not None and proc.returncode == 0:
                # Only persist CWD for pure standalone 'cd <path>' commands.
                # Compound commands like 'cd croc && git checkout ex01' use
                # 'cd' internally but subsequent commands should still run
                # from the original directory (cd is scoped to the subshell).
                _raw = cmd_str.strip()
                _is_pure_cd = (
                    _raw.startswith("cd ")
                    and "&&" not in _raw
                    and "||" not in _raw
                    and ";" not in _raw
                )
                if _is_pure_cd:
                    try:
                        # project_root may be a relative path like "."; resolve it
                        # to an absolute path so relative_to() works correctly.
                        _abs_root = Path(str(project_root)).resolve()
                        _rel = str(Path(new_cwd).relative_to(_abs_root))
                        session.cwd = "" if _rel == "." else _rel
                    except ValueError:
                        session.cwd = new_cwd  # absolute path outside project_root
        else:
            try:
                args = shlex.split(cmd_str, posix=True)
            except ValueError as exc:
                logger.error("shlex parse error for command %r: %s", cmd_str, exc)
                args = cmd_str.split()
            proc = subprocess.run(
                args,
                cwd=effective_cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = (proc.stdout + proc.stderr).strip()

        return RunResult(
            command_str=cmd_str,
            stdout=output,
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
        exe = args[0] if args else cmd_str.split()[0]
        return RunResult(
            command_str=cmd_str,
            stdout=f"Error: executable not found: {exe}",
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
