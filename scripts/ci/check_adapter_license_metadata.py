#!/usr/bin/env python3
"""Stage 1 CI check: Adapter license/redistribution metadata lint (M7).

Validates that every tool in saxoflow/tools/license_metadata.yaml has the
required license and redistribution fields, and that every tool registered in
saxoflow/tools/registry.yaml has a metadata entry.

This check is advisory (warnings) for legacy-installed tools without metadata,
and hard-fails only for tools that declare `education_ready: true` without a
complete metadata entry (since these are included in packaged lab bundles).

Exit code 0 = all checks pass (warnings are non-blocking).
Exit code 1 = one or more hard errors.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = REPO_ROOT / "saxoflow" / "tools" / "registry.yaml"
LICENSE_METADATA_FILE = REPO_ROOT / "saxoflow" / "tools" / "license_metadata.yaml"

REQUIRED_METADATA_FIELDS = {"license", "redistribution", "upstream_url"}
EDUCATION_READY_REQUIRED_FIELDS = {"license", "redistribution", "upstream_url", "license_summary"}


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "error"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as fh:
        return yaml.safe_load(fh) or {}


def run_checks() -> List[Finding]:
    findings: List[Finding] = []

    registry_data = _load_yaml(REGISTRY_FILE)
    tools = registry_data.get("tools", [])
    if not tools:
        findings.append(Finding("missing-registry", f"Tool registry not found or empty: {REGISTRY_FILE}"))
        return findings

    license_data = _load_yaml(LICENSE_METADATA_FILE)
    if not license_data:
        findings.append(Finding(
            "missing-license-metadata",
            f"License metadata file not found or empty: {LICENSE_METADATA_FILE}. "
            "Run 'scripts/ci/check_adapter_license_metadata.py' for details.",
        ))
        return findings

    tool_licenses: Dict[str, Dict] = license_data.get("tool_licenses", {})

    registry_keys = {entry["key"] for entry in tools if "key" in entry}
    metadata_keys = set(tool_licenses.keys())

    # Check for tools without any metadata entry
    missing_metadata = registry_keys - metadata_keys
    for key in sorted(missing_metadata):
        findings.append(Finding(
            "missing-metadata-entry",
            f"Tool '{key}' has no entry in license_metadata.yaml.",
            severity="warning",
        ))

    # Check for stale metadata entries (in metadata but not in registry)
    stale_metadata = metadata_keys - registry_keys
    for key in sorted(stale_metadata):
        findings.append(Finding(
            "stale-metadata-entry",
            f"license_metadata.yaml has entry for '{key}' which is not in registry.yaml.",
            severity="warning",
        ))

    # Validate required fields on present metadata entries
    for key, meta in sorted(tool_licenses.items()):
        education_ready = meta.get("education_ready", False)
        required = EDUCATION_READY_REQUIRED_FIELDS if education_ready else REQUIRED_METADATA_FIELDS

        for field in required:
            if field not in meta or not str(meta[field]).strip():
                severity = "error" if education_ready else "warning"
                findings.append(Finding(
                    "incomplete-metadata",
                    f"Tool '{key}' metadata missing or empty field: '{field}'"
                    + (" (education_ready=true requires this)" if education_ready else ""),
                    severity=severity,
                ))

        # Redistribution must be one of the known values
        redistribution = meta.get("redistribution", "")
        valid_redistribution = {"allowed", "allowed-with-attribution", "restricted", "unknown"}
        if redistribution and redistribution not in valid_redistribution:
            findings.append(Finding(
                "invalid-redistribution",
                f"Tool '{key}' has invalid redistribution value '{redistribution}'. "
                f"Expected one of: {sorted(valid_redistribution)}",
            ))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow adapter license metadata lint (M7 Stage 1).")
    parser.parse_args()

    findings = run_checks()

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[license-meta] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[license-meta] ERROR {e.kind}: {e.detail}")

    if errors:
        print(f"[license-meta] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[license-meta] OK: license metadata validated ({len(warnings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
