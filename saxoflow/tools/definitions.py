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
    LINT_TOOLS,
    ETHZ_IC_DESIGN_TOOLS,
)

__all__ = [
    # Public constants / mappings
    "APT_TOOLS",
    "APT_PACKAGE_MAP",
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
    "LINT_TOOLS",
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
    "openocd",
    "openfpgaloader",
    "qemu-system-riscv64",
    "z3",
]

# Some tool keys are command names while apt package names differ.
APT_PACKAGE_MAP: Dict[str, str] = {
    "qemu-system-riscv64": "qemu-system-misc",
}

# -----------------------------------------------------------------------------
# SaxoFlow-managed tools (script recipes)
# -----------------------------------------------------------------------------
SCRIPT_TOOLS: Dict[str, str] = {
    "bitwuzla": "scripts/recipes/bitwuzla.sh",
    "cocotb": "scripts/recipes/cocotb.sh",
    "covered": "scripts/recipes/covered.sh",
    "cvc5": "scripts/recipes/cvc5.sh",
    "fusesoc": "scripts/recipes/fusesoc.sh",
    "gem5": "scripts/recipes/gem5.sh",
    "kactus2": "scripts/recipes/kactus2.sh",
    "openram": "scripts/recipes/openram.sh",
    "verilator": "scripts/recipes/verilator.sh",
    "openroad": "scripts/recipes/openroad.sh",
    "opensta": "scripts/recipes/opensta.sh",
    "nextpnr": "scripts/recipes/nextpnr.sh",
    "nvc": "scripts/recipes/nvc.sh",
    "rggen": "scripts/recipes/rggen.sh",
    "riscv-toolchain": "scripts/recipes/riscv-toolchain.sh",
    "riscv-pk": "scripts/recipes/riscv-pk.sh",
    "riscv-vp-plusplus": "scripts/recipes/riscv-vp-plusplus.sh",
    "renode": "scripts/recipes/renode.sh",
    "siliconcompiler": "scripts/recipes/siliconcompiler.sh",
    "spike": "scripts/recipes/spike.sh",
    "surfer": "scripts/recipes/surfer.sh",
    "surelog": "scripts/recipes/surelog.sh",
    "sv2v": "scripts/recipes/sv2v.sh",
    "symbiyosys": "scripts/recipes/symbiyosys.sh",
    "verible": "scripts/recipes/verible.sh",
    "yices": "scripts/recipes/yices.sh",
    "vscode": "scripts/recipes/vscode.sh",
    "yosys": "scripts/recipes/yosys.sh",
    "vivado": "scripts/recipes/vivado.sh",
    "bender": "scripts/recipes/bender.sh",
    "edalize": "scripts/recipes/edalize.sh",
}


# -----------------------------------------------------------------------------
# Tool Descriptions (used for CLI selection menus)
# -----------------------------------------------------------------------------
TOOLS: Dict[str, Dict[str, str]] = {
    "simulation": {
        "cocotb": "cocotb: Coroutine-based Python verification framework for HDL simulators.",
        "covered": "Covered: Verilog code-coverage analysis tool.",
        "gem5": "gem5: Full-system architecture simulator for advanced research workflows.",
        "ghdl": "GHDL: Open-source VHDL simulator and compiler.",
        "iverilog": "Icarus Verilog: Open-source Verilog-2005 simulator.",
        "nvc": "NVC: High-performance VHDL compiler and simulator (optional cross-check backend).",
        "verilator": "Verilator: High-performance SystemVerilog simulator.",
    },
    "debug": {
        "gtkwave": "GTKWave: Waveform viewer for VCD/FST files.",
        "surfer": "Surfer: Modern waveform viewer with interactive signal exploration.",
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
    "lint": {
        "verible": "Verible: SystemVerilog linter and code formatter for style consistency and quality gates.",
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
        "edalize": "Edalize: Python EDA tool-flow abstraction library with multi-backend support.",
        "kactus2": "Kactus2: IP-XACT-based SoC/IP packaging and integration environment.",
        "siliconcompiler": "SiliconCompiler: Configurable chip build orchestration framework for reproducible flows.",
        "openram": "OpenRAM: Open-source SRAM compiler for advanced ASIC education/research.",
    },
    # Embedded software / RISC-V bring-up
    "software": {
        "riscv-toolchain": "RISC-V GNU Toolchain: Cross-compiler suite for bare-metal RISC-V firmware.",
        "riscv-pk": "riscv-pk (Proxy Kernel): Runtime loader/environment used with Spike and bring-up workflows.",
        "spike": "Spike: RISC-V ISA reference simulator for ISA-level validation.",
        "renode": "Renode: Scriptable system-level virtual platform for hardware/software co-development.",
        "riscv-vp-plusplus": "riscv-vp-plusplus: RISC-V virtual platform for architectural and bring-up research.",
        "qemu-system-riscv64": "QEMU RISC-V System Emulator: Full-system bring-up and firmware execution beyond ISA-only simulation.",
        "openocd": "OpenOCD: On-chip debug bridge for JTAG/SWD and GDB-based bring-up workflows.",
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
    "verible": "0.0-3800",  # Stable linter + formatter; ~6 months stable
    "qemu-system-riscv64": "7.0",
    "openocd": "0.11.0",
    "riscv-pk": "1.0",
    "surfer": "0.3.0",
    "edalize": "0.4.0",
    "nvc": "1.19.0",
    "kactus2": "3.14.0",
    "siliconcompiler": "0.20.0",
    "renode": "1.16.0",
    "gem5": "25.0",
    "riscv-vp-plusplus": "1.0.0",
    "openram": "1.2.0",
    # TODO: Add/update as needed when diagnose grows or when adding new tools.
}
