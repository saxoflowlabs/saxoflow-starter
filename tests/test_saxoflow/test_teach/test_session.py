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
        assert cmd.background is False

    def test_background_flag(self):
        cmd = CommandDef(native="gtkwave foo.vcd", background=True)
        assert cmd.background is True

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


# ---------------------------------------------------------------------------
# advance / go_back edge cases
# ---------------------------------------------------------------------------

class TestAdvanceGoBack:
    def test_advance_at_last_step_marks_complete(self):
        pack = _make_pack()  # 2 steps: s1, s2
        session = TeachSession(pack=pack)
        session.advance()  # -> s2 (index 1)
        result = session.advance()  # past the end
        assert result is False
        assert session.is_complete is True

    def test_go_back_at_first_step_returns_false(self):
        session = TeachSession(pack=_make_pack())
        assert session.current_step_index == 0
        result = session.go_back()
        assert result is False
        assert session.current_step_index == 0

    def test_go_back_from_second_step(self):
        session = TeachSession(pack=_make_pack())
        session.advance()
        assert session.current_step_index == 1
        result = session.go_back()
        assert result is True
        assert session.current_step_index == 0


# ---------------------------------------------------------------------------
# reset_chunk_state
# ---------------------------------------------------------------------------

class TestResetChunkState:
    def test_resets_all_chunk_fields(self):
        session = TeachSession(pack=_make_pack())
        # Set some non-default values
        session.current_chunk_index = 5
        session.step_chunks = ["a", "b"]
        session.in_content_phase = False
        session.pending_questions = ["q1"]
        session.question_phase = True

        session.reset_chunk_state()

        assert session.current_chunk_index == 0
        assert session.step_chunks == []
        assert session.in_content_phase is True
        assert session.pending_questions == []
        assert session.question_phase is False


# ---------------------------------------------------------------------------
# add_terminal_entry — rolling window
# ---------------------------------------------------------------------------

class TestAddTerminalEntry:
    def test_adds_entry(self):
        session = TeachSession(pack=_make_pack())
        session.add_terminal_entry("ls -l", "total 4\nfile.txt")
        assert len(session.terminal_log) == 1
        assert "ls -l" in session.terminal_log[0]

    def test_empty_output_still_recorded(self):
        session = TeachSession(pack=_make_pack())
        session.add_terminal_entry("pwd", "")
        assert len(session.terminal_log) == 1

    def test_rolling_window_trims_oldest(self):
        session = TeachSession(pack=_make_pack())
        for i in range(session._TERMINAL_LOG_MAX + 5):
            session.add_terminal_entry(f"cmd{i}", f"out{i}")
        assert len(session.terminal_log) == session._TERMINAL_LOG_MAX
        # Latest entries are kept
        last = session.terminal_log[-1]
        assert f"cmd{session._TERMINAL_LOG_MAX + 4}" in last

    def test_long_output_truncated(self):
        session = TeachSession(pack=_make_pack())
        long_out = "x" * (session._TERMINAL_LOG_CAP + 100)
        session.add_terminal_entry("cat big.txt", long_out)
        assert "[truncated]" in session.terminal_log[0]


# ---------------------------------------------------------------------------
# mark_check_passed / store_agent_result
# ---------------------------------------------------------------------------

class TestMarkAndStore:
    def test_mark_check_passed(self):
        session = TeachSession(pack=_make_pack())
        session.mark_check_passed("s1")
        assert session.checks_passed["s1"] is True

    def test_store_agent_result(self):
        session = TeachSession(pack=_make_pack())
        session.store_agent_result("s1", "Generated RTL: module top; endmodule")
        assert "Generated RTL" in session.agent_results["s1"]


# ---------------------------------------------------------------------------
# update_workspace_snapshot
# ---------------------------------------------------------------------------

class TestUpdateWorkspaceSnapshot:
    def test_snapshot_file_exists(self, tmp_path):
        from saxoflow.teach.session import CheckDef, StepDef, PackDef, TeachSession
        (tmp_path / "out.v").touch()
        step = StepDef(
            id="s1", title="T", goal="G",
            success=[CheckDef(kind="file_exists", file="out.v")],
            read=[], commands=[], agent_invocations=[], hints=[], notes="",
        )
        pack = PackDef(id="p", name="P", version="1", authors=[],
                       description="", docs=[], steps=[step],
                       docs_dir=tmp_path, pack_path=tmp_path)
        session = TeachSession(pack=pack)
        session.update_workspace_snapshot(tmp_path)
        assert session.workspace_snapshot.get("out.v") is True

    def test_snapshot_file_missing(self, tmp_path):
        from saxoflow.teach.session import CheckDef, StepDef, PackDef, TeachSession
        step = StepDef(
            id="s1", title="T", goal="G",
            success=[CheckDef(kind="file_exists", file="missing.v")],
            read=[], commands=[], agent_invocations=[], hints=[], notes="",
        )
        pack = PackDef(id="p", name="P", version="1", authors=[],
                       description="", docs=[], steps=[step],
                       docs_dir=tmp_path, pack_path=tmp_path)
        session = TeachSession(pack=pack)
        session.update_workspace_snapshot(tmp_path)
        assert session.workspace_snapshot.get("missing.v") is False


# ---------------------------------------------------------------------------
# load_progress edge cases
# ---------------------------------------------------------------------------

class TestLoadProgressEdgeCases:
    def test_load_progress_file_missing_returns_false(self, tmp_path):
        session = TeachSession(pack=_make_pack())
        session._progress_file = tmp_path / "no_such_progress.json"
        assert session.load_progress() is False

    def test_load_progress_pack_id_mismatch_returns_false(self, tmp_path):
        import json
        progress_file = tmp_path / "progress.json"
        progress_file.write_text(
            json.dumps({"pack_id": "WRONG_PACK", "current_step_index": 1}),
            encoding="utf-8",
        )
        session = TeachSession(pack=_make_pack())  # pack id = "test_pack"
        session._progress_file = progress_file
        assert session.load_progress() is False
        assert session.current_step_index == 0  # unchanged
