"""Canonical command registry for SaxoFlow.

This module provides a centralized list of canonical command surfaces and
legacy-to-canonical transition hints used by completion, migration checks,
and compatibility guidance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class CommandDescriptor:
    """Describes a canonical SaxoFlow command form."""

    command: str
    category: str
    notes: str = ""


CANONICAL_COMMANDS: Tuple[CommandDescriptor, ...] = (
    CommandDescriptor("saxoflow workspace init", "workspace"),
    CommandDescriptor("saxoflow unit init", "workspace"),
    CommandDescriptor("saxoflow workspace validate", "workspace"),
    CommandDescriptor("saxoflow workspace migrate", "workspace"),
    CommandDescriptor("saxoflow workspace lock", "workspace"),
    CommandDescriptor("saxoflow workspace clean", "workspace"),
    CommandDescriptor("saxoflow env init", "env"),
    CommandDescriptor("saxoflow env audit", "env"),
    CommandDescriptor("saxoflow env show", "env"),
    CommandDescriptor("saxoflow env repair", "env"),
    CommandDescriptor("saxoflow env path normalize", "env"),
    CommandDescriptor("saxoflow env enter", "env"),
    CommandDescriptor("saxoflow tool list", "tool"),
    CommandDescriptor("saxoflow tool install", "tool"),
    CommandDescriptor("saxoflow tool use", "tool"),
    CommandDescriptor("saxoflow tool lock", "tool"),
    CommandDescriptor("saxoflow tool resolve", "tool"),
    CommandDescriptor("saxoflow tool audit", "tool"),
    CommandDescriptor("saxoflow tool bundle apply", "tool"),
    CommandDescriptor("saxoflow tool op list", "tool-op"),
    CommandDescriptor("saxoflow tool op run", "tool-op"),
    CommandDescriptor("saxoflow tool op check", "tool-op"),
    CommandDescriptor("saxoflow tool op report", "tool-op"),
    CommandDescriptor("saxoflow flow run", "flow"),
    CommandDescriptor("saxoflow action run", "action"),
    CommandDescriptor("saxoflow ai plan", "ai"),
    CommandDescriptor("saxoflow ai run", "ai"),
    CommandDescriptor("saxoflow ai resume", "ai"),
    CommandDescriptor("saxoflow ai explain", "ai"),
    CommandDescriptor("saxoflow ai review", "ai"),
    CommandDescriptor("saxoflow ai generate rtl", "ai"),
    CommandDescriptor("saxoflow ai generate tb", "ai"),
    CommandDescriptor("saxoflow ai generate formal-props", "ai"),
    CommandDescriptor("saxoflow ai triage", "ai"),
    CommandDescriptor("saxoflow ai verify sim", "ai"),
    CommandDescriptor("saxoflow teach pack list", "teach"),
    CommandDescriptor("saxoflow teach import", "teach"),
    CommandDescriptor("saxoflow teach build", "teach"),
    CommandDescriptor("saxoflow teach validate", "teach"),
    CommandDescriptor("saxoflow teach run", "teach"),
    CommandDescriptor("saxoflow teach session status", "teach"),
    CommandDescriptor("saxoflow model validate", "model"),
    CommandDescriptor("saxoflow model auth setup", "model"),
    CommandDescriptor("saxoflow help env", "help"),
    CommandDescriptor("saxoflow help tool", "help"),
)


# Mapping derived from docs/new_plan.md migration matrix and transition coverage.
LEGACY_ALIAS_HINTS: Dict[str, str] = {
    "saxoflow init-env": "saxoflow env init",
    "saxoflow install": "saxoflow tool install",
    "saxoflow diagnose": "saxoflow env audit",
    "saxoflow diagnose summary": "saxoflow env audit summary",
    "saxoflow diagnose env": "saxoflow env show",
    "saxoflow diagnose repair": "saxoflow env repair --profile required",
    "saxoflow diagnose repair-interactive": "saxoflow env repair --interactive",
    "saxoflow diagnose clean-path": "saxoflow env path normalize",
    "saxoflow diagnose help": "saxoflow help env",
    "saxoflow unit": "saxoflow unit init",
    "saxoflow sim": "saxoflow action run sim.icarus",
    "saxoflow sim-verilator": "saxoflow action run sim.verilator.build",
    "saxoflow sim-verilator-run": "saxoflow action run sim.verilator.run",
    "saxoflow wave": "saxoflow action run wave.gtkwave",
    "saxoflow wave-verilator": "saxoflow action run wave.gtkwave --backend verilator",
    "saxoflow simulate": "saxoflow flow run rtl_to_sim --backend iverilog --with-wave",
    "saxoflow simulate-verilator": "saxoflow flow run rtl_to_sim --backend verilator --with-wave",
    "saxoflow formal": "saxoflow flow run rtl_to_formal",
    "saxoflow synth": "saxoflow flow run rtl_to_netlist --tool yosys",
    "saxoflow clean": "saxoflow workspace clean --artifacts",
    "saxoflow check-tools": "saxoflow tool audit",
    "saxoflow teach list": "saxoflow teach pack list",
    "saxoflow teach index": "saxoflow teach import",
    "saxoflow teach start": "saxoflow teach run",
    "saxoflow teach status": "saxoflow teach session status",
    "saxoflow teach debug-images": "saxoflow teach validate --assets --images",
    "saxoflow agenticai": "saxoflow ai",
    "saxoflow agenticai setupkeys": "saxoflow model auth setup",
    "saxoflow agenticai testllms": "saxoflow model validate --all-agents",
    "saxoflow agenticai rtlgen": "saxoflow ai generate rtl",
    "saxoflow agenticai tbgen": "saxoflow ai generate tb",
    "saxoflow agenticai fpropgen": "saxoflow ai generate formal-props",
    "saxoflow agenticai rtlreview": "saxoflow ai review rtl",
    "saxoflow agenticai tbreview": "saxoflow ai review tb",
    "saxoflow agenticai fpropreview": "saxoflow ai review formal-props",
    "saxoflow agenticai debug": "saxoflow ai triage",
    "saxoflow agenticai sim": "saxoflow ai verify sim",
    "saxoflow agenticai fullpipeline": "saxoflow ai run full-pipeline",
}


# Legacy-friendly first tokens often typed without "saxoflow" in the TUI.
BARE_SAXOFLOW_COMPAT: Tuple[str, ...] = (
    "check-tools",
    "check_tools",
    "agenticai",
    "diagnose",
    "install",
    "synth",
    "formal",
    "simulate",
    "simulate-verilator",
    "wave",
    "wave-verilator",
    "clean",
    "init-env",
    "unit",
    # Canonical nouns for gradual migration and discoverability.
    "workspace",
    "env",
    "tool",
    "flow",
    "action",
    "ai",
    "teach",
    "model",
)


def get_canonical_commands() -> List[str]:
    """Return canonical command strings in stable order."""
    return [item.command for item in CANONICAL_COMMANDS]


def get_legacy_alias_hints() -> Dict[str, str]:
    """Return a copy of legacy command migration hints."""
    return dict(LEGACY_ALIAS_HINTS)


def get_bare_saxoflow_compat_commands() -> List[str]:
    """Return first-token compatibility commands for TUI auto-prefixing."""
    return list(BARE_SAXOFLOW_COMPAT)
