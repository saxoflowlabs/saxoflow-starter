from __future__ import annotations

"""
Tests for cool_cli.bootstrap

This suite is hermetic and defect-oriented:
- Exercises public APIs: ensure_first_run_setup, run_key_setup_wizard
- Covers internal helpers for stability/regression
- Mocks all external effects: filesystem, stdin/TTY, dotenv, provider discovery
"""

from types import SimpleNamespace, ModuleType
from typing import Dict, List, Tuple
import importlib
import os
import sys

import pytest
from rich.panel import Panel
from rich.text import Text


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _fresh_module():
    """Reload the SUT to pick up monkeypatch changes for import-based code paths."""
    import cool_cli.bootstrap as sut
    return importlib.reload(sut)


def _fake_model_selector_module(provider: str, env_var: str) -> ModuleType:
    """
    Create a fake saxoflow_agenticai.core.model_selector module with:
    - ModelSelector.get_provider_and_model -> (provider, "dummy-model")
    - PROVIDERS mapping with .env attributes
    """
    mod = ModuleType("saxoflow_agenticai.core.model_selector")

    class _Spec:
        def __init__(self, env: str):
            self.env = env

    class _MS:
        @staticmethod
        def get_provider_and_model(agent_type=None):
            return (provider, "dummy")

    mod.ModelSelector = _MS
    mod.PROVIDERS = {
        provider: _Spec(env_var),
        "openai": _Spec("OPENAI_API_KEY"),
        "groq": _Spec("GROQ_API_KEY"),
        "gemini": _Spec("GOOGLE_API_KEY"),
        "anthropic": _Spec("ANTHROPIC_API_KEY"),
    }
    return mod


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def test__ensure_env_file_exists_creates_template_when_missing(tmp_path):
    """It must create a .env template with helpful comments if absent."""
    sut = _fresh_module()
    env_path = sut._ensure_env_file_exists(tmp_path)
    assert env_path.exists()
    content = env_path.read_text(encoding="utf-8")
    assert "SaxoFlow .env" in content
    assert "SAXOFLOW_LLM_PROVIDER" in content


def test__ensure_env_file_exists_no_overwrite_if_exists(tmp_path):
    """Existing .env must not be overwritten."""
    sut = _fresh_module()
    p = tmp_path / ".env"
    p.write_text("EXISTING=1\n# comment\n", encoding="utf-8")
    out = sut._ensure_env_file_exists(tmp_path)
    assert out == p
    assert p.read_text(encoding="utf-8").startswith("EXISTING=1")


def test__write_env_kv_adds_and_updates(tmp_path):
    """_write_env_kv should preserve comments, update existing keys, and append new ones."""
    sut = _fresh_module()
    p = tmp_path / ".env"
    p.write_text("# head\nA=1\n# keep\n", encoding="utf-8")

    sut._write_env_kv(p, "A", "2")
    sut._write_env_kv(p, "B", "X")
    text = p.read_text(encoding="utf-8")
    # order preserved: comment, updated A, comment, appended B
    assert "# head" in text and "# keep" in text
    assert "A=2" in text and "B=X" in text
    assert text.endswith("\n")  # ensure trailing newline

@pytest.mark.parametrize(
    "value,show,expected_suffix",
    [
        ("sk-123456", 4, "3456"),
        ("abcd", 4, "abcd"),
        ("x", 4, "x"),
        ("abcdef", 2, "ef"),
    ],
)
def test__mask_tail(value, show, expected_suffix):
    """Masking keeps the last N chars visible; prefix masked."""
    sut = _fresh_module()
    masked = sut._mask_tail(value, show=show)
    assert masked.endswith(expected_suffix)
    # masked part is stars (or empty if shorter)
    assert set(masked[:-len(expected_suffix)] or "*") == {"*"}


def test__provider_env_map_fallback_when_import_missing(monkeypatch):
    """If import fails, a safe fallback map must be returned with gemini/anthropic included."""
    sut = _fresh_module()
    # Ensure module isn't present
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)
    out = sut._provider_env_map()
    assert out["openai"] == "OPENAI_API_KEY"
    assert out["gemini"] == "GOOGLE_API_KEY"
    assert out["anthropic"] == "ANTHROPIC_API_KEY"


def test__resolve_target_provider_env_via_model_selector(monkeypatch):
    """Normal path: use ModelSelector + PROVIDERS to map provider -> env var."""
    mod = _fake_model_selector_module("groq", "GROQ_API_KEY")
    sys.modules["saxoflow_agenticai.core.model_selector"] = mod
    sut = _fresh_module()
    prov, envv = sut._resolve_target_provider_env()
    assert prov == "groq" and envv == "GROQ_API_KEY"
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)


def test__resolve_target_provider_env_fallback_envvar(monkeypatch):
    """Fallback path: missing import uses SAXOFLOW_LLM_PROVIDER env -> correct ENV var."""
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)
    sut = _fresh_module()
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "gemini")
    prov, envv = sut._resolve_target_provider_env()
    assert prov == "gemini" and envv == "GOOGLE_API_KEY"


def test__has_correct_key_true_false(monkeypatch):
    """_has_correct_key returns True iff required env var is set."""
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)
    sut = _fresh_module()
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert sut._has_correct_key() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-xyz")
    assert sut._has_correct_key() is True


# ---------------------------------------------------------------------------
# run_key_setup_wizard
# ---------------------------------------------------------------------------

def test_run_key_setup_wizard_default_choice_and_persistence(
    monkeypatch, tmp_path, dummy_console
):
    """
    Wizard:
    - shows providers from _provider_env_map
    - blank input chooses preferred_provider
    - getpass returns key
    - writes .env, sets env vars, calls load_dotenv(override=True), prints success
    """
    sut = _fresh_module()

    # Use a deterministic provider map (sorted order deterministic)
    provider_map = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY", "gemini": "GOOGLE_API_KEY"}
    monkeypatch.setattr(sut, "_provider_env_map", lambda: provider_map, raising=True)

    # Force cwd to tmp
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)

    # Input: blank → accept preferred 'gemini'
    inputs = [""]  # accept default
    monkeypatch.setattr("builtins.input", lambda prompt="": inputs.pop(0))

    # Hidden key
    monkeypatch.setattr(sut, "getpass", lambda prompt="": "gm-123456")

    # Record load_dotenv calls
    calls: List[Tuple[bool]] = []
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: calls.append((override,)))

    sut.run_key_setup_wizard(dummy_console, preferred_provider="gemini")

    env_file = tmp_path / ".env"
    assert env_file.exists()
    text = env_file.read_text(encoding="utf-8")
    assert "GOOGLE_API_KEY=gm-123456" in text
    assert "SAXOFLOW_LLM_PROVIDER=gemini" in text

    # Env exported immediately
    assert os.getenv("GOOGLE_API_KEY") == "gm-123456"
    assert os.getenv("SAXOFLOW_LLM_PROVIDER") == "gemini"

    # load_dotenv called with override=True at the end
    assert calls and calls[-1] == (True,)

    # Success line printed
    printed = " ".join(dummy_console.output)
    assert "Saved GOOGLE_API_KEY" in printed


def test_run_key_setup_wizard_index_choice(monkeypatch, tmp_path, dummy_console):
    """
    Wizard: invalid choice → error → numeric index selects provider.
    """
    sut = _fresh_module()
    provider_map = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"}
    monkeypatch.setattr(sut, "_provider_env_map", lambda: provider_map, raising=True)
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)

    # First: invalid token, then: "2" -> 'groq'
    inputs = ["NOPE", "2"]
    monkeypatch.setattr("builtins.input", lambda prompt="": inputs.pop(0))
    monkeypatch.setattr(sut, "getpass", lambda prompt="": "g-abc")

    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.run_key_setup_wizard(dummy_console, preferred_provider="openai")
    env_file = tmp_path / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=g-abc" in text
    # Printed invalid choice warning at least once
    assert any("Invalid choice" in t for (_, t, _style) in dummy_console.printed if _ == "Text")


# ---------------------------------------------------------------------------
# ensure_first_run_setup
# ---------------------------------------------------------------------------

def test_ensure_first_run_setup_quiet_when_configured(monkeypatch, dummy_console):
    """
    When the resolved provider's key is present, the function should do nothing (quiet).
    """
    sut = _fresh_module()

    # Resolve to openai, key present
    monkeypatch.setenv("OPENAI_API_KEY", "sk-ok")
    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "openai")

    # No-op dotenv
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.ensure_first_run_setup(dummy_console)
    # Nothing printed
    assert dummy_console.printed_objects == []


@pytest.mark.parametrize("isatty,noninteractive", [(False, None), (True, "1")])
def test_ensure_first_run_setup_headless_instructions_panel(
    monkeypatch, dummy_console, isatty, noninteractive
):
    """
    Headless path (no TTY or NONINTERACTIVE=1): print yellow 'setup required' panel with correct env var hint.
    """
    sut = _fresh_module()

    # Force provider/env resolution
    monkeypatch.setattr(sut, "_resolve_target_provider_env", lambda: ("groq", "GROQ_API_KEY"), raising=True)
    monkeypatch.setattr(sut, "_has_correct_key", lambda: False, raising=True)

    # Fake stdin TTY behavior
    sut.sys.stdin = SimpleNamespace(isatty=(lambda: isatty))
    if noninteractive is not None:
        monkeypatch.setenv("SAXOFLOW_NONINTERACTIVE", noninteractive)
    else:
        monkeypatch.delenv("SAXOFLOW_NONINTERACTIVE", raising=False)

    # No-op dotenv and file ensure
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)
    monkeypatch.setattr(sut, "_ensure_env_file_exists", lambda _cwd: _cwd, raising=True)

    sut.ensure_first_run_setup(dummy_console)

    # A Panel should be printed with instructions mentioning the env var
    assert any(isinstance(obj, Panel) for obj in dummy_console.printed_objects)
    body = " ".join(str(getattr(p, "renderable", "")) for p in dummy_console.printed_objects if isinstance(p, Panel))
    assert "GROQ_API_KEY" in body
    # Title check
    titles = [getattr(p, "title", "") for p in dummy_console.printed_objects if isinstance(p, Panel)]
    assert "setup required" in [t.lower() for t in titles]


def test_ensure_first_run_setup_interactive_success(monkeypatch, dummy_console):
    """
    Interactive path: prints cyan 'setup' panel, runs wizard, reloads env, prints green success when key present.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_has_correct_key", lambda: False, raising=True)
    monkeypatch.setattr(sut, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"), raising=True)

    # TTY present
    sut.sys.stdin = SimpleNamespace(isatty=lambda: True)

    # Wizard sets the env var so verification succeeds
    def _wizard(console, preferred_provider=None):
        os.environ["OPENAI_API_KEY"] = "sk-from-wizard"

    monkeypatch.setattr(sut, "run_key_setup_wizard", _wizard, raising=True)

    # Record load_dotenv called twice (initial, final)
    calls: List[Tuple[bool]] = []
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: calls.append((override,)))

    sut.ensure_first_run_setup(dummy_console)

    # Cyan setup panel printed first, then success message in green
    text_events = [(k, txt, style) for (k, txt, style) in dummy_console.events if k == "print_text"]
    assert any("LLM API key configured" in txt for (_, txt, _style) in text_events)
    assert any(style == "green" for (_k, _txt, style) in text_events)

    # load_dotenv got override=True at the end
    assert calls and calls[-1] == (True,)


def test_ensure_first_run_setup_interactive_wizard_exception(monkeypatch, dummy_console):
    """
    Interactive path: when wizard raises, print a bold red error; no crash.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_has_correct_key", lambda: False, raising=True)
    monkeypatch.setattr(sut, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"), raising=True)

    sut.sys.stdin = SimpleNamespace(isatty=lambda: True)
    monkeypatch.setattr(sut, "run_key_setup_wizard", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")), raising=True)
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.ensure_first_run_setup(dummy_console)

    # Bold red error printed
    assert any(
        e for e in dummy_console.events if e[0] == "print_text" and "Key setup failed" in e[1] and "bold red" in e[2]
    )
