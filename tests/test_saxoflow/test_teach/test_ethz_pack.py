# tests/test_saxoflow/test_teach/test_ethz_pack.py
"""Validates the ethz_ic_design pack loads correctly, including all 10 lessons.

The pack was rewritten in v2.0 to use real ETH Zurich VLSI2 exercise content
(Exercises 1, 3–11) mapped to open-source EDA tools.  These tests guard
against regressions where pack.yaml or a lesson YAML is malformed or missing.

Data-model reference (saxoflow/teach/session.py):
    PackDef    : id, name, version, authors, description, docs, steps, docs_dir, pack_path
    StepDef    : id, title, goal, read, commands, agent_invocations, success, hints, questions, notes
    CommandDef : native, preferred, use_preferred_if_available, background
    CheckDef   : kind, pattern, file
    QuestionDef: text, after_command, kind
"""
from __future__ import annotations

from pathlib import Path

import pytest

from saxoflow.teach.pack import load_pack
from saxoflow.teach.session import CheckDef, CommandDef, PackDef, StepDef

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

PACK_PATH = Path(__file__).parents[3] / "packs" / "ethz_ic_design"

# Lesson IDs as they appear in the lesson YAML files (id: field)
EXPECTED_LESSON_IDS = [
    "env_croc_setup",
    "adder8_simulation",
    "croc_soc_simulation",
    "rtl_croc_exploration",
    "synthesis_yosys",
    "openroad_intro",
    "floorplanning",
    "placement_timing",
    "clock_tree",
    "routing_finishing",
    "power_drc_lvs",
]

EXPECTED_STEP_COUNT = len(EXPECTED_LESSON_IDS)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pack() -> PackDef:
    """Load the ETH Zurich IC design pack once per test module."""
    return load_pack(PACK_PATH)


# ---------------------------------------------------------------------------
# Pack-level smoke tests
# ---------------------------------------------------------------------------

class TestEthzPackLoads:
    """The pack.yaml is valid and produces a well-formed PackDef object."""

    def test_pack_loads_without_error(self):
        p = load_pack(PACK_PATH)
        assert p is not None

    def test_pack_is_packdef_instance(self, pack):
        assert isinstance(pack, PackDef)

    def test_pack_id(self, pack):
        assert pack.id == "ethz_ic_design"

    def test_pack_has_expected_step_count(self, pack):
        assert len(pack.steps) == EXPECTED_STEP_COUNT, (
            f"Expected {EXPECTED_STEP_COUNT} steps, got {len(pack.steps)}; "
            f"ids found: {[s.id for s in pack.steps]}"
        )

    def test_pack_name_not_empty(self, pack):
        # PackDef uses 'name' (human-readable), not 'title'
        assert pack.name and len(pack.name) > 0

    def test_pack_description_not_empty(self, pack):
        assert pack.description and len(pack.description) > 0

    def test_pack_version_not_empty(self, pack):
        assert pack.version and len(pack.version) > 0

    def test_pack_authors_not_empty(self, pack):
        assert pack.authors and len(pack.authors) > 0

    def test_pack_path_matches_disk(self, pack):
        assert pack.pack_path == PACK_PATH.resolve()

    def test_docs_dir_is_absolute(self, pack):
        assert pack.docs_dir.is_absolute()


# ---------------------------------------------------------------------------
# Step presence - all eight lessons
# ---------------------------------------------------------------------------

class TestEthzPackStepPresence:
    """Every expected lesson ID (10 total) is present in the loaded pack."""

    @pytest.mark.parametrize("lesson_id", EXPECTED_LESSON_IDS)
    def test_lesson_id_present(self, pack: PackDef, lesson_id: str):
        ids = [s.id for s in pack.steps]
        assert lesson_id in ids, (
            f"Lesson '{lesson_id}' not found in pack; available: {ids}"
        )


# ---------------------------------------------------------------------------
# Step ordering
# ---------------------------------------------------------------------------

class TestEthzPackStepOrdering:
    """Steps must appear in the canonical order defined in pack.yaml."""

    def test_step_order_matches_expected(self, pack: PackDef):
        actual_ids = [s.id for s in pack.steps]
        assert actual_ids == EXPECTED_LESSON_IDS, (
            f"Step order mismatch.\nExpected: {EXPECTED_LESSON_IDS}\nActual: {actual_ids}"
        )


# ---------------------------------------------------------------------------
# Lesson 09 - Routing & Finishing
# ---------------------------------------------------------------------------

class TestLesson09RoutingFinishing:
    """Lesson 09 (routing_finishing) has well-formed content."""

    @pytest.fixture(scope="class")
    def step(self, pack: PackDef) -> StepDef:
        return next(s for s in pack.steps if s.id == "routing_finishing")

    def test_step_is_stepdef_instance(self, step):
        assert isinstance(step, StepDef)

    def test_title_not_empty(self, step):
        assert step.title and len(step.title) > 0

    def test_goal_not_empty(self, step):
        assert step.goal and len(step.goal) > 0

    def test_has_at_least_one_command(self, step):
        assert len(step.commands) >= 1

    def test_commands_are_commanddef_instances(self, step):
        for cmd in step.commands:
            assert isinstance(cmd, CommandDef), (
                f"Expected CommandDef, got {type(cmd)}: {cmd!r}"
            )

    def test_command_native_fields_are_nonempty_strings(self, step):
        for cmd in step.commands:
            assert isinstance(cmd.native, str) and cmd.native.strip(), (
                f"CommandDef.native is empty: {cmd!r}"
            )

    def test_has_success_checks(self, step):
        assert len(step.success) >= 1

    def test_success_checks_are_checkdef_instances(self, step):
        for chk in step.success:
            assert isinstance(chk, CheckDef), (
                f"Expected CheckDef, got {type(chk)}: {chk!r}"
            )

    def test_success_check_kinds_are_valid(self, step):
        from saxoflow.teach.checks import _CHECKERS
        valid_kinds = set(_CHECKERS.keys())
        for chk in step.success:
            assert chk.kind in valid_kinds, (
                f"Unknown check kind '{chk.kind}' in step '{step.id}'"
            )

    def test_hints_are_strings_when_present(self, step):
        for hint in (step.hints or []):
            assert isinstance(hint, str)

    def test_openroad_referenced_in_command_natives(self, step):
        """OpenROAD (or a make target that drives it) should be in at least one command."""
        combined = " ".join(cmd.native for cmd in step.commands)
        has_openroad = (
            "openroad" in combined.lower()
            or "make route" in combined.lower()
            or "make finish" in combined.lower()
        )
        assert has_openroad, (
            f"Expected openroad or make route/finish; got: {[c.native for c in step.commands]}"
        )


# ---------------------------------------------------------------------------
# Lesson 10 - Power Analysis, DRC & LVS
# ---------------------------------------------------------------------------

class TestLesson10PowerDrcLvs:
    """Lesson 10 (power_drc_lvs) has well-formed content."""

    @pytest.fixture(scope="class")
    def step(self, pack: PackDef) -> StepDef:
        return next(s for s in pack.steps if s.id == "power_drc_lvs")

    def test_step_is_stepdef_instance(self, step):
        assert isinstance(step, StepDef)

    def test_title_not_empty(self, step):
        assert step.title and len(step.title) > 0

    def test_goal_not_empty(self, step):
        assert step.goal and len(step.goal) > 0

    def test_has_at_least_one_command(self, step):
        assert len(step.commands) >= 1

    def test_commands_are_commanddef_instances(self, step):
        for cmd in step.commands:
            assert isinstance(cmd, CommandDef)

    def test_command_natives_are_nonempty_strings(self, step):
        for cmd in step.commands:
            assert isinstance(cmd.native, str) and cmd.native.strip()

    def test_has_success_checks(self, step):
        assert len(step.success) >= 1

    def test_success_checks_are_checkdef_instances(self, step):
        for chk in step.success:
            assert isinstance(chk, CheckDef)

    def test_klayout_or_openroad_present_in_natives(self, step):
        """Either klayout or openroad should appear in native commands."""
        combined = " ".join(cmd.native for cmd in step.commands)
        assert "klayout" in combined.lower() or "openroad" in combined.lower(), (
            f"Expected klayout or openroad; natives: {[c.native for c in step.commands]}"
        )

    def test_hints_are_strings_when_present(self, step):
        for hint in (step.hints or []):
            assert isinstance(hint, str)


# ---------------------------------------------------------------------------
# All steps - generic quality gates
# ---------------------------------------------------------------------------

class TestEthzPackStepsQuality:
    """Every step in the pack meets minimum quality requirements."""

    def test_all_steps_are_stepdef_instances(self, pack: PackDef):
        for step in pack.steps:
            assert isinstance(step, StepDef), f"Step {step!r} is not a StepDef"

    def test_all_steps_have_nonempty_id(self, pack: PackDef):
        for step in pack.steps:
            assert step.id and step.id.strip(), "Found a step with empty id"

    def test_all_steps_have_nonempty_title(self, pack: PackDef):
        for step in pack.steps:
            assert step.title and step.title.strip(), (
                f"Step '{step.id}' has an empty title"
            )

    def test_all_steps_have_nonempty_goal(self, pack: PackDef):
        # StepDef has 'goal', not 'description'
        for step in pack.steps:
            assert step.goal and step.goal.strip(), (
                f"Step '{step.id}' has an empty goal"
            )

    def test_all_steps_have_at_least_one_command(self, pack: PackDef):
        for step in pack.steps:
            assert len(step.commands) >= 1, (
                f"Step '{step.id}' has no commands"
            )

    def test_all_steps_have_at_least_one_success_check(self, pack: PackDef):
        for step in pack.steps:
            assert len(step.success) >= 1, (
                f"Step '{step.id}' has no success checks"
            )

    def test_all_command_natives_are_nonempty(self, pack: PackDef):
        for step in pack.steps:
            for cmd in step.commands:
                assert isinstance(cmd, CommandDef), (
                    f"Step '{step.id}': expected CommandDef, got {type(cmd)}"
                )
                assert cmd.native and cmd.native.strip(), (
                    f"Step '{step.id}': has CommandDef with empty native"
                )

    def test_all_check_kinds_are_valid(self, pack: PackDef):
        # Valid kinds are those registered in saxoflow/teach/checks.py _CHECKERS
        from saxoflow.teach.checks import _CHECKERS
        valid_kinds = set(_CHECKERS.keys())
        for step in pack.steps:
            for chk in step.success:
                assert isinstance(chk, CheckDef), (
                    f"Step '{step.id}': expected CheckDef, got {type(chk)}"
                )
                assert chk.kind in valid_kinds, (
                    f"Step '{step.id}': unknown check kind '{chk.kind}'"
                )


# ---------------------------------------------------------------------------
# Pack file structure
# ---------------------------------------------------------------------------

class TestEthzPackFileStructure:
    """The pack directory has the expected layout on disk."""

    def test_pack_dir_exists(self):
        assert PACK_PATH.is_dir()

    def test_pack_yaml_exists(self):
        assert (PACK_PATH / "pack.yaml").is_file()

    def test_lessons_dir_exists(self):
        assert (PACK_PATH / "lessons").is_dir()

    def test_docs_dir_exists(self):
        assert (PACK_PATH / "docs").is_dir()

    @pytest.mark.parametrize("filename", [
        "01_environment_croc_setup.yaml",
        "02_simulation_verilator.yaml",
        "02b_croc_soc_simulation.yaml",
        "03_rtl_croc_exploration.yaml",
        "04_synthesis_yosys.yaml",
        "05_openroad_intro.yaml",
        "06_floorplanning.yaml",
        "07_placement_timing.yaml",
        "08_clock_tree.yaml",
        "09_routing_finishing.yaml",
        "10_power_drc_lvs.yaml",
    ])
    def test_lesson_yaml_exists(self, filename: str):
        assert (PACK_PATH / "lessons" / filename).is_file(), (
            f"Missing lesson file: lessons/{filename}"
        )
