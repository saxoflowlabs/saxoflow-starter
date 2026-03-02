# tests/test_coolcli/test_commands.py
from __future__ import annotations

import sys

import pytest
from rich.panel import Panel
from rich.text import Text
from types import SimpleNamespace

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
        def __init__(self):
            self.output = ""
            self.exception = exc
            self.exc_info = exc_info

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())

    out = commands_mod.handle_command("report", dummy_console)
    assert isinstance(out, Text)
    assert "Exception:" in out.plain
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


def test_strip_box_lines_empty_and_alias(commands_mod):
    # Early return
    assert commands_mod._strip_box_lines("") == ""
    # Public alias delegates to the same behavior
    assert commands_mod.strip_box_lines("   ") == ""


def test_strip_box_lines_trims_both_edges_to_empty(commands_mod):
    raw = "│   │\n│content│"
    out = commands_mod._strip_box_lines(raw)
    # First line becomes empty after trimming, second line preserved without borders
    assert "content" in out
    assert "│" not in out


def test_prefix_saxoflow_commands_preserves_blank_lines(commands_mod):
    lines = ["", "  ", "install tools"]
    out = commands_mod._prefix_saxoflow_commands(lines)
    assert out[0] == ""
    assert out[1] == "  "
    assert out[2].startswith("saxoflow install")


def test_extract_artifact_all_paths(commands_mod):
    # Not a generation cmd → return original
    assert commands_mod._extract_artifact("report", "hello") == "hello"

    # Empty after strip → return empty
    assert commands_mod._extract_artifact("rtlgen", "   ") == ""

    # Fenced code block
    text_fenced = "blah\n```verilog\nmodule m; endmodule\n```\ntrailing"
    assert commands_mod._extract_artifact("tbgen", text_fenced) == "module m; endmodule"

    # module…endmodule fallback
    text_mod = "intro\nmodule top; endmodule\nnotes"
    assert commands_mod._extract_artifact("rtlgen", text_mod) == "module top; endmodule"

    # property…endproperty fallback
    text_prop = "Some\nproperty p; a |-> b; endproperty\nmore"
    assert commands_mod._extract_artifact("fpropgen", text_prop) == "property p; a |-> b; endproperty"

    # package…endpackage fallback
    text_pkg = "hdr\npackage pk; endpackage\nftr"
    assert commands_mod._extract_artifact("fpropgen", text_pkg) == "package pk; endpackage"

    # Nothing detected → original (stripped)
    text_none = "no artifact here"
    assert commands_mod._extract_artifact("tbgen", text_none) == "no artifact here"


def test_build_help_panel_uses_error_messages_when_invoke_fails(commands_mod, monkeypatch, dummy_console):
    def fake_invoke(_cli, args):
        # Simulate Click result object with an exception
        class R:
            def __init__(self, message):
                self.output = ""
                self.exception = RuntimeError(message)
                self.exc_info = None
        if args == ["--help"]:
            return ("", RuntimeError("boom1"), None)
        if args == ["init-env", "--help"]:
            return ("", RuntimeError("boom2"), None)
        return ("", None, None)

    monkeypatch.setattr(commands_mod, "_invoke_click", fake_invoke, raising=True)
    panel = commands_mod._build_help_panel(dummy_console)
    txt = panel.renderable.plain
    assert "Failed to fetch saxoflow --help: boom1" in txt
    assert "Failed to fetch init-env --help: boom2" in txt


def test_ensure_llm_key_before_agent_noninteractive_bypass(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(commands_mod, "load_dotenv", lambda override=True: None)
    monkeypatch.setattr(commands_mod, "_any_llm_key_present", lambda: False, raising=True)
    commands_mod.sys.stdin = SimpleNamespace(isatty=lambda: False)
    assert commands_mod._ensure_llm_key_before_agent(dummy_console) is True
    # Should not print setup panel in non-interactive bypass
    assert not getattr(dummy_console, "printed", [])


def test_ensure_llm_key_before_agent_interactive_wizard_exception(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(commands_mod, "load_dotenv", lambda override=True: None)
    monkeypatch.setattr(commands_mod, "_any_llm_key_present", lambda: False, raising=True)
    monkeypatch.setattr(commands_mod, "_supported_provider_envs", lambda: {"openai": "OPENAI_API_KEY"})
    commands_mod.sys.stdin = SimpleNamespace(isatty=lambda: True)

    # Patch the imported functions in cool_cli.bootstrap that the code pulls in
    import cool_cli.bootstrap as bootstrap
    monkeypatch.setattr(bootstrap, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"))
    monkeypatch.setattr(bootstrap, "run_key_setup_wizard", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("wizfail")))

    ok = commands_mod._ensure_llm_key_before_agent(dummy_console)
    assert ok is False
    # Bold red error printed
    assert any(e for e in dummy_console.events if e[0] == "print_text" and "Key setup failed" in e[1])


def test_ensure_llm_key_before_agent_interactive_success(commands_mod, monkeypatch, dummy_console):
    # Start: no key → after wizard, key present
    monkeypatch.setattr(commands_mod, "load_dotenv", lambda override=True: None)
    state = {"have_key": False}
    monkeypatch.setattr(commands_mod, "_any_llm_key_present", lambda: state["have_key"], raising=True)
    monkeypatch.setattr(commands_mod, "_supported_provider_envs", lambda: {"openai": "OPENAI_API_KEY"})
    commands_mod.sys.stdin = SimpleNamespace(isatty=lambda: True)

    import cool_cli.bootstrap as bootstrap
    monkeypatch.setattr(bootstrap, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"))
    def wizard_ok(_cns, preferred_provider=None):
        state["have_key"] = True
    monkeypatch.setattr(bootstrap, "run_key_setup_wizard", wizard_ok)

    ok = commands_mod._ensure_llm_key_before_agent(dummy_console)
    assert ok is True
    assert any(e for e in dummy_console.events if e[0] == "print_text" and "LLM API key configured" in e[1])


def test_ensure_llm_key_before_agent_interactive_still_missing(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(commands_mod, "load_dotenv", lambda override=True: None)
    monkeypatch.setattr(commands_mod, "_any_llm_key_present", lambda: False, raising=True)
    monkeypatch.setattr(commands_mod, "_supported_provider_envs", lambda: {"openai": "OPENAI_API_KEY"})
    commands_mod.sys.stdin = SimpleNamespace(isatty=lambda: True)

    import cool_cli.bootstrap as bootstrap
    monkeypatch.setattr(bootstrap, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"))
    monkeypatch.setattr(bootstrap, "run_key_setup_wizard", lambda *a, **k: None)

    ok = commands_mod._ensure_llm_key_before_agent(dummy_console)
    assert ok is False
    assert any(e for e in dummy_console.events if e[0] == "print_text" and "No API key found after setup" in e[1])


def test_run_agentic_command_no_output(commands_mod, monkeypatch, dummy_console):
    # Ensure we actually enter _run_agentic_command
    monkeypatch.setattr(commands_mod, "_ensure_llm_key_before_agent", lambda c: True, raising=True)

    class Result:
        output = ""
        exception = None
        exc_info = None

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())
    out = commands_mod.handle_command("rtlgen", dummy_console)

    from rich.text import Text
    assert isinstance(out, Text)
    # Style now comes from the module’s warning helper
    assert str(out.style).lower() == str(commands_mod.msg_warning("x").style).lower()
    assert "No output from `rtlgen` command." in out.plain


def test_agentic_skipped_when_key_missing(commands_mod, monkeypatch, dummy_console):
    monkeypatch.setattr(commands_mod, "_ensure_llm_key_before_agent", lambda c: False, raising=True)
    monkeypatch.setattr(commands_mod, "_supported_provider_envs", lambda: {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"})
    out = commands_mod.handle_command("report", dummy_console)
    assert isinstance(out, Text)
    assert out.style == "bold red"
    assert "Set one of:" in out.plain
    assert "OPENAI_API_KEY" in out.plain and "GROQ_API_KEY" in out.plain


def test_clear_handles_setattr_exception(commands_mod):
    class WeirdConsole:
        def __init__(self):
            object.__setattr__(self, "calls", [])
        def clear(self):
            self.calls.append("clear")
        def __setattr__(self, key, value):
            if key == "clears":
                raise RuntimeError("nope")
            object.__setattr__(self, key, value)

    wc = WeirdConsole()
    out = commands_mod.handle_command("clear", wc)
    assert isinstance(out, Text)
    assert "Conversation cleared" in out.plain
    # even though setattr failed, no exception escaped
    assert wc.calls == ["clear"]


def test_run_agentic_command_without_printed_attr(commands_mod, monkeypatch):
    # Console with .print but NO ".printed" attribute → branch is False
    class BareConsole:
        def __init__(self):
            self.logged = []
        def print(self, obj):
            self.logged.append(obj)

    c = BareConsole()

    class Result:
        output = "Hello Artifact"
        exception = None
        exc_info = None

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())

    out = commands_mod._run_agentic_command("rtlgen", c)
    # status panel printed once; no .printed append attempted
    assert len(c.logged) == 1
    assert out.plain == "Hello Artifact"


def test_agentic_exception_without_exc_info_tuple(commands_mod, monkeypatch, dummy_console):
    # Ensure we actually enter _run_agentic_command
    monkeypatch.setattr(commands_mod, "_ensure_llm_key_before_agent", lambda c: True, raising=True)

    class Result:
        output = ""
        exception = RuntimeError("oops-no-traceback")
        exc_info = "not-a-tuple"  # not a 3-tuple ⇒ no traceback in message

    monkeypatch.setattr(commands_mod.runner, "invoke", lambda cli, args: Result())
    out = commands_mod.handle_command("rtlgen", dummy_console)

    from rich.text import Text
    assert isinstance(out, Text)
    assert "Exception:" in out.plain
    assert "oops-no-traceback" in out.plain
    assert "Traceback:" not in out.plain


def test_clear_without_clear_method_increments_counter(commands_mod):
    class NoClear:
        pass

    c = NoClear()
    out = commands_mod.handle_command("clear", c)
    assert out.plain.startswith("Conversation cleared")
    assert getattr(c, "clears", 0) == 1  # defaulted, then incremented

def test_clear_with_noncallable_clear_attr(commands_mod):
    class WeirdClear:
        def __init__(self):
            self.clear = "not-callable"  # hasattr True, callable False ⇒ branch skip

    c = WeirdClear()
    out = commands_mod.handle_command("clear", c)
    assert out.plain.startswith("Conversation cleared")
    assert getattr(c, "clears", 0) == 1
