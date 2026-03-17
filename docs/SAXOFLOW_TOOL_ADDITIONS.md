# SaxoFlow Tool Additions

This document lists the external digital-design tools that are the best next additions to SaxoFlow, based on the current supported-tool surface, installer model, and workflow focus.

## Current Focus

SaxoFlow is currently centered on:

- RTL design and simulation
- Formal verification
- FPGA implementation
- ASIC digital backend
- Basic dependency and environment management

The recommendations below prioritize tools that strengthen that workflow directly.

## Recommended First Batch

Status: implemented in SaxoFlow.

These are the highest-value additions and were implemented with:

- installer recipes under `scripts/recipes/`
- tool registry entries in `saxoflow/tools/definitions.py`
- installer preset integration
- CI version checks in `.github/workflows/eda-tools.yml`

### 1. GHDL

Status: implemented as an APT-managed tool.

- Category: simulation / VHDL
- Why add it: fills the current VHDL simulation gap
- Value to SaxoFlow: enables VHDL users without changing the existing digital focus

### 2. cocotb

Status: implemented as a SaxoFlow-managed script installer.

- Category: verification
- Why add it: widely used Python-based verification framework
- Value to SaxoFlow: complements existing simulators and aligns well with Python-driven workflows

### 3. FuseSoC

Status: implemented as a SaxoFlow-managed script installer.

- Category: dependency and build orchestration
- Why add it: strong fit for reusable IP, core packaging, and SoC integration
- Value to SaxoFlow: improves dependency and project composition flows beyond raw filelists

### 4. OpenSTA

Status: implemented as a SaxoFlow-managed script installer.

- Category: ASIC timing analysis
- Why add it: major missing piece in the digital backend stack
- Value to SaxoFlow: enables explicit static timing analysis alongside OpenROAD flows

### 5. Surelog

Status: implemented as a SaxoFlow-managed script installer.

- Category: SystemVerilog front-end
- Why add it: stronger parsing and elaboration support for modern SystemVerilog
- Value to SaxoFlow: useful for more robust frontend handling in advanced RTL flows

## Recommended Second Batch

Status: implemented in SaxoFlow.

These were implemented with:

- installer recipes under `scripts/recipes/`
- tool registry entries in `saxoflow/tools/definitions.py`
- new `SW_TOOLS` preset group for RISC-V tools
- integration into `diagnose_tools.py` FLOW_PROFILES and `find_tool_binary`
- CI cache blocks and build steps in `.github/workflows/eda-tools.yml`
- tests in `tests/test_saxoflow/`

### 6. rggen

- Category: register generation
- Why add it: practical value for control/status register generation in SoC designs
- Value to SaxoFlow: improves project automation around registers and software-visible interfaces

### 7. RISC-V GNU Toolchain

- Category: embedded software / bring-up
- Why add it: needed for firmware flows when working with RISC-V designs
- Value to SaxoFlow: strengthens hardware-software co-development for SoC users

### 8. Spike

- Category: RISC-V ISA simulation
- Why add it: useful companion to the RISC-V toolchain
- Value to SaxoFlow: supports ISA-level validation and early software bring-up

### 9. Covered

- Category: verification coverage
- Why add it: code coverage is useful in verification-heavy projects
- Value to SaxoFlow: improves measurement of testbench effectiveness

### 10. sv2v

- Category: source conversion
- Why add it: helps translate SystemVerilog to Verilog for compatibility-sensitive flows
- Value to SaxoFlow: useful interoperability tool for mixed toolchains

## Phase 3 (Workflow Capability Bundles)

Status: proposed next stage after first and second batch completion.

Phase 3 should prioritize workflow depth over adding many standalone tools.
Each bundle below is intended to turn existing tool installs into complete,
user-facing SaxoFlow flows.

### A. Formal Solver Bundle

- Proposed components: `z3`, `boolector`, `bitwuzla` (or `yices` where packaging is easier)
- Scope: integrate solver selection into SymbiYosys flows and diagnostics
- Why now: strongest improvement in formal convergence and proof/debug flexibility
- Expected SaxoFlow additions:
	- installer entries (APT or script recipes)
	- `diagnose_tools.py` detection + version extraction
	- optional preset/profile (for example: formal-plus)
	- CI checks and minimal solver smoke tests

For the detailed implementation roadmap, see [Formal Solver Bundle Plan](formalsolver_plan.md).

### B. RTL Quality Bundle

- Proposed components: `verible` (linter + formatter)
- Scope: first-class lint/format workflows for RTL and generated artifacts
- Why now: improves code quality, readability, and review velocity for users and AI-generated code
- Expected SaxoFlow additions:
	- recipe and tool definitions
	- commands/workflow hooks for lint and format passes
	- CI gate checks on representative RTL examples

### C. RISC-V Bring-Up Bundle

- Proposed components: `qemu-system-riscv*`, `openocd`, optional `riscv-pk`
- Scope: firmware execution and debug workflows beyond ISA-only simulation
- Why now: extends current `riscv-toolchain` + `spike` support into practical HW/SW bring-up
- Expected SaxoFlow additions:
	- optional software bring-up preset/profile
	- standard run/debug helper commands
	- docs/tutorial path for firmware build -> run -> debug loop

### D. ASIC Flow Bundle

- Proposed components: `openlane2` environment profile (optional)
- Scope: reproducible higher-level RTL-to-GDS flow orchestration for learners
- Why now: leverages existing OpenROAD-centered stack without making it default-heavy
- Expected SaxoFlow additions:
	- profile-based setup (not mandatory in baseline install)
	- compatibility notes for supported PDK/environment assumptions
	- CI smoke flow that validates profile bootstrap

### E. Coverage Workflow Bundle

- Proposed components: build on existing `covered` support
- Scope: standardized coverage run/merge/report commands and report export paths
- Why now: converts current tool availability into measurable verification workflows
- Expected SaxoFlow additions:
	- coverage command wrappers in CLI/makeflow paths
	- consistent report directory conventions
	- sample project/docs demonstrating end-to-end usage

## Tools Already Effectively Covered

These should not be treated as new additions because SaxoFlow already supports them directly or indirectly:

- `abc` via the Yosys flow
- `slang` support through the existing Yosys + Slang plugin flow
- `sby` via `symbiyosys`
- `bender`
- `gtkwave`
- `iverilog`
- `klayout`
- `magic`
- `netgen`
- `nextpnr`
- `openfpgaloader`
- `openroad`
- `verilator`
- `vivado`
- `yosys`

## Not Recommended Right Now

These tool families are not the best fit for SaxoFlow's current scope and should not be prioritized now.

### Analog / RF / Mixed-Signal

- `ngspice`
- `xyce`
- `openems`
- `palace`
- `openvaf-reloaded`
- `qucs-s`
- `pyspice`
- `spyci`
- `spicelib`
- `vacask`
- `gmsh`

Reason: these move SaxoFlow into analog and RF territory, which is outside the current digital-first toolchain focus.

### Photonics / Layout Python Ecosystem

- `gdsfactory`
- `gdspy`
- `gds3d`

Reason: useful in other domains, but not strong matches for the current RTL-to-FPGA/ASIC workflow.

### Python Libraries Instead of External Tools

- `amaranth`
- `pyrtl`
- `pyverilog`
- `pyuvm`
- `hdl21`
- `vlsirtools`
- `schemdraw`

Reason: these are development libraries or frameworks, not first-class external tool installs of the same kind as Yosys, Verilator, or OpenROAD.

### PDK Payloads and PDK Managers

- `sky130`
- `gf180mcu`
- `ihp-sg13g2`
- `open_pdks`
- `ciel`

Reason: these should be handled as platform environments or optional technology bundles, not standard per-tool installer entries.

## Recommended Implementation Order

If SaxoFlow adds tools incrementally, the suggested order is:

1. `ghdl`
2. `cocotb`
3. `fusesoc`
4. `opensta`
5. `surelog`
6. `rggen`
7. `riscv-toolchain`
8. `spike`

This order improves the platform without expanding it into unrelated analog or PDK-management scope too early.