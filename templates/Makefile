# -----------------------------------
# SaxoFlow Universal Makefile (V2)
# -----------------------------------

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
# Icarus Verilog Simulation
# -----------------------
.PHONY: sim
sim:
	@mkdir -p $(BUILD_DIR)
	iverilog -g2012 -Wall -o $(BUILD_DIR)/out.vvp $(SIM_DIR)/*.v $(RTL_DIR)/*.v
	vvp $(BUILD_DIR)/out.vvp

# -----------------------
# Verilator Simulation
# -----------------------
.PHONY: sim-verilator
sim-verilator:
	verilator --cc $(SIM_DIR)/$(TOP_TB).v --exe $(SIM_DIR)/$(TOP_TB).cpp
	cd obj_dir && make -j $(MAKEFLAGS) -f V$(TOP_TB).mk V$(TOP_TB)
	obj_dir/V$(TOP_TB)

# -----------------------
# Waveform Viewer
# -----------------------
.PHONY: wave
wave:
	gtkwave $(VCD_FILE) &

# -----------------------
# Formal Verification
# -----------------------
.PHONY: formal
formal:
	@if [ -f $(FORMAL_DIR)/spec.sby ]; then \
		sby -f $(FORMAL_DIR)/spec.sby; \
	else \
		echo "⚠️ No formal spec found in $(FORMAL_DIR)/spec.sby"; \
	fi

# -----------------------
# Clean
# -----------------------
.PHONY: clean
clean:
	rm -rf $(BUILD_DIR) obj_dir *.vcd *.vvp *.fst $(VCD_FILE)

# -----------------------
# Help
# -----------------------
.PHONY: help
help:
	@echo ""
	@echo "🔧 SaxoFlow Project Makefile"
	@echo "---------------------------"
	@echo "make sim             # Icarus Verilog simulation"
	@echo "make sim-verilator   # Verilator simulation"
	@echo "make formal          # SymbiYosys formal run"
	@echo "make wave            # Launch GTKWave"
	@echo "make clean           # Clean build"
