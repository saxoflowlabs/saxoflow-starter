#!/usr/bin/env python3
"""Validate M1 legacy-command parity contracts.

Checks performed:
- Expected legacy aliases from saxoflow.cli_contracts are all present.
- No unexpected aliases are present.
- Every alias maps to a non-empty canonical saxoflow command string.
- Every canonical hint starts with "saxoflow ".
- Each canonical hint resolves to a registered canonical command prefix.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import List

from saxoflow.cli_contracts import validate_legacy_alias_coverage
from saxoflow.command_registry import get_canonical_commands, get_legacy_alias_hints


@dataclass
class Finding:
    kind: str
    detail: str


def _canonical_prefix_matches(hint: str, canonical_commands: List[str]) -> bool:
    # Remove options/flags because registry stores command surfaces, not option forms.
    parts = hint.split()
    trimmed = []
    for token in parts:
        if token.startswith("-"):
            break
        trimmed.append(token)
    candidate = " ".join(trimmed) if trimmed else hint
    return any(
        candidate == cmd or candidate.startswith(cmd + " ") or cmd.startswith(candidate + " ")
        for cmd in canonical_commands
    )


def run_checks() -> List[Finding]:
    findings: List[Finding] = []

    alias_hints = get_legacy_alias_hints()
    canonical_commands = get_canonical_commands()

    coverage = validate_legacy_alias_coverage(alias_hints)
    for cmd in coverage.missing:
        findings.append(Finding("missing-alias", cmd))
    for cmd in coverage.unexpected:
        findings.append(Finding("unexpected-alias", cmd))

    for legacy, hint in sorted(alias_hints.items()):
        normalized = " ".join(hint.strip().split())
        if not normalized:
            findings.append(Finding("empty-hint", legacy))
            continue
        if not normalized.startswith("saxoflow "):
            findings.append(Finding("non-canonical-prefix", f"{legacy} -> {hint}"))
            continue
        if legacy == normalized:
            findings.append(Finding("identity-mapping", legacy))
            continue
        if not _canonical_prefix_matches(normalized, canonical_commands):
            findings.append(Finding("unregistered-canonical-surface", f"{legacy} -> {hint}"))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Check SaxoFlow legacy command parity for M1.")
    parser.parse_args()

    findings = run_checks()
    if not findings:
        print("[parity] OK: Legacy alias coverage and canonical mappings are valid.")
        return 0

    print("[parity] FAIL: Command parity findings detected:")
    for finding in findings:
        print(f"- {finding.kind}: {finding.detail}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
