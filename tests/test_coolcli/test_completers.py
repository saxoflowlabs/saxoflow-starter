# # tests/test_coolcli/test_completers.py
# from __future__ import annotations

# from typing import Iterable, List, Optional
# import types
# import pytest

# from prompt_toolkit.document import Document
# from cool_cli import completers as sut


# class DummyFuzzy:
#     """Minimal stand-in for FuzzyWordCompleter."""
#     def __init__(self, words: Iterable[str]):
#         self.words = list(words)  # capture for assertions
#         self.last_document: Optional[Document] = None
#         self.raise_on_complete = False

#     def get_completions(self, document, complete_event):
#         if self.raise_on_complete:
#             raise RuntimeError("fuzzy boom")
#         self.last_document = document
#         text = document.text_before_cursor
#         # Simple filter: any word containing the typed text
#         for w in self.words:
#             if text.lower() in w.lower():
#                 yield sut.Completion(text=w, start_position=-len(text))


# class DummyPath:
#     """Minimal stand-in for PathCompleter."""
#     def __init__(self, expanduser: bool = False, **_kw):
#         self.expanduser = expanduser
#         self.last_document: Optional[Document] = None
#         self.raise_on_complete = False
#         # Provided suggestions (suffixes) to yield when called
#         self.suggestions: List[tuple[str, str]] = [("a", ""), ("b", "")]  # (text, meta)

#     def get_completions(self, document, complete_event):
#         if self.raise_on_complete:
#             raise RuntimeError("path boom")
#         self.last_document = document
#         for text, meta in self.suggestions:
#             yield sut.Completion(text=text, display=text, display_meta=meta)


# @pytest.fixture()
# def patch_completer_classes(monkeypatch):
#     """Patch the classes used by the SUT before constructing HybridShellCompleter."""
#     monkeypatch.setattr(sut, "FuzzyWordCompleter", DummyFuzzy)
#     monkeypatch.setattr(sut, "PathCompleter", DummyPath)
#     return DummyFuzzy, DummyPath


# def _collect_texts(iterable):
#     return [c.text for c in iterable]


# def test_command_completion_no_space_happy(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["help", "quit", "ls"])
#     doc = Document(text="he", cursor_position=2)
#     out = list(comp.get_completions(doc, complete_event=None))
#     assert _collect_texts(out) == ["help"]  # "he" matches only "help"


# def test_command_completion_cursor_before_first_space(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["help", "hello", "quit"])
#     # There is a space at pos 5, but cursor at pos 2 => still command mode
#     doc = Document(text="help now", cursor_position=2)
#     out = list(comp.get_completions(doc, complete_event=None))
#     # "he" matches "help" and "hello"
#     assert _collect_texts(out) == ["help", "hello"]


# def test_path_completion_wraps_suffix_and_uses_start_position(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["run"])
#     # After first space -> path mode; fragment is "fi"
#     doc = Document(text="run fi", cursor_position=6)

#     # Access the inner path completer to control suggestions
#     path_inner: DummyPath = comp.path_completer  # type: ignore[assignment]
#     path_inner.suggestions = [("le1", "META1"), ("le2", "META2")]  # suffixes

#     out = list(comp.get_completions(doc, complete_event=None))
#     texts = _collect_texts(out)
#     assert texts == ["file1", "file2"]  # fragment "fi" + suffixes

#     # start_position must replace exactly the fragment length
#     for c in out:
#         assert c.start_position == -2  # len("fi") == 2
#         assert c.display_text in ("file1", "file2")
#         # display_meta should be propagated
#         assert c.display_meta_text in ("META1", "META2")

#     # The inner path completer should have received a Document whose text is the fragment
#     assert path_inner.last_document is not None
#     assert path_inner.last_document.text == "fi"
#     assert path_inner.last_document.cursor_position == 2


# def test_commands_iterable_is_materialized(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes

#     src = ["help", "quit"]
#     comp = sut.HybridShellCompleter(commands=(x for x in src))
#     # mutate the original list after construction to ensure freezing at init
#     src.append("newcmd")

#     fuzzy_inner: DummyFuzzy = comp.command_completer  # type: ignore[assignment]
#     assert fuzzy_inner.words == ["help", "quit"]  # not affected by later mutation


# def test_command_completer_exception_is_swallowed(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["help"])

#     # Force exception
#     fuzzy_inner: DummyFuzzy = comp.command_completer  # type: ignore[assignment]
#     fuzzy_inner.raise_on_complete = True

#     doc = Document(text="h", cursor_position=1)
#     out = list(comp.get_completions(doc, complete_event=None))
#     assert out == []  # swallowed


# def test_path_completer_exception_is_swallowed(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["run"])

#     path_inner: DummyPath = comp.path_completer  # type: ignore[assignment]
#     path_inner.raise_on_complete = True

#     doc = Document(text="run x", cursor_position=5)
#     out = list(comp.get_completions(doc, complete_event=None))
#     assert out == []  # swallowed


# def test_path_completer_expanduser_true(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["run"])
#     path_inner: DummyPath = comp.path_completer  # type: ignore[assignment]
#     assert path_inner.expanduser is True  # created with expanduser=True


# def test_unicode_input(monkeypatch, patch_completer_classes):
#     DummyFuzzy, DummyPath = patch_completer_classes
#     comp = sut.HybridShellCompleter(commands=["héllo", "hélène", "quit"])
#     doc = Document(text="hé", cursor_position=2)
#     out = list(comp.get_completions(doc, complete_event=None))
#     assert _collect_texts(out) == ["héllo", "hélène"]
