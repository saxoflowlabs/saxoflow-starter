from __future__ import annotations

from saxoflow.command_registry import (
    get_bare_saxoflow_compat_commands,
    get_canonical_commands,
    get_legacy_alias_hints,
)


def test_canonical_commands_include_core_surfaces():
    commands = get_canonical_commands()
    assert "saxoflow workspace init" in commands
    assert "saxoflow flow run" in commands
    assert "saxoflow action run" in commands
    assert "saxoflow ai plan" in commands
    assert "saxoflow tool op run" in commands


def test_legacy_alias_hints_cover_expected_legacy_roots():
    hints = get_legacy_alias_hints()
    assert hints["saxoflow init-env"] == "saxoflow env init"
    assert hints["saxoflow check-tools"] == "saxoflow tool audit"
    assert hints["saxoflow agenticai sim"] == "saxoflow ai verify sim"
    assert hints["saxoflow teach start"] == "saxoflow teach run"


def test_bare_compat_has_legacy_and_canonical_prefix_tokens():
    bare = set(get_bare_saxoflow_compat_commands())
    assert "init-env" in bare
    assert "check-tools" in bare
    assert "flow" in bare
    assert "action" in bare
    assert "workspace" in bare
