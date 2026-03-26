# saxoflow/teach/tutorialspec/migrate.py
"""Migration utility: converts legacy pack.yaml + lesson YAMLs to TutorialSpec v1.

Migration strategy
-------------------
All existing :class:`~saxoflow.teach.session.CommandDef` entries are
**preserved** (no commands removed).  The migrator only *adds* a
``canonical_action`` where it can be inferred and sets ``grading_safe``
based on the existing success checks.

Canonical action inference priority
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. **Agent invocations** — if a step has an
   :class:`~saxoflow.teach.session.AgentInvocationDef` whose ``agent_key``
   maps to a :data:`CANONICAL_ACTION_MAP` entry, that mapping is used.
2. **Preferred commands** — if a :class:`~saxoflow.teach.session.CommandDef`
   has ``preferred`` set to a value that exactly matches (or starts with) a
   canonical CLI invocation, that invocation is used.
3. **No match** — ``canonical_action`` is left as ``None``.

``grading_safe`` is set to ``True`` for steps whose entire ``success`` list
consists of :data:`GRADING_SAFE_CHECK_KINDS` checks and is non-empty.

Python: 3.9+
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from saxoflow.teach.pack import load_pack
from saxoflow.teach.session import StepDef
from saxoflow.teach.tutorialspec.schema import (
    CANONICAL_ACTION_MAP,
    TUTORIALSPEC_VERSION,
    TutorialSpec,
    TutorialStep,
)

__all__ = ["MigrationReport", "LegacyPackMigrator"]

logger = logging.getLogger("saxoflow.teach.tutorialspec.migrate")

# Reverse map: agent_key → canonical CLI string
_AGENT_TO_CANONICAL: dict = {k: v for k, v in CANONICAL_ACTION_MAP.items()}

# Check kinds that make a step deterministically gradeable
_GRADING_SAFE_KINDS = frozenset([
    "file_exists",
    "file_contains",
    "stdout_contains",
    "exit_code_0",
])


# ---------------------------------------------------------------------------
# Migration report
# ---------------------------------------------------------------------------

@dataclass
class MigrationReport:
    """Summary of a migration run.

    Attributes
    ----------
    pack_id:
        ``id`` of the pack that was migrated.
    steps_migrated:
        Total number of steps processed.
    steps_with_canonical_action:
        Steps where a canonical action was successfully inferred.
    steps_grading_safe:
        Steps whose success checks are fully deterministic.
    warnings:
        Free-form warning strings accumulated during migration.
    """

    pack_id: str
    steps_migrated: int = 0
    steps_with_canonical_action: int = 0
    steps_grading_safe: int = 0
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable multi-line summary."""
        lines = [
            f"Migration report for pack '{self.pack_id}':",
            f"  Steps migrated:          {self.steps_migrated}",
            f"  Steps with canonical:    {self.steps_with_canonical_action}",
            f"  Steps grading-safe:      {self.steps_grading_safe}",
        ]
        if self.warnings:
            lines.append(f"  Warnings ({len(self.warnings)}):")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Migrator
# ---------------------------------------------------------------------------

class LegacyPackMigrator:
    """Migrates a legacy pack directory to a :class:`TutorialSpec`.

    The pack must conform to the ``pack.yaml`` + ``lessons/*.yaml`` layout
    expected by :func:`~saxoflow.teach.pack.load_pack`.

    Usage::

        migrator = LegacyPackMigrator()
        spec, report = migrator.migrate(Path("packs/ethz_ic_design"))
        print(report.summary())
        compiled = TutorialSpecCompiler().compile(spec)
    """

    def migrate(self, pack_path: Path) -> tuple:
        """Load a legacy pack and produce a :class:`TutorialSpec` + report.

        Parameters
        ----------
        pack_path:
            Absolute (or CWD-relative) path to the pack root directory.

        Returns
        -------
        tuple[TutorialSpec, MigrationReport]
        """
        pack = load_pack(pack_path)
        report = MigrationReport(pack_id=pack.id)

        tutorial_steps: List[TutorialStep] = []
        for step in pack.steps:
            t_step = self._migrate_step(step, report)
            tutorial_steps.append(t_step)
            report.steps_migrated += 1

        spec = TutorialSpec(
            schema_version=TUTORIALSPEC_VERSION,
            id=pack.id,
            name=pack.name,
            version=pack.version,
            authors=pack.authors,
            description=pack.description,
            docs=pack.docs,
            steps=tutorial_steps,
            docs_dir=pack.docs_dir,
            pack_path=pack.pack_path,
        )
        return spec, report

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _migrate_step(self, step: StepDef, report: MigrationReport) -> TutorialStep:
        canonical_action = self._infer_canonical_action(step, report)
        grading_safe = self._is_grading_safe(step)

        if canonical_action is not None:
            report.steps_with_canonical_action += 1
        if grading_safe:
            report.steps_grading_safe += 1

        return TutorialStep(
            id=step.id,
            title=step.title,
            goal=step.goal,
            read=step.read,
            canonical_action=canonical_action,
            commands=step.commands,
            agent_invocations=step.agent_invocations,
            success=step.success,
            hints=step.hints,
            questions=step.questions,
            notes=step.notes,
            mode=step.mode,
            grading_safe=grading_safe,
        )

    def _infer_canonical_action(
        self, step: StepDef, report: MigrationReport
    ) -> Optional[str]:
        # Priority 1: agent_invocations → canonical action map
        for inv in step.agent_invocations:
            key = inv.agent_key
            if key in _AGENT_TO_CANONICAL:
                return _AGENT_TO_CANONICAL[key]
            report.warnings.append(
                f"Step '{step.id}': agent_key '{key}' has no canonical mapping."
            )

        # Priority 2: preferred command → canonical action
        canonical_values = set(CANONICAL_ACTION_MAP.values())
        for cmd in step.commands:
            if not cmd.preferred:
                continue
            preferred = cmd.preferred.strip()
            if preferred in canonical_values:
                return preferred
            # Partial match: preferred starts with a canonical value
            for canonical in canonical_values:
                if preferred.startswith(canonical):
                    return canonical

        # Priority 3: deterministic teach action fallback.
        # This ensures every migrated step has a canonical runtime hook even
        # when no direct saxoflow ai mapping exists.
        return (
            f"saxoflow teach action run --pack {report.pack_id} --step {step.id}"
        )

    @staticmethod
    def _is_grading_safe(step: StepDef) -> bool:
        """``True`` iff all success checks are deterministic and at least one exists."""
        return bool(step.success) and all(
            c.kind in _GRADING_SAFE_KINDS for c in step.success
        )
