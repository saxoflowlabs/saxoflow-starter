# saxoflow/installer/presets.py
"""
Central preset configuration for the SaxoFlow installer.

This module defines reusable tool groups and higher-level presets that are
consumed by the interactive installer and CLI commands (e.g., `init-env`).

Design goals
------------
- Clean separation of tool groupings (simulation, formal, FPGA, ASIC, base, IDE).
- Deterministic ordering of tools within presets (avoid set()-based shuffling).
- PEP 8 / flake8 compliance and Python 3.9+ compatibility.
- Keep deprecated/unused features commented for future reference (see AGENTIC_*).

Notes
-----
- Agentic AI extensions are **not** provided here anymore. They are retained
  in commented form for historical context and to ease future reintroduction.
"""

from __future__ import annotations

from typing import Dict, List

__all__ = [
    "SIM_TOOLS",
    "FORMAL_TOOLS",
    "FPGA_TOOLS",
    "ASIC_TOOLS",
    "BASE_TOOLS",
    "IDE_TOOLS",
    "PRESETS",
    "ALL_TOOL_GROUPS",
]

# ---------------------------------------------------------------------------
# Tool groups for easy reuse
# ---------------------------------------------------------------------------

#: Simulation tools commonly used in student workflows.
SIM_TOOLS: List[str] = ["iverilog", "verilator"]

#: Formal verification tools (SymbiYosys wraps Yosys+backends).
FORMAL_TOOLS: List[str] = ["symbiyosys"]

#: FPGA backend tools (mix of open-source and vendor tooling).
FPGA_TOOLS: List[str] = ["nextpnr", "openfpgaloader", "vivado"]

#: ASIC backend tools (open-source physical design & layout).
ASIC_TOOLS: List[str] = ["openroad", "klayout", "magic", "netgen"]

#: Base tools shared across flows (waveforms, synthesis).
BASE_TOOLS: List[str] = ["gtkwave", "yosys"]

#: IDE integration (VS Code).
IDE_TOOLS: List[str] = ["vscode"]

# --- Deprecated / currently unused -----------------------------------------
# AGENTIC_AI is intentionally disabled in this release.
# Keeping definitions commented-out for future reference to avoid breaking
# older documentation or downstream references that might expect the symbol.
#
# AGENTIC_TOOLS: List[str] = ["agentic-ai"]
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Preset configurations
# ---------------------------------------------------------------------------

#: High-level presets consumed by `init-env --preset <name>`.
#:
#: Keep a deterministic order (avoid list(set(...))) to ensure stable diffs
#: and reproducible UX in printing/selection. If you add new groups, append
#: thoughtfully to maintain a logical progression.
PRESETS: Dict[str, List[str]] = {
    # Minimal, student-friendly setup: IDE + a basic simulator + viewer.
    "minimal": IDE_TOOLS + ["iverilog", "gtkwave"],

    # FPGA-oriented: IDE + Verilator for faster sims + FPGA toolchain + base.
    "fpga": IDE_TOOLS + ["verilator"] + FPGA_TOOLS + BASE_TOOLS,

    # ASIC-oriented: IDE + Verilator + ASIC PD/layout stack + base.
    "asic": IDE_TOOLS + ["verilator"] + ASIC_TOOLS + BASE_TOOLS,

    # Formal-only: IDE + Yosys + formal wrapper.
    "formal": IDE_TOOLS + ["yosys"] + FORMAL_TOOLS,

    # --- Deprecated / currently unused preset ------------------------------
    # "agentic-ai": AGENTIC_TOOLS,
    #
    # Keeping this commented for future reintroduction. If re-enabled,
    # verify that downstream modules include a matching tool group and
    # interactive flows expose an appropriate toggle.

    # Full stack (without Agentic AI for now). Order is intentional.
    "full": IDE_TOOLS + SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS,
}


# ---------------------------------------------------------------------------
# Exportable tool groups (optional for CLI checks/UI)
# ---------------------------------------------------------------------------

#: Named groups exported for interactive UIs and validation in the installer.
ALL_TOOL_GROUPS: Dict[str, List[str]] = {
    "simulation": SIM_TOOLS,
    "formal": FORMAL_TOOLS,
    "fpga": FPGA_TOOLS,
    "asic": ASIC_TOOLS,
    "base": BASE_TOOLS,
    "ide": IDE_TOOLS,
    # "agentic-ai": AGENTIC_TOOLS,  # intentionally disabled; see note above
}

# TODO: If future releases re-enable Agentic AI, ensure:
#  - Interactive flow exposes the toggle in a clear, optional step.
#  - Presets including agentic tools are validated end-to-end.
#  - CLI help text and docs reflect the addition consistently.
