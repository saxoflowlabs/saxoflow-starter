# Tool Groups
SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["yosys", "gtkwave", "yosys_slang"]
IDE_TOOLS = ["vscode"]

ALL_TOOLS = SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + IDE_TOOLS

# APT tools
APT_TOOLS = [
    "gtkwave",
    "iverilog",
    "klayout",
    "magic",
    "netgen",
    "openfpgaloader"
]

# Script installers
SCRIPT_TOOLS = {
    "verilator": "scripts/recipes/verilator.sh",
    "openroad": "scripts/recipes/openroad.sh",
    "nextpnr": "scripts/recipes/nextpnr.sh",
    "symbiyosys": "scripts/recipes/symbiyosys.sh",
    "vscode": "scripts/recipes/vscode.sh",
    "yosys_slang": "scripts/recipes/yosys_slang.sh"
}

# Descriptions (unchanged, updated for yosys_slang)
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
        "yosys": "Yosys: Open-source synthesis for Verilog.",
        "yosys_slang": "Yosys + Slang: Extended SystemVerilog frontend support."
    },
    "formal": {
        "symbiyosys": "SymbiYosys: Formal verification frontend."
    },
    "fpga": {
        "nextpnr": "NextPNR: Place-and-route for FPGA.",
        "openfpgaloader": "Bitstream uploader for FPGAs."
    },
    "asic": {
        "openroad": "OpenROAD: Digital ASIC backend flow.",
        "magic": "Magic: Layout editor for VLSI.",
        "klayout": "KLayout: Layout/GDS viewer.",
        "netgen": "Netgen: LVS comparison tool."
    }
}

TOOL_DESCRIPTIONS = {
    tool: f"[{category.capitalize()}] {desc}"
    for category, group in TOOLS.items()
    for tool, desc in group.items()
}
