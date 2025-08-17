from __future__ import annotations

import types
from typing import Sequence
import io
import pytest
from rich.text import Text
from rich.panel import Panel

from cool_cli import shell as sut


# --------------------------
# Small utilities & stubs
# --------------------------

class _RunResult:
    def __init__(self, stdout="", stderr=""):
        self.stdout = stdout
        self.stderr = stderr


class _PopenOK:
    def __init__(self, cmd: Sequence[str], stdout=None, stderr=None, text=True):
        self.cmd = list(cmd)
        self._stdout = "OUT"
        self._stderr = ""
        self._ret = 0
    def communicate(self):
        return (self._stdout, self._stderr)


class _PopenCancel:
    def __init__(self, *a, **k): pass
    def communicate(self):
        raise KeyboardInterrupt()
    def terminate(self): pass
    def wait(self, timeout=2): pass
    def kill(self): pass


class _PopenBoom:
    def __init__(self, *a, **k): raise RuntimeError("popen bad")


@pytest.fixture()
def patch_which(monkeypatch):
    """Control PATH resolution for cmds not in SHELL_COMMANDS."""
    table = {}
    def which(cmd):
        return table.get(cmd)
    monkeypatch.setattr(sut, "shutil", types.SimpleNamespace(which=which))
    # Allow tests to program the table
    return table


@pytest.fixture()
def patch_subprocess(monkeypatch):
    ns = types.SimpleNamespace(
        run=lambda *a, **k: _RunResult(stdout="RUNOK", stderr=""),
        Popen=lambda *a, **k: _PopenOK(*a, **k),
    )
    monkeypatch.setattr(sut, "subprocess", ns)
    return ns


@pytest.fixture()
def patch_console(monkeypatch):
    class DummyConsole:
        def __init__(self): self.printed = []
        def print(self, x): self.printed.append(x)
    c = DummyConsole()
    monkeypatch.setattr(sut, "console", c)
    return c


# --------------------------
# _safe_split (internal)
# --------------------------

def test__safe_split_ok_and_empty():
    toks, err = sut._safe_split("echo hi")
    assert toks == ["echo", "hi"] and err is None
    toks2, err2 = sut._safe_split("")
    assert toks2 is None and err2 is None  # empty -> (None, None)


def test__safe_split_valueerror():
    toks, err = sut._safe_split('echo "oops')
    assert toks is None and err.startswith("[error] ")


# --------------------------
# is_unix_command
# --------------------------

def test_is_unix_command_variants(patch_which):
    patch_which.clear()
    assert sut.is_unix_command("") is False
    assert sut.is_unix_command("   ") is False
    assert sut.is_unix_command("! ls -l") is True          # alias
    assert sut.is_unix_command("cd ..") is True            # built-in
    patch_which["python3"] = "/usr/bin/python3"
    assert sut.is_unix_command("python3 -V") is True       # PATH
    assert sut.is_unix_command("unknown") is False         # not alias and not on PATH


# --------------------------
# run_shell_command
# --------------------------

def test_run_shell_command_alias_ls_keeps_only_flags(monkeypatch, patch_subprocess):
    # Track the command used by Popen
    called = {}
    def Popen(cmd, **kw):
        called["cmd"] = cmd
        return _PopenOK(cmd, **kw)
    patch_subprocess.Popen = Popen

    out = sut.run_shell_command("ls -la README.md")
    assert out == "OUT"  # from PopenOK
    # Only flag '-la' must be forwarded, not 'README.md'
    assert called["cmd"][:2] == ["ls", "-la"]
    assert "README.md" not in called["cmd"]


def test_run_shell_command_cd_success_and_failure(monkeypatch):
    # Success path
    cwd = {"val": "/home/u"}
    def chdir(path): cwd["val"] = path
    def getcwd(): return cwd["val"]
    monkeypatch.setattr(sut, "os", types.SimpleNamespace(
        chdir=chdir, getcwd=getcwd, path=types.SimpleNamespace(expanduser=lambda p: p)
    ))
    ok = sut.run_shell_command("cd /tmp")
    assert "Changed directory to /tmp" in ok

    # Failure path
    def chdir_bad(path): raise OSError("nope")
    monkeypatch.setattr(sut, "os", types.SimpleNamespace(
        chdir=chdir_bad, getcwd=getcwd, path=types.SimpleNamespace(expanduser=lambda p: p)
    ))
    bad = sut.run_shell_command("cd /bad")
    assert bad.startswith("[error]")


def test_run_shell_command_saxoflow_passthrough_uses_subprocess_run(monkeypatch, patch_subprocess):
    patch_subprocess.run = lambda *a, **k: _RunResult(stdout="A", stderr="B")
    out = sut.run_shell_command("saxoflow install")
    assert out == "AB"  # stdout + stderr concatenated


def test_run_shell_command_path_exec_success_and_cancel(monkeypatch, patch_which, patch_subprocess):
    patch_which["python3"] = "/usr/bin/python3"
    # Success
    out = sut.run_shell_command("python3 -V")
    assert out == "OUT"

    # Cancel path
    patch_subprocess.Popen = lambda *a, **k: _PopenCancel()
    out2 = sut.run_shell_command("python3 -V")
    assert out2 == "[Interrupted] Command cancelled by user."

    # Popen error
    patch_subprocess.Popen = _PopenBoom
    out3 = sut.run_shell_command("python3 -V")
    assert out3.startswith("[error] ")


def test_run_shell_command_unsupported_path_cmd(patch_which):
    patch_which.clear()
    msg = sut.run_shell_command("abcdef")
    assert msg.startswith("[error] Unsupported shell command")


# --------------------------
# dispatch_input
# --------------------------

def test_dispatch_input_editor_hint():
    out = sut.dispatch_input("nano file.v")
    assert isinstance(out, Text)
    # New behavior: hint is cyan (not yellow)
    assert out.style == "cyan"
    # Be robust to wording changes while still checking intent
    lower = out.plain.lower()
    assert ("launch editors" in lower) or ("returned from" in lower)


def test_dispatch_input_shell_escape_text_and_str(monkeypatch):
    # Case 1: handle_terminal_editor returns Text
    monkeypatch.setattr(sut, "handle_terminal_editor", lambda s: Text("ok", style="white"))
    out = sut.dispatch_input("!echo hi")
    assert isinstance(out, Text) and out.plain == "ok"

    # Case 2: handle_terminal_editor returns raw str (defensive path)
    monkeypatch.setattr(sut, "handle_terminal_editor", lambda s: "raw")
    out2 = sut.dispatch_input("!echo hi")
    assert isinstance(out2, Text) and out2.plain == "raw"


def test_dispatch_input_blank_then_unix_then_quick_action(monkeypatch, patch_which, patch_subprocess):
    # Blank
    empty = sut.dispatch_input("   ")
    assert empty.plain == ""

    # Unix command path
    patch_which["python3"] = "/usr/bin/python3"
    u = sut.dispatch_input("python3 -V")
    assert u.plain == "OUT" and u.no_wrap is False

    # Quick action path:
    # Some builds route via run_quick_action; others via handle_command.
    # Patch both so the test remains stable across refactors.
    monkeypatch.setattr(sut, "is_unix_command", lambda s: False)
    monkeypatch.setattr(sut, "run_quick_action", lambda s: "QOUT")
    monkeypatch.setattr(sut, "handle_command", lambda cmd, console: Text("QOUT"))
    q = sut.dispatch_input("rtlgen --unit alu")
    assert q.plain == "QOUT"

    # Fallback apology
    monkeypatch.setattr(sut, "run_quick_action", lambda s: None)
    monkeypatch.setattr(sut, "handle_command", lambda cmd, console: None)
    f = sut.dispatch_input("nada")
    assert "didn’t understand" in f.plain or "didn't understand" in f.plain


# --------------------------
# process_command
# --------------------------

def test_process_command_empty_and_split_error():
    # Empty
    assert sut.process_command("").plain == ""
    # Split error (unbalanced quotes)
    err = sut.process_command('echo "oops')
    assert err.style == "red" and err.plain.startswith("[error] ")


def test_process_command_cd_with_style(monkeypatch):
    # Prepare controlled os
    cwd = {"val": "/home/u"}
    def chdir(path): cwd["val"] = path
    def getcwd(): return cwd["val"]
    os_ns = types.SimpleNamespace(
        chdir=chdir,
        getcwd=getcwd,
        path=types.SimpleNamespace(expanduser=lambda p: "/home/u", isdir=lambda p: True),
    )
    monkeypatch.setattr(sut, "os", os_ns)
    out = sut.process_command("cd /tmp")
    # New behavior: cyan on success
    assert out.style == "cyan"
    assert "Changed directory to /tmp" in out.plain


def test_process_command_editor_hint_and_shell_escape(monkeypatch):
    # Editor hint (new color + wording)
    hint = sut.process_command("vim file.v")
    assert hint.style == "cyan" and (
        "launch editors" in hint.plain.lower() or "returned from" in hint.plain.lower()
    )
    # Shell escape (delegates to editors.handle_terminal_editor)
    monkeypatch.setattr(sut, "handle_terminal_editor", lambda s: Text("H", style="white"))
    esc = sut.process_command("!echo hi")
    assert esc.plain == "H"


def test_process_command_saxoflow_init_env_message():
    out = sut.process_command("saxoflow init-env")
    assert out.style == "yellow"
    assert "Interactive environment setup is not supported" in out.plain


def test_process_command_saxoflow_passthrough_sets_env(monkeypatch):
    captured = {}
    def run(args, capture_output=True, text=True, env=None):
        captured["args"] = args
        captured["env"] = env
        return _RunResult(stdout="X", stderr="Y")
    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(run=run))
    # shlex.split is used; verify args
    out = sut.process_command("saxoflow install")
    assert out.style == "white"
    assert out.plain == "XY"
    assert captured["args"] == ["saxoflow", "install"]
    assert captured["env"]["SAXOFLOW_FORCE_HEADLESS"] == "1"


def test_process_command_generic_supported_and_fallback(monkeypatch, patch_which, patch_subprocess, patch_console):
    # Generic supported command via alias/PATH → run_shell_command
    out = sut.process_command("ls -l")
    assert out.style == "white"
    assert out.plain == "OUT"

    # PATH-based
    patch_which["python3"] = "/usr/bin/python3"
    out2 = sut.process_command("python3 -V")
    assert out2.plain == "OUT"

    # Fallback to handle_command: return Panel or Text should pass through
    def handle_command(cmd, console):
        return Panel.fit(Text(f"handled:{cmd}"))
    monkeypatch.setattr(sut, "handle_command", handle_command)
    fb = sut.process_command("help")
    assert isinstance(fb, Panel)
    assert "handled:help" in str(fb.renderable)
