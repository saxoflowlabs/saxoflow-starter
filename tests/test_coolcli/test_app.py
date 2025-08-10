# tests/test_coolcli/test_app.py
from __future__ import annotations

"""
Comprehensive, hermetic test suite for cool_cli.app in a single file.

This file includes:
- Shared fixtures (DummyConsole, SessionStub, panel stubs, patch_* helpers)
- All unit/integration-like tests covering:
  * Built-ins (help/quit/exit/clear/init-env help variants)
  * Shell/editor commands (blocking and non-blocking, with/without "!")
  * Agentic commands via subprocess helper (success/failure/edge branches)
  * AI Buddy routing
  * Internals: _clear_terminal, _goodbye
  * History rendering and _print_and_record permutations
  * Unicode/adversarial inputs
  * Spinner/status usage for shell/agentic paths

All external effects are mocked. Tests are deterministic and lint-clean.
"""

from typing import Any, Iterable, List
import types
import pytest

from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown


# =============================================================================
# Shared stubs and fixtures (normally in conftest.py)
# =============================================================================


class _StatusCtx:
    """Context manager to record status enter/exit on DummyConsole."""

    def __init__(self, console, msg: str):
        self.console = console
        self.msg = msg

    def __enter__(self):
        self.console.events.append(("status_enter", self.msg))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.console.events.append(("status_exit", None))


class DummyConsole:
    """
    Minimal Rich Console stand-in that records printed objects and status usage.
    """

    def __init__(self, width: int = 100):
        self.width = width
        self.events: List[Any] = []
        self.output: List[str] = []

    def print(self, obj: Any):
        if isinstance(obj, Text):
            self.events.append(("print_text", obj.plain, obj.style or ""))
            self.output.append(obj.plain)
        elif isinstance(obj, Panel):
            self.events.append(("print_panel", getattr(obj, "title", ""), ""))
            self.output.append(f"[PANEL]{getattr(obj, 'title', '')}")
        elif isinstance(obj, Markdown):
            self.events.append(("print_markdown", str(obj), ""))
            self.output.append("[MARKDOWN]")
        else:
            s = str(obj)
            self.events.append(("print_raw", s, ""))
            self.output.append(s)

    def status(self, msg: str, spinner: str = ""):
        return _StatusCtx(self, msg)

    def clear(self):
        self.events.append(("console_clear", None))


class SessionStub:
    """
    Deterministic PromptSession replacement.

    - If an item is an Exception instance, it is raised.
    - If input list is exhausted, raises EOFError.
    """

    def __init__(self, inputs: Iterable[Any]):
        self._inputs = list(inputs)
        self._idx = 0

    def prompt(self, _prompt):
        if self._idx >= len(self._inputs):
            raise EOFError()
        nxt = self._inputs[self._idx]
        self._idx += 1
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


def _simple_ai_panel(renderable, width=None):
    return Panel(renderable, title="ai", width=width, border_style="cyan")


def _simple_agent_panel(renderable, width=None):
    return Panel(renderable, title="agent", width=width, border_style="magenta")


def _simple_output_panel(renderable, border_style="white", width=None, icon=None):
    return Panel(renderable, title="output", width=width, border_style=border_style)


def _simple_user_input_panel(txt: str, width=None):
    return Panel(
        Text(f"> {txt}", style="bold white"),
        title="saxoflow",
        width=width,
        border_style="cyan",
    )


def _simple_welcome_panel(text: str, panel_width=None):
    return Panel(Text(text), title="welcome", width=panel_width, border_style="yellow")


@pytest.fixture(autouse=True)
def _import_sut(monkeypatch):
    """
    Import SUT fresh for each test module run.
    """
    import importlib
    import cool_cli.app as sut  # noqa: F401
    importlib.reload(sut)
    return sut


@pytest.fixture
def dummy_console(_import_sut, monkeypatch):
    """
    Replace app.console with DummyConsole so tests can assert on events.
    """
    dc = DummyConsole(width=120)
    monkeypatch.setattr(_import_sut, "console", dc, raising=True)
    return dc


@pytest.fixture
def empty_history(_import_sut, monkeypatch):
    """
    Provide a reference to the shared conversation_history and reset it per test.
    """
    hist = _import_sut.conversation_history
    hist.clear()
    return hist


@pytest.fixture
def patch_prompt_session(_import_sut, monkeypatch):
    """
    Factory: provide a list of inputs for the CLI loop.
    Usage: patch_prompt_session(["help", "quit"])
    """
    inputs = {"vals": []}

    def _apply(seq):
        inputs["vals"] = list(seq)
        monkeypatch.setattr(
            _import_sut,
            "PromptSession",
            lambda **kw: SessionStub(inputs["vals"]),
            raising=True,
        )
        return inputs

    return _apply


@pytest.fixture
def patch_panels(_import_sut, monkeypatch):
    """
    Replace panel constructors with simple, predictable versions.
    """
    monkeypatch.setattr(_import_sut, "ai_panel", _simple_ai_panel, raising=True)
    monkeypatch.setattr(_import_sut, "agent_panel", _simple_agent_panel, raising=True)
    monkeypatch.setattr(_import_sut, "output_panel", _simple_output_panel, raising=True)
    monkeypatch.setattr(
        _import_sut, "user_input_panel", _simple_user_input_panel, raising=True
    )
    monkeypatch.setattr(_import_sut, "welcome_panel", _simple_welcome_panel, raising=True)
    return True


@pytest.fixture
def patch_constants(_import_sut, monkeypatch):
    """
    Stabilize command sets and prompt HTML.
    """
    monkeypatch.setattr(
        _import_sut,
        "AGENTIC_COMMANDS",
        {"rtlgen", "tbgen", "fpropgen", "report", "debug", "fullpipeline"},
        raising=True,
    )
    monkeypatch.setattr(_import_sut, "CUSTOM_PROMPT_HTML", "<b>SF></b> ", raising=True)
    monkeypatch.setattr(
        _import_sut,
        "SHELL_COMMANDS",
        {
            "ls": "list files",
            "pwd": "print wd",
            "cd": "change dir",
            "nano": "edit",
            "vim": "edit",
            "exit": "exit",
        },
        raising=True,
    )
    return True


@pytest.fixture
def patch_shell(_import_sut, monkeypatch):
    """
    Provide deterministic shell detection and command processing.
    """

    def fake_is_unix(cmd: str) -> bool:
        raw = cmd.strip()
        if raw.startswith("!"):
            return True
        base = raw.split(maxsplit=1)[0].lower()
        return base in {
            "ls",
            "pwd",
            "cd",
            "nano",
            "vim",
            "vi",
            "exit",
            "code",
            "subl",
            "gedit",
        }

    def fake_process(cmd: str):
        if cmd.strip().lstrip("!").split()[0].lower() == "exit":
            return None
        return Text(f"ran:{cmd}", style="white")

    monkeypatch.setattr(_import_sut, "is_unix_command", fake_is_unix, raising=True)
    monkeypatch.setattr(_import_sut, "process_command", fake_process, raising=True)
    return True


@pytest.fixture
def patch_editors(_import_sut, monkeypatch):
    """
    Make nano/vim blocking editors; others non-blocking.
    """

    def fake_is_blocking(cmd: str) -> bool:
        raw = cmd.strip().lstrip("!")
        base = raw.split()[0].lower()
        return base in {"nano", "vim", "vi", "micro"}

    monkeypatch.setattr(
        _import_sut, "is_blocking_editor_command", fake_is_blocking, raising=True
    )
    return True


@pytest.fixture
def patch_banner(_import_sut, monkeypatch):
    """
    Count how many times the banner is printed to verify clear logic.
    """
    counter = {"count": 0}

    def fake_print_banner(console_obj):
        counter["count"] += 1
        console_obj.print(Text("[banner]", style="cyan"))

    monkeypatch.setattr(_import_sut, "print_banner", fake_print_banner, raising=True)
    return counter


@pytest.fixture
def patch_aibuddy(_import_sut, monkeypatch):
    """
    Stub AI buddy to a constant Text response.
    """

    def fake_buddy(prompt: str, history):
        return Text("buddy", style="white")

    monkeypatch.setattr(
        _import_sut, "ai_buddy_interactive", fake_buddy, raising=True
    )
    return True


# =============================================================================
# Small helpers used by tests of _run_agentic_subprocess
# =============================================================================


class PopenOk:
    """Stub Popen returning successful output."""

    def __init__(self, stdout="ok\n", stderr=""):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = 0

    def communicate(self):
        return (self._stdout, self._stderr)


class PopenErr:
    """Stub Popen returning non-zero exit code."""

    def __init__(self, code=1, out="oops\n", err=""):
        self.returncode = code
        self._stdout = out
        self._stderr = err

    def communicate(self):
        return (self._stdout, self._stderr)


# =============================================================================
# Tests — Agentic routing
# =============================================================================


def test_agentic_command_route_to_agent_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
    monkeypatch,
):
    """Agentic command should render into the agent panel and be recorded."""
    import cool_cli.app as sut

    monkeypatch.setattr(
        sut, "_run_agentic_subprocess", lambda line: Text("agent-ok", style="white")
    )

    patch_prompt_session(["rtlgen --foo bar", "quit"])
    sut.main()

    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "agent"
    assert empty_history[0]["assistant"].plain == "agent-ok"


# =============================================================================
# Tests — AI Buddy routing
# =============================================================================


def test_ai_buddy_default_route_to_ai_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
):
    """Unrecognized input should go to AI Buddy and appear in AI panel."""
    import cool_cli.app as sut

    patch_prompt_session(["what is saxoflow?", "quit"])
    sut.main()

    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert isinstance(empty_history[0]["assistant"], Text)
    assert empty_history[0]["assistant"].plain == "buddy"


# =============================================================================
# Tests — Built-ins
# =============================================================================


def test_help_renders_panel_and_records_history(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """When 'help' returns a Panel, it should be printed and recorded as a 'panel' entry."""
    import cool_cli.app as sut

    def process_command(cmd: str):
        return Panel.fit(Text("help content"))

    monkeypatch.setattr(sut, "process_command", process_command)

    patch_prompt_session(["help"])
    sut.main()

    assert len(empty_history) == 1
    assert empty_history[0]["user"] == "help"
    assert empty_history[0]["panel"] == "panel"


def test_quit_and_exit_print_goodbye_and_exit(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
):
    """Both 'quit' and 'exit' should print cyan goodbye and terminate."""
    import cool_cli.app as sut

    patch_prompt_session(["quit"])
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "print_text" and evt[2] == "cyan"
    )

    dummy_console.output.clear()
    dummy_console.events.clear()
    patch_prompt_session(["exit"])
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "print_text" and evt[2] == "cyan"
    )


def test_clear_resets_history_and_shows_banner_next_loop(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """'clear' must wipe in-memory history and show banner on next loop."""
    import cool_cli.app as sut

    empty_history.extend([{"user": "x", "assistant": Text("y"), "panel": "ai"}])
    monkeypatch.setattr(sut, "process_command", lambda cmd: Text("cleared"))
    patch_prompt_session(["clear", "quit"])
    sut.main()

    assert empty_history == []
    assert patch_banner["count"] >= 1


def test_builtin_init_env_help_route_to_output_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """'init-env --help' should be routed to output panel."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "process_command", lambda cmd: Text("init help"))
    patch_prompt_session(["init-env --help"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"


def test_keyboard_interrupt_and_eof_show_goodbye(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
):
    """KeyboardInterrupt and EOFError should both result in cyan goodbye being printed."""
    import cool_cli.app as sut

    patch_prompt_session([KeyboardInterrupt()])
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "print_text" and evt[2] == "cyan"
    )

    dummy_console.events.clear()
    patch_prompt_session([])  # immediately EOF
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "print_text" and evt[2] == "cyan"
    )


def test_empty_input_is_ignored_then_quit(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
):
    """Blank input must be ignored (no history entry)."""
    import cool_cli.app as sut

    patch_prompt_session(["   ", "quit"])
    sut.main()
    assert empty_history == []


def test_init_env_help_space_form_to_output_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
    monkeypatch,
):
    """Verify 'init-env help' (space variant) routes as built-in to output panel."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "process_command", lambda cmd: Text("init help (space)"))
    patch_prompt_session(["init-env help"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"


def test_help_as_text_not_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
    monkeypatch,
):
    """If 'help' returns Text (not Panel), it must be wrapped as output panel and recorded."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "process_command", lambda cmd: Text("plain help"))
    patch_prompt_session(["help"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert isinstance(empty_history[0]["assistant"], Text)
    assert "plain help" in empty_history[0]["assistant"].plain


# =============================================================================
# Tests — Shell routing
# =============================================================================


def test_shell_blocking_editor_flows_through_output_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
):
    """'!nano' is treated as blocking editor and recorded via output panel."""
    import cool_cli.app as sut

    patch_prompt_session(["!nano file.sv", "quit"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert "nano" in empty_history[0]["user"]


def test_shell_nonblocking_uses_status_and_records_output(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
):
    """Non-blocking shell commands should open status and record output panel."""
    import cool_cli.app as sut

    patch_prompt_session(["!ls -l", "quit"])
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "status_enter" and "Loading..." in evt[1]
    )
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"


def test_shell_process_command_none_triggers_exit_and_goodbye(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """If process_command returns None, CLI prints goodbye and exits (no history recorded)."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "process_command", lambda cmd: None)
    patch_prompt_session(["!exit"])
    sut.main()
    assert any(
        evt for evt in dummy_console.events if evt[0] == "print_text" and evt[2] == "cyan"
    )
    assert empty_history == []


def test_plain_nano_without_bang_is_blocking_editor_and_records_output(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
):
    """Typing 'nano file' (no '!') still goes through shell path and records output."""
    import cool_cli.app as sut

    patch_prompt_session(["nano my.v", "quit"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert "nano my.v" in empty_history[0]["user"]


def test_console_width_smoke(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
):
    """Change console width to ensure panel width math doesn't error."""
    import cool_cli.app as sut  # noqa: F401

    dummy_console.width = 77  # odd width, ensure no crash
    patch_prompt_session(["quit"])
    # just run; reaching here is success
    import cool_cli.app as sut2  # noqa: F401
    sut2.main()
    assert True


# =============================================================================
# Tests — App internals
# =============================================================================


def test_goodbye_returns_cyan_text():
    """_goodbye must return a cyan Text with expected phrase."""
    import cool_cli.app as sut

    msg = sut._goodbye()
    assert isinstance(msg, Text)
    assert "timing constraints" in msg.plain
    assert msg.style == "cyan"


def test_clear_terminal_calls_os_system(monkeypatch):
    """_clear_terminal should call os.system with the correct command per OS."""
    import cool_cli.app as sut

    calls = {"cmd": None}

    def fake_system(cmd):
        calls["cmd"] = cmd
        return 0

    import os

    monkeypatch.setattr(
        sut, "os", types.SimpleNamespace(system=fake_system, name="posix")
    )
    sut._clear_terminal()
    assert calls["cmd"] == "clear"


# =============================================================================
# Tests — Agentic subprocess helper
# =============================================================================


def test_run_agentic_subprocess_success(monkeypatch):
    """Successful subprocess returns white Text with stdout."""
    import cool_cli.app as sut

    monkeypatch.setattr(
        sut, "subprocess", types.SimpleNamespace(Popen=lambda *a, **k: PopenOk("hello", ""))
    )
    out = sut._run_agentic_subprocess("rtlgen --unit alu")
    assert isinstance(out, Text)
    assert out.style == "white"
    assert "hello" in out.plain


def test_run_agentic_subprocess_nonzero(monkeypatch):
    """Non-zero return codes produce bold red error Text with combined output."""
    import cool_cli.app as sut

    monkeypatch.setattr(
        sut, "subprocess", types.SimpleNamespace(Popen=lambda *a, **k: PopenErr(2, "bad", "err"))
    )
    out = sut._run_agentic_subprocess("rtlgen --unit alu")
    assert out.style == "bold red"
    assert out.plain.startswith("[❌] Error")


def test_run_agentic_subprocess_file_not_found(monkeypatch):
    """FileNotFoundError should produce a bold red helpful error."""
    import cool_cli.app as sut

    def boom(*a, **k):
        raise FileNotFoundError("python3 not found")

    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=boom))
    out = sut._run_agentic_subprocess("rtlgen")
    assert out.style == "bold red"
    assert "Failed to run agentic command" in out.plain


def test_run_agentic_subprocess_generic_exception(monkeypatch):
    """Generic Exception should be caught and surfaced as bold red unexpected error."""
    import cool_cli.app as sut

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=boom))
    out = sut._run_agentic_subprocess("rtlgen")
    assert out.style == "bold red"
    assert "Unexpected error" in out.plain


class _PopenEmpty:
    def __init__(self):
        self.returncode = 0

    def communicate(self):
        return ("", "")


def test_run_agentic_subprocess_empty_output(monkeypatch):
    """When agentic returns no stdout/stderr, a warning text is produced."""
    import cool_cli.app as sut

    monkeypatch.setattr(
        sut, "subprocess", types.SimpleNamespace(Popen=lambda *a, **k: _PopenEmpty())
    )
    out = sut._run_agentic_subprocess("rtlgen --unit alu")
    assert isinstance(out, Text)
    assert out.style == "white"
    assert "[⚠] No output" in out.plain


def test_agentic_path_uses_status_spinner(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """Agentic route must open a status spinner (clock)."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "_run_agentic_subprocess", lambda s: Text("ok", style="white"))
    patch_prompt_session(["rtlgen --arg x", "quit"])
    sut.main()
    assert any(
        e for e in dummy_console.events if e[0] == "status_enter" and "Agentic AI running" in e[1]
    )


# =============================================================================
# Tests — History rendering & _print_and_record permutations
# =============================================================================


def test_render_history_with_panel_and_panel_types(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
):
    """
    Seed different history entry types and ensure panels are printed:
    - assistant None
    - assistant as Panel (panel kind ignored)
    - panel_type: output, agent, ai
    """
    import cool_cli.app as sut

    empty_history.append({"user": "hello", "assistant": None, "panel": "ai"})
    empty_history.append({"user": "help", "assistant": Panel.fit(Text("X")), "panel": "panel"})
    empty_history.append({"user": "cmd1", "assistant": Text("out"), "panel": "output"})
    empty_history.append({"user": "cmd2", "assistant": Text("agent-ans"), "panel": "agent"})
    empty_history.append({"user": "cmd3", "assistant": Text("ai-ans"), "panel": "ai"})

    patch_prompt_session(["quit"])
    sut.main()

    titles = [e[1] for e in dummy_console.events if e[0] == "print_panel"]
    assert "output" in titles
    assert "agent" in titles
    assert "ai" in titles


def test_print_and_record_variants(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    dummy_console,
    empty_history,
):
    """
    Exercise _print_and_record with multiple renderable types and panel kinds:
    - str into output
    - Text into agent
    - Markdown into ai
    - raw Panel passthrough (panel kind ignored for style)
    """
    import cool_cli.app as sut

    patch_prompt_session([])  # immediate EOF
    panel_width = 80

    sut._print_and_record("cmd-str", "hello", "output", panel_width)
    sut._print_and_record("cmd-text", Text("t"), "agent", panel_width)
    sut._print_and_record("cmd-md", Markdown("# H"), "ai", panel_width)
    raw_panel = Panel(Text("p"))
    sut._print_and_record("cmd-panel", raw_panel, "output", panel_width)

    assert len(empty_history) == 4
    assert empty_history[0]["panel"] == "output"
    assert empty_history[1]["panel"] == "agent"
    assert empty_history[2]["panel"] == "ai"
    assert isinstance(empty_history[3]["assistant"], Panel)


# =============================================================================
# Tests — Unicode inputs
# =============================================================================


def test_unicode_input_to_ai_buddy_recorded(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    empty_history,
):
    """Ensure non-ASCII input routes to AI buddy and is recorded."""
    import cool_cli.app as sut

    patch_prompt_session(["设计验证🤖是什么？", "quit"])
    sut.main()
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert empty_history[0]["user"].startswith("设计验证")
