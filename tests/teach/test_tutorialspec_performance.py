# tests/teach/test_tutorialspec_performance.py
"""Performance smoke tests for M5 TutorialSpec compile/migrate paths.

These are intentionally generous bounds to detect major regressions without
flaking on slower CI machines.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from saxoflow.teach.tutorialspec.compiler import TutorialSpecCompiler
from saxoflow.teach.tutorialspec.migrate import LegacyPackMigrator
from saxoflow.teach.tutorialspec.schema import TutorialSpec, TutorialStep


def _minimal_spec() -> TutorialSpec:
    return TutorialSpec(
        schema_version="1.0",
        id="perf_minimal",
        name="Performance Minimal",
        version="1.0",
        authors=[],
        description="Performance smoke spec",
        docs=[],
        steps=[
            TutorialStep(
                id="s1",
                title="Step 1",
                goal="Compile quickly",
                canonical_action="saxoflow teach action run --pack perf_minimal --step s1",
                commands=[],
                success=[],
            )
        ],
        docs_dir=Path("."),
        pack_path=Path("."),
    )


def test_compile_minimal_spec_is_fast():
    compiler = TutorialSpecCompiler()
    spec = _minimal_spec()

    start = time.perf_counter()
    result = compiler.compile(spec)
    elapsed = time.perf_counter() - start

    assert result.ok, result.summary()
    assert elapsed < 1.0, f"Compile regression: took {elapsed:.3f}s for minimal spec"


ETHZ_PACK_PATH = Path(__file__).parents[2] / "packs" / "ethz_ic_design"


@pytest.mark.skipif(
    not ETHZ_PACK_PATH.exists(),
    reason="ethz_ic_design pack not present in workspace",
)
def test_real_pack_migrate_and_compile_within_budget():
    migrator = LegacyPackMigrator()
    compiler = TutorialSpecCompiler()

    start = time.perf_counter()
    spec, report = migrator.migrate(ETHZ_PACK_PATH)
    migrate_elapsed = time.perf_counter() - start

    start = time.perf_counter()
    result = compiler.compile(spec)
    compile_elapsed = time.perf_counter() - start

    assert report.steps_migrated > 0
    assert result.ok, result.summary()
    # Generous CI-safe budget to catch severe regressions, not micro-optimize.
    assert migrate_elapsed < 15.0, (
        f"Migration regression: took {migrate_elapsed:.3f}s for ethz pack"
    )
    assert compile_elapsed < 10.0, (
        f"Compile regression: took {compile_elapsed:.3f}s for ethz pack"
    )
