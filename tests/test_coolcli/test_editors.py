# # tests/test_coolcli/test_editors.py
# from __future__ import annotations

# import types
# import pytest
# from rich.text import Text

# from cool_cli import editors as sut


# # -----------------------
# # _safe_shlex_split
# # -----------------------

# @pytest.mark.parametrize(
#     "raw, expected",
#     [
#         ("nano file.v", ["nano", "file.v"]),
#         ("", None),
#         ("   ", None),
#     ],
# )
# def test_safe_shlex_split_basic(raw, expected):
#     assert sut._safe_shlex_split(raw) == expected


# def test_safe_shlex_split_unbalanced_quotes_returns_none(monkeypatch):
#     # shlex.split will raise ValueError; ensure we swallow and return None
#     assert sut._safe_shlex_split('nano "file.v') is None


# # -----------------------
# # _first_token
# # -----------------------

# @pytest.mark.parametrize(
#     "cmd, token",
#     [
#         ("nano file.v", "nano"),
#         ("!vim path/to.v", "vim"),
#         ("   vi   file", "vi"),
#         ("!", ""),
#         ("   ", ""),
#         ("", ""),
#     ],
# )
# def test_first_token_variants(cmd, token):
#     assert sut._first_token(cmd) == token


# # -----------------------
# # is_blocking_editor_command / is_terminal_editor
# # -----------------------

# def test_is_blocking_editor_command_handles_bang_prefix_and_non_blocking():
#     assert sut.is_blocking_editor_command("nano x") is True
#     assert sut.is_blocking_editor_command("!vim y") is True
#     assert sut.is_blocking_editor_command("code z") is False


# def test_is_terminal_editor_true_for_both_editor_sets_and_false_other():
#     assert sut.is_terminal_editor("vim x") is True
#     assert sut.is_terminal_editor("!code y") is True
#     assert sut.is_terminal_editor("cat z") is False


# # -----------------------
# # handle_terminal_editor: blocking editors
# # -----------------------

# def test_handle_blocking_editor_with_prompt_toolkit_app(monkeypatch):
#     calls = {"suspend": 0, "os_system": None}

#     # Stub get_app_or_none to return an app with suspend_to_background
#     class App:
#         def suspend_to_background(self, func):
#             calls["suspend"] += 1
#             # Must invoke the provided function so os.system path is exercised
#             func()

#     monkeypatch.setattr(sut, "get_app_or_none", lambda: App())

#     # Capture os.system call
#     def fake_system(cmd):
#         calls["os_system"] = cmd
#         return 0

#     monkeypatch.setattr(sut, "os", types.SimpleNamespace(system=fake_system))

#     out = sut.handle_terminal_editor("nano file.v")
#     assert isinstance(out, Text)
#     assert out.style == "cyan"
#     assert "Returned from nano" in out.plain
#     assert calls["suspend"] == 1
#     assert calls["os_system"] == "nano file.v"


# def test_handle_blocking_editor_without_app(monkeypatch):
#     # No app available
#     monkeypatch.setattr(sut, "get_app_or_none", lambda: None)

#     called = {"cmd": None}
#     monkeypatch.setattr(
#         sut, "os", types.SimpleNamespace(system=lambda c: called.__setitem__("cmd", c))
#     )

#     out = sut.handle_terminal_editor("vi file.v")
#     assert out.style == "cyan"
#     assert "Returned from vi" in out.plain
#     assert called["cmd"] == "vi file.v"


# # -----------------------
# # handle_terminal_editor: non-blocking GUI editors
# # -----------------------

# def test_handle_nonblocking_editor_launch_success(monkeypatch):
#     class P:
#         def __init__(self, *a, **k): pass

#     monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=P))
#     out = sut.handle_terminal_editor("code file.v")
#     assert out.style == "cyan"
#     assert "Launched code in background" in out.plain


# def test_handle_nonblocking_editor_launch_failure(monkeypatch):
#     def boom(*a, **k):
#         raise OSError("no display")
#     monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(Popen=boom))
#     out = sut.handle_terminal_editor("subl file.v")
#     assert out.style == "red"
#     assert "Failed to launch subl" in out.plain
#     assert "no display" in out.plain


# # -----------------------
# # handle_terminal_editor: sync command (non-editor)
# # -----------------------

# class RunResult:
#     def __init__(self, stdout="", stderr=""):
#         self.stdout = stdout
#         self.stderr = stderr


# @pytest.mark.parametrize(
#     "stdout, stderr, expected",
#     [
#         ("OUT\n", "", "OUT\n"),
#         ("", "ERR\n", "ERR\n"),
#         ("", "", ""),  # both empty -> empty Text (white)
#     ],
# )
# def test_handle_sync_command_returns_combined_output(monkeypatch, stdout, stderr, expected):
#     def run(tokens, capture_output=True, text=True):
#         assert tokens == ["echo", "hi"]  # tokenization preserved
#         return RunResult(stdout=stdout, stderr=stderr)

#     monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(run=run))
#     out = sut.handle_terminal_editor("echo hi")
#     assert out.style == "white"
#     assert out.plain == expected


# def test_handle_sync_command_exception_to_readable_error(monkeypatch):
#     def run(*a, **k):
#         raise RuntimeError("boom")
#     monkeypatch.setattr(sut, "subprocess", types.SimpleNamespace(run=run))
#     out = sut.handle_terminal_editor("echo hi")
#     assert out.style == "red"
#     assert "Shell error" in out.plain
#     assert "boom" in out.plain


# # -----------------------
# # handle_terminal_editor: bad/empty commands
# # -----------------------

# def test_handle_terminal_editor_unbalanced_quotes(monkeypatch):
#     # Causes _safe_shlex_split to return None, and since non-empty -> "Bad command"
#     out = sut.handle_terminal_editor('echo "oops')
#     assert out.style == "red"
#     assert "Bad command" in out.plain


# def test_handle_terminal_editor_empty_string(monkeypatch):
#     out = sut.handle_terminal_editor("   ")
#     assert out.style == "red"
#     assert "No command specified" in out.plain
