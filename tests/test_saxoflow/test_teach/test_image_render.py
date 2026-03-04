# tests/test_saxoflow/test_teach/test_image_render.py
"""Tests for saxoflow.teach._image_render — render_image_from_bytes."""

from __future__ import annotations

import pytest

from saxoflow.teach._image_render import _notice, render_image_from_bytes


# ---------------------------------------------------------------------------
# _notice — internal helper
# ---------------------------------------------------------------------------

class TestNotice:
    def test_contains_figure_number(self):
        result = _notice(3)
        assert "Figure 3" in result

    def test_contains_fig_command(self):
        result = _notice(3)
        assert "fig 3" in result

    def test_instructs_image_viewer(self):
        result = _notice(1)
        assert "image viewer" in result.lower()

    def test_is_multiline(self):
        result = _notice(1)
        assert "\n" in result

    def test_plain_text_no_rich_markup(self):
        result = _notice(1)
        assert "[dim]" not in result
        assert "[/dim]" not in result
        assert "[bold]" not in result

    def test_ext_included_in_notice(self):
        result = _notice(2, "jpeg")
        assert "JPEG" in result


# ---------------------------------------------------------------------------
# render_image_from_bytes — always returns a notice, never fails
# ---------------------------------------------------------------------------

class TestRenderImageFromBytes:
    def test_empty_bytes_returns_notice(self):
        result = render_image_from_bytes(b"")
        assert "Figure" in result
        assert "fig" in result

    def test_non_empty_bytes_returns_notice(self):
        result = render_image_from_bytes(b"\x89PNG\r\n\x1a\n")
        assert "Figure" in result
        assert "fig" in result

    def test_returns_str(self):
        assert isinstance(render_image_from_bytes(b"\x89PNG"), str)

    def test_fig_num_propagated(self):
        result = render_image_from_bytes(b"\x89PNG", fig_num=5)
        assert "Figure 5" in result
        assert "fig 5" in result

    def test_default_fig_num_is_1(self):
        result = render_image_from_bytes(b"\x89PNG")
        assert "Figure 1" in result
        assert "fig 1" in result

    def test_image_ext_included(self):
        result = render_image_from_bytes(b"JFIF", image_ext="jpeg", fig_num=2)
        assert "JPEG" in result

    def test_no_ansi_escape_codes(self):
        result = render_image_from_bytes(b"\x89PNG", fig_num=1)
        assert "\x1b[" not in result

    def test_no_rich_markup(self):
        result = render_image_from_bytes(b"\x89PNG", fig_num=1)
        assert "[dim]" not in result
        assert "[bold]" not in result

    def test_large_fig_num(self):
        result = render_image_from_bytes(b"\x89PNG", fig_num=99)
        assert "Figure 99" in result
        assert "fig 99" in result

    def test_extra_kwargs_ignored(self):
        """width/height kwargs from old call sites must not raise."""
        result = render_image_from_bytes(b"\x89PNG", fig_num=1, width=160, height=48)
        assert "fig 1" in result
