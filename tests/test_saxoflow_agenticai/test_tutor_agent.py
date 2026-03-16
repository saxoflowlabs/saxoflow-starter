# tests/test_saxoflow_agenticai/test_tutor_agent.py
"""Tests for saxoflow_agenticai.agents.tutor_agent.TutorAgent."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from saxoflow.teach.session import (
    CommandDef,
    PackDef,
    StepDef,
    TeachSession,
)
from saxoflow_agenticai.agents.tutor_agent import TutorAgent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session() -> TeachSession:
    step = StepDef(
        id="s1",
        title="Run Simulation",
        goal="Compile and run the testbench",
        read=[],
        commands=[CommandDef(native="iverilog -g2012 tb.v dut.v", preferred="saxoflow sim")],
        agent_invocations=[],
        success=[],
        hints=["Check tool path"],
        notes="",
    )
    pack = PackDef(
        id="unit_test", name="Unit Test Pack", version="1", authors=[],
        description="", docs=[], steps=[step],
        docs_dir=Path("."), pack_path=Path("."),
    )
    return TeachSession(pack=pack)


def _mock_llm(reply: str = "This is the tutor response."):
    """A minimal mock LangChain LLM that returns *reply* on invoke."""
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content=reply)
    # BaseAgent calls query_model → llm.invoke
    return llm


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------

class TestTutorAgentInit:
    def test_default_name(self):
        agent = TutorAgent()
        assert agent.name == "TutorAgent"

    def test_template_name(self):
        agent = TutorAgent()
        assert agent.template_name == "tutor_prompt.txt"

    def test_agent_type(self):
        agent = TutorAgent()
        assert agent.agent_type == "tutor"


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------

class TestTutorAgentRun:
    def test_run_raises_without_llm(self):
        session = _make_session()
        agent = TutorAgent(llm=None)
        with pytest.raises(RuntimeError, match="LLM"):
            agent.run(session=session, student_input="hello")

    def test_run_returns_string(self):
        session = _make_session()
        llm = _mock_llm("Simulation step explanation here.")
        agent = TutorAgent(llm=llm)

        # Patch render_prompt and query_model to avoid needing template files
        with patch.object(agent, "render_prompt", return_value="PROMPT"):
            with patch.object(agent, "query_model", return_value="Tutor says: do X"):
                result = agent.run(session=session, student_input="What is iverilog?")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_run_records_turns_in_session(self):
        session = _make_session()
        llm = _mock_llm("Step explanation.")
        agent = TutorAgent(llm=llm)
        with patch.object(agent, "render_prompt", return_value="P"):
            with patch.object(agent, "query_model", return_value="Agent reply"):
                agent.run(session=session, student_input="Tell me about simulation")

        roles = [t["role"] for t in session.conversation_turns]
        assert "student" in roles
        assert "tutor" in roles

    def test_run_on_complete_session_returns_complete_message(self):
        session = _make_session()
        session.advance()  # go past the only step → is_complete
        session.advance()
        agent = TutorAgent(llm=_mock_llm())
        result = agent.run(session=session)
        assert "complete" in result.lower() or "finish" in result.lower()


# ---------------------------------------------------------------------------
# _build_context_bundle tests
# ---------------------------------------------------------------------------

class TestContextBundle:
    def test_bundle_keys_present(self):
        session = _make_session()
        agent = TutorAgent()
        with patch("saxoflow.teach.retrieval.retrieve_chunks", return_value=[]):
            bundle = agent._build_context_bundle(session, "test query")

        expected_keys = {
            "step_index", "total_steps", "step_title", "step_goal",
            "retrieved_chunks", "step_commands", "conversation_history",
            "student_input",
        }
        assert expected_keys.issubset(set(bundle.keys()))

    def test_bundle_step_index_is_1_based(self):
        session = _make_session()
        agent = TutorAgent()
        with patch("saxoflow.teach.retrieval.retrieve_chunks", return_value=[]):
            bundle = agent._build_context_bundle(session, "")
        assert bundle["step_index"] == "1"

    def test_bundle_no_chunks_shows_sentinel(self):
        session = _make_session()
        agent = TutorAgent()
        with patch("saxoflow.teach.retrieval.retrieve_chunks", return_value=[]):
            bundle = agent._build_context_bundle(session, "")
        assert "No document excerpts" in bundle["retrieved_chunks"]


# ---------------------------------------------------------------------------
# improve() tests
# ---------------------------------------------------------------------------

class TestTutorAgentImprove:
    def test_improve_calls_run(self):
        session = _make_session()
        agent = TutorAgent(llm=_mock_llm())
        with patch.object(agent, "run", return_value="Improved reply") as mock_run:
            result = agent.improve(session=session, feedback="simpler please")
        mock_run.assert_called_once()
        assert result == "Improved reply"
