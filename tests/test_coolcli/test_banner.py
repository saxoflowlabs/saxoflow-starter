# tests/test_coolcli/test_banner.py
from __future__ import annotations

from rich.text import Text


def test_interpolate_color_endpoints(banner_mod):
    """t=0 returns first stop; t=1 returns last stop."""
    stops = [(0, 0, 0), (255, 255, 255)]
    assert banner_mod.interpolate_color(stops, 0.0) == (0, 0, 0)
    assert banner_mod.interpolate_color(stops, 1.0) == (255, 255, 255)


def test_interpolate_color_midpoint_is_exact_half(banner_mod):
    """For a linear 0→255 gradient, midpoint channels are 127 (floor)."""
    stops = [(0, 0, 0), (255, 255, 255)]
    mid = banner_mod.interpolate_color(stops, 0.5)
    assert mid == (127, 127, 127)


def test_interpolate_color_clamps_out_of_range(banner_mod):
    """Inputs <0 clamp to first stop, >1 clamp to last stop."""
    stops = [(10, 20, 30), (40, 50, 60)]
    assert banner_mod.interpolate_color(stops, -1.0) == (10, 20, 30)
    assert banner_mod.interpolate_color(stops, 2.0) == (40, 50, 60)


def test_select_ascii_art_variants(banner_mod):
    """Compact art exists and is shorter; full art exists and is longer."""
    compact = banner_mod._select_ascii_art(compact=True)
    full = banner_mod._select_ascii_art(compact=False)
    assert compact and isinstance(compact, list)
    assert full and isinstance(full, list)
    # Sanity: compact banner often uses block glyphs and should be shorter
    assert any("██" in line for line in compact)
    assert len(full) >= len(compact)


def test_build_gradient_text_returns_text_with_spans(banner_mod):
    """Gradient builder returns Text with styled spans applied."""
    art = ["ABC", "DEF"]
    txt = banner_mod._build_gradient_text(art, ((0, 0, 0), (255, 255, 255)))
    assert isinstance(txt, Text)
    assert txt.spans, "No style spans were added to the Text"
    assert any("rgb(" in str(span.style) for span in txt.spans)


def test_print_banner_happy_path_prints_text(banner_mod, dummy_console):
    """Happy path: banner prints a Text object with styling (gradient or bold)."""
    banner_mod.print_banner(dummy_console, compact=True)
    # We store raw objects on printed_objects in conftest
    assert dummy_console.printed_objects, "Console received no output"
    printed = dummy_console.printed_objects[-1]
    assert isinstance(printed, Text)
    # Gradient path should produce styled spans (or bold white, but typically spans exist)
    assert printed.spans, "Expected styled output in happy path"


# ---------------- Errors & fallbacks ----------------

def test_interpolate_color_invalid_stops_raise(banner_mod):
    """Invalid color stops should raise ValueError."""
    import pytest

    with pytest.raises(ValueError):
        banner_mod.interpolate_color([], 0.5)
    with pytest.raises(ValueError):
        banner_mod.interpolate_color([(0, 0, 0), (300, 0, 0)], 0.5)  # channel out of range


def test_build_gradient_text_empty_ascii_art_raises(banner_mod):
    """Empty/whitespace-only ASCII input should raise (no visible art)."""
    import pytest

    with pytest.raises(ValueError):
        banner_mod._build_gradient_text(["   ", ""], ((0, 0, 0), (255, 255, 255)))


def test_print_banner_fallback_when_builder_raises(banner_mod, monkeypatch, dummy_console):
    """If gradient builder fails, print fallback Text with a warning."""
    def boom(*_a, **_k):
        raise ValueError("oops")

    monkeypatch.setattr(banner_mod, "_build_gradient_text", boom)
    banner_mod.print_banner(dummy_console, compact=False)

    assert dummy_console.printed_objects, "Console received no output"
    printed = dummy_console.printed_objects[-1]
    assert isinstance(printed, Text)
    assert "[warning] Banner rendered without gradient:" in printed.plain
    assert printed.plain.strip() != ""


def test_build_gradient_text_no_visible_lines_guard(banner_mod):
    """
    Force the 'no visible lines found in ascii_art.' branch by using a str
    subclass whose .strip() returns truthy once and falsy thereafter.
    """

    class FlipStrip(str):
        def __new__(cls, s, *a, **k):
            obj = super().__new__(cls, s)
            obj._first = True
            return obj

        def strip(self, *a, **k):
            # First call: return self (truthy)
            # Subsequent calls: return empty string (falsy)
            if getattr(self, "_first", False):
                self._first = False
                return self
            return ""

    # One line that pretends to be visible at first, then not visible later
    art = [FlipStrip("X")]

    import pytest
    with pytest.raises(ValueError) as ei:
        banner_mod._build_gradient_text(art, ((0, 0, 0), (255, 255, 255)))

    assert "no visible lines found in ascii_art" in str(ei.value)


def test_interpolate_color_numerical_safety_branch(banner_mod):
    """
    With 4 stops and t just below 1.0, float rounding can make
    int(t/seg) >= len(stops)-1, executing the 'numerical safety' branch.
    """
    import math

    stops = [(0, 0, 0), (85, 85, 85), (170, 170, 170), (255, 255, 255)]  # 4 stops
    # Largest float less than 1.0
    t = math.nextafter(1.0, 0.0)

    # Should still return the last stop; this exercises the idx>=... guard.
    assert banner_mod.interpolate_color(stops, t) == (255, 255, 255)
