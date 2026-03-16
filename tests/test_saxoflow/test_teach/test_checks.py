# tests/test_saxoflow/test_teach/test_checks.py
"""Tests for saxoflow.teach.checks — deterministic success evaluators."""

from __future__ import annotations

from pathlib import Path

import pytest

from saxoflow.teach.checks import CheckResult, evaluate_step_success
from saxoflow.teach.session import CheckDef, CommandDef, PackDef, StepDef, TeachSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session(checks: list, last_log: str = "", last_exit: int = 0) -> tuple:
    """Return (session, project_root_tmp) with the given check list."""
    step = StepDef(
        id="test_step",
        title="Test",
        goal="test goal",
        read=[],
        commands=[],
        agent_invocations=[],
        success=checks,
        hints=[],
        notes="",
    )
    pack = PackDef(
        id="p", name="P", version="1", authors=[], description="",
        docs=[], steps=[step], docs_dir=Path("."), pack_path=Path("."),
    )
    session = TeachSession(pack=pack)
    session.last_run_log = last_log
    session.last_run_exit_code = last_exit
    session.last_run_command = "echo"
    return session


# ---------------------------------------------------------------------------
# Individual checker tests
# ---------------------------------------------------------------------------

class TestFileExistsCheck:
    def test_passes_when_file_exists(self, tmp_path):
        target = tmp_path / "out.v"
        target.touch()
        session = _make_session([CheckDef(kind="file_exists", file="out.v")])
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_when_file_missing(self, tmp_path):
        session = _make_session([CheckDef(kind="file_exists", file="missing.v")])
        assert evaluate_step_success(session, tmp_path) is False

    def test_missing_file_field(self, tmp_path):
        session = _make_session([CheckDef(kind="file_exists", file="")])
        assert evaluate_step_success(session, tmp_path) is False


class TestFileContainsCheck:
    def test_passes_when_pattern_found(self, tmp_path):
        f = tmp_path / "rtl.v"
        f.write_text("module counter ();endmodule")
        session = _make_session([CheckDef(kind="file_contains", file="rtl.v", pattern="module counter")])
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_when_pattern_absent(self, tmp_path):
        f = tmp_path / "rtl.v"
        f.write_text("// empty")
        session = _make_session([CheckDef(kind="file_contains", file="rtl.v", pattern="module counter")])
        assert evaluate_step_success(session, tmp_path) is False

    def test_missing_file(self, tmp_path):
        session = _make_session([CheckDef(kind="file_contains", file="ghost.v", pattern="x")])
        assert evaluate_step_success(session, tmp_path) is False


class TestStdoutContainsCheck:
    def test_passes_when_log_has_pattern(self, tmp_path):
        session = _make_session(
            [CheckDef(kind="stdout_contains", pattern="Icarus Verilog")],
            last_log="Icarus Verilog version 11.0",
        )
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_when_log_missing_pattern(self, tmp_path):
        session = _make_session(
            [CheckDef(kind="stdout_contains", pattern="Icarus Verilog")],
            last_log="some other output",
        )
        assert evaluate_step_success(session, tmp_path) is False


class TestExitCode0Check:
    def test_passes_on_exit_0(self, tmp_path):
        session = _make_session([CheckDef(kind="exit_code_0")], last_exit=0)
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_on_nonzero(self, tmp_path):
        session = _make_session([CheckDef(kind="exit_code_0")], last_exit=1)
        assert evaluate_step_success(session, tmp_path) is False


class TestAlwaysCheck:
    def test_always_passes(self, tmp_path):
        session = _make_session([CheckDef(kind="always")])
        assert evaluate_step_success(session, tmp_path) is True


class TestUserConfirmsCheck:
    def test_user_confirms_always_passes(self, tmp_path):
        check = CheckDef(kind="user_confirms", pattern="Confirm you have opened GTKWave")
        session = _make_session([check])
        assert evaluate_step_success(session, tmp_path) is True

    def test_user_confirms_passes_without_pattern(self, tmp_path):
        session = _make_session([CheckDef(kind="user_confirms")])
        assert evaluate_step_success(session, tmp_path) is True


class TestUnknownKind:
    def test_unknown_check_fails(self, tmp_path):
        session = _make_session([CheckDef(kind="unknown_kind_xyz")])
        assert evaluate_step_success(session, tmp_path) is False


class TestNoChecks:
    def test_no_checks_auto_pass(self, tmp_path):
        session = _make_session([])
        assert evaluate_step_success(session, tmp_path) is True


class TestMultipleChecks:
    def test_all_pass(self, tmp_path):
        f = tmp_path / "out.v"
        f.touch()
        session = _make_session(
            [CheckDef(kind="file_exists", file="out.v"), CheckDef(kind="exit_code_0")],
            last_exit=0,
        )
        assert evaluate_step_success(session, tmp_path) is True

    def test_stops_on_first_failure(self, tmp_path):
        session = _make_session(
            [CheckDef(kind="exit_code_0"), CheckDef(kind="always")],
            last_exit=1,
        )
        assert evaluate_step_success(session, tmp_path) is False


# ---------------------------------------------------------------------------
# _check_file_contains — missing-line coverage
# ---------------------------------------------------------------------------

class TestFileContainsCheck:
    def test_passes_when_pattern_in_file(self, tmp_path):
        f = tmp_path / "out.v"
        f.write_text("module top; endmodule", encoding="utf-8")
        session = _make_session([CheckDef(kind="file_contains", file="out.v", pattern="module top")])
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_when_pattern_not_in_file(self, tmp_path):
        f = tmp_path / "out.v"
        f.write_text("module top; endmodule", encoding="utf-8")
        session = _make_session([CheckDef(kind="file_contains", file="out.v", pattern="missing_signal")])
        assert evaluate_step_success(session, tmp_path) is False

    def test_fails_when_file_not_found(self, tmp_path):
        session = _make_session([CheckDef(kind="file_contains", file="ghost.v", pattern="module")])
        assert evaluate_step_success(session, tmp_path) is False

    def test_fails_when_file_field_empty(self, tmp_path):
        session = _make_session([CheckDef(kind="file_contains", file="", pattern="x")])
        assert evaluate_step_success(session, tmp_path) is False

    def test_fails_when_pattern_field_empty(self, tmp_path):
        f = tmp_path / "out.v"
        f.touch()
        session = _make_session([CheckDef(kind="file_contains", file="out.v", pattern="")])
        assert evaluate_step_success(session, tmp_path) is False


# ---------------------------------------------------------------------------
# _check_stdout_contains
# ---------------------------------------------------------------------------

class TestStdoutContainsCheck:
    def test_passes_when_pattern_in_log(self, tmp_path):
        session = _make_session(
            [CheckDef(kind="stdout_contains", pattern="Compilation OK")],
            last_log="Build started\nCompilation OK\nDone",
        )
        assert evaluate_step_success(session, tmp_path) is True

    def test_fails_when_pattern_not_in_log(self, tmp_path):
        session = _make_session(
            [CheckDef(kind="stdout_contains", pattern="MISSING")],
            last_log="Build started\nDone",
        )
        assert evaluate_step_success(session, tmp_path) is False

    def test_fails_when_pattern_empty(self, tmp_path):
        session = _make_session([CheckDef(kind="stdout_contains", pattern="")])
        assert evaluate_step_success(session, tmp_path) is False


# ---------------------------------------------------------------------------
# Unknown check kind
# ---------------------------------------------------------------------------

class TestUnknownCheckKind:
    def test_unknown_kind_returns_false(self, tmp_path):
        session = _make_session([CheckDef(kind="completely_unknown_check_xyz")])
        assert evaluate_step_success(session, tmp_path) is False
