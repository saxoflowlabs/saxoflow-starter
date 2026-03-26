#!/usr/bin/env python3
"""M8 CI check: evaluate usage telemetry windows for cutover readiness.

Validates sustained usage thresholds from docs/new_plan.md section 9.8:
- Phase C readiness: canonical usage >= 85% for a minor release cycle.
- Phase D readiness: legacy usage < 5% for a major release cycle.

Emits a telemetry summary artifact for RC signoff evidence.
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


def _normalized_cycle_type(value: Any) -> str:
    txt = str(value or "").strip().lower()
    return txt if txt in {"minor", "major"} else ""


def _is_phase_c_ready(samples: List[Dict[str, Any]]) -> bool:
    minor_samples = [s for s in samples if _normalized_cycle_type(s.get("cycle_type")) == "minor"]
    if not minor_samples:
        return False
    latest_minor = minor_samples[-1]
    return _safe_float(latest_minor.get("canonical_usage_pct"), default=0.0) >= 85.0


def _is_phase_d_ready(samples: List[Dict[str, Any]]) -> bool:
    major_samples = [s for s in samples if _normalized_cycle_type(s.get("cycle_type")) == "major"]
    if not major_samples:
        return False
    latest_major = major_samples[-1]
    return _safe_float(latest_major.get("legacy_usage_pct"), default=100.0) < 5.0


def run_checks(history: Dict[str, Any], require_phase_c_ready: bool, require_phase_d_ready: bool) -> List[Finding]:
    findings: List[Finding] = []

    if not history:
        findings.append(Finding("missing-usage-history", "Usage history JSON is missing or empty."))
        return findings

    samples = history.get("samples")
    if not isinstance(samples, list) or not samples:
        findings.append(Finding("missing-samples", "Usage history must include a non-empty samples list."))
        return findings

    for idx, sample in enumerate(samples):
        if not isinstance(sample, dict):
            findings.append(Finding("invalid-sample", f"Sample at index {idx} is not an object."))
            continue
        cycle_type = _normalized_cycle_type(sample.get("cycle_type"))
        if not cycle_type:
            findings.append(Finding("invalid-cycle-type", f"Sample at index {idx} must use cycle_type=minor|major."))

    phase_c_ready = _is_phase_c_ready(samples)
    phase_d_ready = _is_phase_d_ready(samples)

    if require_phase_c_ready and not phase_c_ready:
        findings.append(
            Finding(
                "phase-c-usage-window",
                "Phase C readiness failed: latest minor cycle canonical usage is below 85%.",
            )
        )

    if require_phase_d_ready and not phase_d_ready:
        findings.append(
            Finding(
                "phase-d-usage-window",
                "Phase D readiness failed: latest major cycle legacy usage is not below 5%.",
            )
        )

    if not phase_d_ready:
        findings.append(
            Finding(
                "phase-d-not-ready-warning",
                "Phase D sustained low legacy usage window is not yet satisfied.",
                severity="warning",
            )
        )

    return findings


def _build_summary(history: Dict[str, Any], findings: List[Finding]) -> Dict[str, Any]:
    samples = history.get("samples") if isinstance(history.get("samples"), list) else []
    minor_samples = [s for s in samples if _normalized_cycle_type(s.get("cycle_type")) == "minor"]
    major_samples = [s for s in samples if _normalized_cycle_type(s.get("cycle_type")) == "major"]

    latest_minor = minor_samples[-1] if minor_samples else {}
    latest_major = major_samples[-1] if major_samples else {}

    phase_c_ready = _is_phase_c_ready(samples)
    phase_d_ready = _is_phase_d_ready(samples)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    return {
        "history_metadata": history.get("metadata", {}),
        "sample_counts": {
            "total": len(samples),
            "minor": len(minor_samples),
            "major": len(major_samples),
        },
        "latest_minor": {
            "release": latest_minor.get("release"),
            "canonical_usage_pct": _safe_float(latest_minor.get("canonical_usage_pct"), default=0.0),
        },
        "latest_major": {
            "release": latest_major.get("release"),
            "legacy_usage_pct": _safe_float(latest_major.get("legacy_usage_pct"), default=100.0),
        },
        "phase_c_ready": phase_c_ready,
        "phase_d_ready": phase_d_ready,
        "errors": [asdict(f) for f in errors],
        "warnings": [asdict(f) for f in warnings],
        "status": "pass" if not errors else "fail",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow M8 transition telemetry readiness evaluator.")
    parser.add_argument(
        "--history",
        default=".github/rc-signoff/transition_usage_history.json",
        help="Path to usage telemetry history JSON.",
    )
    parser.add_argument(
        "--output",
        default="artifacts/transition-telemetry-summary.json",
        help="Path to write telemetry summary artifact JSON.",
    )
    parser.add_argument(
        "--require-phase-c-ready",
        action="store_true",
        help="Fail if Phase C canonical usage window is not satisfied.",
    )
    parser.add_argument(
        "--require-phase-d-ready",
        action="store_true",
        help="Fail if Phase D legacy usage window is not satisfied.",
    )
    args = parser.parse_args()

    history = _load_json(Path(args.history))
    findings = run_checks(history, args.require_phase_c_ready, args.require_phase_d_ready)

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[telemetry] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[telemetry] ERROR {e.kind}: {e.detail}")

    summary = _build_summary(history, findings)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[telemetry] Summary artifact: {output_path}")

    if errors:
        print(f"[telemetry] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[telemetry] OK: telemetry windows accepted ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
