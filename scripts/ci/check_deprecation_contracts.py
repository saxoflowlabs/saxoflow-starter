#!/usr/bin/env python3
"""Stage 1 / Stage 5 CI check: Deprecation contract lint (M7).

Validates the SaxoFlow deprecation lifecycle contracts:

1. All expected legacy aliases declared in cli_contracts.EXPECTED_LEGACY_ALIASES
   are present in command_registry.LEGACY_ALIAS_HINTS (no silent removals).
2. No alias maps to itself (identity mapping = regression).
3. All legacy alias hints point to registered canonical command surfaces.
4. Phase guard: no command is in Phase C (disabled by default) or Phase D
   (removed) without the removal being flagged explicitly in REMOVAL_APPROVED.
   This blocks accidental silent removal of legacy support.

Exit code 0 = all checks pass.
Exit code 1 = contract violations found.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[2]

# Commands where Phase C/D removal has been explicitly approved.
# Add approved removals to this tuple in the review that approves Phase C/D.
REMOVAL_APPROVED: tuple[str, ...] = ()

# Commands deprecated into Phase C (opt-out legacy) or Phase D (fully removed).
# Populate this list when a command enters Phase C/D deprecation lifecycle.
PHASE_C_COMMANDS: tuple[str, ...] = ()
PHASE_D_COMMANDS: tuple[str, ...] = ()


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "error"


def run_checks() -> List[Finding]:
    sys.path.insert(0, str(REPO_ROOT))
    findings: List[Finding] = []

    try:
        from saxoflow.cli_contracts import validate_legacy_alias_coverage, EXPECTED_LEGACY_ALIASES  # type: ignore
        from saxoflow.command_registry import get_legacy_alias_hints, get_canonical_commands  # type: ignore
    except ImportError as exc:
        findings.append(Finding("import-error", f"Cannot import SaxoFlow modules: {exc}"))
        return findings

    alias_hints = get_legacy_alias_hints()
    canonical_commands = get_canonical_commands()

    # 1. Coverage check: expected aliases must all be present
    coverage = validate_legacy_alias_coverage(alias_hints)
    for cmd in coverage.missing:
        findings.append(Finding(
            "missing-alias",
            f"Expected legacy alias '{cmd}' is not in LEGACY_ALIAS_HINTS. "
            "This is a silent removal — add the alias back or move to REMOVAL_APPROVED.",
        ))
    for cmd in coverage.unexpected:
        findings.append(Finding(
            "unexpected-alias",
            f"Alias '{cmd}' is in LEGACY_ALIAS_HINTS but not in EXPECTED_LEGACY_ALIASES. "
            "Add it to EXPECTED_LEGACY_ALIASES in cli_contracts.py.",
            severity="warning",
        ))

    # 2. Identity mapping check
    for legacy, hint in alias_hints.items():
        normalized = " ".join(hint.strip().split())
        if legacy == normalized:
            findings.append(Finding(
                "identity-mapping",
                f"Alias '{legacy}' maps to itself — this is a no-op deprecation hint.",
            ))

    # 3. Canonical prefix validation
    canonical_surfaces = list(canonical_commands)

    def _prefix_matches(hint: str) -> bool:
        parts = hint.split()
        trimmed = []
        for token in parts:
            if token.startswith("-"):
                break
            trimmed.append(token)
        candidate = " ".join(trimmed)
        return any(
            candidate == cmd or candidate.startswith(cmd + " ") or cmd.startswith(candidate + " ")
            for cmd in canonical_surfaces
        )

    for legacy, hint in sorted(alias_hints.items()):
        normalized = " ".join(hint.strip().split())
        if not normalized:
            findings.append(Finding("empty-hint", f"Alias '{legacy}' has empty canonical hint."))
            continue
        if not normalized.startswith("saxoflow "):
            findings.append(Finding(
                "non-canonical-prefix",
                f"Alias '{legacy}' hints to '{hint}' which does not start with 'saxoflow '.",
            ))
            continue
        if not _prefix_matches(normalized):
            findings.append(Finding(
                "unregistered-canonical-surface",
                f"Alias '{legacy}' hints to '{hint}' but no matching canonical command surface found.",
            ))

    # 4. Phase guard: block Phase C/D removal without explicit approval
    for cmd in PHASE_C_COMMANDS:
        if cmd not in REMOVAL_APPROVED:
            findings.append(Finding(
                "phase-c-unapproved",
                f"Command '{cmd}' is in Phase C (opt-out) but not in REMOVAL_APPROVED. "
                "Add to REMOVAL_APPROVED after migration threshold is met.",
            ))
    for cmd in PHASE_D_COMMANDS:
        if cmd not in REMOVAL_APPROVED:
            findings.append(Finding(
                "phase-d-unapproved",
                f"Command '{cmd}' is in Phase D (removed) but not in REMOVAL_APPROVED. "
                "This is a hard block on premature removal.",
            ))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow deprecation contract lint (M7 Stage 1/5).")
    parser.parse_args()

    findings = run_checks()
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[deprecation] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[deprecation] ERROR {e.kind}: {e.detail}")

    if errors:
        print(f"[deprecation] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[deprecation] OK: deprecation contracts valid ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
