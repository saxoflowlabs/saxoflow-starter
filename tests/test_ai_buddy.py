"""
Tests for cool_cli.ai_buddy module.

These tests verify that `detect_action` correctly identifies trigger
keywords, that `ask_ai_buddy` returns the appropriate action types
based on input, and that review logic branches behave as expected
when file content is provided or missing.  External dependencies
(`ModelSelector` and `AgentManager`) are patched with lightweight
stubs to isolate the logic.
"""

from unittest import mock

import cool_cli.coolcli.ai_buddy as ai_buddy


def test_detect_action_matches_keyword():
    action, keyword = ai_buddy.detect_action("Please generate RTL for my design")
    assert action == "rtlgen"
    assert keyword in "generate rtl"
    # Unknown messages should return (None, None)
    assert ai_buddy.detect_action("Hello world") == (None, None)


def test_ask_ai_buddy_review_branch(monkeypatch):
    """ask_ai_buddy returns need_file when review action lacks code."""
    # Provide a message that matches a review action
    result = ai_buddy.ask_ai_buddy("review RTL", file_to_review=None)
    assert result["type"] == "need_file"

    # When file content supplied, the review agent should be invoked
    class DummyAgent:
        def run(self, arg):
            return "All good"
    with mock.patch("cool_cli.coolcli.ai_buddy.AgentManager.get_agent", return_value=DummyAgent()):
        res = ai_buddy.ask_ai_buddy("review rtl", file_to_review="module m; endmodule")
        assert res["type"] == "review_result"
        assert res["message"] == "All good"


def test_ask_ai_buddy_chat_and_action(monkeypatch):
    """ask_ai_buddy should differentiate between chat and explicit actions."""
    # Stub a dummy LLM with an invoke method
    class DummyLLM:
        def __init__(self, response):
            self.response = response
        def invoke(self, prompt):
            return self.response
    # For normal chat, return content without action marker
    with mock.patch("cool_cli.coolcli.ai_buddy.ModelSelector.get_model", return_value=DummyLLM("Hello!")):
        res = ai_buddy.ask_ai_buddy("How do I install this?", history=[{"user": "Q", "assistant": "A"}])
        assert res["type"] == "chat"
        assert "Hello" in res["message"]
    # For action triggers, return string containing __ACTION:rtlgen__
    with mock.patch("cool_cli.coolcli.ai_buddy.ModelSelector.get_model", return_value=DummyLLM("Do it __ACTION:rtlgen__")):
        res = ai_buddy.ask_ai_buddy("generate rtl")
        assert res["type"] == "action"
        assert res["action"] == "rtlgen"