# Makefile for SaxoFlow projects

TB=top_tb

all: sim

sim:
	@mkdir -p build
	iverilog -g2012 -o build/out.vvp sim/*.v rtl/*.v && vvp build/out.vvp

sim-verilator:
	verilator --cc sim/$(TB).v --exe sim/$(TB).cpp
	cd obj_dir && make -j -f V$(TB).mk V$(TB)
	obj_dir/V$(TB)

wave:
	gtkwave dump.vcd &

formal:
	sby -f formal/spec.sby

clean:
	rm -rf build obj_dir *.vcd *.vvp

help:
	@echo "make sim             # Run simulation with Icarus Verilog"
	@echo "make sim-verilator   # Run simulation with Verilator"
	@echo "make formal          # Run SymbiYosys formal verification"
	@echo "make wave            # Launch GTKWave"
	@echo "make clean           # Remove all generated files"
