# tests/test_coolcli/test_commands.py
from __future__ import annotations

import sys

import pytest
from rich.panel import Panel
from rich.text import Text


def test_help_panel_happy_path(commands_mod, monkeypatch, dummy_console):
    """help constructs a stitched panel using both --help and init-env --help."""
    def fake_invoke(cli, args):
        class Result:
            def __init__(self, output):
                self.output = output
                self.exception = None
                self.exc_info = None

        if args == ["--help"]:
            return Result("Commands:\n  install  Install tools\n  init-env  Setup env")
        if args == ["init-env", "--help"]:
            return Result("Usage: cli init-env [OPTIONS]\n\nOptions:\n  --fast")
        return Result("")

    monkeypatch.setattr(commands_mod.runner, "invoke", fake_invoke)

    panel = commands_mod.handle_command("help", dummy_console)
    assert isinstance(panel, Panel)
    text = panel.renderable
    assert isinstance(text, Text)
    # prefixed subcommands should show "saxoflow install"
    assert "saxoflow install" in text.plain
    # init-env usage should be prefixed to “Usage: saxoflow …”
    assert "Usage: saxoflow " in text.plain


def test_panel_width_bounds(commands_mod):
    small = type("C", (), {"width": 50})()
    large = type("C", (), {"width": 500})()
    mid = type("C", (), {"width": 100})()
    assert commands_mod._compute_panel_width(small) == 60
    assert commands_mod._compute_panel_width(large) == 120
    # 80% of 100 is 80, within bounds
    assert commands_mod._compute_panel_width(mid) == 80


def test_strip_box_lines(commands_mod):
    raw = "╭ top\n│ inside\n─ line\n text\n╰ bottom"
    out = commands_mod._strip_box_lines(raw)
    assert "text" in out and "inside" not in out and "top" not in out


def test_prefix_saxoflow_commands(commands_mod):
    lines = ["install tools", "random line", "simulate project"]
    prefixed = commands_mod._prefix_saxoflow_commands(lines)
    assert prefixed[0].startswith("saxoflow install")
    assert prefixed[1] == "random line"
    assert prefixed[2].startswith("saxoflow simulate")


def test_init_env_help_success(commands_mod, monkeypatch):
    def fake_invoke(cli, args):
        class Result:
            output = "Usage: cli init-env [OPTIONS]"
            exception = None
            exc_info = None

        return Result()

    monkeypatch.setattr(commands_mod.runner, "invoke", fake_invoke)

    out = commands_mod.handle_command("init-env --help", commands_mod.console)
    assert isinstance(out, Text)
    assert "Usage:" in out.plain


def test_agentic_success_prints_status_and_returns_output(
    commands_mod, monkeypatch, dummy_console
):
    def fake_invoke(cli, args):
        class Result:
            output = "Agentic OK"
            exception = None
            exc_info = None

        return Result()

    monkeypatch.setattr(commands_mod.runner, "invoke", fake_invoke)

    out = commands_mod.handle_command("rtlgen", dummy_console)
    # status panel printed first
    assert dummy_console.printed, "status panel not printed"
    assert isinstance(dummy_console.printed[-1], Panel)
    # returned text with output
    assert isinstance(out, Text)
    assert "Agentic OK" in out.plain


def test_clear_and_exit_and_unknown(commands_mod, dummy_console):
    cleared = commands_mod.handle_command("clear", dummy_console)
    assert isinstance(cleared, Text) and dummy_console.clears == 1

    assert commands_mod.handle_command("quit", dummy_console) is None
    assert commands_mod.handle_command("exit", dummy_console) is None

    unknown = commands_mod.handle_command("whoami", dummy_console)
    assert isinstance(unknown, Text) and "Unknown command" in unknown.plain


def test_shell_acknowledgement(commands_mod, dummy_console):
    for cmd in ("ll -la", "cat file.txt", "cd .."):
        out = commands_mod.handle_command(cmd, dummy_console)
        assert isinstance(out, Text)
        assert "Executing Unix command" in out.plain


def test_none_input_is_defensive(commands_mod, dummy_console):
    out = commands_mod.handle_command(None, dummy_console)  # type: ignore[arg-type]
    assert isinstance(out, Text)
    assert "Unknown command. Type" in out.plain


# ------------------------
# Error-path integrations
# ------------------------

def test_invoke_click_hard_failure(commands_mod, monkeypatch):
    def boom(cli, args):
        raise RuntimeError("runner exploded")

    monkeypatch.setattr(commands_mod.runner, "invoke", boom)

    out, exc, info = commands_mod._invoke_click(object(), ["--help"])
    assert out == ""
    assert isinstance(exc, RuntimeError)
    assert info == ()


def test_help_builder_failure_is_caught(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(
        commands_mod,
        "_build_help_panel",
        lambda c: (_ for _ in ()).throw(RuntimeError("fail")),
    )
    out = commands_mod.handle_command("help", dummy_console)
    assert isinstance(out, Text)
    assert "Failed to render help" in out.plain


def test_init_env_help_failure_returns_error_text(commands_mod, monkeypatch):
    class Result:
        output = ""
        exception = RuntimeError("bad help")
        exc_info = None

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())

    out = commands_mod.handle_command("init-env --help", commands_mod.console)
    assert isinstance(out, Text)
    assert "Failed to run 'init-env --help'" in out.plain


def test_agentic_exception_with_traceback(commands_mod, monkeypatch, dummy_console):
    # Create a real exc_info triple to simulate Click result failure
    try:
        1 / 0
    except Exception as e:  # noqa: PIE786
        exc = e
        exc_info = sys.exc_info()

    class Result:
        output = ""
        exception = exc
        exc_info = exc_info

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())

    out = commands_mod.handle_command("report", dummy_console)
    assert isinstance(out, Text)
    assert "[❌ EXCEPTION]" in out.plain
    assert "Traceback:" in out.plain


def test_agentic_outer_exception_is_caught(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(
        commands_mod,
        "_run_agentic_command",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    out = commands_mod.handle_command("rtlgen", dummy_console)
    assert isinstance(out, Text)
    assert "Outer Exception" in out.plain
