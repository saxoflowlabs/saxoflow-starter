# tests/test_coolcli/test_ai_buddy.py
from __future__ import annotations

import pytest


def test_detect_action_basic(ai_buddy_mod):
    """Detect the primary action and key phrase; no match returns (None, None)."""
    act, key = ai_buddy_mod.detect_action("Please generate RTL for my design")
    assert act == "rtlgen"
    assert key == "generate rtl"
    assert ai_buddy_mod.detect_action("Hello world") == (None, None)


@pytest.mark.parametrize(
    "msg,expected",
    [
        ("rtlgen now", "rtlgen"),
        ("Please run simulation", "sim"),
        ("start synthesis", "synth"),
        ("debug the run", "debug"),
        ("create report", "report"),
        ("run pipeline", "fullpipeline"),
        ("review formal", "fpropreview"),
        ("check testbench", "tbreview"),
        ("check rtl", "rtlreview"),
    ],
)
def test_detect_action_variants(ai_buddy_mod, msg, expected):
    """Ensure synonym variants map to the expected action token."""
    act, _ = ai_buddy_mod.detect_action(msg)
    assert act == expected


def test_detect_action_case_insensitive(ai_buddy_mod):
    """Case-insensitive detection should still hit the 'rtlgen' path."""
    for token in ["GENERATE RTL", "Generate Rtl", "gEnErAtE rTl"]:
        act, key = ai_buddy_mod.detect_action(token)
        assert act == "rtlgen"
        assert key == "generate rtl"


def test_detect_action_first_match_wins(ai_buddy_mod):
    """If multiple phrases appear, the first mapping in the dict wins."""
    msg = "please simulate and also generate rtl soon"
    act, key = ai_buddy_mod.detect_action(msg)
    assert act == "rtlgen"
    assert key == "generate rtl"


def test_history_truncation_and_chat(ai_buddy_mod, patch_model):
    """Only the last 5 turns should be included in the prompt sent to the model."""
    history = [{"user": f"U{i}", "assistant": f"A{i}"} for i in range(1, 8)]
    dummy = patch_model(response="Hello from model")
    res = ai_buddy_mod.ask_ai_buddy("How to proceed?", history=history)
    assert res["type"] == "chat"
    assert "Hello from model" in res["message"]

    # Inspect prompt seen by the model
    prompt = dummy.seen_prompts[-1]
    assert "User: U1" not in prompt and "User: U2" not in prompt  # dropped
    assert "User: U3" in prompt and "User: U7" in prompt          # kept last 5


def test_action_token_path(ai_buddy_mod, patch_model):
    """LLM emits an action token → surface action result with token extracted."""
    dummy = patch_model(response="prep then __ACTION:rtlgen__ go")
    res = ai_buddy_mod.ask_ai_buddy("please generate rtl")
    assert res["type"] == "action"
    assert res["action"] == "rtlgen"
    # Guidance suffix should be part of the composed prompt
    assert dummy.seen_prompts and "__ACTION:{action}__" in dummy.seen_prompts[-1]


def test_review_need_file(ai_buddy_mod):
    """Review path with no file/code should request a file (need_file)."""
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review=None)
    assert res["type"] == "need_file"
    assert "Please provide the code/file to review" in res["message"]


def test_review_with_file_string_result(ai_buddy_mod, patch_agent):
    """Review path: agent returns a string → pass through as review_result.message."""
    agent = patch_agent(result="Looks good")
    res = ai_buddy_mod.ask_ai_buddy("review formal", file_to_review="module m; endmodule")
    assert res["type"] == "review_result"
    assert res["action"] == "fpropreview"
    assert res["message"] == "Looks good"
    assert agent.seen_inputs and "module m" in agent.seen_inputs[-1]


def test_review_with_file_nonstring_result_is_coerced(ai_buddy_mod, patch_agent):
    """Review path: agent returns non-string → coerced to string in message."""
    agent = patch_agent(result={"ok": True})
    res = ai_buddy_mod.ask_ai_buddy("check testbench", file_to_review="tb code")
    assert res["type"] == "review_result"
    assert res["action"] == "tbreview"
    assert isinstance(res["message"], str)
    assert "True" in res["message"]


@pytest.mark.parametrize(
    "msg",
    [
        None,
        "",
        "こんにちは、どうやってインストールしますか？",
        "generate rtl " * 500,  # long input
    ],
)
def test_boundary_inputs_do_not_crash(ai_buddy_mod, patch_model, msg):
    """Boundary/odd inputs shouldn't crash ask_ai_buddy; result has a valid type."""
    patch_model(response="ok")
    res = ai_buddy_mod.ask_ai_buddy(msg)  # type: ignore[arg-type]
    assert res["type"] in {"chat", "action", "need_file", "review_result", "error"}


# -------------------------
# Error handling scenarios
# -------------------------

def test_model_selection_failure_returns_error(ai_buddy_mod, monkeypatch):
    """If model selection fails, surface a structured error result."""
    def boom(**_):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_buddy_mod.ModelSelector, "get_model", boom)
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Model selection failed" in res["message"]


def test_model_invoke_failure_returns_error(ai_buddy_mod, patch_model):
    """If the model’s invoke() fails, return an error result."""
    patch_model(response=None, err=RuntimeError("invoke failed"))
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Model invocation failed" in res["message"]


def test_empty_llm_content_returns_error(ai_buddy_mod, patch_model):
    """Empty string content from LLM is considered invalid and returns error."""
    patch_model(response="")
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Empty or invalid LLM response content" in res["message"]


def test_get_agent_failure_returns_error(ai_buddy_mod, monkeypatch):
    """If AgentManager.get_agent fails, surface a structured error."""
    def boom(action):
        raise RuntimeError("no agent")

    monkeypatch.setattr(ai_buddy_mod.AgentManager, "get_agent", boom)
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review="code")
    assert res["type"] == "error"
    assert "Failed to get review agent" in res["message"]


def test_agent_run_failure_returns_error(ai_buddy_mod, patch_agent):
    """If agent.run() raises, return a structured error."""
    patch_agent(err=RuntimeError("run exploded"))
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review="code")
    assert res["type"] == "error"
    assert "Review agent run failed" in res["message"]
