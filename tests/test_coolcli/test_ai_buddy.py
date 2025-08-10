from __future__ import annotations

import pytest


def test_detect_action_basic(ai_buddy_mod):
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
    act, _ = ai_buddy_mod.detect_action(msg)
    assert act == expected


def test_detect_action_case_insensitive(ai_buddy_mod):
    for token in ["GENERATE RTL", "Generate Rtl", "gEnErAtE rTl"]:
        act, key = ai_buddy_mod.detect_action(token)
        assert act == "rtlgen"
        assert key == "generate rtl"


def test_detect_action_first_match_wins(ai_buddy_mod):
    # Contains both "simulate" and "generate rtl" → dict defines "generate rtl" earlier.
    msg = "please simulate and also generate rtl soon"
    act, key = ai_buddy_mod.detect_action(msg)
    assert act == "rtlgen"
    assert key == "generate rtl"


def test_history_truncation_and_chat(ai_buddy_mod, patch_model):
    # Build 7 turns; only last 5 must be in the prompt sent to the model.
    history = [{"user": f"U{i}", "assistant": f"A{i}"} for i in range(1, 8)]
    dummy = patch_model(response="Hello from model")
    res = ai_buddy_mod.ask_ai_buddy("How to proceed?", history=history)
    assert res["type"] == "chat"
    assert "Hello from model" in res["message"]

    # Inspect the prompt the DummyLLM saw
    assert dummy.seen_prompts, "Model was not invoked"
    prompt = dummy.seen_prompts[-1]
    assert "User: U1" not in prompt and "User: U2" not in prompt  # dropped
    assert "User: U3" in prompt and "User: U7" in prompt          # kept last 5


def test_action_token_path(ai_buddy_mod, patch_model):
    dummy = patch_model(response="prep then __ACTION:rtlgen__ go")
    res = ai_buddy_mod.ask_ai_buddy("please generate rtl")
    assert res["type"] == "action"
    assert res["action"] == "rtlgen"
    # Ensure the prompt used the guidance suffix that mentions the token
    assert dummy.seen_prompts and "__ACTION:{action}__" in dummy.seen_prompts[-1]


def test_review_need_file(ai_buddy_mod):
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review=None)
    assert res["type"] == "need_file"
    assert "Please provide the code/file to review" in res["message"]


def test_review_with_file_string_result(ai_buddy_mod, patch_agent):
    agent = patch_agent(result="Looks good")
    res = ai_buddy_mod.ask_ai_buddy("review formal", file_to_review="module m; endmodule")
    assert res["type"] == "review_result"
    assert res["action"] == "fpropreview"
    assert res["message"] == "Looks good"
    assert agent.seen_inputs and "module m" in agent.seen_inputs[-1]


def test_review_with_file_nonstring_result_is_coerced(ai_buddy_mod, patch_agent):
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
    patch_model(response="ok")
    res = ai_buddy_mod.ask_ai_buddy(msg)  # type: ignore[arg-type]
    # If it contains 'generate rtl', action token is possible; otherwise normal chat.
    assert res["type"] in {"chat", "action", "need_file", "review_result", "error"}
