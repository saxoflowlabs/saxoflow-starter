from __future__ import annotations


def test_model_selection_failure_returns_error(ai_buddy_mod, monkeypatch):
    def boom(**_):
        raise RuntimeError("provider down")

    monkeypatch.setattr(ai_buddy_mod.ModelSelector, "get_model", boom)
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Model selection failed" in res["message"]


def test_model_invoke_failure_returns_error(ai_buddy_mod, patch_model):
    patch_model(response=None, err=RuntimeError("invoke failed"))
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Model invocation failed" in res["message"]


def test_empty_llm_content_returns_error(ai_buddy_mod, patch_model):
    patch_model(response="")  # leads to empty/invalid content
    res = ai_buddy_mod.ask_ai_buddy("hello")
    assert res["type"] == "error"
    assert "Empty or invalid LLM response content" in res["message"]


def test_get_agent_failure_returns_error(ai_buddy_mod, monkeypatch):
    def boom(action):
        raise RuntimeError("no agent")

    monkeypatch.setattr(ai_buddy_mod.AgentManager, "get_agent", boom)
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review="code")
    assert res["type"] == "error"
    assert "Failed to get review agent" in res["message"]


def test_agent_run_failure_returns_error(ai_buddy_mod, patch_agent):
    patch_agent(err=RuntimeError("run exploded"))
    res = ai_buddy_mod.ask_ai_buddy("review rtl", file_to_review="code")
    assert res["type"] == "error"
    assert "Review agent run failed" in res["message"]
