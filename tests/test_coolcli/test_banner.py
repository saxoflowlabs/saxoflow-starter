# tests/test_coolcli/test_banner.py
from __future__ import annotations

from rich.text import Text


def test_interpolate_color_endpoints(banner_mod):
    stops = [(0, 0, 0), (255, 255, 255)]
    assert banner_mod.interpolate_color(stops, 0.0) == (0, 0, 0)
    assert banner_mod.interpolate_color(stops, 1.0) == (255, 255, 255)


def test_interpolate_color_midpoint_is_exact_half(banner_mod):
    stops = [(0, 0, 0), (255, 255, 255)]
    mid = banner_mod.interpolate_color(stops, 0.5)
    assert mid == (127, 127, 127)  # int(255 * 0.5) == 127


def test_interpolate_color_clamps_out_of_range(banner_mod):
    stops = [(10, 20, 30), (40, 50, 60)]
    assert banner_mod.interpolate_color(stops, -1.0) == (10, 20, 30)
    assert banner_mod.interpolate_color(stops, 2.0) == (40, 50, 60)


def test_select_ascii_art_variants(banner_mod):
    compact = banner_mod._select_ascii_art(compact=True)
    full = banner_mod._select_ascii_art(compact=False)
    assert compact and isinstance(compact, list)
    assert full and isinstance(full, list)
    # Sanity: compact banner uses block glyphs and is shorter
    assert any("███" in line for line in compact)
    assert len(full) >= len(compact)


def test_build_gradient_text_returns_text_with_spans(banner_mod):
    art = ["ABC", "DEF"]
    txt = banner_mod._build_gradient_text(art, ((0, 0, 0), (255, 255, 255)))
    assert isinstance(txt, Text)
    # Expect at least one styled span (bold rgb(...))
    assert txt.spans, "No style spans were added to the Text"
    assert any("rgb(" in str(span.style) for span in txt.spans)


def test_print_banner_happy_path_prints_text(banner_mod, dummy_console):
    banner_mod.print_banner(dummy_console, compact=True)
    assert dummy_console.printed, "Console received no output"
    printed = dummy_console.printed[-1]
    assert isinstance(printed, Text)
    # Gradient path should produce styled spans
    assert printed.spans, "Expected styled output in happy path"
