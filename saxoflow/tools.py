TOOL_DESCRIPTIONS = {
    # --- Common tools ---
    "iverilog": "[Simulation] Icarus Verilog: Verilog-2005 simulator (RTL verification)",
    "verilator": "[Simulation] Verilator: Fast Verilog/SystemVerilog simulator (partial SV, synthesizable subset)",
    "gtkwave": "[Debug] GTKWave: View simulation waveforms (VCD/FST)",
    "vscode": "[IDE] VSCode: IDE for RTL/HDL (syntax highlighting, extensions)",

    # --- Shared design tools ---
    "yosys": "[Synthesis] Yosys: Open-source synthesis tool for Verilog (supports most of Verilog-2005)",
    "symbiyosys": "[Formal] SymbiYosys: Formal verification front-end using Yosys and solvers",

    # --- FPGA-specific tools ---
    "nextpnr": "[Implementation – FPGA] nextpnr: Place & route for FPGAs (iCE40, ECP5, Gowin)",
    "openfpgaloader": "[Programming – FPGA] openFPGALoader: Bitstream uploader to FPGA boards",

    # --- ASIC-specific tools ---
    "openroad": "[Implementation – ASIC] OpenROAD: RTL-to-GDSII digital flow (floorplan, CTS, routing)",
    "magic": "[Layout – ASIC] Magic: Full custom VLSI layout editor (standard cell + analog), supports DRC",
    "klayout": "[Layout Viewer – ASIC] KLayout: GUI GDSII layout viewer, used for inspection and viewing final layout",
    "netgen": "[LVS – ASIC] Netgen: Netlist comparison and Layout vs. Schematic (LVS) checking"
}
