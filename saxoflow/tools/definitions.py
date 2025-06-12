# saxoflow/tools/definitions.py

# Tool Groupings
SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader"]
ASIC_TOOLS = ["klayout", "magic", "netgen", "openroad"]
BASE_TOOLS = ["yosys", "gtkwave"]
IDE_TOOLS = ["vscode"]

ALL_TOOLS = SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + IDE_TOOLS

# Scripted install tools (shell recipes)
SCRIPT_TOOLS = {
    "verilator": "scripts/recipes/verilator.sh",
    "openroad": "scripts/recipes/openroad.sh",
    "vscode": "scripts/recipes/vscode.sh",
    "nextpnr": "scripts/recipes/nextpnr.sh",
    "symbiyosys": "scripts/recipes/symbiyosys.sh"
}

# Tool descriptions for CLI and UI
TOOLS = {
    "simulation": {
        "iverilog": "Icarus Verilog: Open-source Verilog-2005 simulator.",
        "verilator": "Verilator: High-performance SystemVerilog simulator (synthesizable subset only)."
    },
    "debug": {
        "gtkwave": "GTKWave: Waveform viewer for VCD/FST files."
    },
    "ide": {
        "vscode": "VS Code: Versatile IDE with HDL syntax support."
    },
    "synthesis": {
        "yosys": "Yosys: Open-source synthesis tool for Verilog RTL."
    },
    "formal": {
        "symbiyosys": "SymbiYosys: Formal verification frontend using Yosys + SMT solvers."
    },
    "fpga": {
        "nextpnr": "nextpnr: Open-source FPGA place-and-route (iCE40, ECP5, Gowin).",
        "openfpgaloader": "openFPGALoader: Bitstream uploader for FPGA boards."
    },
    "asic": {
        "openroad": "OpenROAD: Digital ASIC flow for RTL-to-GDSII.",
        "magic": "Magic: VLSI layout editor with DRC support.",
        "klayout": "KLayout: GDSII layout viewer.",
        "netgen": "Netgen: Layout vs. Schematic comparison (LVS)."
    }
}

TOOL_DESCRIPTIONS = {
    tool: f"[{category.capitalize()}] {desc}"
    for category, group in TOOLS.items()
    for tool, desc in group.items()
}
