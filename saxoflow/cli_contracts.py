"""CLI command-transition contracts for Milestone M1.

This module captures expected legacy alias coverage from docs/new_plan.md and
provides validation helpers used by tests and CI parity checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Set


EXPECTED_LEGACY_ALIASES: Sequence[str] = (
    "saxoflow init-env",
    "saxoflow install",
    "saxoflow diagnose",
    "saxoflow diagnose summary",
    "saxoflow diagnose env",
    "saxoflow diagnose repair",
    "saxoflow diagnose repair-interactive",
    "saxoflow diagnose clean-path",
    "saxoflow diagnose help",
    "saxoflow unit",
    "saxoflow sim",
    "saxoflow sim-verilator",
    "saxoflow sim-verilator-run",
    "saxoflow wave",
    "saxoflow wave-verilator",
    "saxoflow simulate",
    "saxoflow simulate-verilator",
    "saxoflow formal",
    "saxoflow synth",
    "saxoflow clean",
    "saxoflow check-tools",
    "saxoflow teach list",
    "saxoflow teach index",
    "saxoflow teach start",
    "saxoflow teach status",
    "saxoflow teach debug-images",
    "saxoflow agenticai",
    "saxoflow agenticai setupkeys",
    "saxoflow agenticai testllms",
    "saxoflow agenticai rtlgen",
    "saxoflow agenticai tbgen",
    "saxoflow agenticai fpropgen",
    "saxoflow agenticai rtlreview",
    "saxoflow agenticai tbreview",
    "saxoflow agenticai fpropreview",
    "saxoflow agenticai debug",
    "saxoflow agenticai sim",
    "saxoflow agenticai fullpipeline",
)


@dataclass(frozen=True)
class AliasCoverageResult:
    """Coverage summary for expected vs. actual legacy alias mappings."""

    missing: List[str]
    unexpected: List[str]

    @property
    def ok(self) -> bool:
        return not self.missing and not self.unexpected


def expected_legacy_aliases() -> Set[str]:
    """Return expected legacy aliases as a set."""
    return set(EXPECTED_LEGACY_ALIASES)


def validate_legacy_alias_coverage(alias_hints: Dict[str, str]) -> AliasCoverageResult:
    """Validate alias map coverage against M1 contract expectations."""
    expected = expected_legacy_aliases()
    actual = set(alias_hints.keys())

    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)

    return AliasCoverageResult(missing=missing, unexpected=unexpected)
