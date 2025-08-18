from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.reviewers.debug_agent

Hermetic, defect-oriented coverage for:
- Prompt loader (pkg file): success + failure
- extract_structured_debug_report: cleaning, truncation, headings order, custom headings
- DebugAgent.run:
    * happy path (structured output + agent extraction)
    * empty raw -> warning + fallback + 'UserAction'
    * LLM exception wrapped
    * .improve proxies to .run
- _extract_agents_from_debug defaulting behavior

No network; filesystem only via tmp_path when explicitly used.
We patch the agent's PromptTemplate instance when needed to avoid real files.
"""

import re
import types
from typing import Any

import pytest


# ------------------------------
# Local doubles / helpers
# ------------------------------

class DummyLLM:
    """LLM double that records prompts and returns a configured result."""
    def __init__(self, result: Any = "OK", raise_on_invoke: BaseException | None = None):
        self.result = result
        self.raise_on_invoke = raise_on_invoke
        self.seen: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.seen.append(prompt)
        if self.raise_on_invoke:
            raise self.raise_on_invoke
        return self.result


class DummyPrompt:
    """PromptTemplate stand-in exposing .format(**kwargs) like LangChain."""
    def __init__(self, fmt: str):
        self.fmt = fmt

    def format(self, **kwargs) -> str:
        return self.fmt.format(**kwargs)


def _fresh_module():
    """Reload SUT to avoid global state leaking across tests."""
    import importlib
    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.agents.reviewers.debug_agent")
    )


# ------------------------------
# _load_prompt_from_pkg
# ------------------------------

def test__load_prompt_from_pkg_success_and_fail(tmp_path):
    """
    _load_prompt_from_pkg: reads file or raises FileNotFoundError.
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    target = pdir / "debug_prompt.txt"
    target.write_text("DBG_BASE", encoding="utf-8")
    sut._PROMPTS_DIR = pdir

    # success
    assert sut._load_prompt_from_pkg("debug_prompt.txt") == "DBG_BASE"

    # failure
    with pytest.raises(FileNotFoundError):
        sut._load_prompt_from_pkg("missing.txt")


# ------------------------------
# extract_structured_debug_report
# ------------------------------

def test_extract_structured_debug_report_cleans_and_orders():
    """
    Structured report: removes fences/boilerplate, flattens whitespace/bullets,
    preserves canonical heading order, and truncates at 'additional_kwargs'.
    """
    sut = _fresh_module()

    raw = (
        "```log\nignored block\n```\n"
        "content='Problems identified: \\n - missing reset\\n - glitch'\n"
        "For example, this long aside should go away.\n"
        "Explanation: **bad** edge on clk\\n\n"
        "Additionally, consider verbose aside to drop.\n"
        "Suggested Fixes: - add reset, - change edge  \n"
        "Suggested Agent for Correction: RTLGenAgent, TBGenAgent\n"
        "additional_kwargs={'token_usage': 1}\n"
        "tail that must be truncated"
    )

    out = sut.extract_structured_debug_report(raw)

    # Canonical headings in order
    expected_headings = [
        "Problems identified:",
        "Explanation:",
        "Suggested Fixes:",
        "Suggested Agent for Correction:",
    ]
    assert [h for h in expected_headings if h in out] == expected_headings

    # Cleaned values (bullets flattened, bold removed, extras truncated)
    assert "Problems identified: missing reset glitch" in out
    assert "Explanation: bad edge on clk" in out
    assert "Suggested Fixes: add reset, change edge" in out
    assert "Suggested Agent for Correction: RTLGenAgent, TBGenAgent" in out
    assert "tail that must be truncated" not in out


def test_extract_structured_debug_report_custom_headings_and_defaults():
    """
    When custom headings are provided, the function emits them in the same order
    and defaults to 'None' when a heading is missing.
    """
    sut = _fresh_module()

    custom = ["A", "B"]
    raw = "A: value1\nB: value2\n"
    out = sut.extract_structured_debug_report(raw, headings=custom)
    # Exact form: "Heading: value"
    assert out.splitlines()[0] == "A: value1"
    assert out.splitlines()[-1] == "B: value2"

    # Missing values -> 'None'
    out2 = sut.extract_structured_debug_report("A: none\n", headings=custom)
    assert "A: None" in out2
    assert "B: None" in out2


# ------------------------------
# DebugAgent.run / improve
# ------------------------------

def test_debugagent_run_happy_path(monkeypatch):
    """
    run(): renders prompt, invokes LLM, returns structured report and agent list.
    """
    sut = _fresh_module()

    # Deterministic prompt; assert formatting captures variables
    monkeypatch.setattr(
        sut,
        "debug_prompt_template",
        DummyPrompt("R={rtl_code}|T={tb_code}|SO={sim_stdout}|SE={sim_stderr}|EM={sim_error_message}"),
        raising=True,
    )

    raw = (
        "Problems identified: - foo ; bar\n"
        "Explanation: bad ; semicolons\n"
        "Suggested Fixes: fix foo, fix bar\n"
        "Suggested Agent for Correction: RTLGenAgent, TBGenAgent"
    )
    dummy = DummyLLM(raw)
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.DebugAgent(verbose=True)
    out, agents = agent.run("rtl", "tb", "out", "err", "msg")

    # Prompt variables rendered
    assert dummy.seen and "R=rtl|T=tb|SO=out|SE=err|EM=msg" in dummy.seen[0]

    # Structured output contains cleaned sections
    assert "Problems identified: foo bar" in out or "Problems identified: foo ; bar" in out
    assert "Explanation" in out and "Suggested Fixes" in out

    # Agent list extracted from raw (not the cleaned text)
    assert agents == ["RTLGenAgent", "TBGenAgent"]


def test_debugagent_run_empty_raw_warns_and_fallback(monkeypatch):
    """
    If LLM returns empty string, DebugAgent warns and uses a fallback that suggests 'UserAction'.
    Patch *instance* logger to capture the warning.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "debug_prompt_template", DummyPrompt("X"), raising=True)

    dummy = DummyLLM("")
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    seen_warnings: list[str] = []

    def capture_warning(msg, *args, **kwargs):
        seen_warnings.append(msg % args if args else str(msg))

    agent = sut.DebugAgent()
    # Patch instance logger (the agent logs via self.logger, not module logger).
    monkeypatch.setattr(agent.logger, "warning", capture_warning, raising=True)

    out, agents = agent.run("r", "t")
    assert any("LLM returned empty debug output" in m for m in seen_warnings)
    assert "Suggested Agent for Correction: UserAction" in out
    assert agents == ["UserAction"]


def test_debugagent_llm_exception_wrapped(monkeypatch):
    """
    LLM exceptions are wrapped into a RuntimeError with agent name in the message.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "debug_prompt_template", DummyPrompt("Y"), raising=True)

    dummy = DummyLLM(raise_on_invoke=ValueError("boom"))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    with pytest.raises(RuntimeError) as ei:
        sut.DebugAgent().run("r", "t")
    assert "LLM invocation failed in DebugAgent" in str(ei.value)


def test_debugagent_improve_proxies_to_run(monkeypatch):
    """
    improve(): proxies to run(). Validate identical output and agent list.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "debug_prompt_template", DummyPrompt("Z"), raising=True)

    raw = (
        "Problems identified: none\n"
        "Explanation: none\n"
        "Suggested Fixes: none\n"
        "Suggested Agent for Correction: TBGenAgent"
    )
    dummy = DummyLLM(raw)
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.DebugAgent()
    r1, a1 = agent.run("r", "t")
    r2, a2 = agent.improve("r", "t", feedback="ignored")
    assert r1 == r2
    assert a1 == a2 == ["TBGenAgent"]


def test__extract_agents_from_debug_defaults_when_missing():
    """
    If the 'Suggested Agent for Correction' heading is absent, the helper
    defaults to both RTLGenAgent and TBGenAgent.
    """
    sut = _fresh_module()
    text = "Problems identified: x\nExplanation: y\nSuggested Fixes: z"
    out = sut.DebugAgent._extract_agents_from_debug(text)
    assert out == ["RTLGenAgent", "TBGenAgent"]
