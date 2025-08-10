"""
Tests for cool_cli.shell utilities.

These tests verify behaviour of shell helper functions such as
`is_blocking_editor_command`, `is_unix_command` and the dispatch logic
for running simple shell commands.  We avoid launching real editors or
complex commands, focusing instead on classification and basic
command execution.
"""

from unittest import mock

import cool_cli.coolcli.shell as shell


def test_is_blocking_editor_command():
    assert shell.is_blocking_editor_command("nano file.txt")
    assert shell.is_blocking_editor_command("!vim other.v")
    assert not shell.is_blocking_editor_command("ls -la")


def test_is_unix_command(monkeypatch):
    # Use echo as a known command in PATH
    assert shell.is_unix_command("echo hello")
    # Unknown command should return False
    monkeypatch.setattr(shell.shutil, "which", lambda x: None)
    assert not shell.is_unix_command("unknowncmd foo")
    # Shell aliases are recognised
    assert shell.is_unix_command("ls -la")
    assert shell.is_unix_command("cd")


def test_run_shell_command_basic():
    # Running a simple command like 'echo' should return its output
    output = shell._run_shell_command("echo hello world")
    assert "hello" in output


def test_dispatch_input_for_shell(monkeypatch):
    # Patch _run_shell_command to avoid executing real commands
    monkeypatch.setattr(shell, "_run_shell_command", lambda c: "ran shell")
    # Provide an input that should be handled by unix command path
    result = shell.dispatch_input("ls")
    assert "ran shell" in result.plain
    # Unknown design commands yield a fallback hint
    result2 = shell.dispatch_input("foo")
    assert "didn't understand" in result2.plain