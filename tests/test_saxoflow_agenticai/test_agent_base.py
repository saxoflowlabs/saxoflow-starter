# tests/test_saxoflow_agenticai/test_base_agent.py
from __future__ import annotations

"""
Tests for saxoflow_agenticai.core.base_agent.BaseAgent

Goals
-----
- Hermetic coverage of prompt rendering (LangChain & Jinja paths).
- Deterministic verification of verbose/file logging blocks.
- Robust tests for query_model() happy/exception paths + result shape coercion.
- LCEL helpers: build_runnable, build_structured, build_with_tools.
- Clear checks for custom exceptions: MissingLLMError, TemplateNotFoundError, PromptRenderError.

Notes
-----
- No network or irreversible FS writes (only tmp_path).
- Patch as imported in the SUT (module-level symbols on `sut`).
"""

import types
from pathlib import Path
from typing import Any, Dict

import pytest


# ------------------------------
# Helpers & fresh module import
# ------------------------------

def _fresh_module():
    """Reload SUT to avoid cross-test state bleed (e.g., module-level flags)."""
    import importlib

    return importlib.reload(
        importlib.import_module("saxoflow_agenticai.core.base_agent")
    )


def _mini_agent(sut, **kwargs):
    """Factory for a tiny concrete agent subclassing BaseAgent."""
    class Mini(sut.BaseAgent):  # type: ignore[misc]
        def __init__(self, **kw):
            kw.setdefault("template_name", "tmpl.txt")
            super().__init__(**kw)

        def run(self, *_a, **_k):
            return "ok"

    return Mini(**kwargs)


# -------------------------
# Prompt rendering (LC path)
# -------------------------

def test_render_prompt_langchain_ok_and_missing(tmp_path, monkeypatch):
    """
    render_prompt() via LangChain PromptTemplate:
    - Success when file exists
    - TemplateNotFoundError when missing
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()
    (pdir / "greet.txt").write_text("Hello {name}", encoding="utf-8")

    ag = _mini_agent(sut, prompt_dir=pdir, template_name="greet.txt")
    out = ag.render_prompt({"name": "Ada"})
    assert out == "Hello Ada"

    # Missing file -> TemplateNotFoundError
    ag2 = _mini_agent(sut, prompt_dir=pdir, template_name="missing.txt")
    with pytest.raises(sut.TemplateNotFoundError):
        _ = ag2.render_prompt({"name": "X"})


def test_render_prompt_langchain_read_error_and_format_error(tmp_path, monkeypatch):
    """
    render_prompt() via LangChain PromptTemplate:
    - OSError during file read -> TemplateNotFoundError
    - Missing variable in context -> PromptRenderError
    """
    sut = _fresh_module()
    pdir = tmp_path / "prompts"
    pdir.mkdir()

    bad = pdir / "bad.txt"
    bad.write_text("ignored", encoding="utf-8")

    real_read_text = Path.read_text

    def fake_read_text(self, *a, **k):  # noqa: ANN001
        if str(self).endswith("bad.txt"):
            raise OSError("boom")
        return real_read_text(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", fake_read_text, raising=True)

    ag_bad = _mini_agent(sut, prompt_dir=pdir, template_name="bad.txt")
    with pytest.raises(sut.TemplateNotFoundError):
        ag_bad.render_prompt({"x": "y"})

    needs = pdir / "needs.txt"
    needs.write_text("X {var1} {var2}", encoding="utf-8")
    ag_needs = _mini_agent(sut, prompt_dir=pdir, template_name="needs.txt")
    with pytest.raises(sut.PromptRenderError):
        ag_needs.render_prompt({"var1": "ONLY"})


def test_render_prompt_honors_env_default_dir(tmp_path, monkeypatch):
    """
    If prompt_dir is not provided, BaseAgent should use env var SAXOFLOW_PROMPT_DIR.
    """
    sut = _fresh_module()
    pdir = tmp_path / "env_prompts"
    pdir.mkdir()
    (pdir / "env.txt").write_text("E {x}", encoding="utf-8")
    monkeypatch.setenv("SAXOFLOW_PROMPT_DIR", str(pdir))

    ag = _mini_agent(sut, template_name="env.txt")
    out = ag.render_prompt({"x": "ok"})
    assert out == "E ok"


# -------------------------
# Prompt rendering (Jinja)
# -------------------------

def test_render_prompt_jinja_success_and_errors(monkeypatch):
    """
    Jinja path (PromptManager):
    - success: returns PM.render string & logs prompt when verbose
    - PM raises FileNotFoundError -> TemplateNotFoundError
    - PM raises _PMRenderError -> PromptRenderError
    """
    sut = _fresh_module()

    # Expose PromptManager & error type in the SUT.
    sut._HAS_PROMPT_MANAGER = True  # enable Jinja path

    class DummyPM:
        def __init__(self, template_dir: Path):
            self.template_dir = template_dir
            self.calls: list[tuple[str, Dict[str, Any]]] = []

        def render(self, template_file: str, context: Dict[str, Any]) -> str:
            self.calls.append((template_file, dict(context)))
            # default: success path
            return f"JINJA:{template_file}|{context.get('v')}"

    class DummyPMError(Exception):
        pass

    sut._PromptManager = DummyPM  # type: ignore[attr-defined]
    sut._PMRenderError = DummyPMError  # type: ignore[attr-defined]

    # Capture click.secho usage (verbose block)
    seen = []

    def secho(msg, **kw):  # noqa: ANN001
        seen.append((msg, kw))

    monkeypatch.setattr(sut, "click", types.SimpleNamespace(secho=secho), raising=True)

    ag = _mini_agent(
        sut,
        prompt_dir=Path("."),
        template_name="t.j2",
        use_jinja=True,
        verbose=True,
    )
    out = ag.render_prompt({"v": "42"})
    assert out == "JINJA:t.j2|42"
    # At least one verbose header printed
    assert any("PROMPT SENT TO LLM" in t[0] for t in seen)

    # PM -> FileNotFoundError
    def render_404(_self, *_a, **_k):  # noqa: ANN001
        raise FileNotFoundError("nope")

    monkeypatch.setattr(DummyPM, "render", render_404, raising=True)
    with pytest.raises(sut.TemplateNotFoundError):
        ag.render_prompt({"v": "x"})

    # PM -> _PMRenderError
    def render_bad(_self, *_a, **_k):  # noqa: ANN001
        raise DummyPMError("bad ctx")

    monkeypatch.setattr(DummyPM, "render", render_bad, raising=True)
    with pytest.raises(sut.PromptRenderError):
        ag.render_prompt({"v": "x"})


# --------------
# _log_block IO
# --------------

def test_log_block_writes_to_file(tmp_path, monkeypatch):
    """
    _log_block: when verbose & log_to_file set, prompts/outputs are appended.
    Triggered via render_prompt() LC path.
    """
    sut = _fresh_module()
    pdir = tmp_path / "p"
    pdir.mkdir()
    (pdir / "a.txt").write_text("A {x}", encoding="utf-8")

    # Stub click.secho to avoid console noise
    monkeypatch.setattr(sut, "click", types.SimpleNamespace(secho=lambda *a, **k: None), raising=True)

    logf = tmp_path / "agent.log"
    ag = _mini_agent(
        sut,
        prompt_dir=pdir,
        template_name="a.txt",
        verbose=True,
        log_to_file=str(logf),
    )
    _ = ag.render_prompt({"x": "1"})
    txt = logf.read_text(encoding="utf-8")
    assert "[Mini | PROMPT SENT TO LLM]" in txt or "PROMPT SENT TO LLM" in txt


# --------------
# query_model()
# --------------

@pytest.mark.parametrize(
    "returned, expected",
    [
        (types.SimpleNamespace(content=" hi "), "hi"),
        (types.SimpleNamespace(text=" yo "), "yo"),
        (" raw ", "raw"),
        (123, "123"),
    ],
)
def test_query_model_result_shapes(returned, expected, monkeypatch):
    """
    query_model: coercion of various LLM return shapes to text.
    """
    sut = _fresh_module()

    class LLM:
        def invoke(self, prompt: str):
            return returned

    ag = _mini_agent(sut, llm=LLM())
    out = ag.query_model("P")
    assert out == expected


def test_query_model_missing_llm_and_invoke_error(monkeypatch):
    """
    query_model:
    - Missing LLM -> MissingLLMError
    - LLM.invoke exception -> RuntimeError (wrapped)
    """
    sut = _fresh_module()

    # Missing
    ag = _mini_agent(sut, llm=None)
    with pytest.raises(sut.MissingLLMError):
        ag.query_model("P")

    # Invoke error
    class BadLLM:
        def invoke(self, _p):
            raise ValueError("boom")

    ag2 = _mini_agent(sut, llm=BadLLM())
    with pytest.raises(RuntimeError) as ei:
        ag2.query_model("Q")
    assert "Model invocation failed in 'Mini'" in str(ei.value)


def test_query_model_verbose_logs_to_file(tmp_path, monkeypatch):
    """
    query_model: when verbose, a 'LLM RESPONSE' block should be appended to the log file.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "click", types.SimpleNamespace(secho=lambda *a, **k: None), raising=True)

    class LLM:
        def invoke(self, _p):
            return "OK!"

    logf = tmp_path / "m.log"
    ag = _mini_agent(sut, llm=LLM(), verbose=True, log_to_file=str(logf))
    _ = ag.query_model("x")
    txt = logf.read_text(encoding="utf-8")
    assert "LLM RESPONSE" in txt and "OK!" in txt


# --------------
# LCEL helpers
# --------------

def test_build_runnable_requires_lcel_and_llm(monkeypatch):
    """
    build_runnable:
    - Missing LLM -> MissingLLMError
    - _HAS_LCEL False -> RuntimeError
    - Success path returns llm.with_config(...) runnable carrying tags/metadata
    """
    sut = _fresh_module()

    # Missing llm
    ag = _mini_agent(sut, llm=None)
    with pytest.raises(sut.MissingLLMError):
        ag.build_runnable()

    # LCEL unavailable
    sut._HAS_LCEL = False
    ag2 = _mini_agent(sut, llm=object())
    with pytest.raises(RuntimeError):
        ag2.build_runnable()

    # Success
    sut._HAS_LCEL = True

    class LLM:
        def __init__(self):
            self.config_used = None

        def with_config(self, cfg: Dict[str, Any]):
            self.config_used = dict(cfg)
            return self

    llm = LLM()
    ag3 = _mini_agent(sut, llm=llm)
    r = ag3.build_runnable(tags=["a"], metadata={"k": "v"})
    assert r is llm and llm.config_used == {"tags": ["a"], "metadata": {"k": "v"}}


def test_build_structured_pydantic_and_non_pydantic_paths(monkeypatch):
    """
    build_structured:
    - Non-pydantic path -> uses bind(response_format=json_object)
    - Pydantic path -> uses with_structured_output(schema, strict)
    """
    sut = _fresh_module()
    sut._HAS_LCEL = True

    # --- non-pydantic path
    sut._HAS_PYDANTIC = False

    class LLM1:
        def __init__(self):
            self.bound = None
            self.cfg = None

        def bind(self, **kw):
            self.bound = dict(kw)
            return self

        def with_config(self, cfg):
            self.cfg = dict(cfg)
            return self

    llm1 = LLM1()
    ag1 = _mini_agent(sut, llm=llm1)
    r1 = ag1.build_structured(schema=object, tags=["x"])
    assert r1 is llm1
    assert llm1.bound == {"response_format": {"type": "json_object"}}
    assert llm1.cfg == {"tags": ["x"]}

    # --- pydantic path
    sut._HAS_PYDANTIC = True
    # Provide a minimal "BaseModel" marker type inside sut so issubclass() works
    class _FakePBase:  # acts like pydantic BaseModel
        pass

    sut._PydanticModel = _FakePBase  # type: ignore[attr-defined]

    class Schema(_FakePBase):
        pass

    class LLM2:
        def __init__(self):
            self.schema = None
            self.strict = None
            self.cfg = None

        def with_structured_output(self, schema, strict=True):
            self.schema, self.strict = schema, strict
            return self

        def with_config(self, cfg):
            self.cfg = dict(cfg)
            return self

        # Bind fallback not used in this branch

    llm2 = LLM2()
    ag2 = _mini_agent(sut, llm=llm2)
    r2 = ag2.build_structured(schema=Schema, strict=True, metadata={"m": 1})
    assert r2 is llm2
    assert llm2.schema is Schema and llm2.strict is True
    assert llm2.cfg == {"metadata": {"m": 1}}


def test_build_with_tools_happy_and_errors(monkeypatch):
    """
    build_with_tools:
    - Missing LLM -> MissingLLMError
    - _HAS_LCEL False -> RuntimeError
    - Happy path: tools bound, tool_choice optional, config propagated
    """
    sut = _fresh_module()

    # Missing
    ag = _mini_agent(sut, llm=None)
    with pytest.raises(sut.MissingLLMError):
        ag.build_with_tools(tools=[])

    # LCEL unavailable
    sut._HAS_LCEL = False
    ag2 = _mini_agent(sut, llm=object())
    with pytest.raises(RuntimeError):
        ag2.build_with_tools(tools=[])

    # Happy path
    sut._HAS_LCEL = True

    class Bound:
        def __init__(self):
            self.tool_choice = None
            self.cfg = None

        def bind(self, **kw):
            # tool_choice is passed as a kw arg here
            self.tool_choice = kw.get("tool_choice")
            return self

        def with_config(self, cfg):
            self.cfg = dict(cfg)
            return self

    class LLM:
        def __init__(self):
            self.tools = None
            self.bound = Bound()

        def bind_tools(self, tools):
            self.tools = list(tools)
            return self.bound

    llm = LLM()
    ag3 = _mini_agent(sut, llm=llm)
    # with tool_choice
    r = ag3.build_with_tools(tools=["t"], tool_choice="auto", tags=["a"])
    assert isinstance(r, Bound)
    assert llm.tools == ["t"]
    assert r.tool_choice == "auto"
    assert r.cfg == {"tags": ["a"]}

    # without tool_choice
    r2 = ag3.build_with_tools(tools=["t2"])
    assert isinstance(r2, Bound)
    assert r2.tool_choice is None
