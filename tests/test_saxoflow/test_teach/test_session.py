# tests/test_saxoflow/test_teach/test_session.py
"""Tests for saxoflow.teach.session — TeachSession and dataclasses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from saxoflow.teach.session import (
    AgentInvocationDef,
    CheckDef,
    CommandDef,
    PackDef,
    StepDef,
    TeachSession,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_step(step_id: str = "s1", title: str = "Step One") -> StepDef:
    return StepDef(
        id=step_id,
        title=title,
        goal="Achieve something",
        read=[],
        commands=[CommandDef(native="echo hello")],
        agent_invocations=[],
        success=[CheckDef(kind="exit_code_0")],
        hints=["Try this"],
        notes="",
    )


def _make_pack(steps=None) -> PackDef:
    if steps is None:
        steps = [_make_step("s1", "Step One"), _make_step("s2", "Step Two")]
    return PackDef(
        id="test_pack",
        name="Test Pack",
        version="1.0",
        authors=["Test Author"],
        description="A test pack",
        docs=[],
        steps=steps,
        docs_dir=Path("/tmp/docs"),
        pack_path=Path("/tmp/test_pack"),
    )


@pytest.fixture
def session() -> TeachSession:
    return TeachSession(pack=_make_pack())


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestCommandDef:
    def test_defaults(self):
        cmd = CommandDef(native="iverilog -V")
        assert cmd.native == "iverilog -V"
        assert cmd.preferred is None
        assert cmd.use_preferred_if_available is True

    def test_frozen(self):
        cmd = CommandDef(native="echo")
        with pytest.raises((TypeError, AttributeError)):
            cmd.native = "other"  # type: ignore[misc]


class TestCheckDef:
    def test_defaults(self):
        chk = CheckDef(kind="file_exists")
        assert chk.kind == "file_exists"
        assert chk.pattern == ""
        assert chk.file == ""

    def test_full(self):
        chk = CheckDef(kind="file_contains", pattern="module", file="rtl/dut.v")
        assert chk.file == "rtl/dut.v"


class TestAgentInvocationDef:
    def test_defaults(self):
        inv = AgentInvocationDef(agent_key="rtlgen")
        assert inv.agent_key == "rtlgen"
        assert inv.args == {}
        assert inv.description == ""


# ---------------------------------------------------------------------------
# TeachSession tests
# ---------------------------------------------------------------------------

class TestTeachSession:
    def test_initial_state(self, session: TeachSession):
        assert session.current_step_index == 0
        assert not session.is_complete
        assert session.total_steps == 2
        assert session.current_step is not None
        assert session.current_step.id == "s1"

    def test_advance(self, session: TeachSession):
        advanced = session.advance()
        assert advanced is True
        assert session.current_step_index == 1
        assert session.current_step.id == "s2"

    def test_advance_at_end(self, session: TeachSession):
        session.advance()
        advanced = session.advance()
        assert advanced is False
        assert session.is_complete

    def test_go_back(self, session: TeachSession):
        session.advance()
        went_back = session.go_back()
        assert went_back is True
        assert session.current_step_index == 0

    def test_go_back_at_start(self, session: TeachSession):
        went_back = session.go_back()
        assert went_back is False
        assert session.current_step_index == 0

    def test_add_turn_and_history(self, session: TeachSession):
        session.add_turn("student", "Hello")
        session.add_turn("tutor", "Hi there")
        assert len(session.conversation_turns) == 2
        assert session.conversation_turns[0] == {"role": "student", "content": "Hello"}

    def test_history_max_trimmed(self, session: TeachSession):
        """Conversation history respects MAX_HISTORY_TURNS."""
        for i in range(20):
            session.add_turn("student", f"Message {i}")
        assert len(session.conversation_turns) <= TeachSession.MAX_HISTORY_TURNS * 2

    def test_mark_check_passed(self, session: TeachSession):
        session.mark_check_passed("s1")
        assert "s1" in session.checks_passed

    def test_store_agent_result(self, session: TeachSession):
        session.store_agent_result("s1", "RTL generated")
        assert "RTL generated" in session.agent_results["s1"]

    def test_save_and_load_progress(self, session: TeachSession, tmp_path: Path):
        """save_progress / load_progress round-trip."""
        # Override progress dir to tmp_path
        session._progress_file = tmp_path / "progress.json"
        session.advance()
        session.mark_check_passed("s1")
        session.save_progress()

        assert session._progress_file.exists()

        # Create a new session and load
        session2 = TeachSession(pack=_make_pack())
        session2._progress_file = session._progress_file
        loaded = session2.load_progress()
        assert loaded is True
        assert session2.current_step_index == 1
        assert "s1" in session2.checks_passed

    def test_complete_session_has_no_current_step(self, session: TeachSession):
        session.advance()
        session.advance()  # goes past the end
        # After is_complete, current_step should be None
        assert session.is_complete
        assert session.current_step is None
