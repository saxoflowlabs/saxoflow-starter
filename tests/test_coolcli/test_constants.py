# tests/test_coolcli/test_constants.py
from __future__ import annotations

from typing import Dict, List, Tuple

import pytest

from cool_cli import constants as sut


def test_shell_commands_shape_and_safety():
    assert isinstance(sut.SHELL_COMMANDS, dict)
    assert sut.SHELL_COMMANDS  # non-empty

    unsafe = {";", "&&", "|", ">", "<"}
    for alias, cmd_list in sut.SHELL_COMMANDS.items():
        assert isinstance(alias, str)
        assert isinstance(cmd_list, list)
        assert all(isinstance(tok, str) for tok in cmd_list)
        assert cmd_list, f"{alias} should not map to an empty command list"
        # No shell metacharacters—these should be safe argv tokens
        for tok in cmd_list:
            assert not any(ch in tok for ch in unsafe), f"Unsafe token in {alias}: {tok}"


def test_editors_are_tuples_and_disjoint():
    assert isinstance(sut.BLOCKING_EDITORS, tuple)
    assert isinstance(sut.NONBLOCKING_EDITORS, tuple)

    # Expected membership
    for name in ("nano", "vim", "vi", "micro"):
        assert name in sut.BLOCKING_EDITORS
    for name in ("code", "subl", "gedit"):
        assert name in sut.NONBLOCKING_EDITORS

    # Disjointness
    assert set(sut.BLOCKING_EDITORS).isdisjoint(set(sut.NONBLOCKING_EDITORS))


def test_agentic_commands_type_contents_and_ordering():
    cmds = sut.AGENTIC_COMMANDS
    assert isinstance(cmds, tuple)
    # Must contain the documented verbs
    required = {
        "rtlgen", "tbgen", "fpropgen", "report",
        "rtlreview", "tbreview", "fpropreview",
        "debug", "sim", "fullpipeline",
    }
    assert required.issubset(set(cmds))

    # Order is meaningful for display—assert key relative ordering remains stable
    assert cmds.index("rtlgen") < cmds.index("tbgen")
    assert cmds.index("tbgen") < cmds.index("fpropgen")
    assert cmds.index("report") > cmds.index("fpropgen")
    # keep sim/debug/fullpipeline relative order stable
    assert cmds.index("debug") < cmds.index("sim") < cmds.index("fullpipeline")


def test_custom_prompt_contains_brand_and_markup():
    html = sut.CUSTOM_PROMPT_HTML
    assert isinstance(html, str)
    assert "saxoflow" in html.lower()
    # crude sanity: looks like prompt_toolkit ANSI/HTML markup
    assert "<" in html and ">" in html


def test_default_config_is_template_and_not_mutated_by_callers(monkeypatch):
    # Sanity: DEFAULT_CONFIG shape
    assert isinstance(sut.DEFAULT_CONFIG, dict)
    for key in ("model", "temperature", "top_k", "top_p"):
        assert key in sut.DEFAULT_CONFIG

    # Caller gets a deep copy
    cfg1 = sut.new_default_config()
    cfg2 = sut.new_default_config()
    assert cfg1 is not sut.DEFAULT_CONFIG
    assert cfg2 is not sut.DEFAULT_CONFIG
    assert cfg1 is not cfg2
    assert cfg1 == sut.DEFAULT_CONFIG == cfg2

    # Mutate returned copy—DEFAULT_CONFIG must not change
    cfg1["model"] = "changed"
    cfg1["top_k"] = 42
    assert sut.DEFAULT_CONFIG["model"] != "changed"
    assert sut.DEFAULT_CONFIG["top_k"] != 42

    # Simulate nested structure to verify deep-copy semantics
    # (DEFAULT_CONFIG currently flat; we emulate a nested dict at runtime.)
    # Monkeypatch module-level DEFAULT_CONFIG and ensure copies are independent.
    nested = {"outer": {"inner": 1}, **sut.DEFAULT_CONFIG}
    monkeypatch.setattr(sut, "DEFAULT_CONFIG", nested, raising=True)
    c1 = sut.new_default_config()
    c2 = sut.new_default_config()
    assert c1 is not c2
    assert c1["outer"] is not c2["outer"]
    # Mutate c1 deeply; c2 must remain unchanged
    c1["outer"]["inner"] = 999
    assert c2["outer"]["inner"] == 1
