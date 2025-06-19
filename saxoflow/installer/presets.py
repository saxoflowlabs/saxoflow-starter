# saxoflow/installer/presets.py

"""
Central Preset Configuration for SaxoFlow Installer

- Clean separation of tool groupings
- Fully maintainable for FPGA, ASIC, FORMAL, AI extensions
"""

# -------------------------
# Tool groups for easy reuse
# -------------------------

SIM_TOOLS = ["iverilog", "verilator"]
FORMAL_TOOLS = ["symbiyosys"]
FPGA_TOOLS = ["nextpnr", "openfpgaloader", "vivado"]
ASIC_TOOLS = ["openroad", "klayout", "magic", "netgen"]
BASE_TOOLS = ["gtkwave", "yosys"]
IDE_TOOLS = ["vscode"]
AGENTIC_TOOLS = ["agentic_ai"]  # <-- can link to agentic-ai repo later

# -------------------------
# Preset configurations
# -------------------------

PRESETS = {
    "minimal": IDE_TOOLS + ["iverilog", "gtkwave"],
    "fpga": IDE_TOOLS + ["verilator"] + FPGA_TOOLS + BASE_TOOLS,
    "asic": IDE_TOOLS + ["verilator"] + ASIC_TOOLS + BASE_TOOLS,
    "formal": IDE_TOOLS + ["yosys"] + FORMAL_TOOLS,
    "agentic-ai": AGENTIC_TOOLS,
    "full": list(set(SIM_TOOLS + FORMAL_TOOLS + FPGA_TOOLS + ASIC_TOOLS + BASE_TOOLS + IDE_TOOLS + AGENTIC_TOOLS))
}

# -------------------------
# Exportable Tool Groups (optional for CLI checks)
# -------------------------

ALL_TOOL_GROUPS = {
    "simulation": SIM_TOOLS,
    "formal": FORMAL_TOOLS,
    "fpga": FPGA_TOOLS,
    "asic": ASIC_TOOLS,
    "base": BASE_TOOLS,
    "ide": IDE_TOOLS,
    "agentic-ai": AGENTIC_TOOLS
}
