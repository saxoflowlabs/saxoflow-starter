# tests/test_coolcli/conftest.py
from __future__ import annotations
from typing import Any, Iterable, List
import io
import types
import pytest
import importlib
from rich.text import Text
from rich.panel import Panel
from rich.markdown import Markdown


# -------------------------
# Unified DummyConsole
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
    """
    One console that works for both app & agentic tests.

    - .events: list of tuples for behavioral assertions (app tests)
    - .printed: list of (type, text, style) tuples (agentic tests)
    - .output: raw text lines captured from Text/Markdown/etc.
    - .printed_objects: raw objects passed to console.print (for banner tests)
    """
    def __init__(self, width: int = 120):
        self.width = width
        self.events: List[tuple] = []
        self.printed: List[tuple] = []
        self.output: List[str] = []
        self.printed_objects: List[object] = []  # <-- added

    def print(self, obj: Any, *_, **__):
        # Capture the raw object for tests that need the real instance (e.g., Text)
        self.printed_objects.append(obj)  # <-- added

        # For agentic/app tests (style/structure checks)
        if isinstance(obj, Text):
            self.printed.append(("Text", obj.plain, obj.style or ""))
            self.output.append(obj.plain)
            self.events.append(("print_text", obj.plain, obj.style or ""))
        elif isinstance(obj, Panel):
            # Capture the inner renderable text if possible
            inner = getattr(obj, "renderable", "")
            if isinstance(inner, Text):
                txt = inner.plain
                style = inner.style or ""
            else:
                txt = str(inner)
                style = ""
            self.printed.append(("Panel", txt, style))
            self.events.append(("print_panel", getattr(obj, "title", ""), ""))
        elif isinstance(obj, Markdown):
            s = str(obj)
            self.printed.append(("Markdown", s, ""))
            self.events.append(("print_markdown", s, ""))
            self.output.append(s)
        else:
            s = str(obj)
            self.printed.append(("Raw", s, ""))
            self.events.append(("print_raw", s, ""))
            self.output.append(s)

    def status(self, msg: str, spinner: str | None = None):
        return _StatusCtx(self, msg, spinner)

    def clear(self):
        self.events.append(("console_clear", None))


# -------------------------
# PromptSession stub
# -------------------------
class SessionStub:
    def __init__(self, inputs: Iterable[Any]):
        self._inputs = list(inputs)
        self._idx = 0

    def prompt(self, _html):
        if self._idx >= len(self._inputs):
            raise EOFError()
        nxt = self._inputs[self._idx]
        self._idx += 1
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


# -------------------------
# Global guard
# -------------------------
@pytest.fixture(autouse=True)
def no_network():
    yield


# -------------------------
# Shared console fixture for BOTH modules
# -------------------------
@pytest.fixture
def dummy_console(monkeypatch) -> DummyConsole:
    dc = DummyConsole(width=120)

    # Patch app console if module is importable
    try:
        import cool_cli.app as app_mod
        monkeypatch.setattr(app_mod, "console", dc, raising=True)
    except Exception:
        pass

    # Patch agentic console if module is importable
    try:
        import cool_cli.agentic as agentic_mod
        monkeypatch.setattr(agentic_mod, "console", dc, raising=True)
    except Exception:
        pass

    return dc


# =========================
# Fixtures for cool_cli.app
# =========================

@pytest.fixture
def empty_history(monkeypatch):
    import cool_cli.app as sut
    new_hist: list = []
    monkeypatch.setattr(sut, "conversation_history", new_hist, raising=True)
    return new_hist


@pytest.fixture
def patch_prompt_session(monkeypatch):
    def _apply(inputs):
        import cool_cli.app as sut

        def ctor(**_kw):
            return SessionStub(inputs)

        monkeypatch.setattr(sut, "PromptSession", lambda **kw: ctor(), raising=True)
        monkeypatch.setattr(sut, "_build_completer", lambda: object(), raising=True)
        return inputs
    return _apply


@pytest.fixture
def patch_panels(monkeypatch):
    import cool_cli.app as sut

    def _user_input_panel(cmd: str, width: int | None = None):
        return Panel(Text(f"> {cmd}", style="bold white"), title="saxoflow", width=width, border_style="cyan")

    def _output_panel(renderable, border_style="white", width: int | None = None, icon=None):
        return Panel(renderable, title="output", width=width, border_style=border_style)

    def _agent_panel(renderable, width: int | None = None):
        return Panel(renderable, title="agent", width=width, border_style="magenta")

    def _ai_panel(renderable, width: int | None = None):
        return Panel(renderable, title="ai", width=width, border_style="cyan")

    def _welcome_panel(text: str, panel_width: int | None = None):
        return Panel(Text(text), title="welcome", width=panel_width, border_style="yellow")

    monkeypatch.setattr(sut, "user_input_panel", _user_input_panel, raising=True)
    monkeypatch.setattr(sut, "output_panel", _output_panel, raising=True)
    monkeypatch.setattr(sut, "agent_panel", _agent_panel, raising=True)
    monkeypatch.setattr(sut, "ai_panel", _ai_panel, raising=True)
    monkeypatch.setattr(sut, "welcome_panel", _welcome_panel, raising=True)
    return True


@pytest.fixture
def patch_constants(monkeypatch):
    import cool_cli.app as sut
    monkeypatch.setattr(sut, "CUSTOM_PROMPT_HTML", "<b>SF></b> ", raising=True)
    monkeypatch.setattr(
        sut,
        "AGENTIC_COMMANDS",
        {"rtlgen", "tbgen", "fpropgen", "report", "debug", "fullpipeline"},
        raising=True,
    )
    monkeypatch.setattr(
        sut,
        "SHELL_COMMANDS",
        {"ls": "list files", "pwd": "print wd", "cd": "change dir", "nano": "edit", "vim": "edit", "exit": "exit"},
        raising=True,
    )
    return True


@pytest.fixture
def patch_shell(monkeypatch):
    import cool_cli.app as sut

    def fake_is_unix(cmd: str) -> bool:
        raw = cmd.strip()
        if raw.startswith("!"):
            return True
        base = raw.split(maxsplit=1)[0].lower()
        return base in {"ls", "pwd", "cd", "nano", "vim", "vi", "exit", "code", "subl", "gedit"}

    def fake_process(cmd: str):
        if cmd.strip().lstrip("!").split()[0].lower() == "exit":
            return None
        return Text(f"ran:{cmd}", style="white")

    monkeypatch.setattr(sut, "is_unix_command", fake_is_unix, raising=True)
    monkeypatch.setattr(sut, "process_command", fake_process, raising=True)
    return True


@pytest.fixture
def patch_editors(monkeypatch):
    import cool_cli.app as sut

    def fake_is_blocking(cmd: str) -> bool:
        raw = cmd.strip().lstrip("!")
        base = raw.split()[0].lower()
        return base in {"nano", "vim", "vi", "micro"}

    monkeypatch.setattr(sut, "is_blocking_editor_command", fake_is_blocking, raising=True)
    return True


@pytest.fixture
def patch_banner(monkeypatch):
    import cool_cli.app as sut
    calls = {"count": 0}

    def fake_print_banner(console):
        calls["count"] += 1
        console.print(Text("[banner]", style="cyan"))

    monkeypatch.setattr(sut, "print_banner", fake_print_banner, raising=True)
    return calls


@pytest.fixture
def patch_aibuddy(monkeypatch):
    import cool_cli.app as sut
    monkeypatch.setattr(sut, "ai_buddy_interactive", lambda msg, hist: Text("buddy", style="white"), raising=True)
    return True


# ============================
# Fixtures for cool_cli.agentic
# ============================
@pytest.fixture
def patch_input(monkeypatch):
    """Queue inputs for builtins.input() used by agentic prompts."""
    queue: List[str] = []

    def fake_input(_prompt=""):
        if not queue:
            raise AssertionError("Input requested but queue is empty")
        return queue.pop(0)

    monkeypatch.setattr("builtins.input", fake_input, raising=True)

    class Controller:
        def push(self, *items):
            queue.extend(items)

    return Controller()


@pytest.fixture
def patch_isfile(monkeypatch):
    """Control os.path.isfile in cool_cli.agentic."""
    def _set(value: bool):
        import cool_cli.agentic as sut
        monkeypatch.setattr(sut.os.path, "isfile", lambda _p: value, raising=True)
    return _set


@pytest.fixture
def patch_open(monkeypatch):
    """Swap open() in cool_cli.agentic with one that returns content or raises OSError."""
    def success(content: str):
        def fake_open(*_a, **_kw):
            return io.StringIO(content)
        import cool_cli.agentic as sut
        monkeypatch.setattr(sut, "open", fake_open, raising=True)

    def fails(exc: OSError):
        def fake_open(*_a, **_kw):
            raise exc
        import cool_cli.agentic as sut
        monkeypatch.setattr(sut, "open", fake_open, raising=True)

    return types.SimpleNamespace(success=success, fails=fails)


@pytest.fixture
def fake_runner(monkeypatch):
    """Stub Click runner used by cool_cli.agentic._invoke_agent_cli_safely / run_quick_action."""
    class Result:
        def __init__(self, output: str):
            self.output = output
            self.exit_code = 0

    class RunnerStub:
        def __init__(self, default_output="OK"):
            self.default_output = default_output
            self.calls: list = []
        def invoke(self, cli, args):
            self.calls.append((cli, tuple(args)))
            return Result(self.default_output)

    import cool_cli.agentic as mod
    stub = RunnerStub()
    monkeypatch.setattr(mod, "runner", stub, raising=True)
    return stub


@pytest.fixture
def fake_agent_cli(monkeypatch):
    """Sentinel Click app for verification of invoke() wiring."""
    import cool_cli.agentic as mod
    sentinel = object()
    monkeypatch.setattr(mod, "agent_cli", sentinel, raising=True)
    return sentinel


# ============================
# Fixtures for cool_cli.ai_buddy
# ============================
import importlib
from typing import Any, Optional


@pytest.fixture(scope="session")
def ai_buddy_mod():
    """
    Import the ai_buddy module once for all tests here.
    Adjust the import path if your layout changes.
    """
    return importlib.import_module("cool_cli.ai_buddy")


class DummyLLM:
    """Minimal LLM stub that records prompts and returns a fixed response."""
    def __init__(self, response: Any, raise_on_invoke: Optional[BaseException] = None):
        self.response = response
        self.raise_on_invoke = raise_on_invoke
        self.seen_prompts = []

    def invoke(self, prompt: str) -> Any:
        self.seen_prompts.append(prompt)
        if self.raise_on_invoke:
            raise self.raise_on_invoke
        return self.response


class DummyAgent:
    """Minimal review agent stub to stand in for AgentManager agents."""
    def __init__(self, result: Any = "OK", raise_on_run: Optional[BaseException] = None):
        self.result = result
        self.raise_on_run = raise_on_run
        self.seen_inputs = []

    def run(self, arg: str) -> Any:
        self.seen_inputs.append(arg)
        if self.raise_on_run:
            raise self.raise_on_run
        return self.result


@pytest.fixture
def patch_model(monkeypatch, ai_buddy_mod):
    """
    Patch ModelSelector.get_model to return a DummyLLM.
    Usage:
        dummy = patch_model(response="Hello")
    """
    def _factory(response: Any, err: Optional[BaseException] = None) -> DummyLLM:
        dummy = DummyLLM(response=response, raise_on_invoke=err)
        monkeypatch.setattr(ai_buddy_mod.ModelSelector, "get_model", lambda **_: dummy)
        return dummy
    return _factory


@pytest.fixture
def patch_agent(monkeypatch, ai_buddy_mod):
    """
    Patch AgentManager.get_agent to return a DummyAgent.
    Usage:
        agent = patch_agent(result="Review OK")
    """
    def _factory(result: Any = "OK", err: Optional[BaseException] = None) -> DummyAgent:
        dummy = DummyAgent(result=result, raise_on_run=err)
        monkeypatch.setattr(ai_buddy_mod.AgentManager, "get_agent", lambda action: dummy)
        return dummy
    return _factory


# ============================
# Fixture for cool_cli.banner
# ============================
@pytest.fixture(scope="session")
def banner_mod():
    """Import the banner module once for banner tests."""
    return importlib.import_module("cool_cli.banner")


# ============================
# Fixture for cool_cli.commands
# ============================
@pytest.fixture
def commands_mod():
    """
    Provide a fresh import of cool_cli.commands for tests that assert behavior
    on its module-level helpers (help panel builder, width calc, etc.).
    """
    import cool_cli.commands as mod
    return importlib.reload(mod)
