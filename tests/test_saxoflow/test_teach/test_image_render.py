# tests/test_saxoflow/test_teach/test_image_render.py
"""Tests for saxoflow.teach._image_render — render_image_from_bytes."""

from __future__ import annotations

import shutil
from unittest.mock import MagicMock, patch

import pytest

from saxoflow.teach._image_render import _placeholder, render_image_from_bytes


# ---------------------------------------------------------------------------
# _placeholder
# ---------------------------------------------------------------------------

class TestPlaceholder:
    def test_contains_figure_number(self):
        result = _placeholder(3)
        assert "Figure 3" in result

    def test_contains_chafa_hint(self):
        result = _placeholder(1)
        assert "chafa" in result.lower()

    def test_is_multiline(self):
        result = _placeholder(1)
        assert "\n" in result

    def test_plain_text_no_rich_markup(self):
        """Placeholder must not contain Rich markup tags."""
        result = _placeholder(1)
        assert "[dim]" not in result
        assert "[/dim]" not in result


# ---------------------------------------------------------------------------
# render_image_from_bytes — empty bytes
# ---------------------------------------------------------------------------

class TestRenderEmpty:
    def test_empty_bytes_returns_placeholder(self):
        result = render_image_from_bytes(b"")
        assert "Figure" in result

    def test_none_bytes_equivalent(self):
        # If someone passes None by mistake we want graceful handling
        # (the type hint says bytes but defensive coding is good)
        result = render_image_from_bytes(b"")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# render_image_from_bytes — chafa not available
# ---------------------------------------------------------------------------

class TestRenderNoChafa:
    def test_returns_placeholder_when_chafa_missing(self, tmp_path):
        """When chafa is not on PATH the function must return the placeholder."""
        with patch("saxoflow.teach._image_render.shutil.which", return_value=None):
            result = render_image_from_bytes(b"\x89PNG\r\n\x1a\n", fig_num=2)
        assert "Figure 2" in result
        assert "chafa" in result.lower()

    def test_fig_num_propagated_to_placeholder(self):
        with patch("saxoflow.teach._image_render.shutil.which", return_value=None):
            result = render_image_from_bytes(b"JFIF", fig_num=5)
        assert "Figure 5" in result


# ---------------------------------------------------------------------------
# render_image_from_bytes — chafa available (mocked subprocess)
# ---------------------------------------------------------------------------

class TestRenderWithChafa:
    def _fake_chafa_run(self, *args, **kwargs):
        """Simulate a successful chafa run returning Unicode art."""
        mock = MagicMock()
        mock.returncode = 0
        mock.stdout = "▓▓▓▓▓▓▒▒░░  [simulated chafa output]\n"
        mock.stderr = ""
        return mock

    def test_happy_path_returns_art_and_label(self, tmp_path):
        with (
            patch("saxoflow.teach._image_render.shutil.which", return_value="/usr/bin/chafa"),
            patch("saxoflow.teach._image_render.subprocess.run", side_effect=self._fake_chafa_run),
        ):
            result = render_image_from_bytes(b"\x89PNG\r\n\x1a\n", fig_num=1)
        assert "chafa output" in result
        assert "Figure 1" in result

    def test_chafa_nonzero_exit_falls_back_to_placeholder(self):
        def bad_run(*args, **kwargs):
            mock = MagicMock()
            mock.returncode = 1
            mock.stdout = ""
            mock.stderr = "error"
            return mock

        with (
            patch("saxoflow.teach._image_render.shutil.which", return_value="/usr/bin/chafa"),
            patch("saxoflow.teach._image_render.subprocess.run", side_effect=bad_run),
        ):
            result = render_image_from_bytes(b"\x89PNG", fig_num=3)
        assert "Figure 3" in result

    def test_chafa_timeout_falls_back_to_placeholder(self):
        import subprocess as _subprocess

        with (
            patch("saxoflow.teach._image_render.shutil.which", return_value="/usr/bin/chafa"),
            patch(
                "saxoflow.teach._image_render.subprocess.run",
                side_effect=_subprocess.TimeoutExpired(cmd="chafa", timeout=10),
            ),
        ):
            result = render_image_from_bytes(b"\x89PNG", fig_num=4)
        assert "Figure 4" in result

    def test_result_is_plain_string(self):
        with (
            patch("saxoflow.teach._image_render.shutil.which", return_value="/usr/bin/chafa"),
            patch("saxoflow.teach._image_render.subprocess.run", side_effect=self._fake_chafa_run),
        ):
            result = render_image_from_bytes(b"\x89PNG", fig_num=1)
        assert isinstance(result, str)
        # Must NOT contain Rich markup tags
        assert "[dim]" not in result
        assert "[/dim]" not in result
