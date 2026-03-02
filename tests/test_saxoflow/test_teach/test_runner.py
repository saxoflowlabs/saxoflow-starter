# tests/test_saxoflow/test_teach/test_runner.py
"""Tests for saxoflow.teach.runner — step command executor."""

from __future__ import annotations

from pathlib import Path

import pytest

from saxoflow.teach.runner import RunResult, run_step_commands
from saxoflow.teach.session import CheckDef, CommandDef, PackDef, StepDef, TeachSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session_with_commands(commands: list, project_root: Path) -> TeachSession:
    step = StepDef(
        id="run_step",
        title="Run Step",
        goal="Test execution",
        read=[],
        commands=commands,
        agent_invocations=[],
        success=[],
        hints=[],
        notes="",
    )
    pack = PackDef(
        id="p", name="P", version="1", authors=[], description="",
        docs=[], steps=[step], docs_dir=Path("."), pack_path=Path("."),
    )
    return TeachSession(pack=pack)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunStepCommandsNoCommands:
    def test_returns_empty_when_no_commands(self, tmp_path):
        session = _make_session_with_commands([], tmp_path)
        results = run_step_commands(session, tmp_path)
        assert results == []


class TestRunStepCommandsRealCommands:
    def test_echo_command_succeeds(self, tmp_path):
        cmds = [CommandDef(native="echo saxoflow_test_output")]
        session = _make_session_with_commands(cmds, tmp_path)

        import saxoflow.teach.command_map as cm
        cm._availability_checker = lambda c: True
        cm._load_registry.cache_clear()

        results = run_step_commands(session, tmp_path)

        cm._availability_checker = __builtins__["__import__"]("shutil").which and (
            lambda c: __builtins__["__import__"]("shutil").which(c.split()[0]) is not None
        )

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert "saxoflow_test_output" in results[0].stdout

    def test_session_updated_after_run(self, tmp_path):
        # Use 'echo' which is available on all test platforms
        cmds = [CommandDef(native="echo hello")]
        session = _make_session_with_commands(cmds, tmp_path)

        import saxoflow.teach.command_map as cm
        orig = cm._availability_checker
        cm._availability_checker = lambda c: True
        cm._load_registry.cache_clear()

        run_step_commands(session, tmp_path)
        cm._availability_checker = orig

        assert session.last_run_exit_code == 0
        assert "echo" in session.last_run_command

    def test_invalid_cmd_index_raises(self, tmp_path):
        cmds = [CommandDef(native="echo a")]
        session = _make_session_with_commands(cmds, tmp_path)
        with pytest.raises(ValueError, match="cmd_index"):
            run_step_commands(session, tmp_path, cmd_index=99)

    def test_unavailable_command_returns_127(self, tmp_path):
        import saxoflow.teach.command_map as cm
        orig = cm._availability_checker
        cm._availability_checker = lambda c: False  # nothing available
        cm._load_registry.cache_clear()

        cmds = [CommandDef(native="this_does_not_exist_xyz")]
        session = _make_session_with_commands(cmds, tmp_path)
        results = run_step_commands(session, tmp_path)
        cm._availability_checker = orig
        cm._load_registry.cache_clear()

        assert results[0].exit_code == 127

    def test_run_result_dataclass(self):
        r = RunResult(
            command_str="echo hi",
            stdout="hi",
            exit_code=0,
            timed_out=False,
            resolved_wrapper=False,
        )
        assert r.exit_code == 0


class TestBackgroundCommands:
    def test_background_command_returns_launched_message(self, tmp_path):
        """Background commands fire-and-forget; stdout reports 'Launched in background'."""
        import saxoflow.teach.command_map as cm
        orig = cm._availability_checker
        cm._availability_checker = lambda c: True
        cm._load_registry.cache_clear()

        # 'true' is a shell builtin / utility that exits 0 immediately
        cmds = [CommandDef(native="true", background=True)]
        session = _make_session_with_commands(cmds, tmp_path)
        results = run_step_commands(session, tmp_path)

        cm._availability_checker = orig
        cm._load_registry.cache_clear()

        assert len(results) == 1
        assert results[0].exit_code == 0
        assert "background" in results[0].stdout.lower() or "launched" in results[0].stdout.lower()
