"""
Tests for cool_cli.commands.handle_command.

The command dispatcher for the interactive CLI produces different rich
objects based on the input string.  These tests verify that help
produces a Panel, agentic commands trigger invocation of the underlying
command, and unknown commands return a hint.  The real Click runner
invocations are patched to avoid running external logic.
"""

from unittest import mock
from rich.text import Text
from rich.panel import Panel

import cool_cli.coolcli.commands as commands


def test_handle_command_help(monkeypatch):
    # Patch runner.invoke to produce deterministic help output without box drawing
    def fake_invoke(cmd, args):
        class Result:
            output = "Usage: cli [OPTIONS] COMMAND [ARGS]...\n\nCommands:\n  install  install tools\n  help     show help"
            exception = None
            exc_info = None
        return Result()
    monkeypatch.setattr(commands.runner, "invoke", fake_invoke)
    panel = commands.handle_command("help", commands.console)
    assert isinstance(panel, Panel)
    # The panel should contain some of the fake help lines
    assert "install" in panel.renderable.plain


def test_handle_command_agentic(monkeypatch):
    # Patch runner.invoke for agenticai_cli to return simple text
    def fake_agent_invoke(cmd, args):
        class Result:
            output = "Agentic command executed"
            exception = None
            exc_info = None
        return Result()
    monkeypatch.setattr(commands.runner, "invoke", fake_agent_invoke)
    # Use a dummy console; the function prints a panel to console when calling agentic commands
    console = commands.console
    text = commands.handle_command("rtlgen", console)
    assert isinstance(text, Text)
    assert "Agentic command executed" in text.plain


def test_handle_command_unknown():
    result = commands.handle_command("unknowncmd", commands.console)
    # Unknown commands should return a concatenation of Text objects
    assert isinstance(result, Text)
    assert "Unknown command" in result.plain