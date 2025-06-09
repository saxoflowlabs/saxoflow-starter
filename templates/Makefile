# Makefile for SaxoFlow HDL Projects

# Customize these if needed
TOP_TB      := top_tb
RTL_DIR     := rtl
SIM_DIR     := sim
FORMAL_DIR  := formal
BUILD_DIR   := build
VCD_FILE    := dump.vcd

# Default target
.PHONY: all
all: sim

# -----------------------
# Simulation (Icarus Verilog)
# -----------------------
.PHONY: sim
sim:
	@mkdir -p $(BUILD_DIR)
	iverilog -g2012 -o $(BUILD_DIR)/out.vvp $(SIM_DIR)/*.v $(RTL_DIR)/*.v
	vvp $(BUILD_DIR)/out.vvp

# -----------------------
# Simulation (Verilator)
# -----------------------
.PHONY: sim-verilator
sim-verilator:
	verilator --cc $(SIM_DIR)/$(TOP_TB).v --exe $(SIM_DIR)/$(TOP_TB).cpp
	cd obj_dir && make -j -f V$(TOP_TB).mk V$(TOP_TB)
	obj_dir/V$(TOP_TB)

# -----------------------
# Waveform Viewing
# -----------------------
.PHONY: wave
wave:
	gtkwave $(VCD_FILE) &

# -----------------------
# Formal Verification
# -----------------------
.PHONY: formal
formal:
	sby -f $(FORMAL_DIR)/spec.sby

# -----------------------
# Clean Build Artifacts
# -----------------------
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR) obj_dir *.vcd *.vvp $(VCD_FILE)

# -----------------------
# Help Message
# -----------------------
.PHONY: help
help:
	@echo "🔧 SaxoFlow Makefile Commands:"
	@echo ""
	@echo "make sim             # Run simulation with Icarus Verilog"
	@echo "make sim-verilator   # Run simulation with Verilator"
	@echo "make formal          # Run SymbiYosys formal verification"
	@echo "make wave            # Launch GTKWave to view waveforms"
	@echo "make clean           # Remove all generated build artifacts"
