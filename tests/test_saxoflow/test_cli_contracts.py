from __future__ import annotations

from saxoflow.cli_contracts import expected_legacy_aliases, validate_legacy_alias_coverage
from saxoflow.command_registry import get_legacy_alias_hints


def test_cli_contract_coverage_matches_registry_aliases():
    coverage = validate_legacy_alias_coverage(get_legacy_alias_hints())
    assert coverage.missing == []
    assert coverage.unexpected == []


def test_cli_contract_expected_aliases_are_unique_and_prefixed():
    aliases = expected_legacy_aliases()
    assert len(aliases) > 0
    assert all(alias.startswith("saxoflow ") for alias in aliases)
