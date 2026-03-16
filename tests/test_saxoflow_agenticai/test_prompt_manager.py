"""
Hermetic tests for saxoflow_agenticai.core.prompt_manager.

- No network.
- Only ephemeral filesystem (tmp_path).
- Env patched per-test.
- Patches are applied via the SUT's import path.

We verify:
- Directory resolution precedence (arg > env > default).
- Happy-path rendering (+ undefined vars render as empty string).
- Unicode handling.
- Missing template -> FileNotFoundError with clear message.
- Syntax error -> PromptRenderError with filename and line info.
- Runtime error -> PromptRenderError (e.g., ZeroDivisionError in template).
- Cache behavior toggled by cache_templates (without relying on Jinja internals).
- auto_reload prop pass-through to Jinja Environment.
- get_template_path correctness.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _write(tp: Path, name: str, content: str) -> Path:
    """Utility: write a file under tmp_path and return its path."""
    p = tp / name
    p.write_text(content, encoding="utf-8")
    return p


def test_dir_resolution_precedence_arg_over_env(tmp_path, monkeypatch):
    """
    Ensure `template_dir` arg wins even if SAXOFLOW_PROMPT_DIR is set.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.setenv("SAXOFLOW_PROMPT_DIR", str(other))

    mgr = sut.PromptManager(template_dir=tmp_path)
    assert mgr.template_dir == tmp_path


def test_dir_resolution_env_over_default(tmp_path, monkeypatch):
    """
    When arg is absent, SAXOFLOW_PROMPT_DIR is used.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    monkeypatch.setenv("SAXOFLOW_PROMPT_DIR", str(tmp_path))
    mgr = sut.PromptManager()
    assert mgr.template_dir == tmp_path


def test_dir_resolution_default_to_repo_prompts(monkeypatch):
    """
    With no arg and no env, the manager points at <repo>/prompts
    computed from this module's __file__.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    monkeypatch.delenv("SAXOFLOW_PROMPT_DIR", raising=False)
    mgr = sut.PromptManager()
    expected = Path(sut.__file__).resolve().parents[1] / "prompts"
    assert mgr.template_dir == expected


def test_auto_reload_flag_exposed(tmp_path):
    """
    Jinja Environment's auto_reload should match the constructor flag.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    mgr = sut.PromptManager(template_dir=tmp_path, auto_reload=True)
    assert getattr(mgr.env, "auto_reload", None) is True


def test_render_happy_and_undefined_vars(tmp_path, monkeypatch):
    """
    Undefined variables render as empty string (non-strict Jinja behavior).
    Also verify Unicode characters are preserved.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    _write(tmp_path, "greet.txt", "Hello {{ name }} {{ missing }} Café ☕!")
    mgr = sut.PromptManager(template_dir=tmp_path)

    out = mgr.render("greet.txt", {"name": "World"})
    assert out == "Hello World  Café ☕!"  # note the empty slot for {{ missing }}


def test_render_missing_template_raises(tmp_path):
    """
    Missing template raises FileNotFoundError with clear filename and directory.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    mgr = sut.PromptManager(template_dir=tmp_path)
    with pytest.raises(FileNotFoundError) as ei:
        mgr.render("nope.txt", {})
    msg = str(ei.value)
    assert "nope.txt" in msg
    assert str(tmp_path) in msg


def test_render_syntax_error_raises_prompt_render_error(tmp_path):
    """
    Template with Jinja syntax error should raise PromptRenderError.
    Message should include the filename and the word 'line'.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    # Invalid: missing iterable in for statement.
    _write(tmp_path, "bad.j2", "{% for x in %}\n{{ x }}\n{% endfor %}\n")
    mgr = sut.PromptManager(template_dir=tmp_path)
    with pytest.raises(sut.PromptRenderError) as ei:
        mgr.render("bad.j2", {})

    msg = str(ei.value)
    assert "bad.j2" in msg
    assert "Syntax error" in msg
    assert "line" in msg


def test_render_runtime_error_wrapped(tmp_path):
    """
    Runtime errors inside the template (e.g., 1/0) should be wrapped into
    PromptRenderError by the render() method.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    _write(tmp_path, "boom.j2", "{{ 1 / 0 }}\n")
    mgr = sut.PromptManager(template_dir=tmp_path)
    with pytest.raises(sut.PromptRenderError) as ei:
        mgr.render("boom.j2", {})
    assert "Failed to render template 'boom.j2'" in str(ei.value)


def test_cache_templates_true_calls_loader_once(tmp_path, monkeypatch):
    """
    When cache_templates=True, _get_template should hit Jinja loader once
    and place the compiled template in the local _cache.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    _write(tmp_path, "t.txt", "X={{ x }}")
    mgr = sut.PromptManager(template_dir=tmp_path, cache_templates=True)

    calls = {"n": 0}
    orig = mgr.env.get_template

    def counting_get_template(name):
        calls["n"] += 1
        return orig(name)

    monkeypatch.setattr(mgr.env, "get_template", counting_get_template, raising=True)

    # Two renders -> only one loader call; cache should contain the key.
    assert mgr.render("t.txt", {"x": 1}) == "X=1"
    assert mgr.render("t.txt", {"x": 2}) == "X=2"
    assert calls["n"] == 1
    assert "t.txt" in mgr._cache


def test_cache_templates_false_calls_loader_twice(tmp_path, monkeypatch):
    """
    When cache_templates=False, _get_template should call Jinja loader on
    each retrieval and not populate the local _cache.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    _write(tmp_path, "t.txt", "V={{ v }}")
    mgr = sut.PromptManager(template_dir=tmp_path, cache_templates=False)

    calls = {"n": 0}
    orig = mgr.env.get_template

    def counting_get_template(name):
        calls["n"] += 1        # count every retrieval
        return orig(name)

    monkeypatch.setattr(mgr.env, "get_template", counting_get_template, raising=True)

    assert mgr.render("t.txt", {"v": "a"}) == "V=a"
    assert mgr.render("t.txt", {"v": "b"}) == "V=b"
    assert calls["n"] == 2
    assert mgr._cache == {}  # no local caching when disabled


def test_get_template_path_returns_resolved_path(tmp_path):
    """
    get_template_path should compute absolute path under the template_dir.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    mgr = sut.PromptManager(template_dir=tmp_path)
    p = mgr.get_template_path("x/y.txt")
    assert p == (tmp_path / "x" / "y.txt").resolve()


def test_nonexistent_dir_then_missing_template(tmp_path):
    """
    Even if the template_dir does not exist, the manager initializes fine,
    and rendering a missing file produces FileNotFoundError.
    """
    from saxoflow_agenticai.core import prompt_manager as sut

    missing_dir = tmp_path / "no_such_dir"
    assert not missing_dir.exists()

    mgr = sut.PromptManager(template_dir=missing_dir)
    with pytest.raises(FileNotFoundError):
        mgr.render("anything.txt", {})
