from __future__ import annotations

import pytest

from saxoflow.command_registry import get_legacy_alias_hints
from saxoflow.command_resolver import CommandResolver


def test_resolve_legacy_command_detects_known_legacy_input():
    resolver = CommandResolver()
    result = resolver.resolve_legacy_command("saxoflow simulate --tb foo_tb")
    assert result.is_legacy is True
    assert result.canonical_hint == "saxoflow flow run rtl_to_sim --backend iverilog --with-wave"


@pytest.mark.parametrize("legacy,canonical", sorted(get_legacy_alias_hints().items()))
def test_resolve_legacy_command_covers_all_known_aliases(legacy, canonical):
    resolver = CommandResolver()
    result = resolver.resolve_legacy_command(legacy)
    assert result.is_legacy is True
    assert result.canonical_hint == canonical


@pytest.mark.parametrize("legacy,canonical", sorted(get_legacy_alias_hints().items()))
def test_resolve_legacy_command_with_suffix_preserves_mapping(legacy, canonical):
    resolver = CommandResolver()
    result = resolver.resolve_legacy_command(f"{legacy} --dry-run")
    assert result.is_legacy is True
    assert result.canonical_hint == canonical


def test_resolve_legacy_command_ignores_canonical_input():
    resolver = CommandResolver()
    result = resolver.resolve_legacy_command("saxoflow flow run rtl_to_sim")
    assert result.is_legacy is False
    assert result.canonical_hint is None


def test_semantic_suggestions_for_flow_run():
    resolver = CommandResolver()
    suggestions = resolver.semantic_suggestions("saxoflow flow run r")
    assert "rtl_to_sim" in suggestions
    assert "rtl_to_formal" in suggestions


def test_semantic_suggestions_for_workspace_subcommands():
    resolver = CommandResolver()
    suggestions = resolver.semantic_suggestions("saxoflow workspace ")
    assert "init" in suggestions
    assert "migrate" in suggestions
    assert "lock" in suggestions


def test_semantic_suggestions_empty_for_nonsemantic_line():
    resolver = CommandResolver()
    suggestions = resolver.semantic_suggestions("echo hello")
    assert suggestions == []


def test_semantic_suggestions_handles_empty_and_invalid_inputs():
    resolver = CommandResolver()
    assert resolver.semantic_suggestions("") == []
    # Unmatched quote triggers shlex parsing error branch.
    assert resolver.semantic_suggestions("saxoflow flow run \"") == []


def test_semantic_suggestions_returns_full_choices_when_fragment_absent():
    resolver = CommandResolver()
    suggestions = resolver.semantic_suggestions("saxoflow action run ")
    assert "sim.icarus" in suggestions
    assert "synth.yosys" in suggestions


def test_bare_saxoflow_commands_property_is_populated():
    resolver = CommandResolver()
    bare = set(resolver.bare_saxoflow_commands)
    assert "init-env" in bare
    assert "flow" in bare
