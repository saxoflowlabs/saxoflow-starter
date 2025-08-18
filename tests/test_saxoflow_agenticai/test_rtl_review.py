from __future__ import annotations

"""
Tests for saxoflow_agenticai.agents.reviewers.rtl_review

Hermetic, defect-oriented coverage for:
- Prompt/guideline loaders and composition helpers
- Review content extraction/normalization
- RTLReviewAgent.run and .improve, including fallback and error paths

No network; FS interactions are limited to tmp_path.
"""

import types
from pathlib import Path
from typing import Any

import pytest


# ------------------------------
# Local doubles / helpers
# ------------------------------

class DummyLLM:
    """Minimal LLM stub recording prompts and returning a configured result."""
    def __init__(self, result: Any = "", raise_on_invoke: BaseException | None = None):
        self.result = result
        self.raise_on_invoke = raise_on_invoke
        self.seen: list[str] = []

    def invoke(self, prompt: str) -> Any:
        self.seen.append(prompt)
        if self.raise_on_invoke:
            raise self.raise_on_invoke
        return self.result


class DummyPrompt:
    """PromptTemplate stand-in with .format(**kwargs) API."""
    def __init__(self, fmt: str):
        self.fmt = fmt

    def format(self, **kwargs) -> str:
        return self.fmt.format(**kwargs)


def _fresh_module():
    """Reload SUT to avoid cross-test state leaks from module globals."""
    import importlib
    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.agents.reviewers.rtl_review")
    )


# ------------------------------
# Prompt/guideline loaders
# ------------------------------

def test__load_prompt_from_pkg_success_and_fail(tmp_path):
    """
    _load_prompt_from_pkg: reads the file if present, otherwise raises FileNotFoundError.
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    target = pdir / "rtlreview_prompt.txt"
    target.write_text("BASE", encoding="utf-8")

    # Redirect the module prompts dir
    sut._PROMPTS_DIR = pdir

    assert sut._load_prompt_from_pkg("rtlreview_prompt.txt") == "BASE"
    with pytest.raises(FileNotFoundError):
        sut._load_prompt_from_pkg("missing.txt")


def test__load_first_existing_variants(tmp_path):
    """
    _load_first_existing: return first existing file contents else None.
    - First candidate exists
    - Only second candidate exists
    - None exist
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    sut._PROMPTS_DIR = pdir

    a = pdir / "a.txt"
    b = pdir / "b.txt"
    b.write_text("B", encoding="utf-8")

    # Only b exists
    assert sut._load_first_existing(("a.txt", "b.txt")) == "B"

    # Now a exists and should be preferred
    a.write_text("A", encoding="utf-8")
    assert sut._load_first_existing(("a.txt", "b.txt")) == "A"

    # None exist
    assert sut._load_first_existing(("x.txt", "y.txt")) is None


@pytest.mark.parametrize(
    ("guides", "constructs", "expected_contains"),
    [
        ("G", "C", ["[VERILOG GUIDELINES", "G", "[CONSTRUCTS POLICY", "C"]),
        ("G", None, ["[VERILOG GUIDELINES", "G"]),
        (None, "C", ["[CONSTRUCTS POLICY", "C"]),
        (None, None, []),
    ],
)
def test__load_guidelines_bundle_variants(tmp_path, guides, constructs, expected_contains):
    """
    _load_guidelines_bundle: emits labeled blocks for any available files;
    returns empty string if none exist.
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    sut._PROMPTS_DIR = pdir

    # Place candidate guideline/construct files as needed
    if guides is not None:
        (pdir / "verilog_guidelines.txt").write_text(guides, encoding="utf-8")
    if constructs is not None:
        (pdir / "verilog_constructs.txt").write_text(constructs, encoding="utf-8")

    out = sut._load_guidelines_bundle()
    for snippet in expected_contains:
        assert snippet in out
    if not expected_contains:
        assert out == ""


def test__compose_review_prompt_includes_guidelines_and_template(monkeypatch):
    """
    _compose_review_prompt: guidelines bundle should be prepended to the rendered template.
    """
    sut = _fresh_module()
    # Control both the guidelines and the template
    monkeypatch.setattr(sut, "_load_guidelines_bundle", lambda: "GL\n\n", raising=True)
    monkeypatch.setattr(sut, "_rtlreview_prompt_template", DummyPrompt("S={spec}|R={rtl_code}"), raising=True)
    out = sut._compose_review_prompt("specX", "rtlY")
    assert out.startswith("GL\n\n")
    assert out.strip().endswith("S=specX|R=rtlY")


# ------------------------------
# Content extraction helpers
# ------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        (types.SimpleNamespace(content="X"), "X"),
        ({"content": "Y"}, "Y"),
        (123, "123"),
    ],
)
def test__extract_review_content_shapes(raw, expected):
    """
    _extract_review_content should accept AIMessage-like, dict, and other types.
    """
    sut = _fresh_module()
    assert sut._extract_review_content(raw) == expected


# ------------------------------
# extract_structured_rtl_review
# ------------------------------

def test_extract_structured_rtl_review_cleans_and_structures():
    """
    extract_structured_rtl_review:
    - removes fenced blocks/metadata/bold/intros
    - normalizes CRLF
    - parses headings, flattens bullets/whitespace
    - fills missing sections with 'None'
    """
    sut = _fresh_module()

    raw = (
        "Here is the review:\r\n"
        "```verilog\nmodule x; endmodule\n```\n"
        "AIMessage(content=...) extra\n"
        "**Syntax Issues**:  \n- missing reset\n"
        "Logic Issues: item1\n"
        "Port Declaration Issues:\n - width mismatch \n"
        "Overall Comments:  Good job.\n"
    )

    out = sut.extract_structured_rtl_review(raw)

    # All canonical headings should be present exactly once
    for h in [
        "Syntax Issues",
        "Logic Issues",
        "Reset Issues",
        "Port Declaration Issues",
        "Optimization Suggestions",
        "Naming Improvements",
        "Synthesis Concerns",
        "Overall Comments",
    ]:
        assert f"{h}:" in out

    # Representative cleaned content
    assert "Syntax Issues: missing reset" in out
    assert "Logic Issues: item1" in out
    assert "Port Declaration Issues: width mismatch" in out
    assert "Overall Comments: Good job" in out

    # Unspecified sections become 'None'
    assert "Reset Issues: None" in out
    assert "Optimization Suggestions: None" in out
    assert "Naming Improvements: None" in out
    assert "Synthesis Concerns: None" in out

    # Fenced/metadata/bold fragments removed
    assert "module x; endmodule" not in out
    assert "AIMessage(" not in out
    assert "**" not in out


# ------------------------------
# RTLReviewAgent.run / improve
# ------------------------------

def test_rtlreviewagent_run_happy_path(monkeypatch):
    """
    run(): renders prompt (guidelines + template), invokes LLM, normalizes output.
    """
    sut = _fresh_module()

    # Deterministic prompt composition
    monkeypatch.setattr(sut, "_load_guidelines_bundle", lambda: "", raising=True)
    monkeypatch.setattr(sut, "_rtlreview_prompt_template", DummyPrompt("S={spec}|R={rtl_code}"), raising=True)

    # LLM returns a messy-but-parsable review
    content = (
        "Here is the review:\n"
        "**Syntax Issues**:  \n - stray ;\n"
        "Logic Issues: none\n"
        "Overall Comments: looks fine\n"
    )
    dummy = DummyLLM(types.SimpleNamespace(content=content))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.RTLReviewAgent(verbose=True)
    out = agent.run("specA", "rtlB")

    # Prompt variables rendered
    assert dummy.seen and "S=specA|R=rtlB" in dummy.seen[0]
    # Cleaned sections present
    assert "Syntax Issues: stray" in out
    assert "Logic Issues: none" in out
    assert "Overall Comments: looks fine" in out
    # A missing section is normalized to 'None'
    assert "Reset Issues: None" in out


def test_rtlreviewagent_run_empty_triggers_fallback_warning(monkeypatch):
    """
    If the LLM returns an empty/whitespace review, the agent logs a warning
    and returns the built-in fallback text.
    """
    sut = _fresh_module()

    monkeypatch.setattr(sut, "_load_guidelines_bundle", lambda: "", raising=True)
    monkeypatch.setattr(sut, "_rtlreview_prompt_template", DummyPrompt("X"), raising=True)

    # Empty content -> triggers fallback, not the structured parser
    dummy = DummyLLM(types.SimpleNamespace(content="   "))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    agent = sut.RTLReviewAgent()
    seen_warnings: list[str] = []

    def capture_warning(msg, *args, **kwargs):
        text = msg % args if args else str(msg)
        seen_warnings.append(text)

    # Capture the *instance* logger warning call
    monkeypatch.setattr(agent.logger, "warning", capture_warning, raising=True)

    out = agent.run("s", "r")
    assert any("LLM returned empty review. Using fallback critique report." in m for m in seen_warnings)

    # Fallback text must contain all canonical headings and "No major issues found." at the end
    assert "Syntax Issues: None" in out
    assert "Overall Comments: No major issues found." in out


def test_rtlreviewagent_run_llm_error_wrapped(monkeypatch):
    """
    If the LLM invocation raises, the agent should wrap it in RuntimeError
    with a descriptive message.
    """
    sut = _fresh_module()

    monkeypatch.setattr(sut, "_load_guidelines_bundle", lambda: "", raising=True)
    monkeypatch.setattr(sut, "_rtlreview_prompt_template", DummyPrompt("S={spec}|R={rtl_code}"), raising=True)

    dummy = DummyLLM(raise_on_invoke=ValueError("boom"))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    with pytest.raises(RuntimeError) as ei:
        sut.RTLReviewAgent().run("s", "r")
    assert "LLM invocation failed in RTLReviewAgent" in str(ei.value)


def test_rtlreviewagent_improve_proxies_to_run(monkeypatch):
    """
    improve(): current implementation proxies to run(); verify same output path.
    """
    sut = _fresh_module()

    monkeypatch.setattr(sut, "_load_guidelines_bundle", lambda: "", raising=True)
    monkeypatch.setattr(sut, "_rtlreview_prompt_template", DummyPrompt("{spec}:{rtl_code}"), raising=True)

    text = (
        "Syntax Issues: None\n"
        "Logic Issues: None\n"
        "Reset Issues: None\n"
        "Port Declaration Issues: None\n"
        "Optimization Suggestions: None\n"
        "Naming Improvements: None\n"
        "Synthesis Concerns: None\n"
        "Overall Comments: ok\n"
    )
    dummy = DummyLLM(types.SimpleNamespace(content=text))
    monkeypatch.setattr(sut.ModelSelector, "get_model", lambda **_: dummy, raising=True)

    ag = sut.RTLReviewAgent()
    out1 = ag.run("s", "r")
    out2 = ag.improve("s", "r", "feedback-ignored")
    assert out1 == out2
