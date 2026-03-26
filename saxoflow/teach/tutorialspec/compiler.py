# saxoflow/teach/tutorialspec/compiler.py
"""TutorialSpec compiler: validates and compiles :class:`TutorialSpec` objects.

Validation rules (applied in order)
-------------------------------------
1. **Unique step IDs** — no two steps may share the same ``id``.
2. **Canonical actions** — when ``canonical_action`` is set it must either be
   a value in :data:`CANONICAL_ACTION_MAP` or start with ``"saxoflow "``.
   Unknown values are reported as *warnings* (not errors) to allow authoring
   of future commands without breaking validation.
3. **Known check kinds** — every ``CheckDef.kind`` in a step's ``success``
   list must be in :data:`KNOWN_CHECK_KINDS`.  Unknown kinds are errors.
4. **Grading-safe consistency** — steps marked ``grading_safe=True`` must
   have at least one success check whose ``kind`` is in
   :data:`GRADING_SAFE_CHECK_KINDS`.  Violations are *warnings*.

Python: 3.9+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from saxoflow.teach.tutorialspec.schema import (
    CANONICAL_ACTION_MAP,
    TutorialSpec,
    TutorialStep,
)

__all__ = [
    "KNOWN_CHECK_KINDS",
    "GRADING_SAFE_CHECK_KINDS",
    "ValidationIssue",
    "CompileResult",
    "TutorialSpecCompiler",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Check kinds that the compiler knows about.  Any kind outside this set
#: is reported as a validation error.
KNOWN_CHECK_KINDS = frozenset([
    "file_exists",
    "file_contains",
    "stdout_contains",
    "exit_code_0",
    "user_confirms",
    "always",
    "log_regex",
    "exit_code",
])

#: Subset of :data:`KNOWN_CHECK_KINDS` that produce deterministic, exportable
#: outcomes usable for automated grading.
GRADING_SAFE_CHECK_KINDS = frozenset([
    "file_exists",
    "file_contains",
    "stdout_contains",
    "exit_code_0",
])


# ---------------------------------------------------------------------------
# Issue + result containers
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    """One validation problem found during :meth:`TutorialSpecCompiler.compile`.

    Attributes
    ----------
    step_id:
        ``id`` of the step that triggered the issue, or ``"<pack>"`` for
        pack-level issues.
    field:
        Name of the field that is invalid.
    message:
        Human-readable explanation of the problem.
    severity:
        ``"error"`` blocks a successful compile; ``"warning"`` is reported but
        does **not** set :attr:`CompileResult.ok` to ``False``.
    """

    step_id: str
    field: str
    message: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class CompileResult:
    """Output of :meth:`TutorialSpecCompiler.compile`.

    Attributes
    ----------
    spec:
        The :class:`TutorialSpec` that was compiled (same object, not a copy).
    issues:
        List of :class:`ValidationIssue` objects found during compilation.
        May be empty on a clean compile.
    """

    spec: Optional[TutorialSpec]
    issues: List[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """``True`` when no *error*-severity issues were found."""
        return not any(i.severity == "error" for i in self.issues)

    def summary(self) -> str:
        """Human-readable one-line summary of the compile result."""
        if self.ok:
            step_count = len(self.spec.steps) if self.spec else 0
            warn_count = sum(1 for i in self.issues if i.severity == "warning")
            suffix = f", {warn_count} warning(s)" if warn_count else ""
            return f"OK — {step_count} step(s) compiled{suffix}"
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        return f"FAILED — {errors} error(s), {warnings} warning(s)"


# ---------------------------------------------------------------------------
# Compiler
# ---------------------------------------------------------------------------

class TutorialSpecCompiler:
    """Validates and compiles a :class:`TutorialSpec`.

    Usage::

        compiler = TutorialSpecCompiler()
        result = compiler.compile(spec)
        if result.ok:
            print(result.summary())
        else:
            for issue in result.issues:
                print(f"[{issue.severity}] step={issue.step_id}: {issue.message}")
    """

    def compile(self, spec: TutorialSpec) -> CompileResult:
        """Run all validation rules against *spec* and return a :class:`CompileResult`.

        The spec object is **not** mutated.  All issues are collected before
        returning (no early exit on first error).
        """
        issues: List[ValidationIssue] = []
        self._check_unique_ids(spec, issues)
        self._check_canonical_actions(spec, issues)
        self._check_success_checks(spec, issues)
        self._check_grading_safe(spec, issues)
        return CompileResult(spec=spec, issues=issues)

    def preview(self, spec: TutorialSpec, step_index: int = 0) -> str:
        """Return a human-readable preview of one step.

        Parameters
        ----------
        spec:
            The :class:`TutorialSpec` to preview.
        step_index:
            0-based index of the step to show (default: 0).

        Returns
        -------
        str
            Multi-line string suitable for printing to the terminal.
        """
        if not spec.steps:
            return f"Pack '{spec.name}' has no steps."
        if step_index >= len(spec.steps):
            return (
                f"Step index {step_index} out of range "
                f"(pack has {len(spec.steps)} step(s))."
            )
        step = spec.steps[step_index]
        lines = [
            f"Pack:  {spec.name} v{spec.version}",
            f"Step [{step_index + 1}/{len(spec.steps)}]: {step.title}",
            f"  id:   {step.id}",
            f"  Goal: {step.goal}",
        ]
        if step.canonical_action:
            lines.append(f"  Canonical action: {step.canonical_action}")
        if step.commands:
            lines.append(f"  Commands ({len(step.commands)}):")
            for i, cmd in enumerate(step.commands):
                suffix = f"  [preferred: {cmd.preferred}]" if cmd.preferred else ""
                lines.append(f"    [{i}] {cmd.native}{suffix}")
        if step.agent_invocations:
            lines.append(f"  Agent invocations ({len(step.agent_invocations)}):")
            for inv in step.agent_invocations:
                lines.append(f"    - {inv.agent_key}")
        if step.success:
            kinds = [c.kind for c in step.success]
            lines.append(f"  Success checks: {kinds}")
        if step.hints:
            lines.append(f"  Hints: {len(step.hints)} hint(s)")
        if step.grading_safe:
            lines.append("  Grading: deterministic export enabled")
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # Private validators
    # -----------------------------------------------------------------------

    def _check_unique_ids(
        self, spec: TutorialSpec, issues: List[ValidationIssue]
    ) -> None:
        seen: dict = {}
        for i, step in enumerate(spec.steps):
            if step.id in seen:
                issues.append(ValidationIssue(
                    step_id=step.id,
                    field="id",
                    message=(
                        f"Duplicate step ID '{step.id}' "
                        f"(first at index {seen[step.id]}, repeated at {i})."
                    ),
                ))
            else:
                seen[step.id] = i

    def _check_canonical_actions(
        self, spec: TutorialSpec, issues: List[ValidationIssue]
    ) -> None:
        valid_values = set(CANONICAL_ACTION_MAP.values())
        for step in spec.steps:
            if step.canonical_action is None:
                continue
            is_known = (
                step.canonical_action in valid_values
                or step.canonical_action.startswith("saxoflow ")
            )
            if not is_known:
                issues.append(ValidationIssue(
                    step_id=step.id,
                    field="canonical_action",
                    message=(
                        f"Unrecognized canonical_action '{step.canonical_action}'. "
                        "Value should be a CANONICAL_ACTION_MAP value or start "
                        "with 'saxoflow '."
                    ),
                    severity="warning",
                ))

    def _check_success_checks(
        self, spec: TutorialSpec, issues: List[ValidationIssue]
    ) -> None:
        for step in spec.steps:
            for chk in step.success:
                if chk.kind not in KNOWN_CHECK_KINDS:
                    issues.append(ValidationIssue(
                        step_id=step.id,
                        field="success",
                        message=(
                            f"Unknown check kind '{chk.kind}'. "
                            f"Known kinds: {sorted(KNOWN_CHECK_KINDS)}."
                        ),
                    ))

    def _check_grading_safe(
        self, spec: TutorialSpec, issues: List[ValidationIssue]
    ) -> None:
        for step in spec.steps:
            if not step.grading_safe:
                continue
            has_deterministic = any(
                c.kind in GRADING_SAFE_CHECK_KINDS for c in step.success
            )
            if not has_deterministic:
                issues.append(ValidationIssue(
                    step_id=step.id,
                    field="grading_safe",
                    message=(
                        f"Step '{step.id}' is marked grading_safe but has no "
                        "deterministic success check "
                        f"({', '.join(sorted(GRADING_SAFE_CHECK_KINDS))})."
                    ),
                    severity="warning",
                ))
