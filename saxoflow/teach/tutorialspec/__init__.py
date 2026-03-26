# saxoflow/teach/tutorialspec/__init__.py
"""TutorialSpec — canonical authoring contracts for SaxoFlow teaching packs.

Public API
----------
- :class:`~saxoflow.teach.tutorialspec.schema.TutorialSpec`
- :class:`~saxoflow.teach.tutorialspec.schema.TutorialStep`
- :data:`~saxoflow.teach.tutorialspec.schema.CANONICAL_ACTION_MAP`
- :class:`~saxoflow.teach.tutorialspec.compiler.TutorialSpecCompiler`
- :class:`~saxoflow.teach.tutorialspec.compiler.CompileResult`
- :class:`~saxoflow.teach.tutorialspec.migrate.LegacyPackMigrator`
- :class:`~saxoflow.teach.tutorialspec.migrate.MigrationReport`
"""

from saxoflow.teach.tutorialspec.schema import (
    CANONICAL_ACTION_MAP,
    TUTORIALSPEC_VERSION,
    TutorialSpec,
    TutorialStep,
)
from saxoflow.teach.tutorialspec.compiler import (
    CompileResult,
    TutorialSpecCompiler,
    ValidationIssue,
)
from saxoflow.teach.tutorialspec.migrate import (
    LegacyPackMigrator,
    MigrationReport,
)

__all__ = [
    "CANONICAL_ACTION_MAP",
    "TUTORIALSPEC_VERSION",
    "TutorialSpec",
    "TutorialStep",
    "CompileResult",
    "TutorialSpecCompiler",
    "ValidationIssue",
    "LegacyPackMigrator",
    "MigrationReport",
]
