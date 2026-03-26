# saxoflow/teach/tutorialspec/schema.py
"""TutorialSpec schema — v1 dataclasses for canonical lesson authoring.

TutorialSpec is the *new* top-level authoring format for SaxoFlow teaching
packs.  It extends the legacy ``PackDef`` / ``StepDef`` structures with:

- ``schema_version`` for forward compatibility.
- ``canonical_action`` on each step — maps to a deterministic ``saxoflow ai``
  lifecycle command usable instead of raw native shell commands.
- ``grading_safe`` flag on each step — indicates that at least one success
  check produces a deterministic, exportable outcome.

Both :class:`TutorialSpec` and :class:`TutorialStep` expose ``.to_pack_def()``
/ ``.to_step_def()`` converters so the rest of the tutoring runtime (runner,
checks, TUI bridge) continues to work without modification during the
transition window.

Python: 3.9+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from saxoflow.teach.session import (
    AgentInvocationDef,
    CheckDef,
    CommandDef,
    PackDef,
    QuestionDef,
    StepDef,
)

__all__ = [
    "TUTORIALSPEC_VERSION",
    "CANONICAL_ACTION_MAP",
    "TutorialStep",
    "TutorialSpec",
]

# ---------------------------------------------------------------------------
# Version constant
# ---------------------------------------------------------------------------

TUTORIALSPEC_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Canonical action map
# ---------------------------------------------------------------------------

#: Maps a human-readable action key to the canonical ``saxoflow`` CLI
#: invocation.  Steps that reference these actions are automatically
#: re-runnable via :func:`~saxoflow.teach.runner.run_canonical_action`
#: without relying on native EDA tool availability.
CANONICAL_ACTION_MAP: Dict[str, str] = {
    "rtlgen": "saxoflow ai run rtlgen",
    "tbgen": "saxoflow ai run tbgen",
    "fpropgen": "saxoflow ai run fpropgen",
    "report": "saxoflow ai run report",
    "sim": "saxoflow ai run sim --yes",
    "fullpipeline": "saxoflow ai run fullpipeline --yes",
    "rtlreview": "saxoflow ai review --type rtl",
    "tbreview": "saxoflow ai review --type tb",
    "fpropreview": "saxoflow ai review --type formal",
    "debug": "saxoflow ai run debug",
}


# ---------------------------------------------------------------------------
# TutorialStep
# ---------------------------------------------------------------------------

@dataclass
class TutorialStep:
    """Extended lesson step with canonical action support.

    Adds two fields on top of :class:`~saxoflow.teach.session.StepDef`:

    canonical_action
        Optional ``saxoflow ai`` CLI invocation that replaces native commands
        for this step when available
        (e.g. ``"saxoflow ai run rtlgen"``).  ``None`` means the step uses
        only its ``commands`` list (legacy path).

    grading_safe
        ``True`` when the step's success checks are deterministic enough to
        be exported for automated grading (``file_exists``, ``file_contains``,
        ``stdout_contains``, ``exit_code_0``).
    """

    id: str
    title: str
    goal: str
    read: List[Dict[str, Any]] = field(default_factory=list)
    canonical_action: Optional[str] = None
    commands: List[CommandDef] = field(default_factory=list)
    agent_invocations: List[AgentInvocationDef] = field(default_factory=list)
    success: List[CheckDef] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    questions: List[QuestionDef] = field(default_factory=list)
    notes: str = ""
    mode: str = "sequential"
    grading_safe: bool = False

    def to_step_def(self) -> StepDef:
        """Return a backward-compatible :class:`~saxoflow.teach.session.StepDef`.

        The ``canonical_action`` and ``grading_safe`` fields are dropped;
        the remaining fields are forwarded unchanged.  Use this when handing
        off to parts of the runtime that still operate on ``StepDef``.
        """
        return StepDef(
            id=self.id,
            title=self.title,
            goal=self.goal,
            read=self.read,
            commands=self.commands,
            agent_invocations=self.agent_invocations,
            success=self.success,
            hints=self.hints,
            questions=self.questions,
            notes=self.notes,
            mode=self.mode,
            canonical_action=self.canonical_action,
        )


# ---------------------------------------------------------------------------
# TutorialSpec
# ---------------------------------------------------------------------------

@dataclass
class TutorialSpec:
    """Canonical top-level authoring format for a SaxoFlow teaching pack.

    Wraps the information contained in a legacy ``pack.yaml`` + lesson YAML
    collection, adding ``schema_version`` and enriched :class:`TutorialStep`
    objects.

    Attributes
    ----------
    schema_version:
        ``TUTORIALSPEC_VERSION`` constant — bumped only on breaking schema
        changes.
    id, name, version, authors, description, docs, docs_dir, pack_path:
        Direct equivalents of :class:`~saxoflow.teach.session.PackDef` fields.
    steps:
        :class:`TutorialStep` list (extends ``StepDef``).
    """

    schema_version: str
    id: str
    name: str
    version: str
    authors: List[str]
    description: str
    docs: List[Dict[str, str]]
    steps: List[TutorialStep]
    docs_dir: Path
    pack_path: Path

    def to_pack_def(self) -> PackDef:
        """Return a backward-compatible :class:`~saxoflow.teach.session.PackDef`.

        Uses :meth:`TutorialStep.to_step_def` for each step so the result
        can be passed directly into :class:`~saxoflow.teach.session.TeachSession`.
        """
        return PackDef(
            id=self.id,
            name=self.name,
            version=self.version,
            authors=self.authors,
            description=self.description,
            docs=self.docs,
            steps=[s.to_step_def() for s in self.steps],
            docs_dir=self.docs_dir,
            pack_path=self.pack_path,
        )
