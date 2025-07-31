"""
Tests for core components of the agentic AI subpackage.

These tests verify the prompt rendering utilities, model selection logic,
agent factory dispatching, and feedback coordination loops.  The aim
here is to ensure the correct classes are returned and that iteration
terminates appropriately when no further improvements are necessary.
"""

import os
from pathlib import Path
from unittest import mock

import pytest

from saxoflow_agenticai.core.agent_base import BaseAgent
from saxoflow_agenticai.core.prompt_manager import PromptManager
from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator


def test_prompt_manager_render(tmp_path):
    """PromptManager renders Jinja templates from a custom directory."""
    # Create a temporary template directory with a simple template
    tmpl_dir = tmp_path / "templates"
    tmpl_dir.mkdir()
    (tmpl_dir / "hello.txt").write_text("Hi {{name}}!")
    pm = PromptManager(template_dir=str(tmpl_dir))
    rendered = pm.render("hello.txt", {"name": "Alice"})
    assert rendered == "Hi Alice!"


def test_agent_manager_returns_correct_class(monkeypatch):
    """AgentManager.get_agent returns an instance of the requested agent class."""
    # Stub out ModelSelector.get_model to avoid instantiating real LLMs
    from saxoflow_agenticai.core import model_selector
    monkeypatch.setattr(model_selector.ModelSelector, "get_model", lambda *a, **k: object())
    # For each agent key, ensure get_agent returns expected type name
    for name in AgentManager.all_agent_names():
        agent = AgentManager.get_agent(name)
        # The class name should include the key (case insensitive)
        assert name.lower() in agent.__class__.__name__.lower() or name == "sim"


def test_feedback_coordinator_iterate_improvements_stops(monkeypatch):
    """iterate_improvements stops when feedback agent reports no issues."""
    class DummyGen:
        agent_type = "rtlgen"
        def __init__(self):
            self.calls = 0
        def run(self, spec):
            self.calls += 1
            return f"code{self.calls}"
        def improve(self, spec, prev_code, feedback):
            self.calls += 1
            return f"code{self.calls}"
    class DummyReview:
        def __init__(self):
            self.calls = 0
        def run(self, spec, code):
            self.calls += 1
            # Return no issues on second review
            return "No issues" if self.calls >= 2 else "Found a bug"
    gen = DummyGen()
    review = DummyReview()
    out, feedback = AgentFeedbackCoordinator.iterate_improvements(gen, "spec", review, max_iters=3)
    # Should stop after one improvement because second review says no issues
    assert gen.calls == 2
    assert feedback == "No issues"