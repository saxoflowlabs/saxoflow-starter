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
    "FORMAL_SOLVER_TOOLS",
    "FORMAL_SOLVER_TOOLS_TIER2",
    "FPGA_TOOLS",
    "ASIC_TOOLS",
    "BASE_TOOLS",
    "SW_TOOLS",
    "IDE_TOOLS",
    "LINT_TOOLS",
    "SW_BRINGUP_TOOLS",
    "WAVEFORM_UX_TOOLS",
    "VHDL_CROSSCHECK_TOOLS",
    "IPXACT_EDU_TOOLS",
    "ORCHESTRATION_TOOLS",
    "RESEARCH_PLATFORM_TOOLS",
    "RESEARCH_ARCH_TOOLS",
    "RESEARCH_MEMORY_TOOLS",
    "ETHZ_IC_DESIGN_TOOLS",
    "ADVANCED_FLOW_TOOLS",
    "PRESETS",
    "ALL_TOOL_GROUPS",
]

# ---------------------------------------------------------------------------
# Tool groups for easy reuse
# ---------------------------------------------------------------------------

#: Simulation tools commonly used in student workflows.
SIM_TOOLS: List[str] = ["iverilog", "verilator", "ghdl", "cocotb", "covered"]

#: Formal verification tools (SymbiYosys wraps Yosys+backends).
FORMAL_TOOLS: List[str] = ["symbiyosys"]

#: Tier-1 SMT solvers for formal flows (default/recommended).
FORMAL_SOLVER_TOOLS: List[str] = ["boolector", "z3"]

#: Tier-2 SMT solvers for formal flows (complementary/specialized).
FORMAL_SOLVER_TOOLS_TIER2: List[str] = ["bitwuzla", "cvc5", "yices"]

#: FPGA backend tools (mix of open-source and vendor tooling).
FPGA_TOOLS: List[str] = ["nextpnr", "openfpgaloader", "vivado", "bender", "fusesoc", "rggen"]

#: ASIC backend tools (open-source physical design & layout).
ASIC_TOOLS: List[str] = ["openroad", "opensta", "klayout", "magic", "netgen", "bender", "fusesoc", "rggen"]

#: Base tools shared across flows (waveforms, synthesis, frontend support).
BASE_TOOLS: List[str] = ["gtkwave", "yosys", "surelog", "sv2v"]

#: Embedded software / RISC-V bring-up tools.
SW_TOOLS: List[str] = ["riscv-toolchain", "spike", "qemu-system-riscv64", "openocd"]

#: Optional software bring-up extensions (not required in baseline presets).
SW_BRINGUP_TOOLS: List[str] = ["riscv-pk"]

#: Optional waveform UX extension (keep GTKWave baseline as default).
WAVEFORM_UX_TOOLS: List[str] = ["surfer"]

#: Optional VHDL simulator cross-check extension.
VHDL_CROSSCHECK_TOOLS: List[str] = ["nvc"]

#: Optional IP-XACT educational tooling.
IPXACT_EDU_TOOLS: List[str] = ["kactus2"]

#: Advanced flow abstraction tools (optional, Phase 2).
ADVANCED_FLOW_TOOLS: List[str] = ["edalize"]

#: Optional project orchestration layer.
ORCHESTRATION_TOOLS: List[str] = ["siliconcompiler"]

#: Optional system-level virtual platform research tools.
RESEARCH_PLATFORM_TOOLS: List[str] = ["renode"]

#: Optional architecture research simulators.
RESEARCH_ARCH_TOOLS: List[str] = ["gem5", "riscv-vp-plusplus"]

#: Optional memory compiler research tooling.
RESEARCH_MEMORY_TOOLS: List[str] = ["openram"]

#: Tools required for the ETH Zurich open-source IC design flow (VLSI2).
#: Covers the full open-source path: simulate (Verilator) → synthesise (Yosys)
#: → physical design (OpenROAD) → sign-off (KLayout) + HDL deps (Bender).
ETHZ_IC_DESIGN_TOOLS: List[str] = ["verilator", "yosys", "openroad", "klayout", "bender"]

#: IDE integration (VS Code).
IDE_TOOLS: List[str] = ["vscode"]

#: RTL quality and style tools (linting + formatting).
LINT_TOOLS: List[str] = ["verible"]

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

    # Formal-plus: formal profile + Tier-1 solvers.
    "formal-plus": IDE_TOOLS + ["yosys"] + FORMAL_TOOLS + FORMAL_SOLVER_TOOLS,

    # Formal-complete: formal-plus + Tier-2 solvers for complementary solving.
    "formal-complete": IDE_TOOLS + ["yosys"] + FORMAL_TOOLS + FORMAL_SOLVER_TOOLS + FORMAL_SOLVER_TOOLS_TIER2,

    # --- Deprecated / currently unused preset ------------------------------
    # "agentic-ai": AGENTIC_TOOLS,
    #
    # Keeping this commented for future reintroduction. If re-enabled,
    # verify that downstream modules include a matching tool group and
    # interactive flows expose an appropriate toggle.

    # Full stack (without Agentic AI for now). Order is intentional.
    "full": IDE_TOOLS + SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + SW_TOOLS,

    # Optional software bring-up profile for firmware run/debug loops.
    "software-bringup": IDE_TOOLS + SW_TOOLS + SW_BRINGUP_TOOLS,

    # Optional waveform UX profile for modern waveform exploration.
    "waveform-ux": IDE_TOOLS + ["gtkwave"] + WAVEFORM_UX_TOOLS,

    # Optional VHDL cross-check profile (GHDL + NVC for comparative simulation).
    "vhdl-crosscheck": IDE_TOOLS + ["gtkwave", "ghdl"] + VHDL_CROSSCHECK_TOOLS,

    # Optional IP-XACT education profile.
    "ipxact-edu": IDE_TOOLS + IPXACT_EDU_TOOLS,

    # Advanced flow abstraction: IDE + base ecosystem + edalize for multi-backend orchestration.
    "advanced-flow": IDE_TOOLS + BASE_TOOLS + ["fusesoc", "bender"] + ADVANCED_FLOW_TOOLS,

    # Optional project-level orchestration tooling.
    "orchestration": IDE_TOOLS + BASE_TOOLS + ORCHESTRATION_TOOLS,

    # Optional system-level virtual platform research profile.
    "research-platform": IDE_TOOLS + SW_TOOLS + RESEARCH_PLATFORM_TOOLS,

    # Optional architecture research profile.
    "research-arch": IDE_TOOLS + SW_TOOLS + RESEARCH_ARCH_TOOLS,

    # Optional SRAM compiler research/education profile.
    "research-memory": IDE_TOOLS + ASIC_TOOLS + RESEARCH_MEMORY_TOOLS,

    # ETH Zurich VLSI2 open-source IC design course toolchain:
    # Verilator (sim) → Yosys (synth) → OpenROAD (PD) → KLayout (DRC/LVS) + Bender (HDL deps).
    "ethz_ic_design_tools": ETHZ_IC_DESIGN_TOOLS,

    # Full stack with RTL quality tools (lint + format).
    "full-with-quality": IDE_TOOLS + SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + SW_TOOLS + LINT_TOOLS,
}


# ---------------------------------------------------------------------------
# Exportable tool groups (optional for CLI checks/UI)
# ---------------------------------------------------------------------------

#: Named groups exported for interactive UIs and validation in the installer.
ALL_TOOL_GROUPS: Dict[str, List[str]] = {
    "simulation": SIM_TOOLS,
    "formal": FORMAL_TOOLS,
    "formal-solvers": FORMAL_SOLVER_TOOLS,
    "formal-solvers-tier2": FORMAL_SOLVER_TOOLS_TIER2,
    "fpga": FPGA_TOOLS,
    "asic": ASIC_TOOLS,
    "base": BASE_TOOLS,
    "software": SW_TOOLS,
    "ide": IDE_TOOLS,
    "lint": LINT_TOOLS,
    "ethz_ic_design": ETHZ_IC_DESIGN_TOOLS,
    "advanced-flow": ADVANCED_FLOW_TOOLS,
    "vhdl-crosscheck": VHDL_CROSSCHECK_TOOLS,
    "ipxact-edu": IPXACT_EDU_TOOLS,
    "orchestration": ORCHESTRATION_TOOLS,
    "research-platform": RESEARCH_PLATFORM_TOOLS,
    "research-arch": RESEARCH_ARCH_TOOLS,
    "research-memory": RESEARCH_MEMORY_TOOLS,
    # "agentic-ai": AGENTIC_TOOLS,  # intentionally disabled; see note above
}

# TODO: If future releases re-enable Agentic AI, ensure:
#  - Interactive flow exposes the toggle in a clear, optional step.
#  - Presets including agentic tools are validated end-to-end.
#  - CLI help text and docs reflect the addition consistently.
