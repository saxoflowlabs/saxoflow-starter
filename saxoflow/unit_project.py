import click
from pathlib import Path
import shutil
import sys

PROJECT_STRUCTURE = [
    "source/specification",
    "source/rtl/verilog",
    "source/rtl/vhdl",
    "source/rtl/systemverilog",
    "simulation/icarus",
    "simulation/verilator",
    "synthesis/src",
    "synthesis/scripts",
    "synthesis/reports",
    "synthesis/out",
    "formal/src",
    "formal/scripts",
    "formal/reports",
    "formal/out",
    "constraints",
    "pnr"
]

# ---- Yosys synthesis script template ----
YOSYS_SYNTH_TEMPLATE = """\
# ==============================================
#    SaxoFlow Professional Yosys Synthesis Script
#    (Step-by-step, as per full ASIC/FPGA flows)
# ==============================================

# 0. [OPTIONAL] Clean slate
# Uncomment if you want to clear previous state in interactive runs
# yosys reset

#######################################
###### Read Technology Libraries ######
#######################################

# ASIC: Read your liberty file for standard cells
# read_liberty -lib ../constraints/your_tech.lib

# ASIC: (Optional) SRAM macros, IO pads
# read_liberty -lib ../constraints/sram.lib
# read_liberty -lib ../constraints/io.lib

#########################
###### Load Design ######
#########################

# Enable SystemVerilog frontend (slang plugin), if needed:
# plugin -i slang

# For Verilog
read_verilog ../source/rtl/verilog/*.v

# For SystemVerilog (with slang plugin)
# read_verilog -sv ../source/rtl/systemverilog/*.sv

# For VHDL (if yosys built with VHDL support)
# read_vhdl ../source/rtl/vhdl/*.vhd

#########################
###### Elaboration ######
#########################

# Set your top module (edit as needed)
hierarchy -check -top <EDIT_HERE:top_module_name>

# Convert processes to netlists
proc

# Optimize and flatten
opt
flatten

# Export pre-synth report/netlist (optional)
# stat
# write_verilog ../synthesis/out/elaborated.v

####################################
###### Coarse-grain Synthesis ######
####################################

# Early-stage design check (structural checks)
check

# First optimization pass (before FF mapping)
opt

# Extract FSMs, report
fsm
fsm -nomap
fsm -expand
fsm -dotfsm ../synthesis/reports/fsm.dot

# Perform word reduction (optimize bitwidths)
wreduce

# Infer memories and optimize register-files
memory
memory_bram
memory_map

# Optimize flip-flops
opt_clean
opt_merge
dfflibmap -liberty ../constraints/your_tech.lib

###########################################
###### Define Target Clock Frequency ######
###########################################

# Define clock period (replace <value> in ns)
# set clk_period <EDIT_HERE:value>

##################################
###### Fine-grain synthesis ######
##################################

# Generic cell substitution and further mapping
techmap

# Final optimization
opt

# Generate post-synth report
stat

############################
###### Flatten design ######
############################

# Before flattening, you can preserve hierarchy for key modules:
# yosys setattr -set keep_hierarchy 1 "t:<module-name>$*"
# For example:
# yosys setattr -set keep_hierarchy 1 "t:my_cpu$*"

# Then flatten
flatten

################################
###### Technology Mapping ######
################################

# Register mapping
dfflibmap -liberty ../constraints/your_tech.lib

# Combinational logic mapping
abc -liberty ../constraints/your_tech.lib

# Final post-mapping report
stat

# Export final synthesized netlist
write_verilog ../synthesis/out/synthesized.v

# Optional: Export in other formats for P&R tools
# write_json ../synthesis/out/synthesized.json
# write_blif ../synthesis/out/synthesized.blif

#######################################
###### Prepare for OpenROAD flow ######
#######################################

# Split multi-bit nets
splitnets -format $_[0-9]+

# Replace undefined constants with drivers (ASIC)
setundef -zero

# Replace constant bits with driver cells (ASIC)
# (Optional, needed only for some flows)
# opt_const

# Export for OpenROAD
write_verilog ../pnr/synth2openroad.v

exit

# ==========================
#    TIPS & GUIDELINES
# ==========================
# 1. All steps are optional: comment/uncomment for your flow!
# 2. For FPGA, skip liberty/abc steps unless using custom mapping.
# 3. For custom reports: stat -liberty <libfile>
# 4. For more examples: https://yosyshq.net/yosys/documentation.html
"""

@click.command()
@click.argument("name", required=True)
def unit(name):
    """📁 Create a new SaxoFlow professional project structure."""
    root = Path(name)

    if root.exists():
        click.secho("❗ Project folder already exists. Aborting.", fg="red")
        sys.exit(1)

    click.secho(f"📂 Initializing project: {name}", fg="green")
    root.mkdir(parents=True)

    # Create subdirectories and add .gitkeep
    for sub in PROJECT_STRUCTURE:
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()

    # Copy base Makefile template if available
    template_path = Path(__file__).parent.parent / "templates" / "Makefile"
    if template_path.exists():
        shutil.copy(template_path, root / "Makefile")
        click.secho("✅ Makefile template added.", fg="cyan")
    else:
        click.secho("⚠️ Makefile template not found. Please add one manually.", fg="yellow")

    # Write the Yosys synthesis template to synthesis/scripts/synth.ys
    synth_script_path = root / "synthesis/scripts/synth.ys"
    with open(synth_script_path, "w") as f:
        f.write(YOSYS_SYNTH_TEMPLATE)
    click.secho("✅ Yosys synthesis script template added: synthesis/scripts/synth.ys", fg="cyan")

    # Final summary
    click.secho("🎉 Project initialized successfully!", fg="green", bold=True)
    click.secho(f"👉 Next: cd {name} && make sim-icarus", fg="blue")
