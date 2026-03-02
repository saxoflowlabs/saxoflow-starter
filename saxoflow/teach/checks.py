# saxoflow/teach/checks.py
"""
Deterministic step success validators for the SaxoFlow tutoring subsystem.

Each checker receives the step definition and the current project root and
decides whether the step's exit criteria have been met.  The LLM is never
consulted for success evaluation.

Available ``CheckDef.kind`` values
------------------------------------
``file_exists``
    Pass when ``CheckDef.file`` exists under *project_root*.

``file_contains``
    Pass when the file named by ``CheckDef.file`` contains the substring
    or regex pattern in ``CheckDef.pattern``.

``stdout_contains``
    Pass when ``TeachSession.last_run_log`` contains ``CheckDef.pattern``
    (substring or regex).

``exit_code_0``
    Pass when ``TeachSession.last_run_exit_code == 0``.

``always``
    Always passes.  Useful for review-only steps with no shell command.

Python: 3.9+
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Callable, Optional

from saxoflow.teach.session import CheckDef, TeachSession

__all__ = ["evaluate_step_success", "CheckResult"]

logger = logging.getLogger("saxoflow.teach.checks")


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------


class CheckResult:
    """Outcome of evaluating one :class:`CheckDef` against a session.

    Attributes
    ----------
    passed:
        ``True`` if the check passed.
    message:
        Human-readable explanation of the result.
    check_kind:
        Echo of ``CheckDef.kind`` for easy log filtering.
    """

    __slots__ = ("passed", "message", "check_kind")

    def __init__(self, passed: bool, message: str, check_kind: str) -> None:
        self.passed = passed
        self.message = message
        self.check_kind = check_kind

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"CheckResult({status}, kind={self.check_kind!r}, msg={self.message!r})"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_step_success(
    session: TeachSession,
    project_root: Path,
) -> bool:
    """Evaluate all success checks for the current step.

    Each :class:`CheckDef` in ``session.current_step.success`` is evaluated
    in order.  **All** checks must pass for the step to be considered
    successful.

    Parameters
    ----------
    session:
        Active :class:`~saxoflow.teach.session.TeachSession`.
    project_root:
        Absolute path to the student's project directory.

    Returns
    -------
    bool
        ``True`` if every check passes; ``False`` on the first failure
        (short-circuit).  Returns ``True`` immediately when the step has
        no success checks.
    """
    step = session.current_step
    if step is None:
        logger.warning("evaluate_step_success called with no current step")
        return False

    if not step.success:
        logger.debug("Step '%s' has no success checks — auto-passing.", step.id)
        return True

    for check_def in step.success:
        result = _run_check(check_def, session, project_root)
        logger.debug("Check '%s' (%s): %s", step.id, check_def.kind, result)
        if not result.passed:
            return False

    return True


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def _run_check(
    check: CheckDef,
    session: TeachSession,
    project_root: Path,
) -> CheckResult:
    """Dispatch *check* to the appropriate checker function."""
    checker = _CHECKERS.get(check.kind)
    if checker is None:
        msg = f"Unknown check kind '{check.kind}'. Valid kinds: {list(_CHECKERS)}"
        logger.error(msg)
        return CheckResult(passed=False, message=msg, check_kind=check.kind)
    return checker(check, session, project_root)


# ---------------------------------------------------------------------------
# Individual checker implementations
# ---------------------------------------------------------------------------


def _check_file_exists(
    check: CheckDef, session: TeachSession, project_root: Path
) -> CheckResult:
    if not check.file:
        return CheckResult(False, "file_exists check missing 'file' field", check.kind)
    target = project_root / check.file
    passed = target.exists()
    msg = (
        f"File exists: {target}" if passed else f"File not found: {target}"
    )
    return CheckResult(passed=passed, message=msg, check_kind=check.kind)


def _check_file_contains(
    check: CheckDef, session: TeachSession, project_root: Path
) -> CheckResult:
    if not check.file:
        return CheckResult(False, "file_contains check missing 'file' field", check.kind)
    if not check.pattern:
        return CheckResult(False, "file_contains check missing 'pattern' field", check.kind)

    target = project_root / check.file
    if not target.exists():
        return CheckResult(
            False, f"file_contains: file not found: {target}", check.kind
        )

    content = target.read_text(encoding="utf-8", errors="replace")
    passed = bool(re.search(check.pattern, content))
    msg = (
        f"Pattern found in {target.name}"
        if passed
        else f"Pattern '{check.pattern}' not found in {target.name}"
    )
    return CheckResult(passed=passed, message=msg, check_kind=check.kind)


def _check_stdout_contains(
    check: CheckDef, session: TeachSession, project_root: Path
) -> CheckResult:
    if not check.pattern:
        return CheckResult(False, "stdout_contains check missing 'pattern' field", check.kind)

    log = session.last_run_log or ""
    passed = bool(re.search(check.pattern, log))
    msg = (
        f"Pattern found in stdout"
        if passed
        else f"Pattern '{check.pattern}' not in last run output"
    )
    return CheckResult(passed=passed, message=msg, check_kind=check.kind)


def _check_exit_code_0(
    check: CheckDef, session: TeachSession, project_root: Path
) -> CheckResult:
    code = session.last_run_exit_code
    passed = code == 0
    msg = (
        "Last command exited with code 0"
        if passed
        else f"Last command exited with code {code}"
    )
    return CheckResult(passed=passed, message=msg, check_kind=check.kind)


def _check_always(
    check: CheckDef, session: TeachSession, project_root: Path
) -> CheckResult:
    return CheckResult(passed=True, message="Always-pass check", check_kind=check.kind)


# ---------------------------------------------------------------------------
# Dispatcher table
# ---------------------------------------------------------------------------

_CHECKERS: Dict[str, Callable[[CheckDef, TeachSession, Path], CheckResult]] = {
    "file_exists": _check_file_exists,
    "file_contains": _check_file_contains,
    "stdout_contains": _check_stdout_contains,
    "exit_code_0": _check_exit_code_0,
    "always": _check_always,
}
