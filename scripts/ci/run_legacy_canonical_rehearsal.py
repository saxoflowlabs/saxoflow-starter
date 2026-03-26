#!/usr/bin/env python3
"""M8 CI check: Legacy-to-canonical cohort rehearsal replay.

Replays cohort scenario command lists using the legacy resolver and validates
that each legacy command resolves to the expected canonical form from the
transition report.

Outputs a replay artifact used as RC evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

from saxoflow.command_resolver import CommandResolver


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "error"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _matches_canonical_surface(canonical_hint: str, surfaces: List[str]) -> bool:
    return any(canonical_hint == s or canonical_hint.startswith(s + " ") for s in surfaces)


def run_checks(report: Dict[str, Any], scenario: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    if not report:
        findings.append(Finding("missing-report", "Transition report JSON is missing or empty."))
        return findings
    if not scenario:
        findings.append(Finding("missing-scenario", "Cohort scenario JSON is missing or empty."))
        return findings

    alias_map = report.get("alias_transition_map")
    surfaces = report.get("canonical_surfaces")
    cohorts = scenario.get("cohorts")

    if not isinstance(alias_map, dict) or not alias_map:
        findings.append(Finding("missing-alias-map", "Transition report has no alias_transition_map."))
        return findings

    if not isinstance(surfaces, list) or not surfaces:
        findings.append(Finding("missing-canonical-surfaces", "Transition report has no canonical_surfaces."))
        return findings

    if not isinstance(cohorts, dict) or not cohorts:
        findings.append(Finding("missing-cohorts", "Scenario file must define non-empty cohorts."))
        return findings

    resolver = CommandResolver(alias_hints=alias_map)

    for cohort_name, commands in cohorts.items():
        if not isinstance(commands, list) or not commands:
            findings.append(Finding("empty-cohort", f"Cohort '{cohort_name}' has no commands."))
            continue

        for cmd in commands:
            if not isinstance(cmd, str) or not cmd.strip():
                findings.append(Finding("invalid-command", f"Cohort '{cohort_name}' contains empty command entry."))
                continue

            normalized = " ".join(cmd.strip().split())
            expected = alias_map.get(normalized)
            if not expected:
                findings.append(
                    Finding(
                        "unmapped-command",
                        f"Cohort '{cohort_name}' command has no mapping in report: {normalized}",
                    )
                )
                continue

            resolved = resolver.resolve_legacy_command(normalized)
            if not resolved.is_legacy or not resolved.canonical_hint:
                findings.append(
                    Finding(
                        "resolver-nohint",
                        f"Resolver did not return canonical hint for: {normalized}",
                    )
                )
                continue

            if resolved.canonical_hint != expected:
                findings.append(
                    Finding(
                        "resolver-mismatch",
                        f"Resolver mismatch for '{normalized}': expected '{expected}', got '{resolved.canonical_hint}'.",
                    )
                )

            if not _matches_canonical_surface(resolved.canonical_hint, surfaces):
                findings.append(
                    Finding(
                        "non-canonical-surface",
                        f"Resolved command for '{normalized}' is outside canonical surfaces: {resolved.canonical_hint}",
                    )
                )

    return findings


def _build_rehearsal_artifact(report: Dict[str, Any], scenario: Dict[str, Any], findings: List[Finding]) -> Dict[str, Any]:
    alias_map = report.get("alias_transition_map", {})
    cohorts = scenario.get("cohorts", {})
    errors = [f for f in findings if f.severity == "error"]
    return {
        "report_summary": {
            "total_legacy_aliases": report.get("total_legacy_aliases"),
            "total_canonical_commands": report.get("total_canonical_commands"),
        },
        "scenario_summary": {
            "cohort_count": len(cohorts) if isinstance(cohorts, dict) else 0,
            "total_replayed_commands": sum(len(v) for v in cohorts.values()) if isinstance(cohorts, dict) else 0,
            "mapped_aliases_in_report": len(alias_map) if isinstance(alias_map, dict) else 0,
        },
        "errors": [asdict(f) for f in errors],
        "status": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow M8 legacy-to-canonical cohort rehearsal replay.")
    parser.add_argument(
        "--report",
        default="migration-reports/command_transition_report.json",
        help="Path to transition report JSON.",
    )
    parser.add_argument(
        "--scenario",
        default=".github/rc-signoff/cohort_rehearsal_scenarios.json",
        help="Path to cohort rehearsal scenario JSON.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/legacy-canonical-rehearsal.json",
        help="Path to write rehearsal artifact JSON.",
    )
    args = parser.parse_args()

    report = _load_json(Path(args.report))
    scenario = _load_json(Path(args.scenario))

    findings = run_checks(report, scenario)
    errors = [f for f in findings if f.severity == "error"]

    for err in errors:
        print(f"[rehearsal] ERROR {err.kind}: {err.detail}")

    artifact = _build_rehearsal_artifact(report, scenario, findings)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(f"[rehearsal] Artifact: {output_path}")

    if errors:
        print(f"[rehearsal] FAIL: {len(errors)} error(s).")
        return 1

    print("[rehearsal] OK: all cohort replay checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
