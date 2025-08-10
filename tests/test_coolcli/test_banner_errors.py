# tests/test_coolcli/test_banner_errors.py
from __future__ import annotations

import pytest
from rich.text import Text


def test_interpolate_color_invalid_stops_raise(banner_mod):
    with pytest.raises(ValueError):
        banner_mod.interpolate_color([], 0.5)  # fewer than 2 stops
    with pytest.raises(ValueError):
        banner_mod.interpolate_color([(0, 0, 0), (300, 0, 0)], 0.5)  # out of range


def test_build_gradient_text_empty_ascii_art_raises(banner_mod):
    with pytest.raises(ValueError):
        banner_mod._build_gradient_text(["   ", ""], ((0, 0, 0), (255, 255, 255)))


def test_print_banner_fallback_when_builder_raises(banner_mod, monkeypatch, dummy_console):
    # Force _build_gradient_text to raise to hit the fallback path.
    monkeypatch.setattr(banner_mod, "_build_gradient_text", lambda *a, **k: (_ for _ in ()).throw(ValueError("oops")))
    banner_mod.print_banner(dummy_console, compact=False)
    assert dummy_console.printed, "Console received no output"
    printed = dummy_console.printed[-1]
    assert isinstance(printed, Text)
    # Fallback appends a warning message; assert it's present in the text
    assert "[warning] Banner rendered without gradient:" in printed.plain
    # Fallback should not crash; spans may be present (from bold white) but we only assert text exists
    assert printed.plain.strip() != ""
