# tests/test_coolcli/test_state.py
from __future__ import annotations

import types
import pytest
from click.testing import CliRunner
from rich.console import Console

from cool_cli import state as sut


def test_initial_defaults_and_types():
    # Singletons
    assert isinstance(sut.runner, CliRunner)
    assert isinstance(sut.console, Console)
    assert sut.console.options.soft_wrap is True or getattr(sut.console, "soft_wrap", True) is True

    # Session state
    assert isinstance(sut.conversation_history, list) and sut.conversation_history == []
    assert isinstance(sut.attachments, list) and sut.attachments == []
    assert sut.system_prompt == ""

    # Config starts as a COPY of DEFAULT_CONFIG (not same object)
    assert sut.config == sut.DEFAULT_CONFIG
    assert sut.config is not sut.DEFAULT_CONFIG


def test_reset_state_clears_lists_and_rebinds_config_identity(monkeypatch):
    # Seed some data and capture identities
    sut.conversation_history.extend([{"user": "u", "assistant": "a"}])
    sut.attachments.extend([{"name": "file", "content": b"x"}])
    sut.system_prompt = "PROMPT"
    old_config_id = id(sut.config)
    hist_id = id(sut.conversation_history)
    att_id = id(sut.attachments)

    sut.reset_state()

    assert id(sut.conversation_history) == hist_id  # same list object
    assert id(sut.attachments) == att_id            # same list object
    assert sut.conversation_history == []
    assert sut.attachments == []
    assert sut.system_prompt == ""

    # config is a new dict with default contents
    assert id(sut.config) != old_config_id
    assert sut.config == sut.DEFAULT_CONFIG


def test_reset_state_recreate_console_and_runner_when_requested():
    old_console = sut.console
    old_runner = sut.runner

    sut.reset_state(keep_console=False, keep_runner=False)

    assert sut.console is not old_console
    assert sut.runner is not old_runner
    assert isinstance(sut.console, Console) and isinstance(sut.runner, CliRunner)


def test_reset_state_override_config_shallow_merge(monkeypatch):
    # Start from clean
    sut.reset_state()
    base_defaults = dict(sut.DEFAULT_CONFIG)

    # Override merges shallowly
    sut.reset_state(override_config={"model": "m2", "extra": 123})
    # Preserves all default keys unless overridden
    for k, v in base_defaults.items():
        if k == "model":
            assert sut.config[k] == "m2"
        else:
            assert sut.config[k] == v
    # Adds new keys
    assert sut.config["extra"] == 123

    # override_config={} still yields defaults (no change)
    sut.reset_state(override_config={})
    assert sut.config == sut.DEFAULT_CONFIG


def test_reset_state_uses_module_local_DEFAULT_CONFIG(monkeypatch):
    # Prove reset uses sut.DEFAULT_CONFIG (module-local binding)
    patched_defaults = dict(sut.DEFAULT_CONFIG)
    patched_defaults.update({"newkey": "newval", "temperature": 0.123})
    monkeypatch.setattr(sut, "DEFAULT_CONFIG", patched_defaults, raising=True)

    sut.reset_state()
    assert "newkey" in sut.config and sut.config["newkey"] == "newval"
    assert sut.config["temperature"] == 0.123


def test_get_state_snapshot_returns_copies_and_same_singletons():
    # Seed
    sut.reset_state()
    sut.conversation_history.append({"user": "x"})
    sut.attachments.append({"name": "a", "content": b"1"})
    sut.system_prompt = "P"
    sut.config["model"] = "mX"

    snap = sut.get_state_snapshot()

    # console/runner are same identities
    assert snap["console"] is sut.console
    assert snap["runner"] is sut.runner

    # copies for mutable containers
    assert snap["conversation_history"] == sut.conversation_history
    assert snap["attachments"] == sut.attachments
    assert snap["config"] == sut.config
    assert snap["system_prompt"] == sut.system_prompt

    # Mutating snapshot must NOT affect globals
    snap["conversation_history"].append({"user": "mut"})
    snap["attachments"].append({"name": "b", "content": b"2"})
    snap["config"]["model"] = "mut"
    # Strings are immutable, but verify independence
    snap["system_prompt"] = "Q"

    assert sut.conversation_history == [{"user": "x"}]
    assert sut.attachments == [{"name": "a", "content": b"1"}]
    assert sut.config["model"] == "mX"
    assert sut.system_prompt == "P"


def test__SoftWrapConsole_options_returns_real_opts_when_present(monkeypatch):
    """Cover the 'has soft_wrap → return opts' fast-path."""
    from rich.console import Console as RichConsole

    class DummyOpts:
        def __init__(self, val):
            self.soft_wrap = val

    # Patch the base class property so super().options returns an object
    # that *already* has a 'soft_wrap' attribute.
    monkeypatch.setattr(
        RichConsole,
        "options",
        property(lambda self: DummyOpts(False)),
        raising=True,
    )

    c = sut._SoftWrapConsole()
    opts = c.options  # should hit: if hasattr(opts, "soft_wrap"): return opts
    assert hasattr(opts, "soft_wrap")
    assert opts.soft_wrap is False  # proves we returned the real opts, not a proxy


def test__AutoResetList_mutation_and_utility_methods(monkeypatch):
    """Exercise all remaining branches of _AutoResetList methods."""
    L = sut._AutoResetList([3, 1, 2])

    # __setitem__
    L[1] = 9
    assert L[1] == 9

    # __delitem__
    del L[1]
    assert L == [3, 2]

    # insert
    L.insert(1, 5)   # [3, 5, 2]
    assert L[1] == 5

    # remove
    L.remove(5)      # [3, 2]
    assert L == [3, 2]

    # make a few more elements
    L.append(4)
    L.append(1)      # [3, 2, 4, 1]

    # sort
    L.sort()
    assert L == [1, 2, 3, 4]

    # reverse
    L.reverse()
    assert L == [4, 3, 2, 1]

    # pop
    popped = L.pop()
    assert popped == 1 and L == [4, 3, 2]

    # __repr__ (just ensure it returns a string)
    r = repr(L)
    assert isinstance(r, str) and "4" in r

    # __ne__
    assert L != [1, 2, 3]
