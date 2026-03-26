#!/usr/bin/env python3
"""Stage 5 / M8 CI check: Transition closure gates and cutover policy.

Validates M8 closure gates from docs/new_plan.md (section 9.8):
- Gate A: command/alias closure
- Gate B: data/schema closure
- Gate C: UX/docs closure
- Gate D: ecosystem/course closure

Also enforces cutover policy:
- Phase C can start only when all gates pass and canonical usage >= 85%.
- Phase D can start only when all gates pass and legacy usage < 5% for one major cycle.

This script is designed for RC-only cutover workflows and emits a signoff artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "error"  # error | warning


@dataclass
class GateStatus:
    name: str
    passed: bool
    details: List[str]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _gate_a(evidence: Dict[str, Any]) -> GateStatus:
    a = evidence.get("gate_a", {})
    coverage = _safe_float(a.get("legacy_mapping_coverage_pct"))
    unmapped = _safe_int(a.get("unmapped_invocations"))
    parity_ok = bool(a.get("parity_golden_tests_passed", False))

    details = [
        f"legacy_mapping_coverage_pct={coverage}",
        f"unmapped_invocations={unmapped}",
        f"parity_golden_tests_passed={parity_ok}",
    ]
    passed = coverage >= 100.0 and unmapped == 0 and parity_ok
    return GateStatus("A", passed, details)


def _gate_b(evidence: Dict[str, Any]) -> GateStatus:
    b = evidence.get("gate_b", {})
    migration_success = _safe_float(b.get("migration_success_rate_pct"))
    schema_drift = _safe_int(b.get("schema_drift_count"))
    rollback_ok = bool(b.get("rollback_restore_tests_passed", False))

    details = [
        f"migration_success_rate_pct={migration_success}",
        f"schema_drift_count={schema_drift}",
        f"rollback_restore_tests_passed={rollback_ok}",
    ]
    passed = migration_success >= 99.0 and schema_drift == 0 and rollback_ok
    return GateStatus("B", passed, details)


def _gate_c(evidence: Dict[str, Any]) -> GateStatus:
    c = evidence.get("gate_c", {})
    docs_primary = bool(c.get("canonical_docs_primary", False))
    registry_completion = bool(c.get("registry_only_completion", False))
    techref_marked = bool(c.get("techref_legacy_compatibility_marked", False))

    details = [
        f"canonical_docs_primary={docs_primary}",
        f"registry_only_completion={registry_completion}",
        f"techref_legacy_compatibility_marked={techref_marked}",
    ]
    passed = docs_primary and registry_completion and techref_marked
    return GateStatus("C", passed, details)


def _gate_d(evidence: Dict[str, Any]) -> GateStatus:
    d = evidence.get("gate_d", {})
    pack_ok = bool(d.get("real_pack_family_migration_green", False))
    tutor_ok = bool(d.get("tutor_cohort_legacy_free", False))
    researcher_ok = bool(d.get("researcher_cohort_legacy_free", False))
    rc_unmapped = _safe_int(d.get("rc_unmapped_invocations"))

    details = [
        f"real_pack_family_migration_green={pack_ok}",
        f"tutor_cohort_legacy_free={tutor_ok}",
        f"researcher_cohort_legacy_free={researcher_ok}",
        f"rc_unmapped_invocations={rc_unmapped}",
    ]
    passed = pack_ok and tutor_ok and researcher_ok and rc_unmapped == 0
    return GateStatus("D", passed, details)


def run_checks(report: Dict[str, Any], evidence: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []

    if not report:
        findings.append(Finding("missing-migration-report", "Transition report JSON is missing or empty."))
        return findings
    if not evidence:
        findings.append(Finding("missing-transition-evidence", "Transition evidence JSON is missing or empty."))
        return findings

    gates = [_gate_a(evidence), _gate_b(evidence), _gate_c(evidence), _gate_d(evidence)]

    for gate in gates:
        if not gate.passed:
            findings.append(
                Finding(
                    "gate-failed",
                    f"Gate {gate.name} failed: " + "; ".join(gate.details),
                )
            )

    policy = evidence.get("cutover_policy", {})
    phase_c_requested = bool(policy.get("phase_c_requested", False))
    phase_d_requested = bool(policy.get("phase_d_requested", False))
    canonical_usage_pct = _safe_float(policy.get("canonical_usage_pct"))
    legacy_usage_pct_major_cycle = _safe_float(policy.get("legacy_usage_pct_major_cycle"), default=100.0)

    all_gates_green = all(g.passed for g in gates)

    if phase_c_requested:
        if not all_gates_green:
            findings.append(
                Finding(
                    "phase-c-blocked",
                    "Phase C requested but not all gates A-D are green.",
                )
            )
        if canonical_usage_pct < 85.0:
            findings.append(
                Finding(
                    "phase-c-threshold",
                    f"Phase C requires canonical usage >= 85.0%; got {canonical_usage_pct}%.",
                )
            )

    if phase_d_requested:
        if not all_gates_green:
            findings.append(
                Finding(
                    "phase-d-blocked",
                    "Phase D requested but not all gates A-D are green.",
                )
            )
        if legacy_usage_pct_major_cycle >= 5.0:
            findings.append(
                Finding(
                    "phase-d-threshold",
                    f"Phase D requires legacy usage < 5.0%; got {legacy_usage_pct_major_cycle}%.",
                )
            )

    if not phase_c_requested and canonical_usage_pct < 85.0:
        findings.append(
            Finding(
                "phase-c-readiness-warning",
                f"Canonical usage below Phase C readiness threshold: {canonical_usage_pct}% < 85.0%.",
                severity="warning",
            )
        )

    return findings


def _build_signoff(report: Dict[str, Any], evidence: Dict[str, Any], findings: List[Finding]) -> Dict[str, Any]:
    gates = {
        "A": asdict(_gate_a(evidence)),
        "B": asdict(_gate_b(evidence)),
        "C": asdict(_gate_c(evidence)),
        "D": asdict(_gate_d(evidence)),
    }
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    return {
        "report_summary": {
            "total_legacy_aliases": report.get("total_legacy_aliases"),
            "total_canonical_commands": report.get("total_canonical_commands"),
        },
        "evidence_metadata": evidence.get("metadata", {}),
        "gates": gates,
        "errors": [asdict(f) for f in errors],
        "warnings": [asdict(f) for f in warnings],
        "all_gates_green": all(gates[k]["passed"] for k in ("A", "B", "C", "D")),
        "status": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow M8 transition closure gate check.")
    parser.add_argument(
        "--report",
        default="migration-reports/command_transition_report.json",
        help="Path to migration transition report JSON.",
    )
    parser.add_argument(
        "--evidence",
        default=".github/rc-signoff/transition_evidence.json",
        help="Path to transition evidence JSON.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/transition-gate-signoff.json",
        help="Path to write signoff artifact JSON.",
    )
    args = parser.parse_args()

    report_path = Path(args.report)
    evidence_path = Path(args.evidence)
    output_path = Path(args.output)

    report = _load_json(report_path)
    evidence = _load_json(evidence_path)

    findings = run_checks(report, evidence)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[transition-gates] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[transition-gates] ERROR {e.kind}: {e.detail}")

    signoff = _build_signoff(report, evidence, findings)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(signoff, indent=2), encoding="utf-8")
    print(f"[transition-gates] Signoff artifact: {output_path}")

    if errors:
        print(f"[transition-gates] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[transition-gates] OK: all mandatory checks passed ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
