from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _render_and_get_lines(renderable, width: int) -> list[str]:
    """Render a Rich renderable at a fixed width and return the text lines.

    This is the key guard against "panels bursting past the right edge".
    """
    console = Console(width=width, record=True, force_terminal=True)
    console.print(renderable)
    rendered = console.export_text()
    return rendered.rstrip("\n").split("\n")


def _assert_bounded(lines: list[str], width: int, context: str = "") -> None:
    """Assert that no rendered line exceeds the given width."""
    assert all(len(line) <= width for line in lines), (
        f"Rendered output overflowed console width {width} in {context or 'render'}"
    )


# -----------------------------------------------------------------------------
# Core panel behavior
# -----------------------------------------------------------------------------

def test_welcome_panel_returns_panel(panels_mod):
    panel = panels_mod.welcome_panel("Welcome to SaxoFlow", panel_width=99)
    assert isinstance(panel, Panel)
    assert "Welcome to SaxoFlow" in panel.renderable.plain
    assert panel.width == 99
    assert panel.border_style == "cyan"
    assert panel.title == "saxoflow"

    # Render guard: ensure no overflow when actually printed
    lines = _render_and_get_lines(panel, width=99)
    _assert_bounded(lines, 99, "welcome_panel")


def test_error_panel_formats_message(panels_mod):
    panel = panels_mod.error_panel("something went wrong", width=77)
    assert isinstance(panel, Panel)
    assert "Error: something went wrong" in panel.renderable.plain
    assert panel.title == "error"
    assert panel.border_style == "red"
    assert panel.width == 77

    # Render guard
    lines = _render_and_get_lines(panel, width=77)
    _assert_bounded(lines, 77, "error_panel")


def test_user_input_panel_formats_correctly_and_wraps(panels_mod, monkeypatch):
    # Pin width to make behavior deterministic
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 70)
    msg = "User typed this " * 5  # long text to trigger wrapping attributes
    panel = panels_mod.user_input_panel(msg)
    assert isinstance(panel, Panel)
    assert panel.title == "user"
    assert panel.border_style == "cyan"
    assert msg[:10] in panel.renderable.plain
    assert panel.width == 70
    # Ensure wrapping behavior is normalized
    assert panel.renderable.no_wrap is False
    assert panel.renderable.overflow == "fold"

    # Render guard
    lines = _render_and_get_lines(panel, width=70)
    _assert_bounded(lines, 70, "user_input_panel")


def test_output_panel_with_text_and_string_and_unknown_types(panels_mod, monkeypatch):
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 66)

    text_obj = Text("Here is some output")
    panel1 = panels_mod.output_panel(text_obj, border_style="magenta")
    assert isinstance(panel1, Panel)
    assert "Here is some output" in panel1.renderable.plain
    # Preserved quirk: border is always orange1
    assert panel1.border_style == "orange1"
    assert panel1.width == 66
    _assert_bounded(_render_and_get_lines(panel1, width=66), 66, "output_panel/Text")

    # String input
    panel2 = panels_mod.output_panel("output as string", icon="ignored")
    assert "output as string" in panel2.renderable.plain
    assert panel2.border_style == "orange1"
    assert panel2.width == 66
    _assert_bounded(_render_and_get_lines(panel2, width=66), 66, "output_panel/str")

    # Unknown type (coerced via repr)
    panel3 = panels_mod.output_panel(12345)
    assert "12345" in panel3.renderable.plain
    assert panel3.border_style == "orange1"
    _assert_bounded(_render_and_get_lines(panel3, width=66), 66, "output_panel/repr")


def test_ai_panel_with_string_and_text(panels_mod, monkeypatch):
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 71)
    panel = panels_mod.ai_panel("AI says hello")
    assert isinstance(panel, Panel)
    assert "AI says hello" in panel.renderable.plain
    assert panel.border_style == "bold cyan"
    assert panel.title == "saxoflow_AI"
    assert panel.width == 71
    _assert_bounded(_render_and_get_lines(panel, width=71), 71, "ai_panel/str")

    # Text input gets normalized wrapping
    text_obj = Text("AI text object", no_wrap=True)
    panel2 = panels_mod.ai_panel(text_obj, width=72)
    assert "AI text object" in panel2.renderable.plain
    assert panel2.width == 72
    assert panel2.renderable.no_wrap is False
    assert panel2.renderable.overflow == "fold"
    _assert_bounded(_render_and_get_lines(panel2, width=72), 72, "ai_panel/Text")


def test_agent_panel_properties_and_custom_border(panels_mod, monkeypatch):
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 80)
    panel = panels_mod.agent_panel("Agent output", border_style="magenta")
    assert isinstance(panel, Panel)
    assert "Agent output" in panel.renderable.plain
    assert panel.title == "saxoflow_agent"
    assert panel.border_style == "magenta"
    assert panel.width == 80
    _assert_bounded(_render_and_get_lines(panel, width=80), 80, "agent_panel/str")

    # Also test with a Text object, different border
    text_obj = Text("Agent text", no_wrap=True)
    panel2 = panels_mod.agent_panel(text_obj, border_style="yellow", width=81)
    assert "Agent text" in panel2.renderable.plain
    assert panel2.border_style == "yellow"
    assert panel2.width == 81
    # Normalization applied
    assert panel2.renderable.no_wrap is False
    assert panel2.renderable.overflow == "fold"
    _assert_bounded(_render_and_get_lines(panel2, width=81), 81, "agent_panel/Text")


def test_public_api_names_in___all__(panels_mod):
    expected = {
        "welcome_panel",
        "user_input_panel",
        "output_panel",
        "error_panel",
        "ai_panel",
        "agent_panel",
        "saxoflow_panel",  # ensure new public API is exported
    }
    assert set(panels_mod.__all__) >= expected


# -----------------------------------------------------------------------------
# Edge cases & helpers
# -----------------------------------------------------------------------------

def test_default_panel_width_uses_min_bound_when_console_small(panels_mod, monkeypatch):
    """When the console is tiny (50 cols), the function returns the MIN width (80)."""
    class TinyConsole:
        def __init__(self):
            self._width = 50

        @property
        def width(self):
            return self._width

    monkeypatch.setattr(panels_mod, "Console", TinyConsole)
    assert panels_mod._default_panel_width() == 80


def test_default_panel_width_fallback_when_console_width_raises(panels_mod, monkeypatch):
    """If Console.width raises, fallback term_width is 2 * MIN (160) -> width = int(160*0.8)=128."""
    class BadConsole:
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


# -----------------------------------------------------------------------------
# SaxoFlow standard panel + overflow/fit behavior
# -----------------------------------------------------------------------------

def test_saxoflow_panel_non_fit_with_explicit_width(panels_mod):
    # fit=False should use the normal Panel constructor and respect the given width
    panel = panels_mod.saxoflow_panel("Summary text", fit=False, width=101)
    assert isinstance(panel, Panel)
    assert panel.width == 101
    assert panel.border_style == "yellow"
    assert panel.title == "saxoflow"
    assert "Summary text" in panel.renderable.plain

    # Render guard
    lines = _render_and_get_lines(panel, width=101)
    _assert_bounded(lines, 101, "saxoflow_panel/non_fit_explicit")


def test_saxoflow_panel_non_fit_uses_default_width_when_none(monkeypatch, panels_mod):
    # When fit=False and width is None, it should call _default_panel_width()
    monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 87)
    panel = panels_mod.saxoflow_panel(Text("X"), fit=False)  # width=None
    assert isinstance(panel, Panel)
    assert panel.width == 87
    assert panel.border_style == "yellow"
    assert panel.title == "saxoflow"
    assert panel.renderable.plain == "X"

    # Render guard
    lines = _render_and_get_lines(panel, width=87)
    _assert_bounded(lines, 87, "saxoflow_panel/non_fit_default")


def test_panels_never_overflow_narrow_console_with_long_unbroken_tokens(panels_mod):
    long_unbroken = "https://example.com/" + ("a" * 120) + "/end"
    for builder in (
        panels_mod.user_input_panel,
        panels_mod.output_panel,
        panels_mod.error_panel,
        panels_mod.ai_panel,
        panels_mod.agent_panel,
    ):
        panel = builder(long_unbroken, width=48)
        lines = _render_and_get_lines(panel, width=48)
        _assert_bounded(lines, 48, f"{builder.__name__} long token wrap")


def test_render_on_tiny_console_still_bounded(panels_mod):
    msg = "Path: /very/" + ("deep/" * 20) + "file.txt"
    panel = panels_mod.output_panel(msg, width=38)
    lines = _render_and_get_lines(panel, width=38)
    _assert_bounded(lines, 38, "tiny_console_stress")


def test_markup_like_strings_wrap_safely(panels_mod):
    s = "[bold cyan]ThisLooksLikeMarkupButIsJustText " + ("X" * 100)
    panel = panels_mod.user_input_panel(s, width=52)
    lines = _render_and_get_lines(panel, width=52)
    _assert_bounded(lines, 52, "markup_like_text_wrap")


def test_saxoflow_panel_fit_short_content_ok(panels_mod):
    # If your implementation guards Panel.fit by measuring content, this remains bounded.
    panel = panels_mod.saxoflow_panel("short", fit=True)
    lines = _render_and_get_lines(panel, width=60)
    _assert_bounded(lines, 60, "saxoflow_panel/fit_short")


def test_saxoflow_panel_fit_long_content_falls_back_bounded(panels_mod):
    # Long content should NOT overflow even with fit=True; implementation should clamp/fallback.
    long_line = "X" * 120
    panel = panels_mod.saxoflow_panel(long_line, fit=True)
    lines = _render_and_get_lines(panel, width=80)
    _assert_bounded(lines, 80, "saxoflow_panel/fit_long_fallback")


# ==========================================================================
# tutor_panel
# ==========================================================================

class TestTutorPanel:
    """Tests for the tutor_panel() function added in Phase 9 of the tutoring plan."""

    def test_returns_panel(self, panels_mod):
        panel = panels_mod.tutor_panel("Hello student")
        assert isinstance(panel, Panel)

    def test_gold1_border_style(self, panels_mod):
        panel = panels_mod.tutor_panel("step explanation")
        assert panel.border_style == "gold1"

    def test_title_contains_saxoflow_tutor(self, panels_mod):
        panel = panels_mod.tutor_panel("test")
        # Title is a markup string — check its plain-text representation
        from rich.console import Console
        from io import StringIO
        console = Console(file=StringIO(), width=120, highlight=False, markup=True)
        console.print(panel)
        rendered = console.file.getvalue()
        assert "SaxoFlow Tutor" in rendered

    def test_accepts_rich_text(self, panels_mod):
        txt = Text("rich text input", style="cyan")
        panel = panels_mod.tutor_panel(txt)
        assert isinstance(panel, Panel)

    def test_explicit_width_respected(self, panels_mod, monkeypatch):
        monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 100, raising=True)
        panel = panels_mod.tutor_panel("msg", width=90)
        assert panel.width == 90

    def test_default_width_used_when_none(self, panels_mod, monkeypatch):
        monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 88, raising=True)
        panel = panels_mod.tutor_panel("msg")
        assert panel.width == 88

    def test_in___all__(self, panels_mod):
        assert "tutor_panel" in panels_mod.__all__

    def test_bounded_on_short_content(self, panels_mod, monkeypatch):
        monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 80, raising=True)
        panel = panels_mod.tutor_panel("short")
        lines = _render_and_get_lines(panel, width=80)
        _assert_bounded(lines, 80, "tutor_panel/short")

    def test_bounded_on_long_unbroken_token(self, panels_mod, monkeypatch):
        monkeypatch.setattr(panels_mod, "_default_panel_width", lambda: 80, raising=True)
        long_token = "A" * 120
        panel = panels_mod.tutor_panel(long_token)
        lines = _render_and_get_lines(panel, width=80)
        _assert_bounded(lines, 80, "tutor_panel/long_token")
