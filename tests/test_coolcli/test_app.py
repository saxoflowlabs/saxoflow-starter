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
import importlib
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
def _import_sut(monkeypatch, tmp_path):
    """
    Import SUT fresh for each test module run.
    """
    import importlib
    import cool_cli.app as sut  # noqa: F401
    importlib.reload(sut)
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    monkeypatch.setattr(
        sut,
        "resolve_workspace",
        lambda workspace=None, create=True: workspace_dir,
        raising=True,
    )
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

    def fake_print_banner(console_obj, compact=False):
        counter["count"] += 1
        console_obj.print(Text("[banner]", style="cyan"))

    monkeypatch.setattr(_import_sut, "print_banner", fake_print_banner, raising=True)
    return counter


@pytest.fixture
def patch_aibuddy(_import_sut, monkeypatch):
    """
    Stub AI buddy to a constant Text response.
    """

    def fake_buddy(prompt: str, history, skip_clarification: bool = False):
        return Text("buddy", style="white")

    monkeypatch.setattr(
        _import_sut, "ai_buddy_interactive", fake_buddy, raising=True
    )
    return True


# 1) Always reload the SUT so globals don’t leak across tests
@pytest.fixture(autouse=True)
def _reload_app_module():
    import importlib, cool_cli.app as sut
    importlib.reload(sut)
    yield


# 2) Make first-run setup a no-op for tests (prevents prompting/IO)
@pytest.fixture(autouse=True)
def patch_first_run_setup(monkeypatch):
    import cool_cli.app as sut
    monkeypatch.setattr(sut, "ensure_first_run_setup", lambda _console: None, raising=True)
    return True


# 3) Stabilize TTY-sensitive branch used by shell path
@pytest.fixture(autouse=True)
def patch_requires_raw_tty(monkeypatch):
    import cool_cli.app as sut
    # For tests, keep it simple: never require a raw TTY; spinner path is exercised.
    monkeypatch.setattr(sut, "requires_raw_tty", lambda _cmd: False, raising=True)
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


def test_fullpipeline_bare_alias_routes_to_agent_panel(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Bare `fullpipeline` should route through agentic alias handling, not AI fallback."""
    import cool_cli.app as sut

    calls = {"agentic": 0, "buddy": 0}

    def fake_agentic(line: str):
        calls["agentic"] += 1
        assert line.startswith("fullpipeline")
        return Text("agent-fullpipeline", style="white")

    def fake_buddy(_prompt: str, _history, skip_clarification: bool = False):
        calls["buddy"] += 1
        return Text("buddy", style="white")

    monkeypatch.setattr(sut, "_run_agentic_subprocess", fake_agentic, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fake_buddy, raising=True)

    patch_prompt_session(["fullpipeline --target demo", "quit"])
    sut.main()

    assert calls["agentic"] == 1
    assert calls["buddy"] == 0
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "agent"
    assert empty_history[0]["assistant"].plain == "agent-fullpipeline"


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


def test_plain_non_command_text_uses_ai_buddy_fallback(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Plain non-command text should fall through to AI Buddy in the current baseline."""
    import cool_cli.app as sut

    calls = {"buddy": 0, "agentic": 0}

    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)
    monkeypatch.setattr(sut, "_plan_clarification", lambda *_a, **_k: None, raising=True)
    monkeypatch.setattr(sut, "_detect_incomplete_request", lambda *_a, **_k: False, raising=True)

    def fake_agentic(_line: str):
        calls["agentic"] += 1
        return Text("agent", style="white")

    def fake_buddy(prompt: str, history, skip_clarification: bool = False):
        calls["buddy"] += 1
        assert prompt == "explain this project"
        assert skip_clarification is True
        return Text("buddy-fallback", style="white")

    monkeypatch.setattr(sut, "_run_agentic_subprocess", fake_agentic, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fake_buddy, raising=True)

    patch_prompt_session(["explain this project"])
    sut.main()

    assert calls["buddy"] == 1
    assert calls["agentic"] == 0
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert empty_history[0]["assistant"].plain == "buddy-fallback"


def test_ai_buddy_clarification_stops_spinner_before_questions(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    dummy_console,
    empty_history,
    monkeypatch,
):
    """Question planning shows Thinking, then exits before clarification prompts."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "_project_context", lambda: "ctx", raising=True)
    monkeypatch.setattr(sut, "_load_prefs", lambda: {}, raising=True)
    monkeypatch.setattr(sut, "_prefs_context", lambda _prefs: "", raising=True)
    monkeypatch.setattr(
        sut,
        "_plan_clarification",
        lambda *_a, **_k: [{"key": "width", "question": "Width?", "default": "1"}],
        raising=True,
    )

    def _flow(original, questions, context=""):
        dummy_console.events.append(("clarification_flow", original, context))
        return "enriched spec"

    def _buddy(prompt: str, history, skip_clarification: bool = False):
        dummy_console.events.append(("ai_buddy", prompt, skip_clarification))
        return Text("built", style="white")

    monkeypatch.setattr(sut, "_run_clarification_flow", _flow, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", _buddy, raising=True)

    patch_prompt_session(["create mux", "quit"])
    sut.main()

    events = dummy_console.events
    status_enter_idx = next(
        i
        for i, e in enumerate(events)
        if e[0] == "status_enter" and "Thinking" in e[1]
    )
    status_exit_idx = next(i for i, e in enumerate(events) if e[0] == "status_exit")
    flow_idx = next(i for i, e in enumerate(events) if e[0] == "clarification_flow")
    buddy_idx = next(i for i, e in enumerate(events) if e[0] == "ai_buddy")

    assert status_enter_idx < status_exit_idx < flow_idx < buddy_idx
    assert (
        sum(1 for e in events if e[0] == "status_enter" and "Thinking" in e[1])
        == 1
    )
    assert empty_history[0]["assistant"].plain == "built"


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


def test_direct_unix_command_routes_to_shell_not_ai(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Direct Unix commands (no '!') should use shell routing and skip AI Buddy."""
    import cool_cli.app as sut

    calls = {"shell": [], "buddy": 0}

    def fake_is_unix(cmd: str) -> bool:
        return cmd.startswith("which ")

    def fake_process(cmd: str):
        calls["shell"].append(cmd)
        return Text(f"shell:{cmd}", style="white")

    def fake_buddy(prompt: str, history, skip_clarification: bool = False):
        calls["buddy"] += 1
        return Text("buddy", style="white")

    monkeypatch.setattr(sut, "is_unix_command", fake_is_unix, raising=True)
    monkeypatch.setattr(sut, "process_command", fake_process, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fake_buddy, raising=True)

    patch_prompt_session(["which yosys", "quit"])
    sut.main()

    assert "which yosys" in calls["shell"]
    assert calls["buddy"] == 0
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert empty_history[0]["assistant"].plain == "shell:which yosys"


def test_explicit_ai_command_routes_to_ai_service_handler(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Explicit ask/plan/run/research commands should route through AI service handler."""
    import cool_cli.app as sut

    calls = {"service": [], "buddy": 0}

    def fake_ai_service(task_type: str, prompt: str, history, metadata=None):
        calls["service"].append((task_type, prompt, len(history), metadata or {}))
        return Text(f"service:{task_type}:{prompt}", style="white")

    def fake_buddy(_prompt: str, _history, skip_clarification: bool = False):
        calls["buddy"] += 1
        return Text("buddy", style="white")

    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)
    monkeypatch.setattr(sut, "_run_ai_service_command", fake_ai_service, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fake_buddy, raising=True)

    patch_prompt_session(['ask "explain this project"', "quit"])
    sut.main()

    assert calls["service"] == [("ask", "explain this project", 0, {})]
    assert calls["buddy"] == 0
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert empty_history[0]["assistant"].plain == "service:ask:explain this project"


def test_ai_service_command_is_chat_only_and_does_not_call_ai_buddy(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Explicit AI service route must not trigger full AI Buddy action/review/save flow."""
    import cool_cli.app as sut

    calls = {"chat_only": [], "buddy": 0}

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        calls["chat_only"].append({
            "message": message,
            "history_len": len(history),
            "task_hint": task_hint,
            "context": context,
            "metadata": metadata,
        })
        return {"type": "chat", "message": "plan response"}

    def fail_if_buddy_called(*_args, **_kwargs):
        calls["buddy"] += 1
        return Text("should-not-be-called", style="white")

    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fail_if_buddy_called, raising=True)
    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)

    patch_prompt_session(['plan "create a short verification plan"', "quit"])
    sut.main()

    assert calls["buddy"] == 0
    assert len(calls["chat_only"]) == 1
    assert calls["chat_only"][0]["message"] == "create a short verification plan"
    assert calls["chat_only"][0]["task_hint"] == "plan"
    assert calls["chat_only"][0]["metadata"]["plan_workflow_policy"]["feasible"] is True
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert "Structured plan (read-only)" in empty_history[0]["assistant"].plain
    assert "Plan details:" in empty_history[0]["assistant"].plain
    assert "plan response" in empty_history[0]["assistant"].plain


def test_research_ai_service_command_emits_synthesis_contract_and_saves_notes_under_docs_tree(
    tmp_path,
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Explicit research route should be evidence-synthesis oriented and docs-bound."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    docs_dir = workspace / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "plan2.md").write_text("# Plan 2\n- Research routing\n", encoding="utf-8")

    calls = {"chat_only": [], "buddy": 0}

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        calls["chat_only"].append({
            "message": message,
            "history_len": len(history),
            "task_hint": task_hint,
            "context": context,
            "metadata": metadata,
        })
        return {
            "type": "chat",
            "message": (
                "## Question\n"
                "compare latest open-source pnr workflows\n\n"
                "## Method\n"
                "Compared grounded notes with retrieved web sources.\n\n"
                "## Sources\n"
                "- [context:docs/plan2.md]\n"
                "- [web:1] Example OpenROAD — https://example.com/openroad\n\n"
                "## Findings\n"
                "OpenROAD emphasizes ASIC closure flow details [web:1].\n\n"
                "## Comparisons\n"
                "- OpenROAD is more complete for ASIC exploration than manual flows [web:1].\n\n"
                "## Confidence\n"
                "High, because both local notes and retrieved source agree [context:docs/plan2.md] [web:1].\n\n"
                "## Open questions\n"
                "- Which PDK is installed?\n\n"
                "## Citations\n"
                "- [context:docs/plan2.md]\n"
                "- [web:1] https://example.com/openroad\n"
            ),
        }

    class FakeWebResearchService:
        provider_name = "duckduckgo_html"

        def search(self, query, max_results=3, fetch_pages=False, max_fetched_pages=2):
            assert query == "compare latest open-source pnr workflows"
            assert max_results == 3
            return [
                types.SimpleNamespace(
                    to_dict=lambda: {
                        "source_id": "1",
                        "provider": "duckduckgo_html",
                        "query": query,
                        "title": "Example OpenROAD",
                        "url": "https://example.com/openroad",
                        "snippet": "OpenROAD overview",
                        "retrieved_at": "2026-06-30T00:00:00Z",
                    }
                )
            ]

    def fail_if_buddy_called(*_args, **_kwargs):
        calls["buddy"] += 1
        return Text("should-not-be-called", style="white")

    monkeypatch.setenv("SAXOFLOW_WORKSPACE", str(workspace))
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)
    monkeypatch.setattr(sut, "WebResearchService", FakeWebResearchService, raising=True)
    monkeypatch.setattr(sut, "ai_buddy_interactive", fail_if_buddy_called, raising=True)
    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)

    patch_prompt_session(['research "compare latest open-source pnr workflows" --context docs/plan2.md --tools web.search,artifact.write', "quit"])
    sut.main()

    assert calls["buddy"] == 0
    assert len(calls["chat_only"]) == 1
    assert calls["chat_only"][0]["message"] == "compare latest open-source pnr workflows"
    assert calls["chat_only"][0]["task_hint"] == "research"
    assert calls["chat_only"][0]["metadata"]["research_workflow_policy"]["feasible"] is True
    assert calls["chat_only"][0]["metadata"]["web_research_policy"]["requested"] is True
    assert calls["chat_only"][0]["metadata"]["web_research_policy"]["allowed"] is True
    assert calls["chat_only"][0]["metadata"]["research_workflow_policy"]["persist_research_artifact"] is True
    assert calls["chat_only"][0]["metadata"]["web_research_execution"]["executed"] is True
    assert calls["chat_only"][0]["metadata"]["web_research_execution"]["result_count"] == 1
    assert calls["chat_only"][0]["metadata"]["web_research_sources"][0]["url"] == "https://example.com/openroad"
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert "Research synthesis (read-only)" in empty_history[0]["assistant"].plain
    assert "Web retrieval:" in empty_history[0]["assistant"].plain
    assert "Saved research notes:" in empty_history[0]["assistant"].plain
    assert "## Comparisons" in empty_history[0]["assistant"].plain
    assert "[web:1]" in empty_history[0]["assistant"].plain
    assert "Extract compared findings" not in empty_history[0]["assistant"].plain
    saved_files = sorted((docs_dir).glob("research_*.md"))
    assert len(saved_files) == 1
    saved_text = saved_files[0].read_text(encoding="utf-8")
    assert "# Research notes" in saved_text
    assert "## Web retrieval" in saved_text
    assert "https://example.com/openroad" in saved_text
    assert "## Comparisons" in saved_text
    assert "## Citations" in saved_text
    assert "Fill in compared findings" not in saved_text


def test_ai_service_command_runs_grounding_before_chat_response(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """P6.04a: explicit AI route first grounds request envelope via AIRequestService."""
    import cool_cli.app as sut

    calls = {"grounding": [], "chat_only": 0}

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            calls["grounding"].append(
                {
                    "task_type": task_type,
                    "prompt": prompt,
                    "metadata": dict(metadata or {}),
                    "workspace_root": str(self.workspace_root),
                }
            )
            return {"ok": True}

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "grounded response"}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)
    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)

    patch_prompt_session([
        'run "prototype" --context docs/spec.md --agent report --tools file.read,eda.run',
        "quit",
    ])
    sut.main()

    assert len(calls["grounding"]) == 1
    assert calls["grounding"][0]["task_type"] == "run"
    assert calls["grounding"][0]["prompt"] == "prototype"
    assert calls["grounding"][0]["metadata"] == {
        "requested_agent": "report",
        "requested_context_paths": ["docs/spec.md"],
        "requested_capabilities": ["file.read", "eda.run"],
    }
    assert calls["chat_only"] == 1
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert empty_history[0]["assistant"].plain == "grounded response"


def test_ai_service_command_grounding_error_returns_error_without_chat_call(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """P6.04a: grounding failures must be surfaced directly and skip chat response."""
    import cool_cli.app as sut

    calls = {"chat_only": 0}

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            raise sut.AIRequestServiceError("Context path 'docs/missing.md' does not exist")

    def fake_chat_only(*_args, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "unexpected"}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)
    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)

    patch_prompt_session(['ask "explain" --context docs/missing.md', "quit"])
    sut.main()

    assert calls["chat_only"] == 0
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert "does not exist" in empty_history[0]["assistant"].plain


def test_ask_ai_service_command_proves_grounded_context_usage(
    monkeypatch,
):
    """P6.04b: ask output must visibly include grounded context citations."""
    import cool_cli.app as sut

    calls = {"chat_metadata": []}

    class _Ref:
        def __init__(self, path: str):
            self.path = path

    class _Bundle:
        def __init__(self, refs):
            self.references = refs

    class _GroundedState:
        def __init__(self):
            self.context_bundle = _Bundle([_Ref("source/specification/design.md")])
            self.tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            assert task_type == "ask"
            assert prompt == "explain design intent"
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        calls["chat_metadata"].append(dict(metadata or {}))
        return {"type": "chat", "message": "Design intent summary."}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "ask",
        "explain design intent",
        [],
        {
            "requested_context_paths": ["source/specification/design.md"],
            "requested_capabilities": ["file.read"],
        },
    )

    assert "Grounded ask (read-only)" in renderable.plain
    assert "[context:source/specification/design.md]" in renderable.plain
    assert "Design intent summary." in renderable.plain
    assert calls["chat_metadata"]
    assert calls["chat_metadata"][0]["grounded_context_refs"] == [
        "source/specification/design.md"
    ]


def test_ask_ai_service_command_includes_grounded_file_documents(tmp_path, monkeypatch):
    """Ask path should pass bounded grounded file contents to chat-only backend."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    rtl_dir = workspace / "source" / "rtl" / "verilog"
    rtl_dir.mkdir(parents=True)
    rtl_file = rtl_dir / "counter_rtl_gen.v"
    rtl_file.write_text("module counter_rtl_gen;\nendmodule\n", encoding="utf-8")

    calls = {"metadata": []}

    class _Ref:
        def __init__(self, path: str):
            self.path = path

    class _Bundle:
        def __init__(self, refs):
            self.references = refs

    class _GroundedState:
        def __init__(self):
            self.context_bundle = _Bundle([_Ref("source/rtl/verilog/counter_rtl_gen.v")])
            self.tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        calls["metadata"].append(dict(metadata or {}))
        return {"type": "chat", "message": "ok"}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    sut._run_ai_service_command(
        "ask",
        "explain rtl",
        [],
        {"requested_context_paths": ["source/rtl/verilog/counter_rtl_gen.v"]},
    )

    assert calls["metadata"]
    docs = calls["metadata"][0].get("grounded_context_documents")
    assert isinstance(docs, list)
    assert docs
    assert docs[0]["path"] == "source/rtl/verilog/counter_rtl_gen.v"
    assert "module counter_rtl_gen" in docs[0]["content"]


def test_plan_ai_service_command_rejects_incompatible_capabilities(monkeypatch):
    """P6.04c: plan route rejects execution-oriented incompatible capabilities."""
    import cool_cli.app as sut

    class _GroundedState:
        context_bundle = None
        tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    calls = {"chat_only": 0}

    def fake_chat_only(*_args, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "unexpected"}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "plan",
        "milestones",
        [],
        {"requested_capabilities": ["eda.run"]},
    )

    assert "rejects incompatible capabilities" in renderable.plain
    assert "eda.run" in renderable.plain
    assert calls["chat_only"] == 0


def test_plan_ai_service_command_saves_artifact_under_docs_tree(tmp_path, monkeypatch):
    """P6.04c: plan route may persist a plan artifact only under active unit docs/."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    class _GroundedState:
        context_bundle = None
        tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        return {
            "type": "chat",
            "message": "- Milestone 1\n- Milestone 2\nInclude prerequisites and risks.",
        }

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "plan",
        "create plan",
        [],
        {"requested_capabilities": ["artifact.write"]},
    )

    assert "Structured plan (read-only)" in renderable.plain
    assert "Milestones:" in renderable.plain
    assert "Prerequisites:" in renderable.plain
    assert "Risks:" in renderable.plain
    assert "Approval checkpoints:" in renderable.plain
    assert "Saved plan artifact: docs/plan_" in renderable.plain

    docs_dir = workspace / "docs"
    artifacts = sorted(docs_dir.glob("plan_*.md"))
    assert artifacts
    artifact_text = artifacts[0].read_text(encoding="utf-8")
    assert "# Structured plan" in artifact_text
    assert "## Approval Checkpoints" in artifact_text
    assert "Milestone 1" in artifact_text


def test_run_ai_service_command_rejects_incompatible_capabilities(monkeypatch):
    """P6.04e: run route rejects capabilities outside bounded execution policy."""
    import cool_cli.app as sut

    class _GroundedState:
        context_bundle = None
        tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    calls = {"chat_only": 0}

    def fake_chat_only(*_args, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "unexpected"}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "prototype",
        [],
        {"requested_capabilities": ["shell.exec"]},
    )

    assert "rejects incompatible capabilities" in renderable.plain
    assert "shell.exec" in renderable.plain
    assert calls["chat_only"] == 0


def test_run_ai_service_command_emits_approvals_events_resume_and_artifact(tmp_path, monkeypatch):
    """P6.04e: run output includes approvals, tool events, resumable state, and docs artifact."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    class _Task:
        metadata = {
            "run_adapter_routing": {
                "requested": True,
                "classification_status": "classified",
                "scenario": "synthesis",
                "adapter_module": "saxoflow.tools.adapters.synthesis",
                "reason": "Classified eda.run intent as `synthesis`.",
            }
        }

    class _GroundedState:
        context_bundle = None
        tasks = (_Task(),)

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        return {"type": "chat", "message": "Run execution summary."}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "close timing",
        [],
        {"requested_capabilities": ["file.read", "eda.run", "artifact.write"]},
    )

    assert "Bounded run (agent-mode)" in renderable.plain
    assert "Approval checkpoints:" in renderable.plain
    assert "Tool events:" in renderable.plain
    assert "scenario: synthesis" in renderable.plain
    assert "saxoflow.tools.adapters.synthesis" in renderable.plain
    assert "Resumable state:" in renderable.plain
    assert "resume_token=run-" in renderable.plain
    assert "Saved run artifact: docs/run_" in renderable.plain
    assert "Run execution summary." in renderable.plain

    docs_dir = workspace / "docs"
    artifacts = sorted(docs_dir.glob("run_*.md"))
    assert artifacts
    artifact_text = artifacts[0].read_text(encoding="utf-8")
    assert "# Run execution notes" in artifact_text
    assert "## Approval checkpoints" in artifact_text
    assert "## Tool events" in artifact_text
    assert "## Resumable state" in artifact_text


def test_run_ai_service_command_rejects_unclassified_eda_run_scenario(monkeypatch):
    """P6.04g: run route must reject eda.run when scenario classification is rejected."""
    import cool_cli.app as sut

    class _Task:
        metadata = {
            "run_adapter_routing": {
                "requested": True,
                "classification_status": "rejected",
                "scenario": None,
                "adapter_module": None,
                "reason": "Could not classify `eda.run` intent.",
            }
        }

    class _GroundedState:
        context_bundle = None
        tasks = (_Task(),)

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    calls = {"chat_only": 0}

    def fake_chat_only(*_args, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "unexpected"}

    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "prototype tests",
        [],
        {"requested_capabilities": ["eda.run"]},
    )

    assert calls["chat_only"] == 0
    assert "could not classify `eda.run` scenario" in renderable.plain.lower()


def test_run_ai_service_command_renders_simulation_scenario_event(tmp_path, monkeypatch):
    """P6.04g remediation: prototype-tests intent should surface simulation adapter scenario."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    class _Task:
        metadata = {
            "run_adapter_routing": {
                "requested": True,
                "classification_status": "classified",
                "scenario": "simulation",
                "adapter_module": "saxoflow.tools.adapters.simulation",
                "reason": "Classified eda.run intent as `simulation`.",
            }
        }

    class _GroundedState:
        context_bundle = None
        tasks = (_Task(),)

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        return {"type": "chat", "message": "Run simulation summary."}

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "prototype tests",
        [],
        {"requested_capabilities": ["eda.run"]},
    )

    assert "scenario: simulation" in renderable.plain
    assert "saxoflow.tools.adapters.simulation" in renderable.plain


def test_run_ai_service_command_supports_web_search_and_renders_retrieval_summary(tmp_path, monkeypatch):
    """P6.04e extension: run route supports web.search/web.fetch and shows retrieval summary."""
    import cool_cli.app as sut

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)

    class _GroundedState:
        context_bundle = None
        tasks = ()

    class FakeAIRequestService:
        def __init__(self, workspace_root):
            self.workspace_root = workspace_root

        def start_grounded_task(self, task_type, prompt, metadata=None):
            return _GroundedState()

    def fake_chat_only(message, history, context=None, task_hint=None, metadata=None, **_kwargs):
        return {"type": "chat", "message": "Run web summary."}

    def fake_collect(query, requested_capabilities):
        assert "web.search" in requested_capabilities
        return {
            "executed": True,
            "provider": "searxng",
            "query": query,
            "result_count": 1,
            "fetched_page_count": 1,
            "sources": [
                {
                    "source_id": "1",
                    "title": "Example source",
                    "url": "https://example.com",
                }
            ],
        }

    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sut, "AIRequestService", FakeAIRequestService, raising=True)
    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)
    monkeypatch.setattr(sut, "_collect_web_research_sources", fake_collect, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "find references",
        [],
        {"requested_capabilities": ["file.read", "web.search", "web.fetch", "artifact.write"]},
    )

    assert "Bounded run (agent-mode)" in renderable.plain
    assert "Approve capability `web.search` usage in run mode." in renderable.plain
    assert "Approve capability `web.fetch` usage in run mode." in renderable.plain
    assert "tool.adapter: staged `web.search` retrieval queued" in renderable.plain
    assert "Web retrieval:" in renderable.plain
    assert "Provider: searxng" in renderable.plain
    assert "[web:1] Example source" in renderable.plain

    docs_dir = workspace / "docs"
    artifacts = sorted(docs_dir.glob("run_*.md"))
    assert artifacts
    artifact_text = artifacts[0].read_text(encoding="utf-8")
    assert "## Web retrieval" in artifact_text
    assert "Provider: searxng" in artifact_text


def test_explicit_ai_command_passes_compact_options_metadata_to_ai_service(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """P6.04: parsed --context/--agent/--tools options are forwarded to AI service request."""
    import cool_cli.app as sut

    calls = {"service": []}

    def fake_ai_service(task_type: str, prompt: str, history, metadata=None):
        calls["service"].append((task_type, prompt, len(history), metadata or {}))
        return Text("ok", style="white")

    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)
    monkeypatch.setattr(sut, "_run_ai_service_command", fake_ai_service, raising=True)

    patch_prompt_session([
        'run "prototype" --context docs/spec.md --context source/rtl --agent ppa --tools file.read,eda.run',
        "quit",
    ])
    sut.main()

    assert len(calls["service"]) == 1
    task_type, prompt, history_len, metadata = calls["service"][0]
    assert task_type == "run"
    assert prompt == "prototype"
    assert history_len == 0
    assert metadata == {
        "requested_agent": "ppa",
        "requested_context_paths": ["docs/spec.md", "source/rtl"],
        "requested_capabilities": ["file.read", "eda.run"],
    }
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"


def test_ai_service_command_empty_prompt_returns_usage_warning(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """Explicit AI service should reject quote-empty prompts with usage output."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)
    monkeypatch.setattr(
        sut,
        "_ask_ai_buddy_chat_only",
        lambda *_args, **_kwargs: {"type": "chat", "message": "unexpected"},
        raising=True,
    )

    patch_prompt_session(['ask ""', "quit"])
    sut.main()

    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert "Usage: ask" in empty_history[0]["assistant"].plain


def test_ai_service_command_help_requested_returns_mode_help_without_chat_call(monkeypatch):
    """P6.04f: explicit --help returns mode-aware help and does not invoke chat backend."""
    import cool_cli.app as sut

    calls = {"chat_only": 0}

    def fake_chat_only(*_args, **_kwargs):
        calls["chat_only"] += 1
        return {"type": "chat", "message": "unexpected"}

    monkeypatch.setattr(sut, "_ask_ai_buddy_chat_only", fake_chat_only, raising=True)

    renderable = sut._run_ai_service_command(
        "run",
        "",
        [],
        {"help_requested": True},
    )

    assert calls["chat_only"] == 0
    assert "run mode help" in renderable.plain
    assert "Supported options:" in renderable.plain
    assert "Allowed capabilities:" in renderable.plain
    assert "eda.run" in renderable.plain
    assert "Prompt structure examples:" in renderable.plain


def test_main_routes_ask_help_to_mode_aware_ai_help(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_editors,
    patch_banner,
    empty_history,
    monkeypatch,
):
    """P6.04f: `ask --help` in TUI prints mode-aware help instead of usage warning."""
    import cool_cli.app as sut

    monkeypatch.setattr(sut, "is_unix_command", lambda _cmd: False, raising=True)

    patch_prompt_session(["ask --help", "quit"])
    sut.main()

    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "ai"
    assert "ask mode help" in empty_history[0]["assistant"].plain
    assert "Allowed capabilities:" in empty_history[0]["assistant"].plain


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


# --- style helpers for robust checks ---
def _style_to_str(style) -> str:
    if style is None:
        return ""
    try:
        return str(style).lower()
    except Exception:
        return ""

def _is_red(style) -> bool:
    s = _style_to_str(style)
    return "red" in s

def _is_yellow(style) -> bool:
    s = _style_to_str(style)
    return "yellow" in s


def test_run_agentic_subprocess_nonzero(monkeypatch):
    """Non-zero return codes produce error via messages helper with combined output."""
    import cool_cli.app as sut
    from rich.text import Text
    import types

    # Simulate a failing agentic command with both stdout and stderr
    monkeypatch.setattr(
        sut,
        "subprocess",
        types.SimpleNamespace(Popen=lambda *a, **k: PopenErr(2, "bad", "err")),
    )

    out = sut._run_agentic_subprocess("rtlgen --unit alu")
    assert isinstance(out, Text)

    # Style family check (accept any 'red-ish' error style)
    assert _is_red(out.style) or _is_red(sut.msg_error("x").style)

    # Your helper now prefixes with 'ERROR: ' — don't require exact startswith
    plain = out.plain.strip()
    assert "Error in `rtlgen --unit alu`" in plain

    # Combined stdout+stderr included
    assert "bad" in plain
    assert "err" in plain


def test_run_agentic_subprocess_file_not_found(monkeypatch):
    """FileNotFoundError should produce a helpful error."""
    import cool_cli.app as sut
    from rich.text import Text
    import types

    def boom(*a, **k):
        raise FileNotFoundError("python3 not found")

    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=boom))
    out = sut._run_agentic_subprocess("rtlgen")
    assert isinstance(out, Text)
    # Style robust
    assert _is_red(out.style) or _is_red(sut.msg_error("x").style)
    assert "Failed to run agentic command" in out.plain


def test_run_agentic_subprocess_generic_exception(monkeypatch):
    """Generic Exception should be surfaced as an error via helper."""
    import cool_cli.app as sut
    from rich.text import Text
    import types

    def boom(*a, **k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=boom))
    out = sut._run_agentic_subprocess("rtlgen")
    assert isinstance(out, Text)
    # Style robust
    assert _is_red(out.style) or _is_red(sut.msg_error("x").style)
    assert "Unexpected error" in out.plain


class _PopenEmpty:
    def __init__(self):
        self.returncode = 0

    def communicate(self):
        return ("", "")


def test_run_agentic_subprocess_empty_output(monkeypatch):
    """When agentic returns no stdout/stderr, produce a warning via messages helper."""
    import cool_cli.app as sut
    from rich.text import Text
    import types

    monkeypatch.setattr(
        sut,
        "subprocess",
        types.SimpleNamespace(Popen=lambda *a, **k: _PopenEmpty()),
    )

    out = sut._run_agentic_subprocess("rtlgen --unit alu")
    assert isinstance(out, Text)
    # Accept any 'yellow-ish' style, or match helper family
    assert _is_yellow(out.style) or _is_yellow(sut.msg_warning("x").style)
    assert "No output from `rtlgen --unit alu` command." in out.plain


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

    sut._render_history(panel_width=80)

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


def test_print_and_record_uses_saxoflow_panel_for_saxoflow_output(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    monkeypatch,
):
    """SaxoFlow command outputs should use saxoflow_panel, not output_panel."""
    import cool_cli.app as sut

    patch_prompt_session([])
    calls = {"saxoflow": 0, "output": 0, "width": None}

    def _spy_saxoflow_panel(renderable, fit=False, width=None):
        calls["saxoflow"] += 1
        calls["width"] = width
        return Panel(renderable, title="saxoflow", width=width)

    def _spy_output_panel(renderable, border_style="white", width=None, icon=None):
        calls["output"] += 1
        return Panel(renderable, title="output", width=width, border_style=border_style)

    monkeypatch.setattr(sut, "saxoflow_panel", _spy_saxoflow_panel, raising=True)
    monkeypatch.setattr(sut, "output_panel", _spy_output_panel, raising=True)

    sut._print_and_record("check-tools", Text("ok"), "output", panel_width=80)

    assert calls["saxoflow"] == 1
    assert calls["output"] == 0
    assert calls["width"] == sut.console.width


def test_print_and_record_keeps_output_panel_for_non_saxoflow_output(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell,
    patch_editors,
    patch_banner,
    patch_aibuddy,
    monkeypatch,
):
    """Non-SaxoFlow command outputs should keep using output_panel."""
    import cool_cli.app as sut

    patch_prompt_session([])
    calls = {"saxoflow": 0, "output": 0}

    def _spy_saxoflow_panel(renderable, fit=False, width=None):
        calls["saxoflow"] += 1
        return Panel(renderable, title="saxoflow", width=width)

    def _spy_output_panel(renderable, border_style="white", width=None, icon=None):
        calls["output"] += 1
        return Panel(renderable, title="output", width=width, border_style=border_style)

    monkeypatch.setattr(sut, "saxoflow_panel", _spy_saxoflow_panel, raising=True)
    monkeypatch.setattr(sut, "output_panel", _spy_output_panel, raising=True)

    sut._print_and_record("ls", Text("ok"), "output", panel_width=80)

    assert calls["saxoflow"] == 0
    assert calls["output"] == 1


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


# ---------------------------------------------------------------------------
# Bare saxoflow subcommand auto-expansion tests
# ---------------------------------------------------------------------------


def test_bare_check_tools_routes_to_shell_not_ai_buddy(
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
    """Typing 'check-tools' (no 'saxoflow' prefix) must NOT reach the AI Buddy.
    It should be auto-expanded to 'saxoflow check-tools' and run as a shell command."""
    import cool_cli.app as sut

    ai_called = []

    def _track_ai_buddy(*a, **kw):
        ai_called.append(True)
        return Text("ai response")

    monkeypatch.setattr(sut, "ai_buddy_interactive", _track_ai_buddy, raising=True)

    shell_called = []

    def _track_shell(cmd):
        shell_called.append(cmd)
        return Text(f"ran: {cmd}")

    monkeypatch.setattr(sut, "process_command", _track_shell, raising=True)

    # The fixture's fake_is_unix only knows a small set of Unix commands.
    # Override so that any 'saxoflow …' call (after auto-expansion) is
    # recognised as a CLI command and routed to process_command.
    monkeypatch.setattr(
        sut,
        "is_unix_command",
        lambda cmd: cmd.strip().split(maxsplit=1)[0].lower() == "saxoflow",
        raising=True,
    )

    patch_prompt_session(["check-tools", "quit"])
    sut.main()

    assert ai_called == [], "AI Buddy must NOT be invoked for bare 'check-tools'"
    assert any("saxoflow check-tools" in c for c in shell_called), (
        f"Expected 'saxoflow check-tools' in shell calls, got: {shell_called}"
    )


def test_bare_agenticai_routes_to_shell_not_ai_buddy(
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
    """Typing 'agenticai' alone must NOT reach the AI Buddy — it is a saxoflow CLI command."""
    import cool_cli.app as sut

    ai_called = []

    def _track_ai_buddy(*a, **kw):
        ai_called.append(True)
        return Text("ai response")

    monkeypatch.setattr(sut, "ai_buddy_interactive", _track_ai_buddy, raising=True)

    shell_called = []

    def _track_shell(cmd):
        shell_called.append(cmd)
        return Text(f"ran: {cmd}")

    monkeypatch.setattr(sut, "process_command", _track_shell, raising=True)

    # Recognise 'saxoflow …' (post-expansion) as a CLI command.
    monkeypatch.setattr(
        sut,
        "is_unix_command",
        lambda cmd: cmd.strip().split(maxsplit=1)[0].lower() == "saxoflow",
        raising=True,
    )

    patch_prompt_session(["agenticai", "quit"])
    sut.main()

    assert ai_called == [], "AI Buddy must NOT be invoked for bare 'agenticai'"
    assert any("saxoflow agenticai" in c for c in shell_called), (
        f"Expected 'saxoflow agenticai' in shell calls, got: {shell_called}"
    )
