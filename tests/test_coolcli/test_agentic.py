# tests/test_coolcli/test_agentic.py
from __future__ import annotations

import io
import pytest
from rich.text import Text
from cool_cli import agentic as sut


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mk(msg_type, **extra):
    """Build a minimal buddy result payload."""
    payload = {"type": msg_type}
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# AI Buddy Interactive tests (happy/adversarial)
# ---------------------------------------------------------------------------

def test_ai_buddy_need_file_path_happy(
    monkeypatch, patch_input, patch_isfile, patch_open, dummy_console
):
    """User pastes a file path; file is read; buddy returns review_result."""
    first = _mk("need_file", message="please provide file")
    second = _mk("review_result", message="review ok")

    calls = []

    def fake_buddy(user_input, history, file_to_review=None):
        calls.append((user_input, tuple(history), file_to_review))
        return first if len(calls) == 1 else second

    monkeypatch.setattr(sut, "ask_ai_buddy", fake_buddy)

    patch_isfile(True)
    patch_open.success("module X; content")
    patch_input.push("/tmp/code.sv")

    out = sut.ai_buddy_interactive("review this", [{"role": "user", "content": "hi"}])
    assert isinstance(out, Text)
    assert out.plain == "review ok"
    assert out.style == "white"

    # Console printed the yellow need_file message
    assert dummy_console.printed[0][2] == "yellow"
    # First call without code; second call receives file contents
    assert calls[0][2] is None
    assert calls[1][2] == "module X; content"


def test_ai_buddy_need_file_inline_code(
    monkeypatch, patch_input, patch_isfile, dummy_console
):
    """User pastes inline code (not a file); treated as literal."""
    first = _mk("need_file", message="send code")
    second = _mk("review_result", message="looks good")
    calls = []

    def fake_buddy(_u, _h, file_to_review=None):
        calls.append(file_to_review)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(sut, "ask_ai_buddy", fake_buddy)

    patch_isfile(False)  # not a file -> literal code
    patch_input.push("always_ff @(posedge clk) q<=d;")

    out = sut.ai_buddy_interactive("review", [])
    assert isinstance(out, Text)
    assert out.plain == "looks good"
    assert out.style == "white"
    assert calls == [None, "always_ff @(posedge clk) q<=d;"]


def test_ai_buddy_need_file_read_fails(
    monkeypatch, patch_input, patch_isfile, patch_open, dummy_console
):
    """Reading a provided file path fails → surface red error Text."""
    first = _mk("need_file", message="need file now")

    def fake_buddy(*_a, **_kw):
        return first

    monkeypatch.setattr(sut, "ask_ai_buddy", fake_buddy)

    patch_isfile(True)
    patch_open.fails(OSError("perm denied"))
    patch_input.push("/root/secret.sv")

    out = sut.ai_buddy_interactive("review", [])
    assert isinstance(out, Text)
    assert out.style == "red"
    assert "Failed to read file" in out.plain


def test_ai_buddy_review_result_path(monkeypatch):
    """Direct review_result should be returned as white Text."""
    rr = _mk("review_result", message="final review")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: rr)
    out = sut.ai_buddy_interactive("review", [])
    assert isinstance(out, Text)
    assert out.plain == "final review"
    assert out.style == "white"


@pytest.mark.parametrize("confirm", ["yes", "y", "Y"])
def test_ai_buddy_action_confirm_yes_returns_output(
    monkeypatch, fake_runner, fake_agent_cli, patch_input, dummy_console, confirm
):
    """
    On action token and confirmation, run the agentic CLI and show its output.
    Accepts 'yes', 'y', and uppercase 'Y' (lowercased in code).
    """
    ar = _mk("action", message="about to run", action="rtlgen")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ar)

    fake_runner.default_output = "ran rtlgen"
    patch_input.push(confirm)

    out = sut.ai_buddy_interactive("go", [])
    assert isinstance(out, Text)
    assert out.plain == "ran rtlgen"
    assert out.style == "white"

    # Console printed cyan pre-run message
    kind, text, style = dummy_console.printed[0]
    assert style == "cyan"
    assert "about to run" in text
    assert fake_runner.calls == [(fake_agent_cli, ("rtlgen",))]


def test_ai_buddy_action_confirm_yes_no_output(
    monkeypatch, fake_runner, fake_agent_cli, patch_input
):
    """Runner returns empty output → show standardized '[⚠] No output.'."""
    ar = _mk("action", message="running", action="tbgen")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ar)

    fake_runner.default_output = ""  # emulate no output
    patch_input.push("yes")

    out = sut.ai_buddy_interactive("go", [])
    assert out.plain == "[⚠] No output."
    assert out.style == "white"


@pytest.mark.parametrize("deny", ["no", "n", "NO"])
def test_ai_buddy_action_confirm_no(monkeypatch, patch_input, deny):
    """Deny confirmation → yellow 'Action cancelled.'."""
    ar = _mk("action", message="prompt", action="report")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ar)

    patch_input.push(deny)
    out = sut.ai_buddy_interactive("go", [])
    assert out.plain == "Action cancelled."
    assert out.style == "yellow"


def test_ai_buddy_action_empty_token(monkeypatch):
    """Action type with empty 'action' token → red error."""
    ar = _mk("action", message="oops", action="")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ar)
    out = sut.ai_buddy_interactive("go", [])
    assert out.plain == "Received an empty action token."
    assert out.style == "red"


def test_ai_buddy_chat_default(monkeypatch):
    """Default chat path returns white Text with the message."""
    ch = _mk("chat", message="hi there 👋")
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ch)
    out = sut.ai_buddy_interactive("hello", [])
    assert out.plain == "hi there 👋"
    assert out.style == "white"


def test_ai_buddy_missing_message_fields(monkeypatch):
    """
    Robustness: if model omits 'message', return empty white Text
    (uses dict.get default).
    """
    ch = {"type": "chat"}  # missing message
    monkeypatch.setattr(sut, "ask_ai_buddy", lambda *_a, **_kw: ch)
    out = sut.ai_buddy_interactive("hello", [])
    assert isinstance(out, type(Text("")))
    assert out.plain == ""
    assert out.style == "white"


def test_ai_buddy_need_file_retry_unexpected_type(monkeypatch, patch_input):
    """
    After need_file, retry returns a non-review_result type → red 'Unexpected
    response.' branch should fire.
    """
    first = _mk("need_file", message="need code")
    # Return a different type on retry to trigger 'Unexpected response.' path
    second = _mk("chat", message="not a review")

    calls = []

    def fake_buddy(_u, _h, file_to_review=None):
        calls.append(file_to_review)
        return first if len(calls) == 1 else second

    monkeypatch.setattr(sut, "ask_ai_buddy", fake_buddy)
    patch_input.push("literal code")
    out = sut.ai_buddy_interactive("review", [])
    assert out.style == "red"
    assert out.plain == "Unexpected response."
    # First call without code; second with supplied literal
    assert calls == [None, "literal code"]


# ---------------------------------------------------------------------------
# Internals tests
# ---------------------------------------------------------------------------

def test__read_code_from_disk_or_text_reads_file(monkeypatch):
    """Helper reads from disk if path exists; returns file contents."""
    content = "module M; endmodule"
    monkeypatch.setattr(sut.os.path, "isfile", lambda p: True)
    monkeypatch.setattr(sut, "open", lambda *a, **kw: io.StringIO(content))
    assert sut._read_code_from_disk_or_text("/tmp/file.sv") == content


def test__read_code_from_disk_or_text_inline_when_not_file(monkeypatch):
    """Helper treats non-existent path as inline literal."""
    monkeypatch.setattr(sut.os.path, "isfile", lambda p: False)
    assert sut._read_code_from_disk_or_text("inline") == "inline"


def test__invoke_agent_cli_safely_returns_output(monkeypatch):
    """Runner success path returns its .output (or empty string)."""
    class Result:
        def __init__(self, output):
            self.output = output

    class R:
        def __init__(self):
            self.calls = []

        def invoke(self, cli, args):
            self.calls.append((cli, tuple(args)))
            return Result("ok")

    runner = R()
    monkeypatch.setattr(sut, "runner", runner)
    sentinel = object()
    monkeypatch.setattr(sut, "agent_cli", sentinel)

    assert sut._invoke_agent_cli_safely(["rtlgen"]) == "ok"
    assert runner.calls == [(sentinel, ("rtlgen",))]


def test__invoke_agent_cli_safely_handles_exception(monkeypatch):
    """Any exception from runner.invoke is converted to a printable string."""
    class R:
        def invoke(self, *_a, **_kw):
            raise RuntimeError("bad")

    monkeypatch.setattr(sut, "runner", R())
    out = sut._invoke_agent_cli_safely(["report"])
    assert out.startswith("[agentic error] ")
    assert "bad" in out


# ---------------------------------------------------------------------------
# Quick action tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cmd", ["rtlgen", "tbgen", "fpropgen", "report"])
def test_run_quick_action_allowed_returns_output(cmd, fake_runner, fake_agent_cli):
    """Allowlisted commands dispatch to runner and return its output."""
    fake_runner.default_output = f"ran {cmd}"
    out = sut.run_quick_action(cmd)
    assert out == f"ran {cmd}"
    assert fake_runner.calls == [(fake_agent_cli, (cmd,))]


def test_run_quick_action_disallowed_returns_none(fake_runner, fake_agent_cli):
    """Non-allowlisted commands are ignored (return None)."""
    out = sut.run_quick_action("debug")
    assert out is None
    assert fake_runner.calls == []


def test_run_quick_action_allowed_empty_output(fake_runner, fake_agent_cli):
    """Empty runner output is preserved as empty string."""
    fake_runner.default_output = ""
    out = sut.run_quick_action("rtlgen")
    assert out == ""


def test_run_quick_action_invoke_raises_returns_error(
    monkeypatch, fake_runner, fake_agent_cli
):
    """Runner.invoke raising returns '[agentic error] ...' string."""
    def boom(*a, **kw):
        raise RuntimeError("kaboom")

    fake_runner.invoke = boom  # type: ignore[assignment]
    out = sut.run_quick_action("report")
    assert out.startswith("[agentic error] ")
    assert "kaboom" in out


def test_run_quick_action_whitespace_trim_and_case_sensitive(
    fake_runner, fake_agent_cli
):
    """
    Whitespace is trimmed, so ' rtlgen ' is allowed;
    case-sensitivity preserved: 'RTLGEN' is not allowed.
    """
    # Trimmed success
    fake_runner.default_output = "ran rtlgen"
    out = sut.run_quick_action("  rtlgen  ")
    assert out == "ran rtlgen"
    assert fake_runner.calls[-1] == (fake_agent_cli, ("rtlgen",))

    # Case-mismatch → None
    res = sut.run_quick_action("RTLGEN")
    assert res is None
