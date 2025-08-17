from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.generators.rtl_gen

Hermetic, defect-oriented coverage for:
- Verilog extraction heuristics
- Optional/required prompt loaders
- Guidelines/constructs composition
- RTLGenAgent run/improve and _invoke_llm branches
- LangChain Tool wrappers

No network; no irreversible FS.
"""

import types
from pathlib import Path
from typing import Any

import pytest


# ------------------------------
# Small local helpers / doubles
# ------------------------------

class DummyLLM:
    """LLM double that records prompts and returns a configurable result."""
    def __init__(self, result: Any):
        self.result = result
        self.seen: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.seen.append(prompt)
        return self.result


class DummyPrompt:
    """PromptTemplate stand-in with a .format(**kwargs) API."""
    def __init__(self, fmt: str):
        self.fmt = fmt

    def format(self, **kwargs) -> str:
        return self.fmt.format(**kwargs)


def _fresh_module():
    """Import the SUT fresh to avoid cross-test pollution when needed."""
    import importlib
    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.agents.generators.rtl_gen")
    )


# ------------------------------
# extract_verilog_code
# ------------------------------

@pytest.mark.parametrize(
    "raw, expected_contains",
    [
        # 1) fenced code with language tag
        ("```verilog\nmodule a; endmodule\n```", "module a; endmodule"),
        # 2) stray single backticks at line edges
        ("`module b; endmodule`", "module b; endmodule"),
        # 3) content='...'
        ('content="module c; endmodule"', "module c; endmodule"),
        # 4) “Here is …” prefix (case-insensitive)
        ("Here is the code:\nmodule d; endmodule", "module d; endmodule"),
        # 5) multiple modules → joined by blank line
        ("module m1; endmodule\n----\nmodule m2; endmodule", "module m1; endmodule\n\nmodule m2; endmodule"),
        # 6) fallback: find first 'module' and return from there
        ("intro text\nmore intro\nmodule e; endmodule\ntrailer", "module e; endmodule\ntrailer"),
        # 7) no 'module' at all → trimmed
        ("```no module here```", "no module here"),
        # 8) convert escaped newlines
        ("module x;\\nendmodule\\n", "module x;\nendmodule\n"),
        # 9) smart quotes normalized
        ('module f; string s = “hi”; endmodule', 'string s = "hi";'),
    ],
)
def test_extract_verilog_code_cases(raw, expected_contains):
    """
    Verify the extraction heuristics across multiple formats and nuisances.
    """
    sut = _fresh_module()
    out = sut.extract_verilog_code(raw)
    assert expected_contains in out


# ------------------------------
# Optional/required prompt loaders
# ------------------------------

def test__load_optional_prompt_success_and_warn(tmp_path, monkeypatch):
    """
    _load_optional_prompt: returns content if file exists; otherwise logs a warning
    via the module's logger. We monkeypatch `sut.logger.warning` to a spy so we
    assert the warning deterministically without relying on stdout/stderr capture.
    """
    sut = _fresh_module()

    # Point module to a temp prompts dir
    file_ok = tmp_path / "prompts" / "guides.txt"
    file_ok.parent.mkdir(parents=True)
    file_ok.write_text("GUIDE", encoding="utf-8")

    # Monkeypatch module's prompts dir
    sut._PROMPTS_DIR = file_ok.parent

    # success path
    text_ok = sut._load_optional_prompt("guides.txt")
    assert text_ok == "GUIDE"

    # Spy on warnings
    calls: list[str] = []

    class _SpyLogger:
        def warning(self, msg, *args, **kwargs):
            # Reproduce logging %-format behavior so we can match text
            try:
                calls.append(msg % args if args else str(msg))
            except Exception:
                calls.append(str(msg))

    monkeypatch.setattr(sut, "logger", _SpyLogger(), raising=True)

    # warn path (missing)
    text_missing = sut._load_optional_prompt("nope.txt")
    assert text_missing == ""
    assert any("Optional prompt not found" in m for m in calls)


def test__load_prompt_from_pkg_success_and_fail(tmp_path):
    """
    _load_prompt_from_pkg: reads file or raises FileNotFoundError.
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    target = pdir / "rtlgen_prompt.txt"
    target.write_text("BASE", encoding="utf-8")
    sut._PROMPTS_DIR = pdir

    # success
    assert sut._load_prompt_from_pkg("rtlgen_prompt.txt") == "BASE"

    # failure
    with pytest.raises(FileNotFoundError):
        sut._load_prompt_from_pkg("missing.txt")


# ------------------------------
# _compose_with_guidelines
# ------------------------------

@pytest.mark.parametrize(
    ("guides", "constructs", "body", "order_snippet"),
    [
        ("G", "C", "B", "G\n\nC\n\nB"),
        ("", "C", "B", "C\n\nB"),
        ("G", "", "B", "G\n\nB"),
        ("", "", "B", "B"),
    ],
)
def test_compose_with_guidelines_variants(monkeypatch, guides, constructs, body, order_snippet):
    """
    Composition should prepend guideline/constructs text (when non-empty) before the base body.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_GUIDELINES_TXT", guides, raising=True)
    monkeypatch.setattr(sut, "_CONSTRUCTS_TXT", constructs, raising=True)
    out = sut._compose_with_guidelines(body)
    assert order_snippet in out
    # Leading and trailing newlines are intentional for nicer prompts
    assert out.startswith("\n")
    assert out.endswith("\n")


# ------------------------------
# RTLGenAgent.run / improve
# ------------------------------

def test_rtlgenagent_run_happy_path(monkeypatch):
    """
    run(): formats prompt (with guidelines), invokes LLM, extracts clean RTL.
    """
    sut = _fresh_module()

    # Stable prompt body (no need for langchain PromptTemplate)
    monkeypatch.setattr(sut, "_rtlgen_prompt_template", DummyPrompt("SPEC={spec}"), raising=True)
    monkeypatch.setattr(sut, "_GUIDELINES_TXT", "G", raising=True)
    monkeypatch.setattr(sut, "_CONSTRUCTS_TXT", "C", raising=True)

    # LLM returns fenced content; agent must extract
    class R:  # AIMessage-like
        content = "```verilog\nmodule a; endmodule\n```"

    dummy = DummyLLM(R())
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.RTLGenAgent(verbose=True)  # verbose should not crash
    out = agent.run("add spec")

    # LLM saw composed prompt with guidelines + constructs + base body
    seen = "\n".join(dummy.seen)
    assert "G" in seen and "C" in seen and "SPEC=add spec" in seen
    assert out.strip() == "module a; endmodule"


def test_rtlgenagent_improve_happy_path(monkeypatch):
    """
    improve(): uses improve prompt and returns extracted RTL.
    """
    sut = _fresh_module()

    monkeypatch.setattr(
        sut, "_rtlgen_improve_prompt_template",
        DummyPrompt("S={spec};P={prev_rtl_code};R={review}"),
        raising=True,
    )
    monkeypatch.setattr(sut, "_GUIDELINES_TXT", "", raising=True)
    monkeypatch.setattr(sut, "_CONSTRUCTS_TXT", "", raising=True)

    class R:
        content = "Here is the updated RTL:\n```verilog\nmodule b; endmodule\n```"

    dummy = DummyLLM(R())
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.RTLGenAgent()
    out = agent.improve("s", "old", "fix it")
    assert "S=s;P=old;R=fix it" in dummy.seen[0]
    assert out.strip() == "module b; endmodule"


# ------------------------------
# _invoke_llm branches
# ------------------------------

def test__invoke_llm_content_text_str_and_error(monkeypatch):
    """
    _invoke_llm should read .content, then .text, else str(result), and wrap exceptions.
    """
    sut = _fresh_module()
    agent = sut.RTLGenAgent(llm=DummyLLM(types.SimpleNamespace(content="X")))

    # .content
    assert agent._invoke_llm("p") == "X"

    # .text
    agent.llm = DummyLLM(types.SimpleNamespace(text="Y"))
    assert agent._invoke_llm("p2") == "Y"

    # str(result)
    agent.llm = DummyLLM(object())
    assert isinstance(agent._invoke_llm("p3"), str)

    # exception wrap
    class BoomLLM:
        def invoke(self, _):
            raise ValueError("boom")

    agent.llm = BoomLLM()
    with pytest.raises(RuntimeError) as ei:
        agent._invoke_llm("p4")
    assert "LLM invocation failed in RTLGenAgent" in str(ei.value)


# ------------------------------
# Tool wrappers
# ------------------------------

def test_tool_wrappers_call_agent(monkeypatch):
    """
    rtlgen_tool / rtlgen_improve_tool should instantiate the agent and call the appropriate method.
    """
    sut = _fresh_module()
    calls = {"run": [], "improve": []}

    class FakeAgent:
        def __init__(self): pass
        def run(self, spec: str) -> str:
            calls["run"].append(spec)
            return "RUN"
        def improve(self, spec: str, prev_rtl_code: str, review: str) -> str:
            calls["improve"].append((spec, prev_rtl_code, review))
            return "IMP"

    monkeypatch.setattr(sut, "RTLGenAgent", FakeAgent, raising=True)
    assert sut._rtlgen_tool_func("spec1") == "RUN"
    assert sut._rtlgen_improve_tool_func("s", "p", "r") == "IMP"
    assert calls["run"] == ["spec1"]
    assert calls["improve"] == [("s", "p", "r")]
