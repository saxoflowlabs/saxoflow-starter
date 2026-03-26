#!/usr/bin/env python3
"""M8 CI check: approve release transition and legacy retirement schedule.

Combines the transition gate signoff, replay rehearsal, telemetry summary, and
retirement plan contract to determine whether the release is approved for the
next transition phase.
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
    severity: str = "error"


VALID_PHASES = {"phase_c", "phase_d"}
REQUIRED_APPROVERS = ("release_manager", "docs_owner", "cli_owner")


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, dict) else {}


def run_checks(
    signoff: Dict[str, Any],
    rehearsal: Dict[str, Any],
    telemetry: Dict[str, Any],
    plan: Dict[str, Any],
) -> List[Finding]:
    findings: List[Finding] = []

    if not signoff:
        findings.append(Finding("missing-signoff", "Transition signoff artifact is missing or empty."))
        return findings
    if not rehearsal:
        findings.append(Finding("missing-rehearsal", "Rehearsal artifact is missing or empty."))
        return findings
    if not telemetry:
        findings.append(Finding("missing-telemetry", "Telemetry summary artifact is missing or empty."))
        return findings
    if not plan:
        findings.append(Finding("missing-plan", "Legacy retirement plan is missing or empty."))
        return findings

    if signoff.get("status") != "pass" or not bool(signoff.get("all_gates_green", False)):
        findings.append(Finding("signoff-not-green", "Transition signoff is not fully green."))

    if rehearsal.get("status") != "pass":
        findings.append(Finding("rehearsal-not-green", "Legacy-to-canonical rehearsal did not pass."))

    if telemetry.get("status") != "pass":
        findings.append(Finding("telemetry-not-green", "Telemetry summary did not pass."))

    target_phase = str(plan.get("target_phase", "")).strip().lower()
    if target_phase not in VALID_PHASES:
        findings.append(Finding("invalid-target-phase", f"Plan target_phase must be one of {sorted(VALID_PHASES)}."))
        return findings

    if target_phase == "phase_c" and not bool(telemetry.get("phase_c_ready", False)):
        findings.append(Finding("phase-c-not-ready", "Release cannot be approved for Phase C without telemetry readiness."))

    if target_phase == "phase_d" and not bool(telemetry.get("phase_d_ready", False)):
        findings.append(Finding("phase-d-not-ready", "Release cannot be approved for Phase D without sustained low legacy usage."))

    approvals = plan.get("approvals")
    if not isinstance(approvals, dict):
        findings.append(Finding("missing-approvals", "Plan approvals must be provided as an object."))
        return findings

    for approver in REQUIRED_APPROVERS:
        if not bool(approvals.get(approver, False)):
            findings.append(Finding("missing-approval", f"Required approval missing: {approver}."))

    support_window = plan.get("support_window")
    if not isinstance(support_window, dict):
        findings.append(Finding("missing-support-window", "Plan support_window must be provided."))
    else:
        if not str(support_window.get("announced_in_release", "")).strip():
            findings.append(Finding("missing-announcement", "support_window.announced_in_release is required."))
        if not str(support_window.get("removal_target_release", "")).strip():
            findings.append(Finding("missing-removal-target", "support_window.removal_target_release is required."))

    return findings


def _build_summary(
    signoff: Dict[str, Any],
    rehearsal: Dict[str, Any],
    telemetry: Dict[str, Any],
    plan: Dict[str, Any],
    findings: List[Finding],
) -> Dict[str, Any]:
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    return {
        "target_phase": plan.get("target_phase"),
        "support_window": plan.get("support_window", {}),
        "source_status": {
            "signoff": signoff.get("status"),
            "rehearsal": rehearsal.get("status"),
            "telemetry": telemetry.get("status"),
        },
        "phase_readiness": {
            "phase_c_ready": telemetry.get("phase_c_ready"),
            "phase_d_ready": telemetry.get("phase_d_ready"),
        },
        "errors": [asdict(f) for f in errors],
        "warnings": [asdict(f) for f in warnings],
        "status": "approved" if not errors else "blocked",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow M8 release approval evaluator.")
    parser.add_argument("--signoff", default="artifacts/transition-gate-signoff.json")
    parser.add_argument("--rehearsal", default="artifacts/legacy-canonical-rehearsal.json")
    parser.add_argument("--telemetry", default="artifacts/transition-telemetry-summary.json")
    parser.add_argument("--plan", default=".github/rc-signoff/legacy_retirement_plan.json")
    parser.add_argument("--output", default="artifacts/transition-release-approval.json")
    args = parser.parse_args()

    signoff = _load_json(Path(args.signoff))
    rehearsal = _load_json(Path(args.rehearsal))
    telemetry = _load_json(Path(args.telemetry))
    plan = _load_json(Path(args.plan))

    findings = run_checks(signoff, rehearsal, telemetry, plan)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[release-approval] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[release-approval] ERROR {e.kind}: {e.detail}")

    summary = _build_summary(signoff, rehearsal, telemetry, plan, findings)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[release-approval] Summary artifact: {output_path}")

    if errors:
        print(f"[release-approval] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print("[release-approval] OK: release approved for configured transition phase.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
