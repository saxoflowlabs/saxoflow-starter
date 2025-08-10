from __future__ import annotations

from rich.text import Text


def test_default_panel_width_min_bound(panels_mod, monkeypatch):
    # Simulate a tiny terminal: Console().width == 50 → expects min 80
    class TinyConsole:
        def __init__(self):
            self._width = 50
        @property
        def width(self):
            return self._width
    monkeypatch.setattr(panels_mod, "Console", TinyConsole)
    assert panels_mod._default_panel_width() == 80


def test_default_panel_width_fallback_when_console_width_raises(panels_mod, monkeypatch):
    # Make width access raise, forcing fallback path: term_width = 2 * min = 160
    # width = int(160 * 0.8) = 128
    class BadConsole:
        def __init__(self):
            pass
        @property
        def width(self):
            raise RuntimeError("no tty")
    monkeypatch.setattr(panels_mod, "Console", BadConsole)
    assert panels_mod._default_panel_width() == 128


def test_coerce_text_normalizes_text_objects(panels_mod):
    # Start with no_wrap True to verify normalization to False + "fold"
    t = Text("hello", no_wrap=True)
    out = panels_mod._coerce_text(t, no_wrap=False, overflow="fold")
    assert isinstance(out, Text)
    assert out.no_wrap is False
    assert out.overflow == "fold"


def test_coerce_text_coerces_unknown_types_via_repr(panels_mod):
    obj = {"k": 1}
    out = panels_mod._coerce_text(obj)
    assert isinstance(out, Text)
    assert "{'k': 1}" in out.plain


def test_default_width_used_when_none_is_passed(panels_mod, monkeypatch):
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 73)
    # All builders without explicit width should use 73
    assert panels_mod.user_input_panel("foo").width == 73
    assert panels_mod.output_panel("foo").width == 73
    assert panels_mod.error_panel("foo").width == 73
    assert panels_mod.welcome_panel("foo").width == 73
    assert panels_mod.ai_panel("foo").width == 73
    assert panels_mod.agent_panel("foo").width == 73
