# saxoflow/tools/definitions.py
"""
Shared tool definitions for SaxoFlow.

This module centralizes:
- APT-managed tools (`APT_TOOLS`)
- Script-managed tools (`SCRIPT_TOOLS`)
- Human-readable tool descriptions (`TOOLS` and `TOOL_DESCRIPTIONS`)
- Minimum required versions (`MIN_TOOL_VERSIONS`)
- Convenience aggregate list (`ALL_TOOLS`)

Single Source of Truth
----------------------
Tool groupings (SIM/FORMAL/FPGA/ASIC/BASE/IDE) live in
`saxoflow.installer.presets`. We import them here to avoid duplication and
drift. The old in-file group definitions are kept commented-out for reference.

Notes
-----
- If Agentic AI groupings are reintroduced later, prefer to add them to
  `presets.py` and import them here similarly to the other groups.
"""

from __future__ import annotations

from typing import Dict, List

# Use presets.py as the canonical source for groupings.
from saxoflow.installer.presets import (
    SIM_TOOLS,
    FORMAL_TOOLS,
    FORMAL_SOLVER_TOOLS,
    FORMAL_SOLVER_TOOLS_TIER2,
    FPGA_TOOLS,
    ASIC_TOOLS,
    BASE_TOOLS,
    SW_TOOLS,
    IDE_TOOLS,
    ETHZ_IC_DESIGN_TOOLS,
)

__all__ = [
    # Public constants / mappings
    "APT_TOOLS",
    "SCRIPT_TOOLS",
    "TOOLS",
    "TOOL_DESCRIPTIONS",
    "MIN_TOOL_VERSIONS",
    "ALL_TOOLS",
    # Re-exports of groupings from presets (for convenience)
    "SIM_TOOLS",
    "FORMAL_TOOLS",
    "FORMAL_SOLVER_TOOLS",
    "FORMAL_SOLVER_TOOLS_TIER2",
    "FPGA_TOOLS",
    "ASIC_TOOLS",
    "BASE_TOOLS",
    "SW_TOOLS",
    "IDE_TOOLS",
    "ETHZ_IC_DESIGN_TOOLS",
]

# -----------------------------------------------------------------------------
# Tool Groupings (delegated to presets; old local copies retained as comments)
# -----------------------------------------------------------------------------
# SIM_TOOLS = ["iverilog", "verilator"]                # moved to presets.py
# FORMAL_TOOLS = ["symbiyosys"]                        # moved to presets.py
# FPGA_TOOLS = ["nextpnr", "openfpgaloader", "vivado"] # moved to presets.py
# ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]  # moved to presets.py
# BASE_TOOLS = ["gtkwave", "yosys"]                    # moved to presets.py
# IDE_TOOLS = ["vscode"]                               # moved to presets.py
#
# --- Agentic AI (intentionally disabled for now) -----------------------------
# AGENTIC_TOOLS = ["agentic-ai"]  # kept here for historical context only

# Keep a convenient aggregate for callers that want a flat list.
ALL_TOOLS: List[str] = (
    SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + SW_TOOLS + IDE_TOOLS
)

# -----------------------------------------------------------------------------
# APT-managed tools (simple system packages)
# -----------------------------------------------------------------------------
APT_TOOLS: List[str] = [
    "boolector",
    "ghdl",
    "gtkwave",
    "iverilog",
    "klayout",
    "magic",
    "netgen",
    "openfpgaloader",
    "z3",
]

# -----------------------------------------------------------------------------
# SaxoFlow-managed tools (script recipes)
# -----------------------------------------------------------------------------
SCRIPT_TOOLS: Dict[str, str] = {
    "bitwuzla": "scripts/recipes/bitwuzla.sh",
    "cocotb": "scripts/recipes/cocotb.sh",
    "covered": "scripts/recipes/covered.sh",
    "cvc5": "scripts/recipes/cvc5.sh",
    "fusesoc": "scripts/recipes/fusesoc.sh",
    "verilator": "scripts/recipes/verilator.sh",
    "openroad": "scripts/recipes/openroad.sh",
    "opensta": "scripts/recipes/opensta.sh",
    "nextpnr": "scripts/recipes/nextpnr.sh",
    "rggen": "scripts/recipes/rggen.sh",
    "riscv-toolchain": "scripts/recipes/riscv-toolchain.sh",
    "spike": "scripts/recipes/spike.sh",
    "surelog": "scripts/recipes/surelog.sh",
    "sv2v": "scripts/recipes/sv2v.sh",
    "symbiyosys": "scripts/recipes/symbiyosys.sh",
    "yices": "scripts/recipes/yices.sh",
    "vscode": "scripts/recipes/vscode.sh",
    "yosys": "scripts/recipes/yosys.sh",
    "vivado": "scripts/recipes/vivado.sh",
    "bender": "scripts/recipes/bender.sh",
}

# -----------------------------------------------------------------------------
# Tool Descriptions (used for CLI selection menus)
# -----------------------------------------------------------------------------
TOOLS: Dict[str, Dict[str, str]] = {
    "simulation": {
        "cocotb": "cocotb: Coroutine-based Python verification framework for HDL simulators.",
        "covered": "Covered: Verilog code-coverage analysis tool.",
        "ghdl": "GHDL: Open-source VHDL simulator and compiler.",
        "iverilog": "Icarus Verilog: Open-source Verilog-2005 simulator.",
        "verilator": "Verilator: High-performance SystemVerilog simulator.",
    },
    "debug": {
        "gtkwave": "GTKWave: Waveform viewer for VCD/FST files.",
    },
    "ide": {
        "vscode": "VS Code: IDE for RTL development.",
    },
    "synthesis": {
        "yosys": "Yosys + Slang: RTL-to-gate synthesis tool with extended SystemVerilog frontend support.",
    },
    "frontend": {
        "surelog": "Surelog: SystemVerilog parser, elaborator, and UHDM frontend.",
        "sv2v": "sv2v: SystemVerilog-to-Verilog converter for toolchain compatibility.",
    },
    "formal": {
        "boolector": "Boolector: SMT solver optimized for bit-vectors and arrays (Tier-1).",
        "bitwuzla": "Bitwuzla: High-performance bitvector and array SMT solver (Tier-2).",
        "cvc5": "CVC5: SMT solver with quantifier support and theory combinations (Tier-2).",
        "symbiyosys": "SymbiYosys: Formal verification frontend.",
        "yices": "Yices: SMT solver for quantifier-free logic (Tier-2).",
        "z3": "Z3: General-purpose SMT solver (Tier-1, default for formal verification).",
    },
    "fpga": {
        "nextpnr": "NextPNR: Place-and-route for FPGA.",
        "openfpgaloader": "Bitstream uploader for FPGAs.",
        "vivado": "Xilinx Vivado: Full-featured FPGA design suite for Xilinx devices.",
    },
    "asic": {
        "openroad": "OpenROAD: Digital ASIC backend flow.",
        "opensta": "OpenSTA: Static timing analysis engine for digital ASIC flows.",
        "magic": "Magic: Layout editor for VLSI.",
        "klayout": "KLayout: Layout/GDS viewer.",
        "netgen": "Netgen: LVS comparison tool.",
        "rggen": "RgGen: Register map code generator for control/status registers.",
    },
    # Dependency and build orchestration
    "deps": {
        "bender": "Bender: HDL dependency & source manager (filelists/scripts).",
        "fusesoc": "FuseSoC: Core/package manager and build orchestration framework for HDL projects.",
    },
    # Embedded software / RISC-V bring-up
    "software": {
        "riscv-toolchain": "RISC-V GNU Toolchain: Cross-compiler suite for bare-metal RISC-V firmware.",
        "spike": "Spike: RISC-V ISA reference simulator for ISA-level validation.",
    },
}

# Computed description map (for questionary CLI)
TOOL_DESCRIPTIONS: Dict[str, str] = {
    tool: f"[{category.capitalize()}] {desc}"
    for category, group in TOOLS.items()
    for tool, desc in group.items()
}

# -----------------------------------------------------------------------------
# Minimum Required Versions for Key Tools (for diagnose/health checks)
# -----------------------------------------------------------------------------
MIN_TOOL_VERSIONS: Dict[str, str] = {
    "yosys": "0.27",
    "cocotb": "1.8",
    "fusesoc": "2.4",
    "ghdl": "2.0",
    "iverilog": "10.3",
    "verilator": "5.0",
    "gtkwave": "3.3.100",
    "nextpnr": "0.2",
    "openfpgaloader": "0.7.0",
    "openroad": "2.0",
    "klayout": "0.26.0",
    "magic": "8.3",
    "netgen": "1.5.192",
    "symbiyosys": "1.0",
    "boolector": "1.0",   # apt package ships 1.5.x (Debian boolector3 branch)
    "bitwuzla": "0.3.0",  # Tier-2: bitvector reasoning
    "cvc5": "1.0.0",      # Tier-2: quantifiers + theory combinations
    "yices": "2.6.0",     # Tier-2: QF logic + arithmetic
    "z3": "4.8",
    "vscode": "1.60",
    # Second batch
    "rggen": "0.36",
    "covered": "0.9",
    "sv2v": "2023.1",
    # TODO: Add/update as needed when diagnose grows or when adding new tools.
}
