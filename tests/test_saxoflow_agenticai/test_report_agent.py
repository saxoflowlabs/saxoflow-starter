from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.generators.report_agent

Hermetic, defect-oriented coverage for:
- Prompt loader (pkg file): success + failure
- LLM-output cleaning heuristics (_extract_report_content)
- ReportAgent.run (happy + empty-clean fallback) and logging
- ReportAgent._invoke_llm branches: .content, .text, str(), exception wrap
- Tool wrapper delegation (report_tool)

No network; only tmp_path filesystem use.
"""

import io
import logging
import types
from pathlib import Path
from typing import Any, Dict

import pytest


# ------------------------------
# Small doubles / helpers
# ------------------------------

class DummyLLM:
    """LLM double that records prompts and returns a fixed result."""
    def __init__(self, result: Any):
        self.result = result
        self.seen: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.seen.append(prompt)
        return self.result


class DummyPrompt:
    """PromptTemplate stand-in exposing .format(**kwargs) like LangChain,
    and providing .input_variables to mirror the real object.
    """
    def __init__(self, fmt: str, input_variables: list[str] | None = None):
        self.fmt = fmt
        # Mirror production input_variables so ReportAgent.run builds prompt_vars correctly.
        self.input_variables = input_variables or [
            "specification",
            "rtl_code",
            "rtl_review_report",
            "testbench_code",
            "testbench_review_report",
            "formal_properties",
            "formal_property_review_report",
            "simulation_status",
            "simulation_stdout",
            "simulation_stderr",
            "simulation_error_message",
            "debug_report",
        ]

    def format(self, **kwargs) -> str:
        return self.fmt.format(**kwargs)



def _fresh_module():
    """Reload SUT to avoid global state leaking across tests."""
    import importlib
    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.agents.generators.report_agent")
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
    target = pdir / "report_prompt.txt"
    target.write_text("REPORT_BASE", encoding="utf-8")
    sut._PROMPTS_DIR = pdir

    # success
    assert sut._load_prompt_from_pkg("report_prompt.txt") == "REPORT_BASE"

    # failure
    with pytest.raises(FileNotFoundError):
        sut._load_prompt_from_pkg("missing.txt")


# ------------------------------
# _extract_report_content
# ------------------------------

@pytest.mark.parametrize(
    "raw, expected_contains, expected_absent",
    [
        # 1) AIMessage-like object with .content.
        (types.SimpleNamespace(content="Hello report"), "Hello report", []),
        # 2) dict-style with 'content' key, fenced code is stripped.
        (
            {"content": "Intro\n```python\nprint(1)\n```\nOutro"},
            "Intro",
            ["print(1)", "```"],
        ),
        # 3) unmatched code-fence opener is removed.
        ("```python\nStart only", "Start only", ["```python"]),
        # 4) multiple blank lines condense to a single blank.
        ("a\n\n\nb", "a\n\nb", []),
        # 5) metadata fragments stripped from the line onward.
        ("Keep this AIMessage more stuff\nAfter", "After", ["AIMessage", "more stuff"]),
        ("foo content=bar\nbaz", "baz", ["content=bar"]),
        ("x additional_kwargs=something\nz", "z", ["additional_kwargs"]),
        ("y response_metadata=q\nw", "w", ["response_metadata"]),
        ("u usage_metadata=tokens\nv", "v", ["usage_metadata"]),
        # 6) generic object becomes str(result).
        (object(), "", []),  # can't assert exact string; just no crash
    ],
)
def test__extract_report_content_cases(raw, expected_contains, expected_absent):
    """
    Verify content extraction/cleaning heuristics across nuisances:
    fences, openers, multi-blank condense, metadata removal.
    """
    sut = _fresh_module()
    out = sut._extract_report_content(raw)
    if expected_contains:
        assert expected_contains in out
    for frag in expected_absent:
        assert frag not in out


# ------------------------------
# ReportAgent.run (happy + fallback)
# ------------------------------

def test_reportagent_run_happy_path(monkeypatch):
    """
    run(): formats prompt with defaults for missing keys, invokes LLM, cleans output.
    """
    sut = _fresh_module()

    # Replace the PromptTemplate with a deterministic formatter containing all vars.
    # Only use a subset of keys in input; others should default to "" without KeyError.
    monkeypatch.setattr(
        sut,
        "_report_prompt_template",
        DummyPrompt("S={specification}, R={rtl_code}, TB={testbench_code}"),
        raising=True,
    )

    # LLM returns content with fenced code and extra blanks -> should be cleaned.
    class R:
        content = "Header\n\n```text\nignore me\n```\n\nSummary line"

    dummy = DummyLLM(R())
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.ReportAgent(verbose=True)
    out = agent.run({"specification": "specX", "rtl_code": "rtlX"})  # testbench_code is missing
    # Prompt had defaults for missing keys, and LLM was invoked once
    assert dummy.seen and "S=specX, R=rtlX, TB=" in dummy.seen[0]
    # Cleaned report should have header + summary, but not the fenced block
    assert "Header" in out and "Summary line" in out and "ignore me" not in out


def test_reportagent_run_empty_clean_fallback_warns(monkeypatch):
    """
    If cleaning produces an empty string, ReportAgent should warn and
    return the fallback text. We assert by monkeypatching the module
    logger's .warning() (stdout capture is unreliable here).
    """
    sut = _fresh_module()

    # Deterministic prompt (no file reads)
    monkeypatch.setattr(sut, "_report_prompt_template", DummyPrompt("X"), raising=True)

    # LLM returns only a fenced block -> cleaned content becomes empty
    class R:
        content = "```md\nall removed\n```"

    dummy = DummyLLM(R())
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    # Capture warnings via the module logger directly
    seen_warnings: list[str] = []

    def capture_warning(msg, *args, **kwargs):
        text = msg % args if args else str(msg)
        seen_warnings.append(text)

    monkeypatch.setattr(sut.logger, "warning", capture_warning, raising=True)

    out = sut.ReportAgent().run({})

    assert any(
        "LLM returned empty report. Using fallback summary." in m for m in seen_warnings
    )
    assert out == "No report generated. Please check pipeline phase outputs."


# ------------------------------
# _invoke_llm branches
# ------------------------------

def test__invoke_llm_content_text_str_and_error(monkeypatch):
    """
    _invoke_llm should prefer .content, then .text, else str(result), and wrap exceptions.
    """
    sut = _fresh_module()
    agent = sut.ReportAgent(llm=DummyLLM(types.SimpleNamespace(content="C")))

    assert agent._invoke_llm("p1") == "C"        # .content
    agent.llm = DummyLLM(types.SimpleNamespace(text="T"))
    assert agent._invoke_llm("p2") == "T"        # .text
    agent.llm = DummyLLM(object())
    assert isinstance(agent._invoke_llm("p3"), str)  # str(result)

    class Boom:
        def invoke(self, _):
            raise ValueError("boom")

    agent.llm = Boom()
    with pytest.raises(RuntimeError) as ei:
        agent._invoke_llm("p4")
    assert "LLM invocation failed in ReportAgent" in str(ei.value)


# ------------------------------
# Tool wrapper
# ------------------------------

def test_report_tool_wrapper_calls_agent(monkeypatch):
    """
    report_tool should instantiate ReportAgent and call .run once.
    """
    sut = _fresh_module()
    calls: list[Dict[str, str]] = []

    class FakeAgent:
        def run(self, phase_outputs: Dict[str, str]) -> str:
            calls.append(phase_outputs)
            return "OK"

    monkeypatch.setattr(sut, "ReportAgent", FakeAgent, raising=True)
    out = sut._report_tool_func({"a": "b"})
    assert out == "OK"
    assert calls == [{"a": "b"}]
