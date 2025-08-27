# tests/test_coolcli/test_app_edges.py
from __future__ import annotations

from typing import Any, Iterable, List
import types
import pytest
from rich.text import Text
from rich.panel import Panel


# -------------------------
# Lightweight test doubles
# -------------------------
class _StatusCtx:
    def __init__(self, console, msg: str, spinner: str | None):
        self.console = console
        self.msg = msg
        self.spinner = spinner

    def __enter__(self):
        self.console.events.append(("status_enter", self.msg, self.spinner))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.console.events.append(("status_exit", self.msg, self.spinner))
        return False


class DummyConsole:
    """Rich-like console that records prints and status usage."""

    def __init__(self, width: int = 120):
        self.width = width
        self.events: List[tuple] = []
        self.output: List[str] = []

    def print(self, obj: Any, *_, **__):
        if isinstance(obj, Text):
            self.events.append(("print_text", obj.plain, obj.style or ""))
            self.output.append(obj.plain)
        elif isinstance(obj, Panel):
            self.events.append(("print_panel", getattr(obj, "title", ""), ""))
            # also capture small trace of the inner text for smoke checks
            inner = getattr(obj, "renderable", "")
            self.output.append(str(getattr(inner, "plain", inner)))
        else:
            s = str(obj)
            self.events.append(("print_raw", s, ""))
            self.output.append(s)

    def status(self, msg: str, spinner: str | None = None):
        return _StatusCtx(self, msg, spinner)

    def clear(self):
        self.events.append(("console_clear", None))


class SessionStub:
    """Deterministic PromptSession replacement."""

    def __init__(self, inputs: Iterable[Any]):
        self._inputs = list(inputs)
        self._i = 0

    def prompt(self, _prompt):
        if self._i >= len(self._inputs):
            raise EOFError()
        item = self._inputs[self._i]
        self._i += 1
        if isinstance(item, BaseException):
            raise item
        return item


# -------------------------
# Common fixtures
# -------------------------
@pytest.fixture(autouse=True)
def _fresh_import(monkeypatch):
    """Ensure module is (re)loaded fresh for each test."""
    import importlib
    import cool_cli.app as sut  # noqa: F401
    importlib.reload(sut)
    return sut


@pytest.fixture
def dummy_console(monkeypatch, _fresh_import):
    dc = DummyConsole(width=100)
    monkeypatch.setattr(_fresh_import, "console", dc, raising=True)
    return dc


@pytest.fixture
def empty_history(monkeypatch, _fresh_import):
    hist: list = []
    monkeypatch.setattr(_fresh_import, "conversation_history", hist, raising=True)
    return hist


@pytest.fixture
def patch_prompt_session(monkeypatch, _fresh_import):
    def apply(seq):
        monkeypatch.setattr(
            _fresh_import,
            "PromptSession",
            lambda **kw: SessionStub(seq),
            raising=True,
        )
        # keep completer trivial (we test _build_completer separately)
        monkeypatch.setattr(_fresh_import, "_build_completer", lambda: object(), raising=True)
        return seq
    return apply


@pytest.fixture
def patch_panels(monkeypatch, _fresh_import):
    def _user_input_panel(cmd: str, width=None):
        return Panel(Text(f"> {cmd}"), title="saxoflow", width=width)

    def _output_panel(r, border_style="white", width=None, icon=None):
        return Panel(r, title="output", width=width)

    def _agent_panel(r, width=None):
        return Panel(r, title="agent", width=width)

    def _ai_panel(r, width=None):
        return Panel(r, title="ai", width=width)

    def _welcome_panel(txt: str, panel_width=None):
        return Panel(Text(txt), title="welcome", width=panel_width)

    monkeypatch.setattr(_fresh_import, "user_input_panel", _user_input_panel, raising=True)
    monkeypatch.setattr(_fresh_import, "output_panel", _output_panel, raising=True)
    monkeypatch.setattr(_fresh_import, "agent_panel", _agent_panel, raising=True)
    monkeypatch.setattr(_fresh_import, "ai_panel", _ai_panel, raising=True)
    monkeypatch.setattr(_fresh_import, "welcome_panel", _welcome_panel, raising=True)
    return True


@pytest.fixture
def patch_constants(monkeypatch, _fresh_import):
    monkeypatch.setattr(_fresh_import, "CUSTOM_PROMPT_HTML", "<b>SF></b> ", raising=True)
    monkeypatch.setattr(
        _fresh_import,
        "AGENTIC_COMMANDS",
        {"rtlgen", "tbgen", "fpropgen", "report", "debug", "fullpipeline"},
        raising=True,
    )
    monkeypatch.setattr(
        _fresh_import,
        "SHELL_COMMANDS",
        {"ls": "list", "pwd": "pwd", "cd": "cd", "nano": "edit", "vim": "edit"},
        raising=True,
    )
    return True


@pytest.fixture
def patch_shell_basics(monkeypatch, _fresh_import):
    # default: treat leading "!" or known basename as shell
    def fake_is_unix(cmd: str) -> bool:
        raw = cmd.strip()
        if raw.startswith("!"):
            return True
        base = raw.split(maxsplit=1)[0].lower()
        return base in {"ls", "pwd", "cd", "nano", "vim"}

    monkeypatch.setattr(_fresh_import, "is_unix_command", fake_is_unix, raising=True)
    return True


@pytest.fixture
def patch_aibuddy(monkeypatch, _fresh_import):
    monkeypatch.setattr(
        _fresh_import,
        "ai_buddy_interactive",
        lambda msg, hist: Text("buddy"),
        raising=True,
    )
    return True


# -------------------------
# Tests
# -------------------------
def test_requires_raw_tty_skips_spinner(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell_basics,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
    _fresh_import,
):
    """Shell path: when requires_raw_tty=True, no status spinner is used."""
    # require raw tty for this command
    monkeypatch.setattr(_fresh_import, "requires_raw_tty", lambda _c: True, raising=True)
    # simple processor
    monkeypatch.setattr(_fresh_import, "process_command", lambda c: Text("ran"), raising=True)

    patch_prompt_session(["!saxoflow init-env", "quit"])
    _fresh_import.main()

    # history recorded once, and no status_enter event
    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert not any(e for e in dummy_console.events if e[0] == "status_enter")


def test_blocking_editor_never_shows_spinner(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell_basics,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
    _fresh_import,
):
    """Blocking editors go straight through without status spinner."""
    monkeypatch.setattr(_fresh_import, "requires_raw_tty", lambda _c: False, raising=True)
    monkeypatch.setattr(_fresh_import, "process_command", lambda c: Text("ok"), raising=True)

    # classify this as blocking editor
    monkeypatch.setattr(
        _fresh_import, "is_blocking_editor_command", lambda _c: True, raising=True
    )

    patch_prompt_session(["!nano notes.v", "quit"])
    _fresh_import.main()

    assert len(empty_history) == 1
    assert empty_history[0]["panel"] == "output"
    assert not any(e for e in dummy_console.events if e[0] == "status_enter")


def test_quit_cleanup_called_even_if_raises(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell_basics,
    patch_aibuddy,
    dummy_console,
    monkeypatch,
    _fresh_import,
):
    """On 'quit', process_command is attempted; exceptions are swallowed."""
    called = {"n": 0}

    def boom(_cmd):
        called["n"] += 1
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(_fresh_import, "process_command", boom, raising=True)

    patch_prompt_session(["quit"])
    _fresh_import.main()

    # goodbye printed and cleanup attempted exactly once
    assert called["n"] == 1
    assert any(e for e in dummy_console.events if e[0] == "print_text" and e[2] == "cyan")


def test_clear_calls_cleanup_and_resets_history_even_if_raises(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell_basics,
    patch_aibuddy,
    dummy_console,
    empty_history,
    monkeypatch,
    _fresh_import,
):
    """'clear' triggers cleanup, clears history, shows banner next loop."""
    empty_history.extend([{"user": "x", "assistant": Text("y"), "panel": "ai"}])
    called = {"n": 0}

    def boom(_cmd):
        called["n"] += 1
        raise ValueError("nope")

    monkeypatch.setattr(_fresh_import, "process_command", boom, raising=True)

    # count banner prints
    cnt = {"n": 0}

    def fake_banner(cons):
        cnt["n"] += 1
        cons.print(Text("[banner]", style="cyan"))

    monkeypatch.setattr(_fresh_import, "print_banner", fake_banner, raising=True)

    patch_prompt_session(["clear", KeyboardInterrupt()])
    _fresh_import.main()

    assert called["n"] == 1
    assert empty_history == []
    assert cnt["n"] >= 1  # banner re-shown on next loop


def test_build_completer_contains_expected_commands(monkeypatch, _fresh_import):
    """_build_completer should include built-ins, agentic, utilities and shell keys."""
    captured = {"commands": None}

    class CapturingCompleter:
        def __init__(self, commands: list[str]):
            captured["commands"] = list(commands)

    monkeypatch.setattr(_fresh_import, "HybridShellCompleter", CapturingCompleter, raising=True)
    monkeypatch.setattr(
        _fresh_import,
        "SHELL_COMMANDS",
        {"ls": "list files", "pwd": "print", "nano": "edit"},
        raising=True,
    )
    comp = _fresh_import._build_completer()
    assert comp is not None
    cmds = set(captured["commands"] or [])
    # spot check a few categories
    assert {"help", "quit", "exit", "ai"}.issubset(cmds)
    assert {"rtlgen", "tbgen", "fullpipeline"}.issubset(cmds)
    assert {"ls", "pwd", "nano"}.issubset(cmds)


def test_show_opening_look_prints_banner_welcome_and_tips(
    patch_panels,
    dummy_console,
    _fresh_import,
    monkeypatch,
):
    """_show_opening_look should print banner, welcome panel, tips, and a blank line."""
    calls = {"banner": 0}

    def fake_banner(cons):
        calls["banner"] += 1
        cons.print(Text("[banner]", style="cyan"))

    monkeypatch.setattr(_fresh_import, "print_banner", fake_banner, raising=True)
    _fresh_import._show_opening_look(panel_width=80)

    # At least: banner, welcome panel, tips text, trailing blank
    kinds = [e[0] for e in dummy_console.events]
    assert calls["banner"] == 1
    assert kinds.count("print_panel") >= 1  # welcome panel
    assert any(e for e in dummy_console.events if e[0] == "print_text")  # tips line(s)


def test_render_history_unknown_panel_defaults_to_ai(
    patch_panels,
    dummy_console,
    empty_history,
    _fresh_import,
    patch_prompt_session,
):
    """Unknown panel tag should fall back to ai panel in _render_history."""
    empty_history.append(
        {"user": "cmd", "assistant": Text("hi"), "panel": "something-weird"}
    )
    patch_prompt_session(["quit"])
    _fresh_import.main()

    # One of the printed panels should be titled "ai"
    ai_titles = [t for (k, t, _) in dummy_console.events if k == "print_panel" and t == "ai"]
    assert ai_titles  # non-empty implies ai fallback was used


def test_bootstrap_first_run_called_once(
    patch_prompt_session,
    patch_panels,
    patch_constants,
    patch_shell_basics,
    patch_aibuddy,
    _fresh_import,
    monkeypatch,
):
    """ensure_first_run_setup(console) must be called exactly once on startup."""
    count = {"n": 0}

    def fake_bootstrap(cons):
        count["n"] += 1

    monkeypatch.setattr(_fresh_import, "ensure_first_run_setup", fake_bootstrap, raising=True)
    patch_prompt_session(["quit"])
    _fresh_import.main()
    assert count["n"] == 1
