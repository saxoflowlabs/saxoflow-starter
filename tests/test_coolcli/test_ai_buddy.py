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
    "message,expected",
    [
        ("list available pdks", {"operation": "list"}),
        (
            "install the sky130 pdk",
            {"operation": "install", "platform": "sky130hd"},
        ),
        (
            "verify gf180 pdk",
            {"operation": "verify", "platform": "gf180mcu"},
        ),
        ("diagnose pdk", {"operation": "diagnose"}),
    ],
)
def test_detect_pdk_intent_resolves_platform_aliases(ai_buddy_mod, message, expected):
    assert ai_buddy_mod.detect_pdk_intent(message) == expected


def test_ask_ai_buddy_returns_structured_pdk_action_without_llm(ai_buddy_mod):
    result = ai_buddy_mod.ask_ai_buddy("install the ihp pdk")

    assert result == {
        "type": "pdk_action",
        "operation": "install",
        "platform": "ihp-sg13g2",
    }


def test_detect_repair_intent_from_broad_failure_request(ai_buddy_mod):
    """Broad repair requests should select the latest verification failure."""
    result = ai_buddy_mod.detect_repair_intent(
        "there is an issue in the rtl or tb, help me correct whichever needed"
    )
    assert result is not None
    assert result["post_hook"] == "auto"


def test_detect_repair_intent_from_formal_failure_request(ai_buddy_mod):
    """Formal repair requests should force the formal post-check path."""
    result = ai_buddy_mod.detect_repair_intent(
        "the formal proof failed, check the issue and fix it"
    )
    assert result is not None
    assert result["post_hook"] == "formal"


def test_repair_intent_ignores_explicit_edit_file(ai_buddy_mod):
    """Explicit file requests should stay on the normal edit-file path."""
    assert ai_buddy_mod.detect_repair_intent("fix source/rtl/systemverilog/top.sv") is None


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


def test_plain_non_command_text_defaults_to_chat(ai_buddy_mod, patch_model):
    """Baseline: plain text without action keywords should remain chat output."""
    patch_model(response="This is a plain chat response")

    result = ai_buddy_mod.ask_ai_buddy("explain this project in simple terms")

    assert result["type"] == "chat"
    assert "plain chat response" in result["message"]


def test_action_token_path(ai_buddy_mod, patch_model):
    """LLM emits an action token → surface action result with token extracted."""
    dummy = patch_model(response="prep then __ACTION:rtlgen__ go")
    res = ai_buddy_mod.ask_ai_buddy("please generate rtl")
    assert res["type"] == "action"
    assert res["action"] == "rtlgen"
    # Guidance suffix should be part of the composed prompt
    assert dummy.seen_prompts and "__ACTION:{action}__" in dummy.seen_prompts[-1]


def test_chat_only_research_prompt_includes_web_sources_and_section_contract(ai_buddy_mod, monkeypatch):
    prompts_seen = []

    monkeypatch.setattr(
        ai_buddy_mod,
        "_invoke_llm",
        lambda **kw: prompts_seen.append(kw.get("prompt", "")) or "## Question\nQ\n\n## Method\nM\n\n## Sources\nS\n\n## Findings\nF\n\n## Comparisons\nC\n\n## Confidence\nHigh\n\n## Open questions\nO\n\n## Citations\n- [web:1] https://example.com",
    )

    result = ai_buddy_mod.ask_ai_buddy_chat_only(
        "compare pnr flows",
        task_hint="research",
        metadata={
            "grounded_context_refs": ["docs/plan2.md"],
            "research_workflow_policy": {"feasible": True},
            "web_research_policy": {"requested": True, "allowed": True},
            "web_research_execution": {
                "executed": True,
                "provider": "duckduckgo_html",
                "query": "compare pnr flows",
                "result_count": 1,
            },
            "web_research_sources": [
                {
                    "source_id": "1",
                    "title": "Example OpenROAD",
                    "url": "https://example.com/openroad",
                    "snippet": "OpenROAD overview",
                    "retrieved_at": "2026-06-30T00:00:00Z",
                }
            ],
        },
    )

    assert result["type"] == "chat"
    assert prompts_seen
    prompt = prompts_seen[0]
    assert "## Question, ## Method, ## Sources, ## Findings, ## Comparisons, ## Confidence, ## Open questions, ## Citations" in prompt
    assert "Web research execution metadata" in prompt
    assert "Retrieved web sources (cite them as [web:<id>])" in prompt
    assert "id: web:1" in prompt
    assert "https://example.com/openroad" in prompt


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
