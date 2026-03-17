# saxoflow/unit_project.py
"""
Project scaffolding utilities and CLI for SaxoFlow.

This module provides a Click command `unit` that initializes a professional
project structure for RTL → simulation/formal → synthesis flows.

Design goals
------------
- Preserve existing user-visible behavior and messages.
- Add clear docstrings, small helpers, and defensive error handling.
- Keep unused/legacy constructs commented for reference.
- PEP 8 / flake8 clean, Python 3.9+ compatible.

Notes
-----
- The original monolithic Yosys template string is kept **commented** to avoid
  flake8 E501 violations and to make edits easier. The active template is
  assembled from a list of shorter string literals and joined with newlines,
  producing the same end result for users (Yosys script content).
"""

from __future__ import annotations

import sys
import shutil
from pathlib import Path
from typing import Iterable, List, Sequence

import click

__all__ = ["unit"]

# ---------------------------------------------------------------------------
# Project structure definition
# ---------------------------------------------------------------------------

#: Directory tree created under the new project root.
PROJECT_STRUCTURE: Sequence[str] = [
    "source/specification",
    "source/rtl/include",
    "source/rtl/verilog",
    "source/rtl/vhdl",
    "source/rtl/systemverilog",
    "source/tb/verilog",
    "source/tb/vhdl",
    "source/tb/systemverilog",
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
    "pnr",
]

# ---------------------------------------------------------------------------
# Yosys synthesis script template
# ---------------------------------------------------------------------------

# --- Unused (kept for reference) --------------------------------------------
# The original monolithic triple-quoted template is retained to show the
# intended script body, but commented out to keep flake8 line length rules
# happy. If you prefer the original style, replace the active template with
# this block and add project-level E501 exceptions as needed.
#
# YOSYS_SYNTH_TEMPLATE = """\
# # ==============================================
# #    SaxoFlow Professional Yosys Synthesis Script
# #    (Step-by-step, as per full ASIC/FPGA flows)
# # ==============================================
# ...
# """  # noqa: E501 (if re-enabled)
# ---------------------------------------------------------------------------

def _yosys_template_lines() -> List[str]:
    """Return the Yosys synthesis script template as a list of lines.

    Using a list of shorter string literals allows us to satisfy flake8
    line-length constraints while producing the same on-disk file content.

    Returns
    -------
    list of str
        Lines to be joined with ``\n`` when writing the file.
    """
    return [
        "# ==============================================",
        "#    SaxoFlow Professional Yosys Synthesis Script",
        "#    (Step-by-step, as per full ASIC/FPGA flows)",
        "# ==============================================",
        "",
        "# 0. [OPTIONAL] Clean slate",
        "# Uncomment if you want to clear previous state in interactive runs",
        "# yosys reset",
        "",
        "#######################################",
        "###### Read Technology Libraries ######",
        "#######################################",
        "",
        "# ASIC: Read your liberty file for standard cells",
        "# read_liberty -lib ../constraints/your_tech.lib",
        "",
        "# ASIC: (Optional) SRAM macros, IO pads",
        "# read_liberty -lib ../constraints/sram.lib",
        "# read_liberty -lib ../constraints/io.lib",
        "",
        "#########################",
        "###### Load Design ######",
        "#########################",
        "",
        "# Enable SystemVerilog frontend (slang plugin), if needed:",
        "# plugin -i slang",
        "",
        "# For Verilog",
        "read_verilog ../source/rtl/verilog/*.v",
        "",
        "# For SystemVerilog (with slang plugin)",
        "# read_verilog -sv ../source/rtl/systemverilog/*.sv",
        "",
        "# For VHDL (if yosys built with VHDL support)",
        "# read_vhdl ../source/rtl/vhdl/*.vhd",
        "",
        "#########################",
        "###### Elaboration ######",
        "#########################",
        "",
        "# Set your top module (edit as needed)",
        "hierarchy -check -top <EDIT_HERE:top_module_name>",
        "",
        "# Convert processes to netlists",
        "proc",
        "",
        "# Optimize and flatten",
        "opt",
        "flatten",
        "",
        "# Export pre-synth report/netlist (optional)",
        "# stat",
        "# write_verilog ../synthesis/out/elaborated.v",
        "",
        "####################################",
        "###### Coarse-grain Synthesis ######",
        "####################################",
        "",
        "# Early-stage design check (structural checks)",
        "check",
        "",
        "# First optimization pass (before FF mapping)",
        "opt",
        "",
        "# Extract FSMs, report",
        "fsm",
        "fsm -nomap",
        "fsm -expand",
        "fsm -dotfsm ../synthesis/reports/fsm.dot",
        "",
        "# Perform word reduction (optimize bitwidths)",
        "wreduce",
        "",
        "# Infer memories and optimize register-files",
        "memory",
        "memory_bram",
        "memory_map",
        "",
        "# Optimize flip-flops",
        "opt_clean",
        "opt_merge",
        "dfflibmap -liberty ../constraints/your_tech.lib",
        "",
        "###########################################",
        "###### Define Target Clock Frequency ######",
        "###########################################",
        "",
        "# Define clock period (replace <value> in ns)",
        "# set clk_period <EDIT_HERE:value>",
        "",
        "##################################",
        "###### Fine-grain synthesis ######",
        "##################################",
        "",
        "# Generic cell substitution and further mapping",
        "techmap",
        "",
        "# Final optimization",
        "opt",
        "",
        "# Generate post-synth report",
        "stat",
        "",
        "############################",
        "###### Flatten design ######",
        "############################",
        "",
        "# Before flattening, you can preserve hierarchy for key modules:",
        '# yosys setattr -set keep_hierarchy 1 "t:<module-name>$*"',
        "# For example:",
        '# yosys setattr -set keep_hierarchy 1 "t:my_cpu$*"',
        "",
        "# Then flatten",
        "flatten",
        "",
        "################################",
        "###### Technology Mapping ######",
        "################################",
        "",
        "# Register mapping",
        "dfflibmap -liberty ../constraints/your_tech.lib",
        "",
        "# Combinational logic mapping",
        "abc -liberty ../constraints/your_tech.lib",
        "",
        "# Final post-mapping report",
        "stat",
        "",
        "# Export final synthesized netlist",
        "write_verilog ../synthesis/out/synthesized.v",
        "",
        "# Optional: Export in other formats for P&R tools",
        "## write_json ../synthesis/out/synthesized.json",
        "## write_blif ../synthesis/out/synthesized.blif",
        "",
        "#######################################",
        "###### Prepare for OpenROAD flow ######",
        "#######################################",
        "",
        "# Split multi-bit nets",
        "splitnets -format $_[0-9]+",
        "",
        "# Replace undefined constants with drivers (ASIC)",
        "setundef -zero",
        "",
        "# Replace constant bits with driver cells (ASIC)",
        "# (Optional, needed only for some flows)",
        "# opt_const",
        "",
        "# Export for OpenROAD",
        "write_verilog ../pnr/synth2openroad.v",
        "",
        "exit",
        "",
        "# ==========================",
        "#    TIPS & GUIDELINES",
        "# ==========================",
        "# 1. All steps are optional: comment/uncomment for your flow!",
        "# 2. For FPGA, skip liberty/abc steps unless using custom mapping.",
        "# 3. For custom reports: stat -liberty <libfile>",
        "# 4. For more examples: https://yosyshq.net/yosys/documentation.html",
    ]


# Active template built from short lines (flake8-friendly).
YOSYS_SYNTH_TEMPLATE: str = "\n".join(_yosys_template_lines())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_directories(root: Path, structure: Iterable[str]) -> None:
    """Create all project subdirectories and add ``.gitkeep`` files.

    Parameters
    ----------
    root
        Project root directory.
    structure
        Iterable of relative directory paths to create.

    Raises
    ------
    OSError
        If creating any directory or file fails.

    Notes
    -----
    This function preserves the original behavior of always creating a
    ``.gitkeep`` file in each created directory.
    """
    for sub in structure:
        path = root / sub
        path.mkdir(parents=True, exist_ok=True)
        (path / ".gitkeep").touch()


def _copy_makefile_template(root: Path) -> None:
    """Copy the Makefile template into the project if available.

    Parameters
    ----------
    root
        Project root directory.

    Notes
    -----
    - If the template is missing, a warning is printed (original behavior).
    - Template is expected at ``<repo>/templates/Makefile``.
    """
    template_path = Path(__file__).parent.parent / "templates" / "Makefile"
    if template_path.exists():
        shutil.copy(template_path, root / "Makefile")
        click.secho("SUCCESS: Makefile template added.", fg="green")
    else:
        click.secho("WARNING: Makefile template not found. Please add one manually.", fg="yellow")


def _write_yosys_template(root: Path, content: str) -> None:
    """Write the Yosys synthesis script template.

    Parameters
    ----------
    root
        Project root directory.
    content
        Text to write to ``synthesis/scripts/synth.ys``.
    """
    synth_script_path = root / "synthesis/scripts" / "synth.ys"
    with synth_script_path.open("w", encoding="utf-8") as f:
        f.write(content)
    click.secho(
        "SUCCESS: Yosys synthesis script template added: synthesis/scripts/synth.ys",
        fg="green",
    )


def _formal_spec_template() -> str:
        """Return a commented starter SymbiYosys spec for new unit projects.

        The template is intentionally conservative:
        - stable Tier-1 tasks are enabled by default,
        - Tier-2 examples are provided as commented snippets,
        - file names and top module names are obvious placeholders.
        """
        return """# SaxoFlow starter formal specification
#
# What this file is for:
# - SymbiYosys reads this file to decide which proof tasks to run.
# - Each task can choose a mode (bmc/prove/cover), depth, and solver engine.
# - This starter is intentionally simple so you can edit it without learning
#   the whole SBY syntax at once.
#
# First edits to make:
# 1. Replace 'dut.sv' below with your real RTL file name(s).
# 2. Replace 'formal_top' below if you rename the harness module.
# 3. Adjust depth values to match your design latency and proof goals.
# 4. Keep the Tier-1 tasks first; add Tier-2 tasks after the basic flow works.

[tasks]
# Fast bounded check with a widely compatible solver.
bmc_z3

# Alternative bounded check for bit-vector heavy designs.
bmc_boolector

# Proof-oriented task using induction.
prove_z3

# Optional examples for later exploration. Uncomment once your environment and
# design are stable enough for solver comparison experiments.
# bmc_yices
# bmc_cvc5
# bmc_bitwuzla

[options]
# BMC: search for counterexamples up to a bounded number of steps.
bmc_z3: mode bmc
bmc_z3: depth 20

bmc_boolector: mode bmc
bmc_boolector: depth 20

# Prove: run basecase + induction. Often the best next step after BMC passes.
prove_z3: mode prove
prove_z3: depth 20

# Tier-2 examples. Uncomment matching tasks above before enabling these.
# bmc_yices: mode bmc
# bmc_yices: depth 20
# bmc_cvc5: mode bmc
# bmc_cvc5: depth 20
# bmc_bitwuzla: mode bmc
# bmc_bitwuzla: depth 20

[engines]
bmc_z3: smtbmc z3
bmc_boolector: smtbmc boolector
prove_z3: smtbmc z3

# Tier-2 examples. These are useful for solver comparison and debugging.
# bmc_yices: smtbmc yices
# bmc_cvc5: smtbmc cvc5
# bmc_bitwuzla: smtbmc bitwuzla

[script]
# Read your DUT RTL plus the formal harness.
# Add more source files here if your design is split across multiple modules.
read -formal dut.sv formal_top.sv

# Set the harness as the proof top.
prep -top formal_top

[files]
# These paths are relative to formal/reports when SaxoFlow runs `sby`.
../../source/rtl/systemverilog/dut.sv
../src/formal_top.sv

# Notes:
# - If your project uses Verilog or VHDL instead, update the path accordingly.
# - If your harness instantiates packages/interfaces, add those source files too.
# - Start small: get one BMC task passing before adding more tasks or solvers.
"""


def _formal_harness_template() -> str:
        """Return a learner-friendly starter formal harness."""
        return """// SaxoFlow starter formal harness
//
// Purpose:
// - Instantiate your DUT in a small verification wrapper.
// - Declare symbolic inputs with (* anyseq *) or (* anyconst *).
// - Add assumptions for legal environment behavior.
// - Add assertions for the properties you want to prove.
//
// Suggested workflow:
// 1. Replace module/port names to match your DUT.
// 2. Keep only one or two simple assumptions/assertions at first.
// 3. Run BMC first, then try a prove task once BMC is clean.

module formal_top;
    // Use the global formal clock generated by Yosys/SymbiYosys.
    (* gclk *) reg clk;

    // Example symbolic stimulus. Rename or add signals to match your DUT.
    (* anyseq *) reg req;
    (* anyseq *) reg ack;

    // Example observed DUT signal.
    wire done;

    // Replace this example instance with your actual DUT and ports.
    dut u_dut (
        .clk(clk),
        .req(req),
        .ack(ack),
        .done(done)
    );

    // Track whether $past(...) is safe to use.
    reg past_valid = 1'b0;

    always @(posedge clk) begin
        past_valid <= 1'b1;

        // Example environment rule:
        // request and acknowledge should not be high at the same time.
        assume (!(req && ack));

        if (!past_valid) begin
            // Put power-on constraints here if your DUT has no reset.
            // Example:
            // assume(done == 1'b0);
        end else begin
            // Example safety property:
            // if done was low and ack is low, done should not rise unexpectedly.
            if (!$past(done) && !$past(ack)) assert (!done);

            // Add your real protocol, arithmetic, or state-machine properties here.
            // Good first properties for learners:
            // - illegal state is unreachable
            // - output only changes after a valid input event
            // - counter never exceeds a bound
            // - request is eventually followed by acknowledge (for cover/prove tasks)
        end
    end

    // Example cover statement for exploration.
    // Uncomment after the harness matches your DUT behavior.
    // always @(posedge clk) begin
    //   cover (past_valid && done);
    // end
endmodule
"""


def _write_formal_templates(root: Path) -> None:
        """Write starter formal artifacts (spec + harness) for quick adoption.

        Generates:
        - formal/scripts/spec.sby with documented, editable starter tasks
        - formal/src/formal_top.sv with a beginner-friendly example harness
        """
        spec_path = root / "formal/scripts/spec.sby"
        harness_path = root / "formal/src/formal_top.sv"
        spec_path.write_text(_formal_spec_template(), encoding="utf-8")
        harness_path.write_text(_formal_harness_template(), encoding="utf-8")

        click.secho(
                "SUCCESS: Formal starter templates added: formal/scripts/spec.sby, formal/src/formal_top.sv",
                fg="green",
        )


def _write_bender_manifest(root: Path, project_name: str) -> None:
    """Create a starter Bender.yml manifest for source/filelist management.

    The manifest defines basic targets:
      - rtl: core RTL sources
      - sim: testbench-only files
      - synth: synthesis-only add-ons (optional)

    Users can then run, for example:
      bender update
      bender script verilator --target sim
      bender script synopsys --target synth
    """
    content = f"""# Bender manifest generated by SaxoFlow (unit project)
package:
  name: "{project_name}"
  version: "0.1.0"
  description: "SaxoFlow unit project"

# Add external IPs or libraries here (git/https/paths)
dependencies: {{}}

# Group sources by purpose; select with --target <name>
sources:
  # Core RTL used in all flows
  - files:
      - source/rtl/verilog/*.v
      - source/rtl/systemverilog/*.sv
      - source/rtl/vhdl/*.vhd
    include_dirs:
      - source/rtl/include
    target: [rtl]

  # Simulation-only files (testbenches, sim models)
  - files:
      - source/tb/verilog/*.v
      - source/tb/systemverilog/*.sv
      - source/tb/vhdl/*.vhd
    target: [sim]

  # Synthesis-only add-ons (wrappers, blackboxes, etc.)
  - files:
      - synthesis/src/*.v
    target: [synth]

# Tips:
# - Use `bender update` to resolve deps and write Bender.lock (commit it).
# - Use `Bender.local` for local edits/paths; keep it out of version control.
"""
    manifest = root / "Bender.yml"
    with manifest.open("w", encoding="utf-8") as f:
        f.write(content)
    click.secho("SUCCESS: Bender manifest added: Bender.yml", fg="green")


def _ensure_gitignore_bender_local(root: Path) -> None:
    """Append Bender.local to .gitignore (idempotent)."""
    gi_path = root / ".gitignore"
    try:
        existing = gi_path.read_text(encoding="utf-8") if gi_path.exists() else ""
    except OSError:
        existing = ""
    if "Bender.local" not in existing:
        try:
            with gi_path.open("a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("# SaxoFlow/Bender local overrides\nBender.local\n")
            click.secho("SUCCESS: Updated .gitignore with Bender.local", fg="green")
        except OSError:
            click.secho("WARNING: Could not update .gitignore for Bender.local", fg="yellow")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.argument("name", required=True)
def unit(name: str) -> None:
    """Create a new SaxoFlow project structure.

    Parameters
    ----------
    name
        Name of the new project folder to create.

    Behavior
    --------
    - Aborts if the folder already exists (exit code 1), preserving the
      original message and behavior.
    - Creates the directory tree and adds a Makefile template (if present).
    - Writes ``synthesis/scripts/synth.ys`` with a ready-to-edit Yosys script.
        - Writes starter formal templates in ``formal/scripts/spec.sby`` and
            ``formal/src/formal_top.sv``.
    - Prints the same success/tip messages as the original implementation.
    """
    root = Path(name)

    if root.exists():
        click.secho("ERROR: Project folder already exists. Aborting.", fg="red")
        sys.exit(1)

    click.secho(f"INFO: Initializing project: {name}", fg="cyan")

    try:
        root.mkdir(parents=True, exist_ok=False)
        _create_directories(root, PROJECT_STRUCTURE)
        _copy_makefile_template(root)
        _write_yosys_template(root, YOSYS_SYNTH_TEMPLATE)
        _write_formal_templates(root)
        _write_bender_manifest(root, name)          # <- Bender: new
        _ensure_gitignore_bender_local(root)        # <- Bender: new (optional)
    except OSError as exc:
        # Fail fast with a clear message; avoids leaving a half-baked project.
        click.secho(f"ERROR: Failed to initialize project: {exc}", fg="red")
        sys.exit(1)

    # Final summary (unchanged)
    click.secho("SUCCESS: Project initialized successfully!", fg="green", bold=True)
    click.secho(f"TIP: Next: cd {name} && make sim-icarus", fg="cyan")
