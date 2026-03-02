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

    NOTE: Provider names are sorted alphabetically inside the wizard.
    For {"openai","groq"}, sorted order is ["groq","openai"], so index "1" selects "groq".
    """
    sut = _fresh_module()
    provider_map = {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"}
    monkeypatch.setattr(sut, "_provider_env_map", lambda: provider_map, raising=True)
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)

    # First: invalid token, then: "1" -> selects 'groq' (alphabetical index)
    inputs = ["NOPE", "1"]
    monkeypatch.setattr("builtins.input", lambda prompt="": inputs.pop(0))
    monkeypatch.setattr(sut, "getpass", lambda prompt="": "g-abc")

    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.run_key_setup_wizard(dummy_console, preferred_provider="openai")
    env_file = tmp_path / ".env"
    text = env_file.read_text(encoding="utf-8")
    assert "GROQ_API_KEY=g-abc" in text
    # Printed invalid choice warning at least once
    assert any("Invalid choice" in t for (k, t, _style) in dummy_console.printed if k == "Text")


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
    Interactive path: prints cyan 'setup' panel, runs wizard, reloads env,
    then prints green success when key becomes present.
    """
    sut = _fresh_module()

    # Start with no key present so we take the interactive path.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # The provider/env pair used by the run
    monkeypatch.setattr(
        sut, "_resolve_target_provider_env", lambda: ("openai", "OPENAI_API_KEY"), raising=True
    )

    # TTY present
    sut.sys.stdin = SimpleNamespace(isatty=lambda: True)

    # Wizard stub: set the key as if user completed input
    def _wizard(console, preferred_provider=None):
        os.environ["OPENAI_API_KEY"] = "sk-from-wizard"
    monkeypatch.setattr(sut, "run_key_setup_wizard", _wizard, raising=True)

    # Record load_dotenv calls
    calls: List[Tuple[bool]] = []
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: calls.append((override,)))

    sut.ensure_first_run_setup(dummy_console)

    # Look for the success line printed in green
    text_events = [(k, txt, style) for (k, txt, style) in dummy_console.events if k == "print_text"]
    assert any("LLM API key configured" in txt for (_, txt, _style) in text_events)
    assert any(style == "green" for (_k, _txt, style) in text_events)

    # Final load_dotenv should have been called with override=True
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


def test__resolve_target_provider_env_fallback_unknown_defaults_openai(monkeypatch):
    """
    Fallback path: if PROVIDERS import fails AND SAXOFLOW_LLM_PROVIDER is unknown,
    the env var defaults to OPENAI_API_KEY.
    """
    # Ensure the deferred import fails
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)
    sut = _fresh_module()

    monkeypatch.setenv("SAXOFLOW_LLM_PROVIDER", "notarealprovider")
    prov, envv = sut._resolve_target_provider_env()
    assert prov == "notarealprovider"
    assert envv == "OPENAI_API_KEY"  # fallback.get(..., "OPENAI_API_KEY")


def test__provider_env_map_uses_model_selector_when_import_succeeds(monkeypatch):
    """
    Try path: with a real PROVIDERS module present, return its mapping.
    """
    fake = _fake_model_selector_module("groq", "GROQ_API_KEY")
    # Add an extra provider to ensure we're reading from PROVIDERS
    class _Spec:
        def __init__(self, env: str): self.env = env
    fake.PROVIDERS["mistral"] = _Spec("MISTRAL_API_KEY")

    sys.modules["saxoflow_agenticai.core.model_selector"] = fake
    sut = _fresh_module()
    out = sut._provider_env_map()
    assert out["groq"] == "GROQ_API_KEY"
    assert out["mistral"] == "MISTRAL_API_KEY"
    # cleanup
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)


def test_run_key_setup_wizard_accepts_name_choice(monkeypatch, tmp_path, dummy_console):
    """
    Wizard branch where `choice in names` hits (user types provider name).
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_provider_env_map",
                        lambda: {"mistral": "MISTRAL_API_KEY", "openai": "OPENAI_API_KEY"},
                        raising=True)
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)

    # User enters provider name directly
    inputs = ["mistral"]
    monkeypatch.setattr("builtins.input", lambda _p="": inputs.pop(0))
    monkeypatch.setattr(sut, "getpass", lambda _p="": "ms-SECRET")

    # Avoid touching real env files beyond tmp; track dotenv calls
    called = []
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: called.append(override))

    sut.run_key_setup_wizard(dummy_console, preferred_provider="openai")
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "MISTRAL_API_KEY=ms-SECRET" in text
    assert "SAXOFLOW_LLM_PROVIDER=mistral" in text
    assert os.getenv("MISTRAL_API_KEY") == "ms-SECRET"
    # final call overrides
    assert called and called[-1] is True


def test_run_key_setup_wizard_empty_key_prompts_again(monkeypatch, tmp_path, dummy_console):
    """
    getpass loop: empty input prints 'Key cannot be empty.' in red, then accepts next key.
    """
    sut = _fresh_module()
    monkeypatch.setattr(sut, "_provider_env_map",
                        lambda: {"openai": "OPENAI_API_KEY"}, raising=True)
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)
    # Accept default provider
    monkeypatch.setattr("builtins.input", lambda _p="": "")

    # getpass returns empty once, then valid key
    keys = ["", "sk-valid"]
    monkeypatch.setattr(sut, "getpass", lambda _p="": keys.pop(0))
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.run_key_setup_wizard(dummy_console, preferred_provider="openai")

    # Red warning printed at least once
    red_events = [e for e in dummy_console.events
                  if e[0] == "print_text" and e[2] == "red"]
    assert any("Key cannot be empty" in msg for (_k, msg, _s) in red_events)

    # And the key eventually persisted
    text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-valid" in text


def test_ensure_first_run_setup_interactive_still_missing_prints_red(monkeypatch, dummy_console):
    """
    Final verification branch: after wizard + reload, _has_correct_key() still False ->
    prints bold red 'No API key found after setup.' message.
    """
    sut = _fresh_module()

    # Force interactive path (no key) and specific provider/env
    monkeypatch.setattr(sut, "_has_correct_key", lambda: False, raising=True)
    monkeypatch.setattr(sut, "_resolve_target_provider_env",
                        lambda: ("openai", "OPENAI_API_KEY"), raising=True)
    sut.sys.stdin = SimpleNamespace(isatty=lambda: True)

    # Wizard runs but doesn't set anything
    monkeypatch.setattr(sut, "run_key_setup_wizard", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.ensure_first_run_setup(dummy_console)

    assert any(
        e for e in dummy_console.events
        if e[0] == "print_text"
        and "No API key found after setup" in e[1]
        and e[2] == "bold red"
    )


def test__provider_env_map_except_branch_returns_fallback(monkeypatch):
    """
    Ensure the 'except' block in _provider_env_map runs: make the module import
    succeed but the attribute import fail by omitting PROVIDERS.
    """
    import sys, types, importlib
    import cool_cli.bootstrap as sut

    # Inject a dummy module *without* PROVIDERS so `from ... import PROVIDERS` fails
    fake_mod = types.ModuleType("saxoflow_agenticai.core.model_selector")
    sys.modules["saxoflow_agenticai.core.model_selector"] = fake_mod

    # Reload to be safe around import state
    sut = importlib.reload(sut)

    mapping = sut._provider_env_map()

    # We are in the fallback block: verify a few keys to cover the return literal
    assert mapping["openai"] == "OPENAI_API_KEY"
    assert mapping["groq"] == "GROQ_API_KEY"
    assert mapping["anthropic"] == "ANTHROPIC_API_KEY"
    assert mapping["gemini"] == "GOOGLE_API_KEY"
    assert mapping["perplexity"] == "PPLX_API_KEY"

    # Cleanup (optional; other tests won't be confused)
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)


def test__resolve_target_provider_env_try_none_defaults_openai(monkeypatch):
    """
    Try-branch fallback: when ModelSelector returns None, it should default
    to openai within the *try* block (not the except fallback).
    """
    import sys, importlib, types
    import cool_cli.bootstrap as sut

    # Fake module with PROVIDERS but ModelSelector returning (None, "dummy")
    fake = types.ModuleType("saxoflow_agenticai.core.model_selector")

    class _Spec:
        def __init__(self, env: str):
            self.env = env

    class _MS:
        @staticmethod
        def get_provider_and_model(agent_type=None):
            return (None, "dummy-model")

    fake.ModelSelector = _MS
    fake.PROVIDERS = {
        "openai": _Spec("OPENAI_API_KEY"),
        "groq": _Spec("GROQ_API_KEY"),
    }

    sys.modules["saxoflow_agenticai.core.model_selector"] = fake
    sut = importlib.reload(sut)

    prov, envv = sut._resolve_target_provider_env()
    assert prov == "openai"        # (prov or "openai") path exercised
    assert envv == "OPENAI_API_KEY"  # PROVIDERS.get(..., PROVIDERS["openai"]) fallback exercised

    # cleanup
    sys.modules.pop("saxoflow_agenticai.core.model_selector", None)


def test_ensure_first_run_setup_after_wizard_branching(monkeypatch, dummy_console):
    """
    Drive both final verification branches around the wizard by toggling
    _has_correct_key() return values across calls:
      - First call (pre-wizard): False -> we go interactive
      - Second call (post-wizard + reload): True -> green success line
    This explicitly exercises the 'if ... else ...' decision arc.
    """
    import cool_cli.bootstrap as sut

    # Make it interactive
    sut.sys.stdin = type("S", (), {"isatty": staticmethod(lambda: True)})

    # Count calls so we can return False once, then True
    calls = {"n": 0}

    def _has_key_flip():
        calls["n"] += 1
        return calls["n"] >= 2   # False on first check, True after reload

    monkeypatch.setattr(sut, "_has_correct_key", _has_key_flip, raising=True)
    # Provider/env used on the run doesn't really matter here
    monkeypatch.setattr(sut, "_resolve_target_provider_env",
                        lambda: ("openai", "OPENAI_API_KEY"), raising=True)

    # No-op wizard & dotenv (we're stubbing _has_correct_key anyway)
    monkeypatch.setattr(sut, "run_key_setup_wizard", lambda *a, **k: None, raising=True)
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None, raising=True)

    sut.ensure_first_run_setup(dummy_console)

    # We should have printed the green success line (final True branch)
    assert any(
        e for e in dummy_console.events
        if e[0] == "print_text" and "LLM API key configured" in e[1] and e[2] == "green"
    )


def test__write_env_kv_creates_file_when_absent(tmp_path):
    """
    When .env does not exist, _write_env_kv should create it with just KEY=VALUE.
    Covers the env_path.exists() == False branch.
    """
    import importlib
    import cool_cli.bootstrap as sut
    sut = importlib.reload(sut)

    env_path = tmp_path / ".env"  # do NOT create file
    assert not env_path.exists()

    sut._write_env_kv(env_path, "FOO", "BAR")

    assert env_path.exists()
    text = env_path.read_text(encoding="utf-8")
    assert text == "FOO=BAR\n"


def test_run_key_setup_wizard_digit_out_of_range_then_name(monkeypatch, tmp_path, dummy_console):
    """
    First enter a numeric index that's out of range (triggers 'Invalid choice'),
    then a valid provider NAME (hits `if choice in names:`).
    This covers the 'isdigit() and out-of-range' path and the 'in names' branch.
    """
    import importlib
    import cool_cli.bootstrap as sut
    sut = importlib.reload(sut)

    # Deterministic provider map; sorted(names) == ['groq','openai']
    monkeypatch.setattr(
        sut, "_provider_env_map",
        lambda: {"openai": "OPENAI_API_KEY", "groq": "GROQ_API_KEY"},
        raising=True,
    )
    monkeypatch.setattr(sut.os, "getcwd", lambda: str(tmp_path), raising=True)

    # 1st input: '999' -> digit & out of range -> "Invalid choice"
    # 2nd input: 'openai' -> hits `if choice in names:`
    inputs = ["999", "openai"]
    monkeypatch.setattr("builtins.input", lambda _p="": inputs.pop(0))

    # Provide a key and no-op dotenv
    monkeypatch.setattr(sut, "getpass", lambda _p="": "sk-XYZ")
    monkeypatch.setattr(sut, "load_dotenv", lambda override=False: None)

    sut.run_key_setup_wizard(dummy_console, preferred_provider="groq")

    # Confirm we printed the invalid-choice warning at least once
    # (works with either events or plain output, depending on your DummyConsole)
    text_stream = " ".join(getattr(dummy_console, "output", []))
    saw_invalid = "Invalid choice" in text_stream or any(
        e for e in getattr(dummy_console, "events", [])
        if e[0] == "print_text" and "Invalid choice" in e[1]
    )
    assert saw_invalid

    # And the final provider by name was accepted and saved
    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-XYZ" in env_text
