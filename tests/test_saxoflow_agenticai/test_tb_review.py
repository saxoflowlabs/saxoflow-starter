from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.reviewers.tb_review

Hermetic, defect-oriented coverage for:
- Prompt loader (pkg file): success + failure
- Optional guidance loader: success + warning path (monkeypatch logger)
- Prompt composition: guidelines/constructs + base template order/markers
- LLM-output coercion (_extract_review_content)
- Text normalization (extract_structured_review)
- TBReviewAgent.run happy path + empty-clean fallback (warning)
- TBReviewAgent.improve proxies to run
- LLM invocation error wrapped as RuntimeError

No network; filesystem only via tmp_path. We avoid relying on repository prompts
by monkeypatching the module's PromptTemplate instance where needed.
"""

import types
from pathlib import Path
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
        importlib.import_module("saxoflow_agenticai.agents.reviewers.tb_review")
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
    target = pdir / "tbreview_prompt.txt"
    target.write_text("TB_BASE", encoding="utf-8")
    sut._PROMPTS_DIR = pdir

    # success
    assert sut._load_prompt_from_pkg("tbreview_prompt.txt") == "TB_BASE"

    # failure
    with pytest.raises(FileNotFoundError):
        sut._load_prompt_from_pkg("missing.txt")


# ------------------------------
# _maybe_read_guidance
# ------------------------------

def test__maybe_read_guidance_success_and_warn(tmp_path, monkeypatch):
    """
    _maybe_read_guidance: returns content if file exists; else logs warning and returns empty.
    We patch sut.logger.warning to avoid relying on logging capture layers.
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    ok = pdir / "tb_guidelines.txt"
    ok.write_text("GUIDE", encoding="utf-8")

    sut._PROMPTS_DIR = pdir

    # Success path
    assert sut._maybe_read_guidance("tb_guidelines.txt", "TB guidelines") == "GUIDE"

    # Missing -> warning + empty
    seen: list[str] = []

    def capture_warning(msg, *args, **kwargs):
        text = msg % args if args else str(msg)
        seen.append(text)

    monkeypatch.setattr(sut.logger, "warning", capture_warning, raising=True)
    assert sut._maybe_read_guidance("nope.txt", "TB guidelines") == ""
    assert any("Optional TB guidelines file not found" in m for m in seen)


# ------------------------------
# _build_tb_review_prompt
# ------------------------------

def test__build_tb_review_prompt_variants(monkeypatch):
    """
    _build_tb_review_prompt: validates ordering and markers when guidance present/absent.
    """
    sut = _fresh_module()

    # With both sections
    def reader(filename: str, label: str) -> str:  # noqa: ARG001
        if "guidelines" in filename:
            return "G"
        if "constructs" in filename:
            return "C"
        return ""

    monkeypatch.setattr(sut, "_maybe_read_guidance", reader, raising=True)
    out = sut._build_tb_review_prompt("BODY")
    assert "[TESTBENCH GUIDELINES" in out and "<<BEGIN_TB_GUIDELINES>>" in out
    assert "[TESTBENCH CONSTRUCTS" in out and "<<BEGIN_TB_CONSTRUCTS>>" in out
    assert out.strip().endswith("BODY")

    # No guidance at all -> returns body
    monkeypatch.setattr(sut, "_maybe_read_guidance", lambda *_: "", raising=True)
    out2 = sut._build_tb_review_prompt("B2")
    assert out2 == "B2"


# ------------------------------
# _extract_review_content
# ------------------------------

@pytest.mark.parametrize(
    "raw, expected_contains",
    [
        (types.SimpleNamespace(content="X"), "X"),             # AIMessage-like
        ({"content": "Y"}, "Y"),                               # dict
        ("plain text", "plain text"),                          # str passthrough
    ],
)
def test__extract_review_content_cases(raw, expected_contains):
    """
    Ensure common result shapes are coerced to text.
    """
    sut = _fresh_module()
    assert sut._extract_review_content(raw) == expected_contains


# ------------------------------
# extract_structured_review
# ------------------------------

@pytest.mark.parametrize(
    "raw, expectations",
    [
        # Fenced code and boilerplate removed; headings parsed; missing ones default to None.
        (
            "```verilog\nmodule m; endmodule\n```\n"
            "Here is the feedback on the testbench code:\n"
            "**Instantiation Issues**:  \n - port mismatch\n"
            "Overall Comments: looks ok\n",
            {
                "Instantiation Issues: port mismatch",
                "Overall Comments: looks ok",
                "Signal Declaration Issues: None",
                "Stimulus Issues: None",
                "Coverage Gaps: None",
                "Randomization Usage: None",
                "Corner Case Suggestions: None",
                "Output Checking Suggestions: None",
                "Waveform/Monitoring Suggestions: None",
                "Standards Compliance Issues: None",
            },
        ),
        # Bullet/dash collapse, CR/LF normalization, none-ish -> 'None'
        (
            "Signal Declaration Issues:\r\n  - none\r\nStimulus Issues: --\n",
            {
                "Signal Declaration Issues: None",
                "Stimulus Issues: None",
            },
        ),
        # Escaped newlines flattened
        (
            "Coverage Gaps: item1\\nitem2\n",
            {
                "Coverage Gaps: item1 item2",
            },
        ),
    ],
)
def test_extract_structured_review_cases(raw, expectations):
    """
    Verify normalization heuristics: fences removed, metadata stripped,
    bullets collapsed, CR/LF normalized, 'none' canonicalized to 'None',
    escaped newlines flattened, missing headings defaulted to 'None'.
    """
    sut = _fresh_module()
    out = sut.extract_structured_review(raw)
    for expected in expectations:
        assert expected in out


# ------------------------------
# TBReviewAgent.run / improve
# ------------------------------

def test_tbreviewagent_run_happy_path(monkeypatch):
    """
    run(): renders prompt, invokes LLM, returns structured, normalized report.
    """
    sut = _fresh_module()

    # Make prompt deterministic (no file reads at runtime)
    monkeypatch.setattr(
        sut,
        "_tbreview_prompt_template",
        DummyPrompt("S={spec}|R={rtl_code}|TB={testbench_code}"),
        raising=True,
    )

    content = (
        "Here is the output feedback:\n"
        "Instantiation Issues: - port mismatch ; extra\n"
        "Overall Comments: good\n"
    )
    dummy = DummyLLM(types.SimpleNamespace(content=content))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    ag = sut.TBReviewAgent(verbose=True)
    out = ag.run("specA", "rtlB", "topX", "tbY")

    # Prompt variables rendered
    assert dummy.seen and "S=specA|R=rtlB|TB=tbY" in dummy.seen[0]

    # Normalized output contains canonical sections, missing ones default to 'None'
    # NOTE: punctuation inside content is preserved by the normalizer.
    assert "Instantiation Issues: port mismatch ; extra" in out
    assert "Overall Comments: good" in out
    assert "Stimulus Issues: None" in out
    assert "Signal Declaration Issues: None" in out


def test_tbreviewagent_run_empty_clean_fallback_warns(monkeypatch):
    """
    If coercion yields an *empty raw* string, TBReviewAgent warns and returns
    the legacy fallback critique text. (Fallback triggers only when the RAW
    text is empty/whitespace, not merely when cleaning removes content.)
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_tbreview_prompt_template", DummyPrompt("X"), raising=True)

    # Raw empty -> triggers fallback + warning
    class R:
        content = ""

    dummy = DummyLLM(R())
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    # Capture the warning via monkeypatching logger.warning directly
    seen: list[str] = []

    def capture_warning(msg, *args, **kwargs):
        seen.append(msg % args if args else str(msg))

    monkeypatch.setattr(sut.logger, "warning", capture_warning, raising=True)

    out = sut.TBReviewAgent().run("s", "r", "t", "tb")
    assert any("LLM returned empty review" in m for m in seen)

    # Fallback text contains these legacy headings
    assert "Assertions & Checking Suggestions: None" in out
    assert "Monitoring & Debug Suggestions: None" in out
    assert "Overall Comments: No major issues found." in out


def test_tbreviewagent_improve_proxies_to_run(monkeypatch):
    """
    improve(): current implementation proxies to run(); verify identical behavior.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_tbreview_prompt_template", DummyPrompt("X={spec}"), raising=True)

    dummy = DummyLLM(types.SimpleNamespace(content="Overall Comments: ok"))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    ag = sut.TBReviewAgent()
    out1 = ag.run("s1", "r1", "t1", "tb1")
    out2 = ag.improve("s1", "r1", "t1", "tb1", "fb")
    assert out1 == out2
    assert "Overall Comments: ok" in out1


def test_tbreviewagent_llm_exception_wrapped(monkeypatch):
    """
    LLM exception is wrapped into a RuntimeError with the agent name in the message.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_tbreview_prompt_template", DummyPrompt("Y"), raising=True)

    dummy = DummyLLM(raise_on_invoke=ValueError("boom"))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    with pytest.raises(RuntimeError) as ei:
        sut.TBReviewAgent().run("s", "r", "t", "tb")
    assert "LLM invocation failed in TBReviewAgent" in str(ei.value)
