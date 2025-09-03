from __future__ import annotations

import types
from typing import Sequence
import io
import pytest
from rich.text import Text
from rich.panel import Panel
import json
from pathlib import Path
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
    # New behavior: returns a recap Panel (yellow SaxoFlow-style panel)
    assert isinstance(out, Panel)

    # Body text varies depending on whether a tools file exists:
    # - "No saved tool selection..." (when interactive wizard aborts in CI/TTY-less env)
    # - "You selected these tools..." (when a selection file exists)
    body = str(out.renderable).lower()
    assert ("no saved tool selection" in body) or ("you selected these tools" in body)


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


def test_extract_artifact_text_empty_and_passthrough():
    # empty -> early return
    assert sut._extract_artifact_text("") == ""
    # no markers -> returns original
    s = "plain output"
    assert sut._extract_artifact_text(s) == s


def test_extract_artifact_text_fenced_code_block():
    src = "pre\n```verilog\nCODE\n```\npost"
    assert sut._extract_artifact_text(src) == "CODE"


def test_extract_artifact_text_module_property_package():
    mod = "noise\nmodule foo; endmodule\ntrail"
    assert sut._extract_artifact_text(mod) == "module foo; endmodule"

    prop = "blah\nproperty p; endproperty\nzz"
    assert sut._extract_artifact_text(prop) == "property p; endproperty"

    pkg = "aaa\npackage p; endpackage\nbbb"
    assert sut._extract_artifact_text(pkg) == "package p; endpackage"


def test_is_agentic_generation_passthrough_true_and_false():
    assert sut._is_agentic_generation_passthrough(["saxoflow", "agenticai", "rtlgen"]) is True
    assert sut._is_agentic_generation_passthrough(["saxoflow", "agenticai", "report"]) is False
    assert sut._is_agentic_generation_passthrough([]) is False           # not parts
    assert sut._is_agentic_generation_passthrough(["echo"]) is False     # first != saxoflow


def test_is_interactive_init_env_cmd_variants():
    # True: saxoflow init-env with no flags
    assert sut._is_interactive_init_env_cmd(["saxoflow", "init-env"]) is True
    # False: not saxoflow
    assert sut._is_interactive_init_env_cmd(["echo", "hi"]) is False
    # False: preset or headless present
    assert sut._is_interactive_init_env_cmd(["saxoflow", "init-env", "--preset", "full"]) is False
    assert sut._is_interactive_init_env_cmd(["saxoflow", "init-env", "--headless"]) is False


class _PopenCancelWaitError:
    def __init__(self, *a, **k):
        self.kill_called = False
    def communicate(self):
        raise KeyboardInterrupt()
    def terminate(self): pass
    def wait(self, timeout=2):
        raise RuntimeError("wait fail")   # forces inner except -> kill()
    def kill(self):
        self.kill_called = True


def test__run_subprocess_popen_cancel_kill(monkeypatch):
    ns = type("NS", (), {"PIPE": object(), "Popen": lambda *a, **k: _PopenCancelWaitError()})
    monkeypatch.setattr(sut, "subprocess", ns)
    out = sut._run_subprocess_popen(["python3", "-V"])
    assert out == "[Interrupted] Command cancelled by user."
    # We can’t access the instance directly, but the codepath is now covered.


def test__read_tools_file_nonexistent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert sut._read_tools_file() == []  # no file -> []


def test__read_tools_file_list_and_nonlist_and_invalid(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p = Path(".saxoflow_tools.json")

    # valid list
    p.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert sut._read_tools_file() == ["a", "b"]

    # non-list -> []
    p.write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert sut._read_tools_file() == []

    # invalid json -> []
    p.write_text("{not json}", encoding="utf-8")
    assert sut._read_tools_file() == []


def test__summary_panel_no_tools_and_with_tools(tmp_path, monkeypatch):
    from rich.panel import Panel

    # No file -> "No saved..."
    monkeypatch.chdir(tmp_path)
    panel = sut._summary_panel()
    assert isinstance(panel, Panel)
    assert "No saved tool selection" in panel.renderable.plain

    # File with list -> "You selected..."
    (tmp_path / ".saxoflow_tools.json").write_text('["toolA","toolB"]', encoding="utf-8")
    panel2 = sut._summary_panel()
    assert "You selected these tools" in panel2.renderable.plain


def test_requires_raw_tty_variants(monkeypatch):
    # interactive init-env
    assert sut.requires_raw_tty("saxoflow init-env") is True

    # direct editor
    monkeypatch.setattr(sut, "_editor_hint_set", lambda: ("nano",))
    assert sut.requires_raw_tty("nano file") is True

    # shell '!' editor
    monkeypatch.setattr(sut, "_editor_hint_set", lambda: ("vi",))
    assert sut.requires_raw_tty("! vi file") is True

    # shell '!' saxoflow init-env
    assert sut.requires_raw_tty("! saxoflow init-env") is True

    # shell '!' non-editor → False
    monkeypatch.setattr(sut, "_editor_hint_set", lambda: ())
    assert sut.requires_raw_tty("! ls -l") is False

    # default → False
    assert sut.requires_raw_tty("echo ok") is False


def test_run_shell_command_alias_non_ls_base(monkeypatch):
    # Use a custom alias not in ('ls','ll') so the "else: cmd = base_cmd" runs
    monkeypatch.setattr(sut, "SHELL_COMMANDS", {"foo": ("foo_base",)})
    captured = {}
    class _P:
        def __init__(self, cmd, **kw): captured["cmd"] = cmd
        def communicate(self): return ("OUT", "")
    ns = type("NS", (), {"PIPE": object(), "Popen": _P})
    monkeypatch.setattr(sut, "subprocess", ns)
    out = sut.run_shell_command("foo arg1 arg2")
    assert out == "OUT"
    assert captured["cmd"] == ["foo_base"]  # args not forwarded for generic alias


def test_run_shell_command_saxoflow_init_env_success_and_error(monkeypatch, tmp_path):
    # Success: returns "" and prints a recap panel
    prints = []
    monkeypatch.setattr(sut, "console", type("C", (), {"print": lambda self, x: prints.append(x)})())
    monkeypatch.setattr(sut, "subprocess", type("NS", (), {"run": lambda *a, **k: None}))
    out = sut.run_shell_command("saxoflow init-env")
    assert out == ""
    assert any(isinstance(p, Panel) for p in prints), "recap Panel not printed"

    # Error: subprocess.run raises -> error string
    def boom(*a, **k): raise RuntimeError("fail")
    monkeypatch.setattr(sut, "subprocess", type("NS", (), {"run": boom}))
    err = sut.run_shell_command("saxoflow init-env")
    assert err.startswith("[error] Failed to run saxoflow CLI: ")


def test_dispatch_input_agentic_returns_panel_stringified(monkeypatch):
    from rich.panel import Panel
    monkeypatch.setattr(sut, "handle_command", lambda cmd, c: Panel.fit(Text("PANEL")))
    out = sut.dispatch_input("rtlgen")
    assert isinstance(out, Text)
    # str(Panel) => "<rich.panel.Panel object at 0x...>"
    assert "rich.panel.Panel" in out.plain


def test_dispatch_input_no_llm_key_red_guard(monkeypatch):
    # Force free-text path (not agentic, not editor, not unix command)
    monkeypatch.setattr(sut, "is_unix_command", lambda s: False)
    monkeypatch.setattr(sut, "_ensure_llm_key_before_agent", lambda c: False)
    monkeypatch.setattr(sut, "run_quick_action", lambda s: None)

    out = sut.dispatch_input("free text")
    assert isinstance(out, Text)
    assert out.style == "bold red"
    assert "no llm api key" in out.plain.lower()


def test_process_command_saxoflow_run_error(monkeypatch):
    def boom(*a, **k): raise OSError("bad")
    monkeypatch.setattr(sut, "subprocess", type("NS", (), {"run": boom}))
    out = sut.process_command("saxoflow diagnose")
    assert isinstance(out, Text)
    assert out.style == "red" and "Failed to run saxoflow CLI" in out.plain


def test_run_shell_command_empty_parts_is_empty():
    assert sut.run_shell_command("   ") == ""


def test_process_command_saxoflow_agentic_generation_extracts(monkeypatch):
    # Make the saxoflow call return a fenced code block → extraction branch
    def run(args, capture_output=True, text=True, env=None):
        return _RunResult(stdout="before\n```verilog\nART_ONLY\n```\nafter", stderr="")
    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(run=run))
    out = sut.process_command("saxoflow agenticai rtlgen")
    assert isinstance(out, Text)
    assert out.plain == "ART_ONLY"


def test_process_command_saxoflow_init_env_error(monkeypatch):
    # Hit the init-env try/except (error path)
    def boom(*a, **k): raise RuntimeError("init-fail")
    monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(run=boom))
    out = sut.process_command("saxoflow init-env")
    assert isinstance(out, Text) and out.style == "red"
    assert "Failed to run saxoflow CLI" in out.plain


def test_process_command_agentic_delegates(monkeypatch):
    # Parts[0] in _AGENTIC_COMMANDS → early return from handle_command
    monkeypatch.setattr(sut, "handle_command", lambda cmd, c: Text("AGENT_ROUTE", style="white"))
    out = sut.process_command("rtlgen")
    assert isinstance(out, Text) and out.plain == "AGENT_ROUTE"


def test_dispatch_input_quick_action_non_agentic(monkeypatch):
    # Force free-text path and make run_quick_action return a value
    monkeypatch.setattr(sut, "is_unix_command", lambda s: False)
    monkeypatch.setattr(sut, "_ensure_llm_key_before_agent", lambda c: True)
    monkeypatch.setattr(sut, "run_quick_action", lambda s: "QACT")
    out = sut.dispatch_input("please make an adder")
    assert isinstance(out, Text) and out.plain == "QACT"


def test_dispatch_input_editor_returns_str(monkeypatch):
    # Editors block: when handle_terminal_editor returns str → wrap into Text
    monkeypatch.setattr(sut, "_editor_hint_set", lambda: ("nano",))
    monkeypatch.setattr(sut, "handle_terminal_editor", lambda s: "RAW-EDITOR-RESULT")
    out = sut.dispatch_input("nano file.v")
    assert isinstance(out, Text) and out.plain == "RAW-EDITOR-RESULT"


def test_run_shell_command_agentic_extract(monkeypatch):
    # run_shell_command → saxoflow agenticai rtlgen → extraction branch
    monkeypatch.setattr(sut, "_run_subprocess_run", lambda parts: "xxx```sv\nG\n```yyy")
    out = sut.run_shell_command("saxoflow agenticai rtlgen --foo")
    assert out == "G"


def test_run_shell_command_split_error():
    # err, _ = _safe_split(...) path → immediate error return
    msg = sut.run_shell_command('echo "unbalanced')
    assert msg.startswith("[error] ")


def test_run_shell_command_saxoflow_run_raises(monkeypatch):
    # _run_subprocess_run catches subprocess.run exception and returns error string
    ns = types.SimpleNamespace(run=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(sut, "subprocess", ns)
    msg = sut.run_shell_command("saxoflow install")
    assert msg.startswith("[error] Failed to run saxoflow CLI:")