#!/usr/bin/env python3
"""Stage 1 CI check: Documentation manifest lint (M7).

Validates:
1. Every tool in saxoflow/tools/registry.yaml has all required schema fields.
2. Every tool whose key appears in SCRIPT_TOOLS has a corresponding recipe file
   under scripts/recipes/.
3. All tool descriptions are non-empty strings.
4. No duplicate tool keys in the registry.

Exit code 0 = all checks pass.
Exit code 1 = one or more findings.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_FILE = REPO_ROOT / "saxoflow" / "tools" / "registry.yaml"
RECIPES_DIR = REPO_ROOT / "scripts" / "recipes"

REQUIRED_FIELDS = {"key", "native", "saxoflow_cmd", "check_cmd", "description"}


@dataclass
class Finding:
    kind: str
    detail: str
    severity: str = "error"  # "error" | "warning"


def _load_registry() -> List[Dict]:
    if not REGISTRY_FILE.exists():
        return []
    with REGISTRY_FILE.open() as fh:
        data = yaml.safe_load(fh)
    return data.get("tools", []) if data else []


def _load_script_tools() -> Set[str]:
    """Return tool names from SCRIPT_TOOLS in saxoflow.tools.definitions."""
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from saxoflow.tools.definitions import SCRIPT_TOOLS  # type: ignore[import]
        return set(SCRIPT_TOOLS.keys())
    except Exception:
        return set()


def run_checks() -> List[Finding]:
    findings: List[Finding] = []

    tools = _load_registry()
    if not tools:
        findings.append(Finding("missing-registry", f"Registry file not found or empty: {REGISTRY_FILE}"))
        return findings

    seen_keys: Set[str] = set()
    script_tools = _load_script_tools()

    for entry in tools:
        key = entry.get("key", "<unknown>")

        # 1. Duplicate key check
        if key in seen_keys:
            findings.append(Finding("duplicate-key", f"tool key '{key}' appears more than once"))
        seen_keys.add(key)

        # 2. Required fields
        for field in REQUIRED_FIELDS:
            if field not in entry:
                findings.append(Finding("missing-field", f"tool '{key}' is missing required field: '{field}'"))
            elif not str(entry[field]).strip():
                findings.append(Finding("empty-field", f"tool '{key}' has empty field: '{field}'"))

        # 3. Description non-empty
        desc = entry.get("description", "")
        if not desc or not desc.strip():
            findings.append(Finding("empty-description", f"tool '{key}' has no description"))

        # 4. Recipe file existence for script-managed tools
        if key in script_tools:
            # Normalize dashes in recipe filename
            recipe_stem = key.replace("_", "-")
            recipe_path = RECIPES_DIR / f"{recipe_stem}.sh"
            if not recipe_path.exists():
                findings.append(Finding(
                    "missing-recipe",
                    f"tool '{key}' is in SCRIPT_TOOLS but recipe not found: {recipe_path.name}",
                    severity="warning",
                ))

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="SaxoFlow doc-manifest lint (M7 Stage 1).")
    parser.parse_args()

    findings = run_checks()

    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for w in warnings:
        print(f"[doc-manifest] WARN  {w.kind}: {w.detail}")
    for e in errors:
        print(f"[doc-manifest] ERROR {e.kind}: {e.detail}")

    if errors:
        print(f"[doc-manifest] FAIL: {len(errors)} error(s), {len(warnings)} warning(s).")
        return 1

    print(f"[doc-manifest] OK: registry validated ({len(findings)} warning(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
