# tests/teach/test_tutorialspec_compiler.py
"""Tests for TutorialSpecCompiler, ValidationIssue, and CompileResult.

Covers:
- Happy-path compile with no issues.
- Duplicate step ID detection.
- Unknown canonical_action (warning, not error).
- Unknown success check kind (error).
- grading_safe consistency warning.
- CompileResult.ok / summary().
- TutorialSpecCompiler.preview() for various states.
- CANONICAL_ACTION_MAP values pass canonical_action validation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from saxoflow.teach.session import CheckDef, CommandDef
from saxoflow.teach.tutorialspec.schema import (
    CANONICAL_ACTION_MAP,
    TUTORIALSPEC_VERSION,
    TutorialSpec,
    TutorialStep,
)
from saxoflow.teach.tutorialspec.compiler import (
    GRADING_SAFE_CHECK_KINDS,
    KNOWN_CHECK_KINDS,
    CompileResult,
    TutorialSpecCompiler,
    ValidationIssue,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_step(
    step_id: str = "step1",
    title: str = "A Step",
    goal: str = "Do something",
    canonical_action=None,
    success=None,
    grading_safe: bool = False,
) -> TutorialStep:
    return TutorialStep(
        id=step_id,
        title=title,
        goal=goal,
        canonical_action=canonical_action,
        success=success or [],
        grading_safe=grading_safe,
    )


def _make_spec(steps=None) -> TutorialSpec:
    if steps is None:
        steps = [_make_step()]
    return TutorialSpec(
        schema_version=TUTORIALSPEC_VERSION,
        id="test_pack",
        name="Test Pack",
        version="1.0",
        authors=["Tester"],
        description="A test pack",
        docs=[],
        steps=steps,
        docs_dir=Path("/fake/docs"),
        pack_path=Path("/fake/pack"),
    )


# ---------------------------------------------------------------------------
# CompileResult
# ---------------------------------------------------------------------------

class TestCompileResult:
    def test_ok_when_no_errors(self):
        result = CompileResult(spec=_make_spec(), issues=[])
        assert result.ok is True

    def test_not_ok_when_error_present(self):
        issue = ValidationIssue(step_id="s1", field="id", message="dup", severity="error")
        result = CompileResult(spec=_make_spec(), issues=[issue])
        assert result.ok is False

    def test_ok_when_only_warnings(self):
        issue = ValidationIssue(step_id="s1", field="f", message="warn", severity="warning")
        result = CompileResult(spec=_make_spec(), issues=[issue])
        assert result.ok is True

    def test_summary_ok(self):
        spec = _make_spec(steps=[_make_step("s1"), _make_step("s2")])
        result = CompileResult(spec=spec, issues=[])
        assert result.summary().startswith("OK")
        assert "2 step(s)" in result.summary()

    def test_summary_failed(self):
        issue = ValidationIssue(step_id="s1", field="id", message="dup", severity="error")
        result = CompileResult(spec=_make_spec(), issues=[issue])
        assert "FAILED" in result.summary()
        assert "1 error" in result.summary()

    def test_summary_ok_with_warning(self):
        issue = ValidationIssue(step_id="s1", field="f", message="w", severity="warning")
        result = CompileResult(spec=_make_spec(), issues=[issue])
        summary = result.summary()
        assert "OK" in summary
        assert "warning" in summary


# ---------------------------------------------------------------------------
# Compiler — unique ID check
# ---------------------------------------------------------------------------

class TestUniqueIds:
    def test_no_issue_for_unique_ids(self):
        spec = _make_spec(steps=[_make_step("a"), _make_step("b")])
        result = TutorialSpecCompiler().compile(spec)
        assert result.ok
        assert not any(i.field == "id" for i in result.issues)

    def test_error_for_duplicate_id(self):
        spec = _make_spec(steps=[_make_step("same"), _make_step("same")])
        result = TutorialSpecCompiler().compile(spec)
        assert not result.ok
        id_issues = [i for i in result.issues if i.field == "id"]
        assert len(id_issues) == 1
        assert "same" in id_issues[0].message

    def test_three_duplicates_reported_once_each(self):
        """Only the *repeated* occurrences are reported, not the first."""
        spec = _make_spec(steps=[
            _make_step("dup"),
            _make_step("dup"),
            _make_step("dup"),
        ])
        result = TutorialSpecCompiler().compile(spec)
        id_issues = [i for i in result.issues if i.field == "id"]
        # Two repetitions → two issues
        assert len(id_issues) == 2


# ---------------------------------------------------------------------------
# Compiler — canonical action check
# ---------------------------------------------------------------------------

class TestCanonicalActions:
    def test_none_canonical_action_passes(self):
        spec = _make_spec(steps=[_make_step(canonical_action=None)])
        result = TutorialSpecCompiler().compile(spec)
        assert result.ok

    @pytest.mark.parametrize("action", list(CANONICAL_ACTION_MAP.values()))
    def test_all_canonical_map_values_pass(self, action):
        spec = _make_spec(steps=[_make_step(canonical_action=action)])
        result = TutorialSpecCompiler().compile(spec)
        canon_issues = [i for i in result.issues if i.field == "canonical_action"]
        assert not canon_issues, f"Unexpected issue for known action '{action}'"

    def test_saxoflow_prefix_passes(self):
        action = "saxoflow custom run something"
        spec = _make_spec(steps=[_make_step(canonical_action=action)])
        result = TutorialSpecCompiler().compile(spec)
        canon_issues = [i for i in result.issues if i.field == "canonical_action"]
        assert not canon_issues

    def test_unknown_canonical_is_warning_not_error(self):
        action = "some_unknown_tool --do-stuff"
        spec = _make_spec(steps=[_make_step(canonical_action=action)])
        result = TutorialSpecCompiler().compile(spec)
        # Should still compile OK (warnings don't block)
        assert result.ok
        canon_issues = [i for i in result.issues if i.field == "canonical_action"]
        assert len(canon_issues) == 1
        assert canon_issues[0].severity == "warning"


# ---------------------------------------------------------------------------
# Compiler — success check kinds
# ---------------------------------------------------------------------------

class TestSuccessChecks:
    @pytest.mark.parametrize("kind", list(KNOWN_CHECK_KINDS))
    def test_all_known_kinds_pass(self, kind):
        step = _make_step(success=[CheckDef(kind=kind, pattern="x")])
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        kind_issues = [i for i in result.issues if i.field == "success"]
        assert not kind_issues

    def test_unknown_kind_is_error(self):
        step = _make_step(success=[CheckDef(kind="totally_made_up", pattern="x")])
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        assert not result.ok
        kind_issues = [i for i in result.issues if i.field == "success"]
        assert len(kind_issues) == 1
        assert "totally_made_up" in kind_issues[0].message

    def test_multiple_unknown_kinds_all_reported(self):
        checks = [CheckDef(kind="bad1"), CheckDef(kind="bad2")]
        step = _make_step(success=checks)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        kind_issues = [i for i in result.issues if i.field == "success"]
        assert len(kind_issues) == 2


# ---------------------------------------------------------------------------
# Compiler — grading-safe consistency
# ---------------------------------------------------------------------------

class TestGradingSafe:
    def test_grading_safe_with_deterministic_check_passes(self):
        check = CheckDef(kind="file_exists", pattern="out.v")
        step = _make_step(success=[check], grading_safe=True)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        g_issues = [i for i in result.issues if i.field == "grading_safe"]
        assert not g_issues

    def test_grading_safe_false_with_no_deterministic_check_passes(self):
        # grading_safe=False — no warning expected even without deterministic checks
        check = CheckDef(kind="user_confirms", pattern="")
        step = _make_step(success=[check], grading_safe=False)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        g_issues = [i for i in result.issues if i.field == "grading_safe"]
        assert not g_issues

    def test_grading_safe_without_deterministic_check_is_warning(self):
        check = CheckDef(kind="user_confirms", pattern="")
        step = _make_step(success=[check], grading_safe=True)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        # Compile should still succeed (warning only)
        assert result.ok
        g_issues = [i for i in result.issues if i.field == "grading_safe"]
        assert len(g_issues) == 1
        assert g_issues[0].severity == "warning"

    def test_grading_safe_with_no_success_checks_is_warning(self):
        step = _make_step(success=[], grading_safe=True)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        g_issues = [i for i in result.issues if i.field == "grading_safe"]
        assert len(g_issues) == 1
        assert g_issues[0].severity == "warning"

    @pytest.mark.parametrize("kind", sorted(GRADING_SAFE_CHECK_KINDS))
    def test_each_grading_safe_kind_satisfies_check(self, kind):
        check = CheckDef(kind=kind, pattern="x")
        step = _make_step(success=[check], grading_safe=True)
        spec = _make_spec(steps=[step])
        result = TutorialSpecCompiler().compile(spec)
        g_issues = [i for i in result.issues if i.field == "grading_safe"]
        assert not g_issues, f"Kind '{kind}' should satisfy grading_safe"


# ---------------------------------------------------------------------------
# Compiler — full compile combinations
# ---------------------------------------------------------------------------

class TestCompileIntegration:
    def test_clean_pack_compiles_ok(self):
        steps = [
            _make_step(
                "rtlgen_step",
                canonical_action="saxoflow ai run rtlgen",
                success=[CheckDef(kind="file_exists", pattern="out.v")],
                grading_safe=True,
            ),
            _make_step(
                "sim_step",
                canonical_action="saxoflow ai run sim --yes",
                success=[CheckDef(kind="exit_code_0")],
                grading_safe=True,
            ),
        ]
        spec = _make_spec(steps=steps)
        result = TutorialSpecCompiler().compile(spec)
        assert result.ok
        assert not result.issues

    def test_multiple_issues_all_collected(self):
        """Compiler does not stop at first error — collects everything."""
        steps = [
            _make_step("dup"),
            _make_step("dup"),  # duplicate id error
            _make_step("s3", success=[CheckDef(kind="unknown_kind")]),  # check error
        ]
        spec = _make_spec(steps=steps)
        result = TutorialSpecCompiler().compile(spec)
        assert not result.ok
        assert len(result.issues) >= 2  # at least dup + unknown kind


# ---------------------------------------------------------------------------
# Compiler — preview
# ---------------------------------------------------------------------------

class TestPreview:
    def test_preview_empty_pack(self):
        spec = _make_spec(steps=[])
        text = TutorialSpecCompiler().preview(spec)
        assert "no steps" in text.lower()

    def test_preview_out_of_range(self):
        spec = _make_spec(steps=[_make_step()])
        text = TutorialSpecCompiler().preview(spec, step_index=99)
        assert "out of range" in text.lower()

    def test_preview_shows_pack_and_step_info(self):
        step = _make_step("s1", title="My Step", goal="Learn things")
        spec = _make_spec(steps=[step])
        text = TutorialSpecCompiler().preview(spec, step_index=0)
        assert "Test Pack" in text
        assert "My Step" in text
        assert "Learn things" in text

    def test_preview_shows_canonical_action(self):
        step = _make_step(canonical_action="saxoflow ai run rtlgen")
        spec = _make_spec(steps=[step])
        text = TutorialSpecCompiler().preview(spec)
        assert "saxoflow ai run rtlgen" in text

    def test_preview_shows_commands(self):
        step = _make_step()
        step.commands.append(CommandDef(native="make all"))
        spec = _make_spec(steps=[step])
        text = TutorialSpecCompiler().preview(spec)
        assert "make all" in text

    def test_preview_shows_grading_safe_flag(self):
        check = CheckDef(kind="file_exists", pattern="out.v")
        step = _make_step(success=[check], grading_safe=True)
        spec = _make_spec(steps=[step])
        text = TutorialSpecCompiler().preview(spec)
        assert "grading" in text.lower()

    def test_preview_default_index_is_zero(self):
        step0 = _make_step("s0", title="First Step")
        step1 = _make_step("s1", title="Second Step")
        spec = _make_spec(steps=[step0, step1])
        text = TutorialSpecCompiler().preview(spec)  # default step_index=0
        assert "First Step" in text
        assert "Second Step" not in text

    def test_preview_second_step(self):
        step0 = _make_step("s0", title="First Step")
        step1 = _make_step("s1", title="Second Step")
        spec = _make_spec(steps=[step0, step1])
        text = TutorialSpecCompiler().preview(spec, step_index=1)
        assert "Second Step" in text


# ---------------------------------------------------------------------------
# TutorialStep.to_step_def conversion
# ---------------------------------------------------------------------------

class TestToStepDef:
    def test_to_step_def_preserves_core_fields(self):
        step = TutorialStep(
            id="s1",
            title="T",
            goal="G",
            canonical_action="saxoflow ai run tbgen",
            grading_safe=True,
            success=[CheckDef(kind="file_exists", pattern="tb.v")],
        )
        sdef = step.to_step_def()
        assert sdef.id == "s1"
        assert sdef.title == "T"
        assert sdef.goal == "G"
        assert len(sdef.success) == 1
        # grading_safe remains TutorialSpec-only, but canonical_action is
        # preserved on StepDef for runtime canonical execution.
        assert hasattr(sdef, "canonical_action")
        assert sdef.canonical_action == "saxoflow ai run tbgen"
        assert not hasattr(sdef, "grading_safe")


# ---------------------------------------------------------------------------
# TutorialSpec.to_pack_def conversion
# ---------------------------------------------------------------------------

class TestToPackDef:
    def test_to_pack_def_converts_all_steps(self):
        steps = [_make_step("s1"), _make_step("s2")]
        spec = _make_spec(steps=steps)
        pack = spec.to_pack_def()
        assert pack.id == spec.id
        assert len(pack.steps) == 2
        assert pack.steps[0].id == "s1"
        assert pack.steps[1].id == "s2"
