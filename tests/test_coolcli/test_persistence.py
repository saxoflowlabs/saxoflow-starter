# # tests/test_coolcli/test_persistence.py
# from __future__ import annotations

# import json
# import os
# import types
# import io
# import pytest
# from rich.text import Text

# from cool_cli import persistence as sut


# # -----------------------
# # Shared state fixture
# # -----------------------

# @pytest.fixture()
# def fresh_state(monkeypatch):
#     """
#     Replace sut._state with a fresh, lightweight namespace so tests don't rely on
#     the real module-level globals. This keeps tests hermetic and independent.
#     """
#     ns = types.SimpleNamespace(
#         conversation_history=[],
#         attachments=[],
#         system_prompt="",
#         config={"keep": 1, "default_only": True},
#     )
#     monkeypatch.setattr(sut, "_state", ns, raising=True)
#     return ns


# # -----------------------
# # Helpers to patch isfile/open on SUT path
# # -----------------------

# @pytest.fixture()
# def patch_isfile(monkeypatch):
#     def _set(value: bool):
#         monkeypatch.setattr(sut.os.path, "isfile", lambda p: value, raising=True)
#     return _set


# @pytest.fixture()
# def chdir_tmp(monkeypatch, tmp_path):
#     """Switch CWD for tests that rely on default filenames."""
#     monkeypatch.chdir(tmp_path)
#     return tmp_path


# # -----------------------
# # attach_file
# # -----------------------

# def test_attach_file_requires_path(fresh_state):
#     out = sut.attach_file("")
#     assert out.style == "bold red"
#     assert "requires a file path" in out.plain


# def test_attach_file_not_found(patch_isfile, fresh_state):
#     patch_isfile(False)
#     out = sut.attach_file("/no/such/file.bin")
#     assert out.style == "bold red"
#     assert "File not found" in out.plain
#     assert fresh_state.attachments == []


# def test_attach_file_success_reads_bytes(tmp_path, monkeypatch, patch_isfile, fresh_state):
#     f = tmp_path / "note.txt"
#     data = b"hello world"
#     f.write_bytes(data)
#     patch_isfile(True)
#     # Use real open (safe with tmp_path)
#     out = sut.attach_file(str(f))
#     assert out.style == "cyan"
#     assert "Attached note.txt" in out.plain
#     assert len(fresh_state.attachments) == 1
#     att = fresh_state.attachments[0]
#     assert att["name"] == "note.txt"
#     assert att["content"] == data


# def test_attach_file_open_failure(monkeypatch, patch_isfile, fresh_state, tmp_path):
#     f = tmp_path / "x.bin"
#     f.write_bytes(b"123")
#     patch_isfile(True)

#     def boom(*a, **k):
#         raise OSError("perm denied")
#     # Patch open on SUT import path
#     monkeypatch.setattr(sut, "open", boom, raising=True)

#     out = sut.attach_file(str(f))
#     assert out.style == "bold red"
#     assert "Failed to attach file" in out.plain
#     assert "perm denied" in out.plain
#     assert fresh_state.attachments == []


# # -----------------------
# # save_session
# # -----------------------

# def test_save_session_success_writes_json(tmp_path, fresh_state):
#     fresh_state.conversation_history.extend([
#         {"user": "hi", "assistant": "there"},
#         {"user": "u2", "assistant": "a2"},
#     ])
#     fresh_state.attachments.extend([
#         {"name": "a.txt", "content": b"AAA"},
#         {"name": "b.v", "content": b"BBB"},
#     ])
#     fresh_state.system_prompt = "SYS"
#     fresh_state.config.update({"new": 2})

#     out_file = tmp_path / "sess.json"
#     res = sut.save_session(str(out_file))
#     assert res.style == "cyan"
#     assert "Session saved to" in res.plain

#     data = json.loads(out_file.read_text(encoding="utf-8"))
#     assert data["conversation_history"] == fresh_state.conversation_history
#     # attachments must only have 'name'
#     assert data["attachments"] == [{"name": "a.txt"}, {"name": "b.v"}]
#     assert data["system_prompt"] == "SYS"
#     # config copied as-is
#     for k in ("keep", "default_only", "new"):
#         assert k in data["config"]


# def test_save_session_default_filename_when_falsey(chdir_tmp, fresh_state):
#     # Using CWD -> default filename session.json
#     res = sut.save_session("")
#     assert res.style == "cyan"
#     assert (chdir_tmp / "session.json").exists()


# def test_save_session_open_raises_returns_bold_red(monkeypatch, fresh_state, tmp_path):
#     def boom(*a, **k):
#         raise OSError("read-only fs")
#     monkeypatch.setattr(sut, "open", boom, raising=True)
#     res = sut.save_session(str(tmp_path / "x.json"))
#     assert res.style == "bold red"
#     assert "Failed to save session" in res.plain
#     assert "read-only fs" in res.plain


# # -----------------------
# # load_session
# # -----------------------

# def test_load_session_requires_filename(fresh_state):
#     res = sut.load_session("")
#     assert res.style == "bold red"
#     assert "requires a filename" in res.plain


# def test_load_session_file_not_found(patch_isfile, fresh_state):
#     patch_isfile(False)
#     res = sut.load_session("/nope.json")
#     assert res.style == "bold red"
#     assert "Session file not found" in res.plain


# def test_load_session_success_mutates_in_place(tmp_path, monkeypatch, patch_isfile, fresh_state):
#     # Prepare initial objects to verify in-place mutation (identities preserved)
#     conv = fresh_state.conversation_history
#     atts = fresh_state.attachments
#     cfg = fresh_state.config

#     # Create a source JSON with history, attachment names only, new prompt and config
#     src = {
#         "conversation_history": [
#             {"user": "hello", "assistant": "ok"},
#             {"user": "bye", "assistant": "ok2"},
#         ],
#         "attachments": [{"name": "doc.md"}, {"name": "wave.vcd"}],
#         "system_prompt": "NEW_PROMPT",
#         "config": {"new": 3, "keep": 9},  # 'keep' should override value, others preserved
#     }
#     p = tmp_path / "in.json"
#     p.write_text(json.dumps(src), encoding="utf-8")

#     patch_isfile(True)  # file exists

#     res = sut.load_session(str(p))
#     assert res.style == "cyan"
#     assert "Session loaded from" in res.plain

#     # Identities unchanged (in-place mutation)
#     assert fresh_state.conversation_history is conv
#     assert fresh_state.attachments is atts
#     assert fresh_state.config is cfg

#     # Content updated from file
#     assert fresh_state.conversation_history == src["conversation_history"]
#     # Attachments names only, with empty bytes
#     assert fresh_state.attachments == [
#         {"name": "doc.md", "content": b""},
#         {"name": "wave.vcd", "content": b""},
#     ]
#     # System prompt updated
#     assert fresh_state.system_prompt == "NEW_PROMPT"
#     # Config merged/updated, not replaced:
#     # - 'keep' value updated to 9
#     # - 'new' added
#     # - existing 'default_only' preserved
#     assert fresh_state.config["keep"] == 9
#     assert fresh_state.config["new"] == 3
#     assert fresh_state.config["default_only"] is True


# def test_load_session_open_or_json_error_returns_bold_red(tmp_path, monkeypatch, patch_isfile, fresh_state):
#     # Case 1: open raises
#     patch_isfile(True)
#     def boom_open(*a, **k):
#         raise OSError("cant read")
#     monkeypatch.setattr(sut, "open", boom_open, raising=True)
#     out = sut.load_session(str(tmp_path / "bad.json"))
#     assert out.style == "bold red"
#     assert "Failed to load session" in out.plain
#     assert "cant read" in out.plain

#     # Case 2: json.load raises
#     def ok_open(*a, **k):
#         # Provide a file-like object with invalid JSON
#         return io.StringIO("{ invalid json ")
#     monkeypatch.setattr(sut, "open", ok_open, raising=True)
#     out2 = sut.load_session(str(tmp_path / "bad2.json"))
#     assert out2.style == "bold red"
#     assert "Failed to load session" in out2.plain


# # -----------------------
# # clear_history / set_system_prompt
# # -----------------------

# def test_clear_history_empties_lists_and_returns_light_cyan(fresh_state):
#     fresh_state.conversation_history[:] = [{"user": "x"}]
#     fresh_state.attachments[:] = [{"name": "a", "content": b"1"}]
#     res = sut.clear_history()
#     assert res.style == "light cyan"
#     assert fresh_state.conversation_history == []
#     assert fresh_state.attachments == []


# def test_set_system_prompt_sets_and_clears(fresh_state):
#     res1 = sut.set_system_prompt("   hello world  ")
#     assert res1.style == "cyan"
#     assert fresh_state.system_prompt == "hello world"

#     res2 = sut.set_system_prompt("  ")  # clears when empty after strip
#     assert res2.style == "yellow"
#     assert fresh_state.system_prompt == ""
