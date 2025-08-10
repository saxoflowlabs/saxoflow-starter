# tests/test_coolcli/test_commands_errors.py
from __future__ import annotations

import sys

import pytest
from rich.text import Text


def test_invoke_click_hard_failure(commands_mod, monkeypatch):
    def boom(cli, args):
        raise RuntimeError("runner exploded")
    monkeypatch.setattr(commands_mod.runner, "invoke", boom)

    out, exc, info = commands_mod._invoke_click(object(), ["--help"])
    assert out == ""
    assert isinstance(exc, RuntimeError)
    assert info == ()


def test_help_builder_failure_is_caught(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(commands_mod, "_build_help_panel", lambda c: (_ for _ in ()).throw(RuntimeError("fail")))
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
    monkeypatch.setattr(commands_mod, "_run_agentic_command", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = commands_mod.handle_command("rtlgen", dummy_console)
    assert isinstance(out, Text)
    assert "Outer Exception" in out.plain
