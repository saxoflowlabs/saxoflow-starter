# saxoflow/tools/definitions.py

# ------------------------------------
# Tool Groupings (functional layers)
# ------------------------------------

SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader", "vivado"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["gtkwave", "yosys"]
IDE_TOOLS = ["vscode"]

ALL_TOOLS = SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + IDE_TOOLS

# ------------------------------------
# APT-managed tools (simple system packages)
# ------------------------------------
APT_TOOLS = [
    "gtkwave",
    "iverilog",
    "klayout",
    "magic",
    "netgen",
    "openfpgaloader"
]

# ------------------------------------
# SaxoFlow-managed tools (script recipes)
# ------------------------------------
SCRIPT_TOOLS = {
    "verilator": "scripts/recipes/verilator.sh",
    "openroad": "scripts/recipes/openroad.sh",
    "nextpnr": "scripts/recipes/nextpnr.sh",
    "symbiyosys": "scripts/recipes/symbiyosys.sh",
    "vscode": "scripts/recipes/vscode.sh",
    "yosys": "scripts/recipes/yosys.sh",
    "vivado": "scripts/recipes/vivado.sh"
}

# ------------------------------------
# Tool Descriptions (used for CLI selection menus)
# ------------------------------------
TOOLS = {
    "simulation": {
        "iverilog": "Icarus Verilog: Open-source Verilog-2005 simulator.",
        "verilator": "Verilator: High-performance SystemVerilog simulator."
    },
    "debug": {
        "gtkwave": "GTKWave: Waveform viewer for VCD/FST files."
    },
    "ide": {
        "vscode": "VS Code: IDE for RTL development."
    },
    "synthesis": {
        "yosys": "Yosys + Slang: RTL-to-gate synthesis tool with extended SystemVerilog frontend support."
    },
    "formal": {
        "symbiyosys": "SymbiYosys: Formal verification frontend."
    },
    "fpga": {
        "nextpnr": "NextPNR: Place-and-route for FPGA.",
        "openfpgaloader": "Bitstream uploader for FPGAs.",
        "vivado": "Xilinx Vivado: Full-featured FPGA design suite for Xilinx devices."
    },
    "asic": {
        "openroad": "OpenROAD: Digital ASIC backend flow.",
        "magic": "Magic: Layout editor for VLSI.",
        "klayout": "KLayout: Layout/GDS viewer.",
        "netgen": "Netgen: LVS comparison tool."
    }
}

# ------------------------------------
# Minimum Required Versions for Key Tools (for diagnose/health checks)
# ------------------------------------
MIN_TOOL_VERSIONS = {
    "yosys": "0.27",
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
    "vscode": "1.60",
    # Add more as needed...
}

# ------------------------------------
# Computed description map (for questionary CLI)
# ------------------------------------
TOOL_DESCRIPTIONS = {
    tool: f"[{category.capitalize()}] {desc}"
    for category, group in TOOLS.items()
    for tool, desc in group.items()
}
