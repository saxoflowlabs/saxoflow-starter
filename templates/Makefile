# -----------------------------------
# SaxoFlow Universal Makefile (Pro Layout, Waveform Ready + Simulate Shortcuts)
# -----------------------------------

TOP_TB        ?= top_tb
VERILOG_SRC   := source/rtl/verilog/*.v
VHDL_SRC      := source/rtl/vhdl/*.vhd
SV_SRC        := source/rtl/systemverilog/*.sv
TB_SV_SRC     := source/tb/systemverilog/*.sv
TB_V_SRC      := source/tb/verilog/*.v
TB_VHDL_SRC   := source/tb/vhdl/*.vhd
RTL_SRCS      ?= $(wildcard $(VERILOG_SRC)) $(wildcard $(SV_SRC))
TB_SRCS       ?= $(wildcard $(TB_V_SRC)) $(wildcard $(TB_SV_SRC))
INCLUDE_DIRS  ?= -Isource/rtl/include
ICARUS_SIMDIR := simulation/icarus
VERILATOR_SIMDIR := simulation/verilator
SYNTH_SRC     := synthesis/src
SYNTH_SCRIPTS := synthesis/scripts
SYNTH_REPORTS := synthesis/reports
SYNTH_OUT     := synthesis/out
YOSYS_BIN     ?= yosys
YOSYS_SCRIPT  ?= synthesis/scripts/synth.ys
FORMAL_SCRIPTS := formal/scripts
FORMAL_REPORTS := formal/reports
FORMAL_OUT    := formal/out
LINT_REPORTS  := lint/reports
SBY_FILE      ?= ../scripts/spec.sby
SBY_TASK      ?=
SBY_TIMEOUT   ?=
SBY_AUTOTUNE  ?=
SBY_DUMPTASKS ?=
SBY_DUMPCFG   ?=
SBY_SOLVER    ?=

# Default target
.PHONY: all
all: sim-icarus

# ======== Icarus Verilog Simulation ========
.PHONY: sim sim-icarus
sim: sim-icarus

sim-icarus:
	@mkdir -p $(ICARUS_SIMDIR)
	@if [ -z "$(strip $(RTL_SRCS))" ]; then \
		printf "\033[1;31m[ERROR]\033[0m No RTL sources found. Add .v/.sv files or pass RTL_SRCS=...\n"; \
		exit 1; \
	fi
	@if [ -z "$(strip $(TB_SRCS))" ]; then \
		printf "\033[1;31m[ERROR]\033[0m No testbench sources found. Add .v/.sv files or pass TB_SRCS=...\n"; \
		exit 1; \
	fi
	iverilog -g2012 -Wall $(INCLUDE_DIRS) -o $(ICARUS_SIMDIR)/$(TOP_TB).vvp $(RTL_SRCS) $(TB_SRCS)
	cd $(ICARUS_SIMDIR) && vvp $(TOP_TB).vvp

# ======== Verilator Simulation (Build) ========
.PHONY: sim-verilator
sim-verilator:
	@mkdir -p $(VERILATOR_SIMDIR)/obj_dir
	verilator --cc $(VERILOG_SRC) $(SV_SRC) $(TB_V_SRC) $(TB_SV_SRC) $(TB_VHDL_SRC) \
		--exe $(VERILATOR_SIMDIR)/$(TOP_TB).cpp \
		--Mdir $(VERILATOR_SIMDIR)/obj_dir --build --timing --trace

# ======== Verilator Simulation (Run) ========
.PHONY: sim-verilator-run
sim-verilator-run:
	cd $(VERILATOR_SIMDIR)/obj_dir && ./V$(TOP_TB)

# ======== Waveform Viewer (GTKWave) ========
.PHONY: wave wave-verilator
wave:
	gtkwave $(ICARUS_SIMDIR)/$(TOP_TB).vcd &
wave-verilator:
	gtkwave $(VERILATOR_SIMDIR)/obj_dir/$(TOP_TB).vcd &

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
	@if [ -f "$(YOSYS_SCRIPT)" ]; then \
		"$(YOSYS_BIN)" -s "$(YOSYS_SCRIPT)" > $(SYNTH_REPORTS)/yosys.log 2>&1; \
	else \
		printf "\033[1;31m[ERROR]\033[0m No synthesis script found: %s\n" "$(YOSYS_SCRIPT)"; \
		exit 1; \
	fi

# ======== Formal Verification (SymbiYosys) ========
.PHONY: formal
formal:
	@mkdir -p $(FORMAL_REPORTS) $(FORMAL_OUT)
	@if [ -f $(FORMAL_SCRIPTS)/spec.sby ]; then \
		cd $(FORMAL_REPORTS) && \
		SBY_FLAGS=""; \
		if [ -n "$(SBY_TIMEOUT)" ]; then SBY_FLAGS="$$SBY_FLAGS --timeout $(SBY_TIMEOUT)"; fi; \
		if [ -n "$(SBY_AUTOTUNE)" ]; then SBY_FLAGS="$$SBY_FLAGS --autotune"; fi; \
		if [ -n "$(SBY_DUMPTASKS)" ]; then SBY_FLAGS="$$SBY_FLAGS --dumptasks"; fi; \
		if [ -n "$(SBY_DUMPCFG)" ]; then SBY_FLAGS="$$SBY_FLAGS --dumpcfg"; fi; \
		if [ -n "$(SBY_SOLVER)" ]; then \
			echo "[INFO] solver preference: $(SBY_SOLVER)"; \
		fi; \
		if [ -n "$(SBY_TASK)" ]; then \
			sby $$SBY_FLAGS -f $(SBY_FILE) $(SBY_TASK); \
		else \
			sby $$SBY_FLAGS -f $(SBY_FILE); \
		fi; \
	else \
		printf "\033[1;33m[WARN]\033[0m No formal spec found in %s\n" "$(FORMAL_SCRIPTS)/spec.sby"; \
	fi

# ======== Clean ========
.PHONY: clean
clean:
	rm -rf $(ICARUS_SIMDIR)/* $(VERILATOR_SIMDIR)/* $(SYNTH_REPORTS)/* $(SYNTH_OUT)/* $(FORMAL_REPORTS)/* $(FORMAL_OUT)/* $(LINT_REPORTS)/*

# ======== Help ========
.PHONY: help
help:
	@echo ""
	@echo "SaxoFlow Project Makefile (Pro Layout, Waveform Ready, Easy Simulate)"
	@echo "---------------------------------------------------------"
	@echo "make simulate            # Full Icarus flow (build, run, gtkwave)"
	@echo "make simulate-verilator  # Full Verilator flow (build, run, gtkwave)"
	@echo "make sim-icarus          # Icarus simulation (looks for .v/.sv RTL and TB files)"
	@echo "make sim-verilator       # Verilator build (looks for TBs in source/tb/verilog)"
	@echo "make sim-verilator-run   # Verilator run"
	@echo "make wave                # Launch GTKWave on simulation/icarus/dump.vcd"
	@echo "make wave-verilator      # Launch GTKWave on simulation/verilator/obj_dir/dump.vcd"
	@echo "make synth               # Run YOSYS_SCRIPT with YOSYS_BIN"
	@echo "make formal              # SymbiYosys formal run"
	@echo "make clean               # Clean all generated outputs"
