# -----------------------------------
# SaxoFlow Universal Makefile (Pro Layout, Waveform Ready + Simulate Shortcuts)
# -----------------------------------

TOP_TB        ?= top_tb
VERILOG_SRC   := source/rtl/verilog/*.v
VHDL_SRC      := source/rtl/vhdl
SV_SRC        := source/rtl/systemverilog
ICARUS_SIMDIR := simulation/icarus
VERILATOR_SIMDIR := simulation/verilator
SYNTH_SRC     := synthesis/src
SYNTH_SCRIPTS := synthesis/scripts
SYNTH_REPORTS := synthesis/reports
SYNTH_OUT     := synthesis/out
FORMAL_SCRIPTS := formal/scripts
FORMAL_REPORTS := formal/reports
FORMAL_OUT    := formal/out

# Default target
.PHONY: all
all: sim-icarus

# ======== Icarus Verilog Simulation ========
.PHONY: sim sim-icarus
sim: sim-icarus

sim-icarus:
	@mkdir -p $(ICARUS_SIMDIR)
	iverilog -g2012 -Wall -o $(ICARUS_SIMDIR)/out.vvp $(ICARUS_SIMDIR)/$(TOP_TB).v $(VERILOG_SRC)
	cd $(ICARUS_SIMDIR) && vvp out.vvp

# ======== Verilator Simulation (Build) ========
.PHONY: sim-verilator
sim-verilator:
	@mkdir -p $(VERILATOR_SIMDIR)/obj_dir
	verilator --cc $(VERILATOR_SIMDIR)/$(TOP_TB).v $(VERILOG_SRC) \
		--exe $(VERILATOR_SIMDIR)/$(TOP_TB).cpp \
		--Mdir $(VERILATOR_SIMDIR)/obj_dir --build --timing --trace

# ======== Verilator Simulation (Run) ========
.PHONY: sim-verilator-run
sim-verilator-run:
	cd $(VERILATOR_SIMDIR)/obj_dir && ./V$(TOP_TB)

# ======== Waveform Viewer (GTKWave) ========
.PHONY: wave wave-verilator
wave:
	gtkwave $$(ls -t $(ICARUS_SIMDIR)/*.vcd | head -n 1) &
wave-verilator:
	gtkwave $$(ls -t $(VERILATOR_SIMDIR)/obj_dir/*.vcd | head -n 1) &

# ======== One-Step Full Simulate Shortcuts ========
.PHONY: simulate simulate-verilator

simulate:
	$(MAKE) sim-icarus TOP_TB=$(TOP_TB)
	$(MAKE) wave

simulate-verilator:
	$(MAKE) sim-verilator TOP_TB=$(TOP_TB)
	$(MAKE) sim-verilator-run TOP_TB=$(TOP_TB)
	$(MAKE) wave-verilator

# ======== Synthesis (Yosys) ========
.PHONY: synth
synth:
	@mkdir -p $(SYNTH_REPORTS) $(SYNTH_OUT)
	@if [ -f $(SYNTH_SCRIPTS)/synth.ys ]; then \
		yosys -c $(SYNTH_SCRIPTS)/synth.ys > $(SYNTH_REPORTS)/yosys.log; \
	else \
		echo "⚠️ No synthesis script found in $(SYNTH_SCRIPTS)/synth.ys"; \
	fi

# ======== Formal Verification (SymbiYosys) ========
.PHONY: formal
formal:
	@mkdir -p $(FORMAL_REPORTS) $(FORMAL_OUT)
	@if [ -f $(FORMAL_SCRIPTS)/spec.sby ]; then \
		cd $(FORMAL_REPORTS) && sby -f ../scripts/spec.sby; \
	else \
		echo "⚠️ No formal spec found in $(FORMAL_SCRIPTS)/spec.sby"; \
	fi

# ======== Clean ========
.PHONY: clean
clean:
	rm -rf $(ICARUS_SIMDIR)/* $(VERILATOR_SIMDIR)/* $(SYNTH_REPORTS)/* $(SYNTH_OUT)/* $(FORMAL_REPORTS)/* $(FORMAL_OUT)/*

# ======== Help ========
.PHONY: help
help:
	@echo ""
	@echo "🔧 SaxoFlow Project Makefile (Pro Layout, Waveform Ready, Easy Simulate)"
	@echo "---------------------------------------------------------"
	@echo "make simulate            # Full Icarus flow (build, run, gtkwave)"
	@echo "make simulate-verilator  # Full Verilator flow (build, run, gtkwave)"
	@echo "make sim-icarus          # Icarus Verilog simulation"
	@echo "make sim-verilator       # Verilator build"
	@echo "make sim-verilator-run   # Verilator run"
	@echo "make wave                # Launch GTKWave on simulation/icarus/dump.vcd"
	@echo "make wave-verilator      # Launch GTKWave on simulation/verilator/obj_dir/dump.vcd"
	@echo "make synth               # Yosys synthesis"
	@echo "make formal              # SymbiYosys formal run"
	@echo "make clean               # Clean all generated outputs"
