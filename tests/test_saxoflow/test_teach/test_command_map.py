# tests/test_saxoflow/test_teach/test_command_map.py
"""Tests for saxoflow.teach.command_map — command resolution logic."""

from __future__ import annotations

import pytest

from saxoflow.teach import command_map as cmd_map_module
from saxoflow.teach.command_map import (
    ResolvedCommand,
    ToolEntry,
    _find_entry,
    _load_registry,
    resolve_command,
)
from saxoflow.teach.session import CommandDef


# ---------------------------------------------------------------------------
# Helpers: mock availability
# ---------------------------------------------------------------------------

def _always_available(cmd: str) -> bool:
    return True


def _never_available(cmd: str) -> bool:
    return False


def _only_prefer(preferred_cmd: str):
    """Return an availability checker that accepts only preferred_cmd."""
    def checker(cmd: str) -> bool:
        return cmd.split()[0] == preferred_cmd.split()[0]
    return checker


# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------

class TestRegistryLoading:
    def test_registry_loads_without_error(self):
        registry = _load_registry()
        assert isinstance(registry, dict)

    def test_iverilog_in_registry(self):
        registry = _load_registry()
        assert "iverilog" in registry

    def test_entry_fields(self):
        registry = _load_registry()
        entry = registry["iverilog"]
        assert isinstance(entry, ToolEntry)
        assert entry.native == "iverilog"
        assert entry.saxoflow_cmd.startswith("saxoflow")


# ---------------------------------------------------------------------------
# resolve_command logic
# ---------------------------------------------------------------------------

class TestResolveCommand:
    def setup_method(self):
        """Reset the lru_cache and availability checker before each test."""
        _load_registry.cache_clear()
        cmd_map_module._availability_checker = _never_available

    def teardown_method(self):
        _load_registry.cache_clear()
        import shutil
        cmd_map_module._availability_checker = lambda cmd: shutil.which(cmd.split()[0]) is not None

    def test_preferred_used_when_available(self):
        cmd_map_module._availability_checker = _only_prefer("saxoflow sim iverilog")
        cmd_def = CommandDef(
            native="iverilog -g2012 -o out.o tb.v dut.v",
            preferred="saxoflow sim iverilog",
            use_preferred_if_available=True,
        )
        result = resolve_command(cmd_def)
        assert result.command_str == "saxoflow sim iverilog"
        assert result.is_wrapper is True
        assert result.is_available is True

    def test_preferred_skipped_when_flag_false(self):
        cmd_map_module._availability_checker = _never_available
        cmd_def = CommandDef(
            native="echo hello",
            preferred="saxoflow echo",
            use_preferred_if_available=False,
        )
        result = resolve_command(cmd_def)
        # preferred not available AND use_preferred_if_available=False → native
        assert result.is_wrapper is False
        assert result.command_str == "echo hello"

    def test_native_fallback_when_nothing_available(self):
        cmd_map_module._availability_checker = _never_available
        cmd_def = CommandDef(native="iverilog some.v")
        result = resolve_command(cmd_def)
        assert result.command_str == "iverilog some.v"
        assert result.is_wrapper is False
        assert result.is_available is False

    def test_bare_invocation_wrapped_when_available(self):
        """A bare tool name (no arguments) is wrapped to its saxoflow_cmd."""
        cmd_map_module._availability_checker = _always_available
        cmd_def = CommandDef(native="iverilog")
        result = resolve_command(cmd_def)
        assert result.is_wrapper is True
        assert result.command_str == "saxoflow sim iverilog"

    def test_command_with_args_not_wrapped(self):
        """Commands with extra arguments must stay native.

        Wrappers like ``saxoflow sim iverilog`` do not accept the full
        Icarus/Verilator CLI, so ``iverilog -g2012 tb.v`` must run as-is.
        """
        cmd_map_module._availability_checker = _always_available
        cmd_def = CommandDef(native="iverilog -g2012 tb.v")
        result = resolve_command(cmd_def)
        assert result.is_wrapper is False
        assert result.command_str == "iverilog -g2012 tb.v"

    def test_tool_entry_returned_for_known_native(self):
        cmd_map_module._availability_checker = _never_available
        cmd_def = CommandDef(native="iverilog tb.v")
        result = resolve_command(cmd_def)
        assert result.tool_entry is not None
        assert result.tool_entry.key == "iverilog"


# ---------------------------------------------------------------------------
# _find_entry
# ---------------------------------------------------------------------------

class TestFindEntry:
    def test_finds_exact_native_match(self):
        registry = _load_registry()
        entry = _find_entry(registry, "iverilog -V")
        assert entry is not None
        assert entry.key == "iverilog"

    def test_returns_none_for_unknown(self):
        registry = _load_registry()
        entry = _find_entry(registry, "somethingobscure12345 arg")
        assert entry is None
