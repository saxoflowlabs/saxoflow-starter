# tests/test_coolcli/test_exporters.py
from __future__ import annotations

import io
import os
import types
import pytest
from rich.text import Text
from rich.markdown import Markdown

from cool_cli import exporters as sut


# --------
# Fixtures
# --------

@pytest.fixture()
def reset_state(monkeypatch):
    """
    Give each test a fresh conversation_history and system_prompt on the
    module-under-test import path.
    """
    monkeypatch.setattr(sut, "conversation_history", [], raising=True)
    monkeypatch.setattr(sut, "system_prompt", "", raising=True)
    return sut.conversation_history


# -------------
# Internal helper
# -------------


def test__assistant_to_str_variants(reset_state):
    # Text -> .plain
    t = Text("hello <not-markup>")
    assert sut._assistant_to_str(t) == "hello <not-markup>"

    # Markdown -> .text (raw markdown)
    m = Markdown("# Title\n**bold** text")
    assert sut._assistant_to_str(m) == "# Title\n**bold** text"

    # Fallback -> str()
    class X:
        def __str__(self):
            return "repr(X)"
    assert sut._assistant_to_str(X()) == "repr(X)"


# -----------------
# export_markdown()
# -----------------

def test_export_markdown_success_with_explicit_path(tmp_path, reset_state, monkeypatch):
    # Arrange conversation with mixed content types
    sut.system_prompt = "SYS_PROMPT"
    sut.conversation_history.extend([
        {"user": "hello world", "assistant": Text("plain text resp")},
        {"user": "show me *md*", "assistant": Markdown("**md-bold** and _italics_")},
        {"user": "obj?", "assistant": 123},  # non-rich object -> str(123)
    ])
    out = tmp_path / "out.md"

    # Act
    res = sut.export_markdown(str(out))

    # Assert result Text
    assert isinstance(res, Text)
    assert res.style == "cyan"
    assert str(out) in res.plain

    # Assert file contents
    content = out.read_text(encoding="utf-8")
    # System prompt header first
    assert "## System Prompt" in content and "SYS_PROMPT" in content
    # Three turns, each with headers
    assert content.count("### User") == 3
    assert content.count("### Assistant") == 3
    # Assistant normalization rules were applied
    assert "plain text resp" in content
    assert "**md-bold** and _italics_" in content  # Markdown .text
    assert "123" in content


def test_export_markdown_default_filename_when_falsey(tmp_path, reset_state, monkeypatch):
    # Use tmp_path as CWD so default path is predictable
    monkeypatch.chdir(tmp_path)
    sut.conversation_history.append({"user": "u", "assistant": Text("a")})

    res = sut.export_markdown("")  # falsey filename triggers default
    assert isinstance(res, Text)
    assert res.style == "cyan"
    assert "conversation.md" in res.plain

    data = (tmp_path / "conversation.md").read_text(encoding="utf-8")
    assert "### User" in data and "### Assistant" in data
    assert "u" in data and "a" in data


def test_export_markdown_open_raises_returns_red_text(monkeypatch, reset_state, tmp_path):
    # Force open() on the SUT import path to fail
    def boom(*a, **k):
        raise OSError("perm denied")
    monkeypatch.setattr(sut, "open", boom, raising=True)

    res = sut.export_markdown(str(tmp_path / "x.md"))
    assert isinstance(res, Text)
    assert res.style == "red"
    assert "Failed to export conversation" in res.plain
    assert "perm denied" in res.plain


# -----------
# get_stats()
# -----------

def test_get_stats_counts_user_and_assistant_tokens(reset_state):
    # Tokens counted via whitespace split after normalization
    # Turn 1: user (3 tokens), assistant Text (2 tokens)
    # Turn 2: user unicode (2 tokens), assistant Markdown ".text" (3 tokens)
    # Turn 3: user empty (0), assistant plain str (4 tokens)
    sut.conversation_history.extend([
        {"user": "this has three", "assistant": Text("two words")},
        {"user": "hé là", "assistant": Markdown("alpha beta gamma")},
        {"user": "", "assistant": "four tokens right here"},
    ])
    out = sut.get_stats()
    assert isinstance(out, Text)
    assert out.style == "light cyan"
    # total = 3 + 2 + 2 + 3 + 0 + 4 = 14
    assert "Approx token count: 14" in out.plain
    assert "ignoring attachments" in out.plain
