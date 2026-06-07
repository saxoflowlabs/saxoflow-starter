# SaxoFlow Technical Reference

**Document purpose:** Authoritative developer reference for the current SaxoFlow codebase

**Audience:** SaxoFlow developers, contributors, instructors, researchers, and advanced users

**Reference snapshot:** June 7, 2026

**Validated supported test snapshot:** 1494 passed, 1 warning

**Project context:** SMACD, Smart Methods for Advanced Chip Design

This document describes the executable behavior of the current repository. The Python source, packaged data, Click registrations, and command help are authoritative when they disagree with historical documentation.

## 1. Interface Labels

SaxoFlow contains several distinct interfaces. This reference labels them explicitly so that internal APIs are not mistaken for stable commands.

| Label | Meaning |
|---|---|
| **Public CLI** | Supported command available through the installed `saxoflow` console entry point |
| **TUI-only** | Command or behavior available only inside the interactive SaxoFlow shell |
| **Agentic** | LLM-backed behavior that requires a configured provider and may modify project files |
| **Internal or experimental** | Developer subsystem without a stable public CLI contract |
| **Environment-dependent** | Requires external EDA tools, display support, PDK data, or optional Python packages |

## 2. Production Runtime Model

### 2.1 Installation and entry point

Production users install SaxoFlow as a Python application and invoke:

```bash
saxoflow
```

The console entry point is:

```text
saxoflow = saxoflow.cli:cli
```

The command has two operating modes:

```bash
saxoflow
```

Starts the interactive TUI in the resolved user workspace.

```bash
saxoflow <command> [options]
```

Runs a public CLI command without starting the TUI.

The repository-level `saxoflow.py` launcher exists for development and backward compatibility. It is not the recommended production entry point.

### 2.2 Application and workspace separation

Installed application code belongs in Python site-packages. User projects, generated files, examples, state, and agent logs belong in the user workspace.

```text
Python environment or site-packages
├── saxoflow/
├── cool_cli/
├── saxoflow_agenticai/
├── templates/
└── packaged teach packs and examples

~/SaxoFlow/
├── README.md
├── projects/
├── examples/
└── .saxoflow/
    ├── agent_sessions/
    └── runtime state
```

The TUI changes its working directory to the resolved workspace before accepting commands. Shell commands, path completion, `Path.cwd()` based operations, AI file creation, and project discovery therefore operate on user-owned files instead of the installed source tree.

### 2.3 Workspace resolution

Workspace selection follows this precedence:

1. Global `--workspace PATH`
2. `SAXOFLOW_WORKSPACE`
3. Saved runtime configuration
4. `~/SaxoFlow`

Examples:

```bash
saxoflow --workspace /work/chip-lab
SAXOFLOW_WORKSPACE=/work/chip-lab saxoflow
```

On first use, SaxoFlow creates:

```text
<workspace>/
├── README.md
├── projects/
├── examples/
└── .saxoflow/
```

Bundled examples are copied from package resources. Teach packs remain packaged read-only resources unless a lesson explicitly materializes editable starter files.

### 2.4 Configuration and state paths

Runtime configuration uses:

1. `SAXOFLOW_CONFIG_HOME`
2. `$XDG_CONFIG_HOME/saxoflow`
3. `~/.config/saxoflow`

Workspace state defaults to:

```text
<workspace>/.saxoflow/
```

Managed ORFS, PDK, and platform data use:

```text
~/.local/share/saxoflow/
├── orfs/
├── pdks/
├── platforms/
└── registry/
```

PDK content is never installed into site-packages or copied into a project by default.

## 3. Architecture

### 3.1 Runtime overview

```text
                         installed console entry
                                  |
                    +-------------+-------------+
                    |                           |
              no subcommand              public subcommand
                    |                           |
               cool_cli TUI              Click command tree
                    |                           |
        shell, AI routing, teach          flow and management APIs
                    |                           |
                    +-------------+-------------+
                                  |
                         user unit workspace
                                  |
       +------------+-------------+-------------+-------------+
       |            |             |             |             |
   simulation     formal         lint        synthesis        P&R
   Icarus or      SBY          Verible       Yosys          ORFS
   Verilator                    Verilator      |               |
                                                + NetlistSVG   OpenROAD
                                                              |
                                                    OpenSTA, KLayout
                                  |
                   reports, artifacts, and agent logs
```

### 3.2 PDK and physical-design architecture

```text
packaged platform manifests
            |
            v
   versioned PDK registry <---- custom platform manifests
            |
            v
 resolved platform object
            |
      platform lock
            |
   +--------+---------+
   |                  |
Yosys ASIC mapping   ORFS orchestration
   |                  |
mapped netlist       OpenROAD stages
                      |
        floorplan -> place -> CTS -> route -> finish
                      |
          ODB, reports, metrics, DEF, GDS
```

Generic orchestration consumes resolved platform metadata. It does not select behavior by hardcoded design name or unit name.

### 3.3 Repository map

The following map highlights current ownership boundaries rather than every file:

```text
HelloWorld/
├── saxoflow.py                      development launcher
├── pyproject.toml                   packaging and console entry
├── saxoflow/
│   ├── cli.py                       unified public Click CLI
│   ├── runtime_paths.py             workspace and runtime path policy
│   ├── unit_project.py              unit scaffolding
│   ├── makeflow.py                  generated Makefile support
│   ├── simflow.py                   simulation discovery and execution
│   ├── formalflow.py                formal discovery and SBY execution
│   ├── lintflow.py                  Verible and Verilator wrapper
│   ├── synthflow.py                 generated Yosys synthesis flow
│   ├── schematicflow.py             NetlistSVG generation and opening
│   ├── pdk_registry.py              manifest and platform resolution
│   ├── pdk_cli.py                   PDK lifecycle commands
│   ├── pnrflow.py                   ORFS and OpenROAD orchestration
│   ├── diagnose.py                  diagnosis command group
│   ├── diagnose_tools.py            environment inspection and repair
│   ├── teach_cli.py                 public teach commands
│   └── installer/                   tool catalog, groups, and presets
├── cool_cli/
│   ├── shell.py                     interactive shell and AI routing
│   ├── agent_session_log.py         user-facing session transparency
│   └── teach/                       interactive lesson runtime
├── saxoflow_agenticai/
│   ├── agents/                      registered agent implementations
│   ├── core/                        providers, orchestration, logging
│   └── cli/                         agentic command registrations
├── templates/                       packaged unit and flow templates
├── teach_packs/                     packaged lessons
├── scripts/
│   ├── recipes/                     source and tool installers
│   └── common/                      installer shell infrastructure
├── tests/
│   ├── test_coolcli/
│   ├── test_saxoflow/
│   └── test_saxoflow_agenticai/
└── docs/
```

## 4. Public Command Catalog

SaxoFlow currently registers 21 public top-level commands.

| Command | Category | Purpose |
|---|---|---|
| `agenticai` | Agentic | Run direct generator, reviewer, debug, flow, and provider commands |
| `check-tools` | Public CLI | Check required EDA tools |
| `clean` | Public CLI | Clean generated unit artifacts through the unit Makefile |
| `diagnose` | Public CLI | Inspect and repair environment problems |
| `formal` | Environment-dependent | Discover RTL and assertions, update `spec.sby`, and run SymbiYosys |
| `init-env` | Public CLI | Initialize local SaxoFlow environment configuration |
| `install` | Environment-dependent | Install tools, groups, or presets |
| `lint` | Environment-dependent | Lint RTL with Verible and Verilator |
| `pdk` | Environment-dependent | Manage platform manifests and PDK installations |
| `pnr` | Environment-dependent | Configure and run physical design |
| `schematic` | Environment-dependent | Render a Yosys JSON netlist with NetlistSVG |
| `sim` | Environment-dependent | Run Icarus simulation |
| `sim-verilator` | Environment-dependent | Compile a design with Verilator |
| `sim-verilator-run` | Environment-dependent | Run an existing Verilator executable |
| `simulate` | Environment-dependent | Run Icarus simulation and open a waveform |
| `simulate-verilator` | Environment-dependent | Compile and run with Verilator |
| `synth` | Environment-dependent | Run generic, FPGA, or ASIC Yosys synthesis |
| `teach` | Public CLI | List, index, start, and inspect teach packs |
| `unit` | Public CLI | Create a project unit |
| `wave` | Environment-dependent | Open an Icarus-produced VCD |
| `wave-verilator` | Environment-dependent | Open a Verilator-produced VCD |

### 4.1 Execution contracts

This table summarizes where commands run and what they depend on. Detailed options and artifacts are described in the later flow chapters.

| Command | Working directory | Main requirement | Primary output and failure behavior |
|---|---|---|---|
| `agenticai` | Usually a unit root | Provider credentials for LLM agents; EDA backend for flow agents | Generated files, reviews, tool output, and nonzero exit on command failure |
| `check-tools` | Any directory | None | Tool availability report |
| `clean` | Unit root | Unit Makefile | Removes generated artifacts after confirmation; `--yes` skips confirmation |
| `diagnose` | Any directory; unit root for project checks | Depends on selected diagnosis | Health report or repair result; unresolved required checks remain visible |
| `formal` | Unit root | SymbiYosys, Yosys, and a solver | Updated `spec.sby`, formal output, reports, and nonzero exit on failure |
| `init-env` | Any directory | Interactive terminal unless `--headless` | Saved tool selection for later `install selected` |
| `install` | Any directory | Network, disk space, and package privileges as needed | Installed tools and recipe logs; nonzero exit on unsupported mode or failed installation |
| `lint` | Unit root | Verible and/or Verilator | Timestamped lint reports and nonzero exit for findings unless `--no-fail` |
| `pdk` | Any directory | Network and disk for install; platform files for verify | Managed platform data, registry metadata, or verification report |
| `pnr` | Unit root | Locked platform, ORFS, OpenROAD, and mapped netlist or RTL | Per-variant logs, checkpoints, reports, and physical-design results |
| `schematic` | Unit root | NetlistSVG, Node.js, and Yosys JSON | SVG under `synthesis/reports/` by default |
| `sim` | Unit root | Icarus Verilog | Compiled simulation, VCD, stdout, and nonzero exit on compile or run failure |
| `sim-verilator` | Unit root | Verilator and unit Makefile | Compiled Verilator model |
| `sim-verilator-run` | Unit root | Previously compiled Verilator model | Simulation output and waveform |
| `simulate` | Unit root | Icarus and waveform viewer | Simulation result followed by waveform opening |
| `simulate-verilator` | Unit root | Verilator and unit Makefile | Compiled and executed model |
| `synth` | Unit root | Yosys; Slang for broader SystemVerilog | Generated Yosys script, logs, statistics, and netlists |
| `teach` | Workspace or selected project | Packaged or explicit teach pack | Indexes, progress state, and optional starter files |
| `unit` | Parent directory for the new unit | Packaged templates | New unit directory; exits nonzero if the target already exists |
| `wave` | Unit root or any directory with explicit VCD | GTKWave | Viewer process |
| `wave-verilator` | Unit root or any directory with explicit VCD | GTKWave | Viewer process |

Use executable help for the exact installed version:

```bash
saxoflow --help
saxoflow <command> --help
saxoflow <group> <command> --help
```

Click exposes Python identifiers with hyphens in the public command line. For example, use `sim-verilator`, not `sim_verilator`.

## 5. Unit Projects

### 5.1 Create a unit

**Public CLI**

```bash
cd ~/SaxoFlow/projects
saxoflow unit sample_core
```

The command creates a design-neutral structure:

```text
sample_core/
├── Bender.yml
├── Makefile
├── constraints/
├── formal/
│   ├── out/
│   ├── reports/
│   ├── scripts/
│   │   └── spec.sby
│   └── source/
├── lint/
│   └── reports/
├── pnr/
│   ├── generated/
│   ├── logs/
│   ├── objects/
│   ├── reports/
│   ├── results/
│   ├── runs/
│   └── scripts/
├── simulation/
│   ├── icarus/
│   └── verilator/
├── source/
│   ├── rtl/
│   │   ├── include/
│   │   ├── systemverilog/
│   │   ├── verilog/
│   │   └── vhdl/
│   ├── specification/
│   └── tb/
│       ├── systemverilog/
│       ├── verilog/
│       └── vhdl/
└── synthesis/
    ├── out/
    ├── reports/
    ├── scripts/
    │   └── synth.ys
    └── src/
```

Unit creation does not generate an RTL module, testbench, or formal harness. The starter `spec.sby` and `synth.ys` files are editable examples and must not contain design-specific source globs.

### 5.2 Working-directory rule

Most design commands operate on the current unit:

```bash
cd ~/SaxoFlow/projects/sample_core
saxoflow lint
saxoflow synth
```

Run them from the directory containing the unit `Makefile`, `source/`, and flow directories unless the command accepts an explicit project path.

### 5.3 Cleaning

```bash
saxoflow clean
```

This delegates to the generated unit Makefile and removes generated simulation, synthesis, formal, lint, and related report artifacts. It must not delete authored RTL, testbenches, constraints, custom scripts, or PDK data.

## 6. Simulation and Waveforms

### 6.1 Icarus simulation

**Public CLI, environment-dependent**

```bash
saxoflow sim
saxoflow sim --tb source/tb/systemverilog/sample_core_tb.sv
saxoflow sim \
  --rtl source/rtl/systemverilog \
  --tb-file source/tb/systemverilog/sample_core_tb.sv \
  --include source/rtl/include
```

Important options:

| Option | Behavior |
|---|---|
| `--tb VALUE` | Testbench name or path, depending on the supplied value |
| `--rtl PATH` | Repeatable RTL file, directory, or supported pattern |
| `--tb-file PATH` | Repeatable explicit testbench file |
| `--include DIR` | Repeatable include directory |

Default discovery searches the unit RTL and testbench trees for Verilog and SystemVerilog files. Files are resolved, deduplicated, and passed to Icarus with SystemVerilog support enabled when needed.

VHDL files are recognized as HDL inputs but are rejected by the Icarus backend with an actionable message. Use a VHDL-capable flow such as GHDL or NVC outside this wrapper until a public VHDL simulation wrapper is added.

Outputs normally appear under:

```text
simulation/icarus/
```

Common failures:

| Failure | Action |
|---|---|
| No RTL or TB found | Add files under the unit source tree or pass explicit paths |
| Multiple possible testbenches | Select one with `--tb` or `--tb-file` |
| Include not found | Add `--include` |
| Syntax or elaboration error | Fix the reported HDL location or use the agentic debug flow |
| VHDL input | Use a VHDL simulator |

The command exits nonzero when compilation or simulation fails.

### 6.2 Simulate and open waveform

```bash
saxoflow simulate
saxoflow simulate --tb source/tb/systemverilog/sample_core_tb.sv
```

`simulate` runs the Icarus flow and opens the resulting waveform when successful.

```bash
saxoflow wave
saxoflow wave simulation/icarus/tb.vcd
```

`wave` opens a VCD with the configured waveform viewer, normally GTKWave.

### 6.3 Verilator flow

```bash
saxoflow sim-verilator --tb sample_core_tb
saxoflow sim-verilator-run
saxoflow simulate-verilator --tb sample_core_tb
saxoflow wave-verilator
```

| Command | Purpose |
|---|---|
| `sim-verilator` | Build the Verilator simulation |
| `sim-verilator-run` | Run the existing compiled executable |
| `simulate-verilator` | Build and run |
| `wave-verilator [VCD]` | Open the generated waveform |

These commands use the unit Makefile and currently expose a smaller override surface than `sim`. Use `--tb` to select the testbench name.

## 7. Formal Verification

### 7.1 Command

**Public CLI, environment-dependent**

```bash
saxoflow formal
saxoflow formal \
  --rtl source/rtl/systemverilog/sample_core.sv \
  --sva formal/source/sample_core_formal.sv
saxoflow formal --solver z3 --sby-task bmc_z3
```

Important options:

| Option | Purpose |
|---|---|
| `--rtl PATH` | Repeatable RTL file, directory, or pattern |
| `--sva PATH` | Repeatable assertion or formal harness file, directory, or pattern |
| `--solver auto\|z3\|boolector\|bitwuzla\|yices\|cvc5` | Select the formal solver |
| `--sby-task TASK` | Run a named task from `spec.sby` |
| `--autotune` | Request solver or configuration tuning where supported |
| `--timeout SECONDS` | Limit execution time |
| `--dumptasks` | Print available SBY tasks |
| `--dumpcfg` | Print resolved configuration |

### 7.2 Discovery

Without explicit overrides, SaxoFlow searches:

```text
source/rtl/verilog/
source/rtl/systemverilog/
formal/source/
```

RTL and SVA paths are written into the existing:

```text
formal/scripts/spec.sby
```

SaxoFlow does not create `_saxoflow_auto.sby`. The project keeps one visible, editable specification.

If an explicit formal harness module is present, it becomes the formal top. Otherwise SaxoFlow uses the inferred RTL top where possible. Designs with multiple plausible tops should provide a harness or edit `spec.sby` explicitly.

### 7.3 Harness expectations

A useful harness generally:

1. Declares symbolic or constrained DUT inputs.
2. Instantiates the DUT.
3. Defines clock and reset assumptions correctly.
4. Uses Yosys-compatible procedural `assert`, `assume`, and `$past` constructs when full SVA syntax is unsupported.
5. Guards `$past` assertions during the initial cycle.
6. Avoids assumptions that accidentally eliminate all reachable behavior.

The `.sby` file does not bind clock, reset, or ports by itself. Those connections belong in the harness or RTL. The SBY script reads files, selects the top, and configures engines and tasks.

### 7.4 Validation behavior

Formal repair must be validated with SymbiYosys:

```bash
saxoflow formal --sby-task bmc_z3
saxoflow formal --sby-task prove_z3
```

Running Icarus after editing a formal harness checks only simulation syntax and does not establish that the formal job is valid.

Outputs appear under `formal/out/` and `formal/reports/`. The command exits nonzero for parse, preparation, solver, assertion, or timeout failures.

## 8. RTL Linting

### 8.1 Command

**Public CLI, environment-dependent**

```bash
saxoflow lint
saxoflow lint --rtl source/rtl --top sample_core
saxoflow lint --include-tb --tool all
saxoflow lint --tool verible --ruleset all
```

Options:

| Option | Purpose |
|---|---|
| `--rtl PATH` | Repeatable file, directory, or glob |
| `--include DIR` | Repeatable include directory |
| `--top MODULE` | Explicit Verilator top module |
| `--include-tb` | Include files under `source/tb` |
| `--tool auto\|all\|verible\|verilator` | Select lint engines |
| `--ruleset default\|all\|none` | Select Verible ruleset |
| `--rules TEXT` | Pass Verible rule configuration |
| `--config FILE` | Use a Verible lint configuration |
| `--waiver FILE` | Repeatable Verible waiver file |
| `--no-fail` | Report findings without returning failure |

### 8.2 Discovery and ordering

Default recursive discovery includes:

```text
source/rtl/systemverilog/**/*.sv
source/rtl/verilog/**/*.v
```

Explicit paths may be files, directories, or glob patterns relative to the unit. Results are deduplicated and deterministically sorted. SystemVerilog package files are ordered before normal modules for Verilator.

VHDL inputs are rejected because the current lint wrapper has no VHDL backend.

### 8.3 Engines and reports

Verible provides syntax and style diagnostics. Verilator provides elaboration-aware linting. `--tool auto` runs available default engines and warns when only one is installed. `--tool all` requires both.

Reports are timestamped under:

```text
lint/reports/
```

Linting is read-only. It never modifies HDL.

## 9. Yosys Synthesis

### 9.1 Common usage

**Public CLI, environment-dependent**

```bash
saxoflow synth
saxoflow synth --rtl source/rtl/systemverilog --top sample_core
saxoflow synth --frontend slang --define FPGA_BUILD=1
saxoflow synth --preflight-lint --show-log
```

Default discovery searches:

```text
source/rtl/verilog/
source/rtl/systemverilog/
synthesis/src/
```

Explicit inputs may be files, directories, or patterns. Sources are deduplicated, and SystemVerilog packages are placed first.

### 9.2 Options

| Option | Purpose |
|---|---|
| `--rtl PATH` | Repeatable source path |
| `--include DIR` | Repeatable include directory |
| `--define NAME[=VALUE]` | Repeatable preprocessor definition |
| `--top MODULE` | Explicit top module |
| `--param NAME=VALUE` | Repeatable top parameter override |
| `--frontend auto\|builtin\|slang` | Select SystemVerilog frontend policy |
| `--target generic\|ice40\|ecp5\|xilinx\|asic` | Select synthesis profile |
| `--device hx\|lp\|u` | Select iCE40 device family |
| `--family FAMILY` | Select Xilinx family |
| `--liberty FILE` | ASIC standard-cell Liberty file |
| `--clock-period NS` | ASIC ABC delay target |
| `--lut INTEGER` | Generic LUT mapping width |
| `--flatten` or `--keep-hierarchy` | Hierarchy policy |
| `--format verilog\|json\|blif\|edif` | Repeatable output format |
| `--output-prefix PATH` | Output basename |
| `--preflight-lint` | Require lint success first |
| `--script FILE` | Run a custom Yosys script unchanged |
| `--show-log` | Stream or print the useful Yosys log |
| `--schematic` | Render a schematic after synthesis |
| `--schematic-output PATH` | Schematic output path |
| `--schematic-input PATH` | Override the JSON input |
| `--schematic-skin FILE` | NetlistSVG skin |
| `--schematic-timeout SECONDS` | Rendering timeout |
| `--open-schematic` | Open the rendered image |

Wrapper-generation options are rejected with `--script` when they would otherwise be silently ignored.

### 9.3 Frontends

`--frontend auto` uses:

1. `read_verilog` for `.v`.
2. The operational Yosys Slang plugin for `.sv` when available.
3. `read_verilog -sv` as a limited fallback with a warning.

`--frontend slang` fails clearly if the plugin cannot load. Built-in Yosys SystemVerilog support does not cover the complete language.

VHDL inputs are rejected by this wrapper.

### 9.4 Targets

| Target | Yosys flow | Typical output |
|---|---|---|
| `generic` | `synth` | Verilog and JSON |
| `ice40` | `synth_ice40` | JSON |
| `ecp5` | `synth_ecp5` | JSON |
| `xilinx` | `synth_xilinx` | JSON |
| `asic` | Liberty read, `dfflibmap`, and `abc` | Mapped Verilog and JSON |

ASIC synthesis requires `--liberty` unless the command is invoked through P&R with a resolved platform.

### 9.5 Reproducibility and artifacts

Normal wrapper operation generates:

```text
synthesis/reports/saxoflow_synth.ys
synthesis/reports/yosys.log
synthesis/reports/stats.txt
synthesis/reports/stats.json
synthesis/out/synthesized.v
synthesis/out/synthesized.json
```

Requested formats and output prefixes alter the netlist files. The generated script records the exact flow. The editable `synthesis/scripts/synth.ys` remains untouched unless selected with `--script`.

For legacy unit Makefiles that do not support the current `YOSYS_SCRIPT` variable, SaxoFlow detects the mismatch and runs Yosys directly with the generated script.

## 10. Netlist Schematics

### 10.1 Command

**Public CLI, environment-dependent**

```bash
saxoflow schematic
saxoflow schematic --input synthesis/out/synthesized.json
saxoflow schematic --open
saxoflow synth --schematic --open-schematic
```

The schematic flow:

1. Selects a Yosys JSON netlist.
2. Runs NetlistSVG.
3. Writes `synthesis/reports/schematic.svg` or the requested output path.
4. Optionally opens the image through WSLg, Windows interop, or a Linux desktop opener.

Options:

| Option | Purpose |
|---|---|
| `--input FILE` | Yosys JSON input, default `synthesis/out/synthesized.json` |
| `--output FILE` | SVG destination, default `synthesis/reports/schematic.svg` |
| `--skin FILE` | Optional NetlistSVG skin |
| `--timeout SECONDS` | Rendering timeout |
| `--open` or `--no-open` | Control desktop viewer opening |

### 10.2 Installation

```bash
saxoflow install netlistsvg
```

The installer reuses an existing Node.js and npm installation where possible. Otherwise it installs a suitable runtime through the supported recipe path, including NVM fallback where applicable. The Debian package name is `nodejs`, not `node`.

Common failures include missing `node`, missing `npm`, invalid Yosys JSON, unsupported SVG viewer integration, and no graphical display.

## 11. Tool Installation

### 11.1 Command model

**Public CLI, environment-dependent**

```bash
saxoflow install yosys
saxoflow install lint
saxoflow install formal
saxoflow install full
saxoflow install selected
saxoflow install all
```

The optional positional mode accepts:

| Mode | Behavior |
|---|---|
| Omitted or `selected` | Install the selection saved by `init-env` |
| `all` | Install every catalog tool |
| Preset name | Install that preset |
| Group name | Install that tool group |
| Tool name | Install that single tool |

There is currently no `install --list` option. An unsupported mode prints the valid presets, groups, and tools before exiting nonzero. Run `saxoflow install --help` before automating installation because installer behavior may evolve.

### 11.2 Installable tools

The current catalog contains 44 unique tools.

#### System package tools

| Tool | Primary role |
|---|---|
| `boolector` | SMT solver |
| `ghdl` | VHDL simulation and analysis |
| `gtkwave` | Waveform viewing |
| `iverilog` | Verilog and SystemVerilog simulation |
| `klayout` | GDS viewing, merge, and optional physical verification |
| `magic` | Optional layout and DRC tooling |
| `netgen` | Optional LVS tooling |
| `openfpgaloader` | FPGA programming |
| `openocd` | On-chip debug |
| `qemu-system-riscv64` | RISC-V system emulation |
| `z3` | SMT solver |

#### Recipe-installed tools

| Tool | Primary role |
|---|---|
| `bender` | HDL dependency management |
| `bitwuzla` | SMT solver |
| `cocotb` | Python verification |
| `covered` | Verilog coverage |
| `cvc5` | SMT solver |
| `edalize` | EDA backend abstraction |
| `fusesoc` | IP and core package management |
| `gem5` | Architecture simulation |
| `kactus2` | IP-XACT tooling |
| `netlistsvg` | JSON netlist schematic rendering |
| `nextpnr` | FPGA place and route |
| `nvc` | VHDL simulation |
| `openram` | SRAM generation |
| `openroad` | Physical design implementation |
| `opensta` | Standalone static timing analysis |
| `orfs` | OpenROAD Flow Scripts orchestration |
| `renode` | Embedded-system simulation |
| `rggen` | Register generator |
| `riscv-pk` | RISC-V proxy kernel |
| `riscv-toolchain` | RISC-V compiler toolchain |
| `riscv-vp-plusplus` | RISC-V virtual platform |
| `siliconcompiler` | EDA flow orchestration |
| `spike` | RISC-V ISA simulator |
| `surelog` | SystemVerilog parser and elaborator |
| `surfer` | Waveform viewer |
| `sv2v` | SystemVerilog to Verilog conversion |
| `symbiyosys` | Formal flow orchestration |
| `verible` | SystemVerilog lint and formatting tools |
| `verilator` | Compiled simulation and lint |
| `vivado` | Xilinx vendor flow |
| `vscode` | Development editor |
| `yices` | SMT solver |
| `yosys` | RTL synthesis |

Installer recipes currently assume a Debian or Ubuntu-like environment for system package operations unless a recipe explicitly handles another platform.

### 11.3 Tool groups

The current catalog defines 18 groups:

| Group | Intended scope |
|---|---|
| `simulation` | Core simulation and waveform tools |
| `formal` | Formal orchestration and base solver |
| `formal-solvers` | Additional common formal solvers |
| `formal-solvers-tier2` | Extended solver set |
| `fpga` | Open FPGA flow tools |
| `asic` | ASIC synthesis and physical design |
| `base` | Core HDL development tools |
| `software` | Software and RISC-V support |
| `ide` | Development environment tools |
| `lint` | RTL lint engines |
| `ethz_ic_design` | ETH Zurich IC design tools |
| `advanced-flow` | Advanced orchestration tools |
| `vhdl-crosscheck` | Multiple VHDL implementations |
| `ipxact-edu` | IP-XACT education |
| `orchestration` | Flow and package orchestration |
| `research-platform` | Virtual and research platforms |
| `research-arch` | Architecture research |
| `research-memory` | Memory generation and research |

### 11.4 Presets

The catalog defines 18 presets:

```text
minimal
fpga
asic
formal
formal-plus
formal-complete
full
software-bringup
waveform-ux
vhdl-crosscheck
ipxact-edu
advanced-flow
orchestration
research-platform
research-arch
research-memory
ethz_ic_design_tools
full-with-quality
```

Presets expand into groups and tools. They do not install PDK data. Use `saxoflow pdk install` separately.

## 12. PDK Registry and Lifecycle

### 12.1 Command catalog

**Public CLI, environment-dependent**

The `pdk` group contains seven commands.

| Command | Important options | Purpose |
|---|---|---|
| `saxoflow pdk list` | None | List known platforms and installation state |
| `saxoflow pdk info IDENTIFIER` | Identifier is required | Show manifest, libraries, corners, status, and compatibility |
| `saxoflow pdk install IDENTIFIER` | `--root`, `--accept-license` | Install or activate pinned platform collateral |
| `saxoflow pdk verify IDENTIFIER` | Identifier is required | Verify files, checksums, and technology-load readiness |
| `saxoflow pdk remove IDENTIFIER` | `--yes` | Remove managed installed data |
| `saxoflow pdk register` | `--manifest`, `--replace`, `--root`, `--smoke-test` | Register a custom manifest |
| `saxoflow pdk template` | `--output`, `--force` | Generate a custom-platform manifest template |

### 12.2 Initial platforms

| Platform | Family | Classification | Notes |
|---|---|---|---|
| `sky130hd` | SkyWater SKY130 | Validated, fabrication-oriented | High-density digital library |
| `sky130hs` | SkyWater SKY130 | Validated, fabrication-oriented | High-speed variant where supported |
| `gf180mcu` | GlobalFoundries GF180MCU | Validated, fabrication-oriented | Multiple supported digital libraries and corners |
| `ihp-sg13g2` | IHP SG13G2 | Experimental, fabrication-oriented | Public digital flow may be preview quality |
| `nangate45` | Nangate45 | Reference | Research platform, not a fabrication PDK |
| `asap7` | ASAP7 | Reference | Predictive research platform; use an external compatible netlist where synthesis mapping is unavailable |

An open PDK does not imply foundry signoff qualification. The CLI and documentation preserve the upstream support classification.

### 12.3 Install and verify

Install OpenROAD and ORFS separately:

```bash
saxoflow install openroad
saxoflow install orfs
```

ORFS installation does not install another OpenROAD binary and does not download every PDK.

Install a selected platform:

```bash
saxoflow pdk install sky130hd --accept-license
saxoflow pdk verify sky130hd
```

Important installation options include:

| Option | Purpose |
|---|---|
| `--root DIR` | Override managed data root |
| `--accept-license` | Confirm the displayed license |

Installation uses pinned sources, checksums, temporary staging, validation, and atomic activation. The command reports download and disk estimates before materialization.

### 12.4 Custom platforms

```bash
saxoflow pdk template --output platform.yaml
saxoflow pdk register --manifest platform.yaml --smoke-test
```

Registration options include replacement control, storage root, and an optional smoke test. A custom manifest describes:

```text
identity and aliases
provider and process family
support classification
source revision and checksums
license metadata
ORFS platform mapping
compatible ORFS and OpenROAD revisions
libraries and timing corners
technology LEF, cell LEF, GDS, and Liberty files
RC extraction rules
layer and site metadata
KLayout, Magic, and Netgen configuration
default flow settings
required environment variables
validation design
```

Registration validates external paths but does not copy proprietary PDK files into SaxoFlow-managed storage unless the user explicitly chooses a managed installation path.

### 12.5 Switching platforms

To move a project to another platform:

```bash
saxoflow pdk install gf180mcu --accept-license
saxoflow pdk verify gf180mcu
cd ~/SaxoFlow/projects/sample_core
saxoflow pnr init --platform gf180mcu --top sample_core --force
saxoflow pnr run --synthesize --variant gf180-baseline --show-log
```

Changing platform requires a new lock, technology mapping, and physical run. Do not reuse a gate-level netlist mapped to another standard-cell library. Floorplan dimensions and routing layers also require review.

## 13. Physical Design

### 13.1 Backend responsibilities

| Tool | Role in the current flow |
|---|---|
| Yosys | RTL synthesis and technology mapping |
| ORFS | Reproducible flow orchestration, stage dependencies, file layout, and reports |
| OpenROAD | Floorplan, PDN, placement, CTS, routing, timing repair, extraction, and database handling |
| OpenSTA | Timing engine embedded in OpenROAD; standalone executable is optional |
| KLayout | GDS viewing, final stream handling, and optional DRC or LVS integration |
| Magic | Optional independent layout and DRC tooling |
| Netgen | Optional independent LVS tooling |

OpenROAD is more than a router, but it does not replace the complete ORFS project flow or Yosys RTL synthesis. ORFS coordinates the standard flow. Magic and Netgen are not required by the current default successful P&R path.

### 13.2 Project initialization

**Public CLI, environment-dependent**

```bash
saxoflow pnr init --platform sky130hd --top sample_core
```

Important initialization options:

| Option | Purpose |
|---|---|
| `--platform PLATFORM` | Required platform selection |
| `--library LIBRARY` | Select a standard-cell library |
| `--corner CORNER` | Select a timing corner |
| `--top MODULE` | Set design top |
| `--netlist PATH` | Repeatable existing mapped netlist |
| `--sdc FILE` | Use authored timing constraints |
| `--clock-port PORT` | Generate a basic clock constraint |
| `--clock-period NS` | Set generated clock period |
| `--force` | Replace existing P&R configuration and lock |

Initialization creates or updates:

```text
pnr/
├── config.yaml
├── platform.lock.yaml
├── generated/
├── logs/
├── objects/
├── reports/
├── results/
├── runs/
└── scripts/
```

The lock records platform, PDK version, library, corner, ORFS revision, OpenROAD version, and relevant artifact checksums. SaxoFlow never silently switches the locked platform.

### 13.3 P&R command catalog

The `pnr` group contains 12 commands.

| Command | Purpose |
|---|---|
| `pnr init` | Select and lock a platform and project configuration |
| `pnr run` | Run the complete configured flow |
| `pnr floorplan` | Run through floorplan, tracks, tap cells, and PDN |
| `pnr place` | Run placement and required prerequisites |
| `pnr cts` | Run clock-tree synthesis and required prerequisites |
| `pnr route` | Run global and detailed routing |
| `pnr finish` | Run extraction, timing, fillers, and final outputs |
| `pnr status` | Show stage and artifact status |
| `pnr report` | Summarize or compare PPA and flow metrics |
| `pnr gui` | Open an OpenROAD checkpoint |
| `pnr clean` | Clean one or more generated runs |
| `pnr openroad` | Run a custom OpenROAD Tcl script |

### 13.4 Shared stage options

`run`, `floorplan`, `place`, `cts`, `route`, and `finish` share most of these options:

| Option | Purpose |
|---|---|
| `--platform PLATFORM` | Override resolved platform where permitted |
| `--library LIBRARY` | Select library |
| `--corner CORNER` | Select timing corner |
| `--top MODULE` | Select top module |
| `--netlist PATH` | Repeatable mapped-netlist input |
| `--sdc FILE` | Timing constraints |
| `--synthesize` | Invoke SaxoFlow ASIC synthesis before P&R |
| `--unsafe-netlist` | Explicitly bypass compatible-netlist checks |
| `--rtl PATH` | Repeatable RTL override for synthesis |
| `--include DIR` | Repeatable include path |
| `--define NAME[=VALUE]` | Repeatable macro definition |
| `--param NAME=VALUE` | Repeatable top parameter |
| `--clock-port PORT` | Clock port for generated SDC |
| `--clock-period NS` | Clock period |
| `--utilization FLOAT` | Target core utilization |
| `--aspect-ratio FLOAT` | Core aspect ratio |
| `--core-margin VALUE` | Core-to-die margin |
| `--die-area "LX LY UX UY"` | Explicit die area |
| `--core-area "LX LY UX UY"` | Explicit core area |
| `--place-density FLOAT` | Placement density |
| `--min-routing-layer LAYER` | Lowest routing layer |
| `--max-routing-layer LAYER` | Highest routing layer |
| `--threads INTEGER` | Tool thread count |
| `--variant NAME` | Isolated experiment name |
| `--set NAME=VALUE` | Repeatable ORFS or platform override |
| `--fresh` | Restart instead of reusing checkpoints |
| `--dry-run` | Resolve and print without running tools |
| `--show-log` | Stream detailed stage output |

Values such as layers, corners, libraries, areas, and density are validated against the selected platform and generic constraints.

Utility command options:

| Command | Options |
|---|---|
| `pnr status` | `--variant` |
| `pnr report` | `--variant`, repeatable `--compare`, `--json-output` |
| `pnr gui` | `--variant`, `--stage`, `--db` |
| `pnr clean` | `--variant`, `--yes` |
| `pnr openroad` | `--script`, `--db`, `--gui`, `--threads`, `--log`, `--metrics` |

### 13.5 Synthesis handoff

Without `--synthesize`, P&R uses:

1. Explicit `--netlist`.
2. A compatible netlist discovered from SaxoFlow synthesis metadata.

With `--synthesize`, SaxoFlow:

1. Resolves RTL and top.
2. Resolves platform Liberty and synthesis settings.
3. Invokes the existing ASIC Yosys wrapper.
4. Records platform, library, and corner metadata.
5. Verifies mapped cells against the selected library.
6. passes the mapped netlist into ORFS.

P&R does not ask ORFS to repeat RTL synthesis after SaxoFlow has produced the mapped netlist.

### 13.6 Runs, variants, and restart behavior

Experiments are isolated under:

```text
pnr/runs/<variant>/
```

Each run records resolved configuration, environment, commands, versions, status, and artifacts. Later stages reuse valid prerequisites. Use `--fresh` after a material configuration change or when a cached checkpoint is invalid.

Examples:

```bash
saxoflow pnr run --synthesize --variant baseline --show-log
saxoflow pnr run \
  --synthesize \
  --variant dense \
  --utilization 0.55 \
  --place-density 0.62
```

### 13.7 Status and reports

```bash
saxoflow pnr status
saxoflow pnr status --variant baseline
saxoflow pnr report --variant baseline
saxoflow pnr report --compare baseline --compare dense
saxoflow pnr report --json-output pnr/reports/comparison.json
```

Reports summarize available metrics such as:

```text
area and utilization
instance and buffer counts
WNS and TNS
clock skew
wirelength
congestion
DRC violations
power when available
runtime and memory
final artifact locations
```

Current limitation: report discovery primarily scans JSON names containing `metrics`. Some ORFS outputs, including files named like `6_report.json`, may not yet appear in the summary even though the raw result exists.

### 13.8 GUI

```bash
saxoflow pnr gui --stage route
saxoflow pnr gui --stage finish --variant baseline
saxoflow pnr gui --db path/to/design.odb
```

The GUI flow selects the requested ODB checkpoint and generates an OpenROAD bootstrap that loads:

1. Platform Liberty files.
2. The selected ODB.
3. Matching SDC constraints.
4. RC extraction setup from the platform manifest.

On WSL, SaxoFlow detects WSLg or X11 and applies Qt compatibility settings where needed. Diagnose GUI readiness with:

```bash
saxoflow diagnose pnr --platform sky130hd
```

Inside OpenROAD GUI, inspect:

```text
floorplan and core boundary
standard-cell placement
clock tree
routed nets and congestion
timing paths
DRC markers
power grid
design hierarchy
```

### 13.9 Custom OpenROAD Tcl

```bash
saxoflow pnr openroad --script pnr/scripts/custom.tcl
saxoflow pnr openroad --script pnr/scripts/custom.tcl --gui
saxoflow pnr openroad --db pnr/results/sample_core.odb
```

This is the research escape hatch for scripts outside the standard ORFS stages. Options include script, database, GUI mode, thread count, log, and metrics paths.

## 14. Diagnosis

### 14.1 Command catalog

**Public CLI**

The `diagnose` group contains eight commands.

| Command | Purpose |
|---|---|
| `diagnose summary` | Summarize environment health and optionally export it |
| `diagnose env` | Inspect environment variables and path configuration |
| `diagnose help` | Explain diagnostic usage |
| `diagnose repair` | Apply supported noninteractive repairs |
| `diagnose repair-interactive` | Review repairs interactively |
| `diagnose clean-path` | Generate shell-specific PATH cleanup guidance |
| `diagnose pnr` | Check OpenROAD, ORFS, display, project, and platform readiness |
| `diagnose pdk [IDENTIFIER]` | Check PDK registry and installed artifacts |

Examples:

```bash
saxoflow diagnose summary
saxoflow diagnose summary --export diagnostics.json
saxoflow diagnose env
saxoflow diagnose clean-path --shell bash
saxoflow diagnose pnr --platform sky130hd
saxoflow diagnose pdk sky130hd
```

There is no `pnr doctor` command. P&R and PDK inspection belongs under `diagnose`.

### 14.2 P&R checks

P&R diagnosis covers:

```text
OpenROAD executable and version
ORFS checkout and compatibility
Yosys and OpenSTA
KLayout, Magic, and Netgen where relevant
platform manifests and locks
PDK checksums and required artifacts
technology LEF
cell LEF, GDS, and Liberty
RC extraction rules
layer maps
display and WSL GUI support
project synthesis compatibility
```

Optional Magic and Netgen warnings do not necessarily invalidate the default ORFS and OpenROAD flow.

## 15. Interactive TUI

### 15.1 Starting the shell

**TUI-only**

```bash
saxoflow
```

The shell starts in the resolved workspace. It supports:

```text
SaxoFlow command execution
Unix shell commands
shell operators and pipelines
blocking editor handoff
path and command completion
AI buddy conversation
autonomous file actions
teach sessions
agent-session inspection
```

Recognized bare SaxoFlow command names are automatically routed as if prefixed by `saxoflow`. Both of these are valid inside the TUI:

```text
synth --show-log
saxoflow synth --show-log
```

Built-in shell commands include:

```text
help
clear
quit
exit
agentlog
```

Normal shell commands may legitimately produce no stdout:

```bash
rm -rf generated_directory
```

An empty response means the command produced no output. Exit status and errors remain the meaningful indicators.

### 15.2 Autonomous file intents

**Agentic, TUI-only**

The AI router recognizes these file-oriented intents:

| Intent | Behavior |
|---|---|
| `read_file` | Read a workspace file for analysis |
| `save_file` | Create or replace a requested file |
| `edit_file` | Modify an existing target |
| `multi_file` | Coordinate changes across related files |
| `repair_sim` | Inspect a simulation failure, edit likely RTL or TB targets, and rerun |

Natural-language requests do not need to contain a rigid phrase such as "edit this file." The router combines intent detection, current working directory, recent tool output, and candidate file selection.

File operations remain constrained to the workspace and are logged. Ambiguous or destructive changes may require confirmation.

### 15.3 Domain-specific validation

Agent repairs must validate with the backend that produced the failure:

| Failure domain | Correct validation |
|---|---|
| Simulation | Icarus or Verilator command that failed |
| Lint | Selected Verible or Verilator lint engine |
| Synthesis | Yosys synthesis |
| Formal | SymbiYosys task |
| P&R | Relevant ORFS or OpenROAD stage |

Editing an RTL file after a formal or P&R failure and then running only Icarus is insufficient. The original domain command must pass.

## 16. Agent Session Transparency

### 16.1 Purpose

**TUI-only**

User-facing session logs make agent actions inspectable without claiming to expose private model chain-of-thought. They record concise decision summaries, selected agents, actions, targets, results, errors, and user-visible responses.

They do not contain hidden chain-of-thought.

### 16.2 Storage

Default path:

```text
~/SaxoFlow/.saxoflow/agent_sessions/<timestamp>-<id>/
├── events.jsonl
└── transcript.md
```

| File | Purpose |
|---|---|
| `events.jsonl` | Append-only structured event stream |
| `transcript.md` | Human-readable session review |

Append-only writes preserve useful partial traces after a crash.

### 16.3 Modes

| Mode | Behavior |
|---|---|
| `off` | Writes no session content |
| `summary` | Default. Stores prompts as summaries or excerpts, intent, agent, target paths, action summaries, command excerpts, errors, and final responses |
| `full` | Opt-in. Stores full prompts, generated content, and unified diffs where practical |

Common secrets and API-key-like values are redacted. Full mode can expose sensitive HDL and prompts and should be enabled only for an appropriate workspace.

Environment controls:

```bash
SAXOFLOW_AGENT_LOG_MODE=off|summary|full
SAXOFLOW_AGENT_LOG_DIR=/custom/path
```

### 16.4 Commands

```text
agentlog path
agentlog list
agentlog show
agentlog mode summary
agentlog mode full
agentlog mode off
agentlog dir /custom/path
```

These commands operate inside the TUI. Persisted mode and directory settings use the SaxoFlow runtime configuration.

Logged paths include normal buddy chat, detected file intents, file writes, direct agentic commands, simulation repair, formal and P&R routing, and visible command results.

## 17. Agentic AI

### 17.1 Direct command catalog

**Public CLI, agentic**

The `agenticai` group contains 13 commands.

| Command | Important options | Purpose and behavior |
|---|---|---|
| `agenticai rtlgen` | `--input-file`, `--output-file`, `--iters` | Generate and iteratively review RTL from a specification |
| `agenticai tbgen` | `--input-file`, `--output-file`, `--iters` | Generate and iteratively review a Verilog testbench from RTL |
| `agenticai fpropgen` | `--input-file`, `--output-file`, `--iters` | Generate a Yosys-compatible formal harness from RTL |
| `agenticai rtlreview` | `--input-file` | Review RTL, with default discovery under the unit RTL tree |
| `agenticai tbreview` | `--input-file` | Review a testbench, with default discovery under the unit TB tree |
| `agenticai fpropreview` | `--input-file` | Review a formal property or harness file |
| `agenticai debug` | `--input-file` | Diagnose supplied RTL, TB, property, or log content |
| `agenticai sim` | `--rtl-file`, `--tb-file`, `--top-module` | Run the simulation agent with three required explicit inputs |
| `agenticai synth` | None | Run synthesis for the current unit through `SynthAgent` |
| `agenticai pnr` | `--stage`, repeatable `--arg`, `--allow-configuration-change` | Route a PDK, diagnosis, stage, report, or GUI action through `PnrAgent` |
| `agenticai fullpipeline` | `--iters`, `--open-wave` | Run the enabled generation, review, simulation, repair, and optional synthesis pipeline |
| `agenticai setupkeys` | None | Interactively configure one provider key in `.env` |
| `agenticai testllms` | None | Test registered provider connectivity and credentials |

`agenticai pnr --stage` accepts:

```text
run
floorplan
place
cts
route
finish
status
report
gui
diagnose
pdk-list
pdk-info
pdk-install
pdk-verify
pdk-diagnose
```

Forwarded `--arg` values are passed to the selected public command. Arguments that may alter locked P&R configuration require `--allow-configuration-change`.

Run command-specific help because generation and review options differ:

```bash
saxoflow agenticai rtlgen --help
saxoflow agenticai pnr --help
```

### 17.2 Registered agents

The current registry contains 12 agents:

| Agent ID | Implementation role |
|---|---|
| `rtlgen` | RTL generation |
| `tbgen` | Testbench generation |
| `fpropgen` | Formal property generation |
| `report` | Result and artifact reporting |
| `rtlreview` | RTL review |
| `tbreview` | Testbench review |
| `fpropreview` | Formal-property review |
| `debug` | Failure analysis and repair |
| `sim` | Simulation orchestration |
| `synth` | Synthesis orchestration |
| `pnr` | Physical-design orchestration |
| `tutor` | Teach-session guidance |

The P&R agent uses the project lock and must not silently change platform, library, corner, or floorplan configuration.

### 17.3 Providers

The provider registry currently contains 11 provider integrations:

```text
openai
groq
fireworks
together
mistral
perplexity
deepseek
dashscope
openrouter
anthropic
gemini
```

Provider availability depends on installed client libraries, API credentials, account access, and model availability.

### 17.4 Pipeline status

The full pipeline can generate and review RTL and TB content, simulate, debug, and optionally synthesize after successful simulation. Formal generation remains disabled in the default full pipeline even though standalone formal agents and the `formal` command exist.

Generated or repaired content should be treated as a proposed engineering change. The relevant EDA backend remains the acceptance criterion.

## 18. Teach Packs

### 18.1 Public commands

**Public CLI**

The `teach` group contains five commands.

| Command | Purpose |
|---|---|
| `teach list` | List available teach packs |
| `teach index PACK_ID` | Build or refresh a pack index |
| `teach start PACK_ID` | Start or resume a lesson |
| `teach status` | Show lesson progress |
| `teach debug-images PACK_ID` | Rebuild and inspect lesson image extraction |

Examples:

```bash
saxoflow teach list
saxoflow teach index digital-design --force
saxoflow teach start digital-design --project-root ~/SaxoFlow/projects/lab1
saxoflow teach status
```

Important options:

| Command | Options |
|---|---|
| `list` | `--packs-dir` |
| `index` | `--packs-dir`, `--force` |
| `start` | `--packs-dir`, `--project-root`, `--resume`, `--provider`, `--model`, `--verbose` |
| `status` | `--packs-dir` |
| `debug-images` | `--packs-dir`, `--force-rebuild` |

Packaged packs are read-only resources. Indexes, progress, and starter files live in user-owned locations.

### 18.2 In-session commands

**TUI-only**

Once a lesson is active, these commands control the session:

```text
run
next
back
skip
hint
status
agents
confirm
fig N
doc [page]
quit
```

Shell commands can also run during a lesson. Recent output is supplied to the tutor context so the tutor can respond to actual compiler and EDA results.

## 19. Environment and Utility Commands

### 19.1 Tool checks

```bash
saxoflow check-tools
```

Checks the base tools expected by the current environment and reports missing executables.

### 19.2 Environment initialization

```bash
saxoflow init-env
saxoflow init-env --preset asic
saxoflow init-env --headless
```

`--preset` selects one of the 18 registered presets. `--headless` avoids prompts and uses `minimal` when no preset is supplied. The resulting selection is consumed by:

```bash
saxoflow install
saxoflow install selected
```

Prefer the workspace and runtime path APIs over embedding repository paths in shell startup files.

## 20. End-to-End Workflows

### 20.1 RTL through waveform

```bash
cd ~/SaxoFlow/projects
saxoflow unit sample_core
cd sample_core

# Add RTL and a testbench under source/.
saxoflow lint --include-tb
saxoflow simulate --tb source/tb/systemverilog/sample_core_tb.sv
```

### 20.2 RTL through generic synthesis and schematic

```bash
cd ~/SaxoFlow/projects/sample_core
saxoflow synth --top sample_core --preflight-lint --show-log
saxoflow schematic --input synthesis/out/synthesized.json --open
```

### 20.3 Formal

```bash
cd ~/SaxoFlow/projects/sample_core
# Add a formal harness under formal/source/.
saxoflow formal \
  --rtl source/rtl/systemverilog/sample_core.sv \
  --sva formal/source/sample_core_formal.sv \
  --sby-task bmc_z3
```

### 20.4 Sky130 physical design

```bash
saxoflow install openroad
saxoflow install orfs
saxoflow pdk install sky130hd --accept-license
saxoflow pdk verify sky130hd

cd ~/SaxoFlow/projects/sample_core
saxoflow pnr init \
  --platform sky130hd \
  --top sample_core \
  --clock-port clk \
  --clock-period 10
saxoflow pnr run --synthesize --variant baseline --show-log
saxoflow pnr status --variant baseline
saxoflow pnr report --variant baseline
saxoflow pnr gui --stage finish --variant baseline
```

### 20.5 Compare physical-design experiments

```bash
saxoflow pnr run \
  --synthesize \
  --variant compact \
  --utilization 0.50 \
  --place-density 0.58

saxoflow pnr report \
  --compare baseline \
  --compare compact
```

## 21. Testing

### 21.1 Test organization

The repository currently contains 73 Python test modules organized primarily as:

```text
tests/
├── test_coolcli/                TUI, shell, formatting, logging, and teach tests
├── test_saxoflow/               core CLI and EDA wrapper tests
├── test_saxoflow_agenticai/     agents, providers, and orchestration tests
└── test_*.py                    cross-cutting or standalone tests
```

Fixtures use temporary workspaces, generic HDL module names, mocked executables, fake provider responses, generated manifests, and captured Click output. Tests must not depend on a production design name.

### 21.2 Test categories

| Category | Typical coverage |
|---|---|
| Unit | Path resolution, discovery, parsing, command construction, schema validation |
| CLI | Click registration, help, options, errors, exit codes |
| Integration | Temporary unit workflows and interactions across modules |
| Recipe | Installer dependency and command behavior |
| Environment-dependent | Real EDA tools, displays, PDKs, and large external data |
| Agentic | Routing, generated content, repair actions, provider adapters |

Major covered areas include:

```text
workspace runtime
unit scaffolding
simulation and waveform flows
formal discovery and SBY updates
lint discovery and engine selection
synthesis scripts, targets, frontends, logs, and outputs
schematic rendering and viewer selection
PDK manifests, installation, verification, and registration
P&R configuration, stages, reports, locks, GUI, and diagnosis
teach packs and tutor sessions
agent session logs and redaction
agent registries, providers, and direct commands
installer recipes and diagnosis
```

### 21.3 Supported full regression

The currently validated supported suite is:

```bash
pytest -q \
  --ignore=tests/test_response_formatter.py \
  --ignore=tests/test_formatter_standalone.py
```

Validated result on June 7, 2026:

```text
1494 passed, 1 warning
```

This is a dated snapshot, not a permanent count. Update it only after running the same command.

The excluded formatter tests require optional dependencies in the current repository. A raw all-test collection may have additional environment-dependent failures and should not replace the supported-suite result without resolving those dependencies.

### 21.4 Focused tests

Examples:

```bash
pytest -q tests/test_saxoflow/test_makeflow.py -k 'sim or formal'
pytest -q tests/test_saxoflow/test_lintflow.py
pytest -q tests/test_saxoflow/test_synthflow.py
pytest -q tests/test_saxoflow/test_schematicflow.py
pytest -q \
  tests/test_saxoflow/test_pdk_registry.py \
  tests/test_saxoflow/test_pnrflow.py \
  tests/test_saxoflow/test_diagnose.py
pytest -q tests/test_coolcli
pytest -q tests/test_saxoflow_agenticai
```

Use `rg --files tests` to confirm exact filenames before relying on a focused command in automation.

### 21.5 Real-tool validation

Mocked tests validate orchestration without requiring large installations. Release qualification also needs real-tool smoke tests.

PDK verification:

```bash
saxoflow pdk verify sky130hd
saxoflow diagnose pdk sky130hd
```

P&R resolution without execution:

```bash
cd ~/SaxoFlow/projects/sample_core
saxoflow pnr run --synthesize --dry-run --show-log
```

Real generic synthesis:

```bash
saxoflow synth --top sample_core --show-log
test -s synthesis/out/synthesized.json
test -s synthesis/reports/yosys.log
```

Real P&R:

```bash
saxoflow diagnose pnr --platform sky130hd
saxoflow pnr run --synthesize --variant smoke --fresh --show-log
saxoflow pnr status --variant smoke
```

Headless GUI bootstrap validation:

```bash
openroad -exit pnr/generated/gui-default.tcl
```

The generated Tcl filename can vary by stage or variant. Use the path printed by `pnr gui` or inspect `pnr/generated/`.

Formal smoke:

```bash
saxoflow formal --sby-task bmc_z3
```

Real-tool tests should record executable versions, platform lock, host environment, and relevant logs.

### 21.6 Documentation verification

Before merging changes to this reference:

1. Compare top-level command tables with Click registrations and `saxoflow --help`.
2. Compare nested command tables with each group help.
3. Run all documented `--help` examples.
4. Verify referenced paths against the unit scaffold and package tree.
5. Search for obsolete underscore command spellings.
6. Search for historical directories such as `formal/src`.
7. Recount tools, groups, presets, agents, and providers from source definitions.
8. Run a Markdown link and heading check if available.
9. Run `git diff --check`.

Useful searches:

```bash
rg 'saxoflow [a-z_]+_[a-z_]+' docs/SAXOFLOW_TECHNICAL_REFERENCE.md
rg 'formal/src|_saxoflow_auto\.sby' \
  docs/SAXOFLOW_TECHNICAL_REFERENCE.md
git diff --check -- docs/SAXOFLOW_TECHNICAL_REFERENCE.md
```

## 22. Known Limitations

1. Built-in Yosys SystemVerilog support is limited without the Slang plugin.
2. Generated P&R SDC files define only the clock. Real timing closure requires authored input delay, output delay, uncertainty, false-path, multicycle, and related constraints where applicable.
3. `pnr report` currently misses some ORFS JSON reports whose filenames do not contain `metrics`.
4. Magic and Netgen are optional and are not part of the current default successful P&R run.
5. The default full agentic pipeline still leaves formal-property generation disabled.
6. Some formatter tests require optional dependencies.
7. Icarus simulation does not support VHDL inputs.
8. The lint and Yosys wrappers currently reject VHDL rather than selecting a VHDL frontend.
9. Provider availability and model behavior depend on external services and credentials.
10. Installer system-package handling primarily targets Debian and Ubuntu environments.
11. Open PDK availability does not constitute fabrication signoff or foundry qualification.
12. Agent transparency logs provide action and rationale summaries, not hidden chain-of-thought.
13. Environment-dependent GUI behavior varies between WSLg, X11, native Linux, and headless systems.

## 23. Developer Maintenance Rules

When adding or changing a public command:

1. Register it in the unified Click tree.
2. Add CLI tests for help, valid input, invalid input, and exit status.
3. Add flow-level tests for discovery and artifacts.
4. Update this command catalog and the relevant workflow section.
5. Preserve workspace ownership and avoid repository-root assumptions.

When adding a platform:

1. Add or register a versioned manifest.
2. Avoid platform-specific branches in generic orchestration.
3. Define libraries, corners, layers, RC data, and compatibility.
4. Add technology-load and configuration tests.
5. Add an environment-dependent full-flow job when practical.
6. Classify fabrication, experimental, reference, or custom status honestly.

When adding agent behavior:

1. Define its target files and action contract.
2. Log user-visible decisions and actions.
3. Apply workspace restrictions and redaction.
4. Validate with the domain tool that motivated the action.
5. Add mocked tests and at least one real-tool smoke path where feasible.

## 24. Quick Reference

| Goal | Command |
|---|---|
| Start TUI | `saxoflow` |
| Create unit | `saxoflow unit NAME` |
| Simulate | `saxoflow sim` |
| Simulate and view | `saxoflow simulate` |
| Formal verification | `saxoflow formal` |
| Lint RTL | `saxoflow lint` |
| Synthesize | `saxoflow synth --show-log` |
| Render netlist | `saxoflow schematic --open` |
| List PDKs | `saxoflow pdk list` |
| Install PDK | `saxoflow pdk install PLATFORM --accept-license` |
| Verify PDK | `saxoflow pdk verify PLATFORM` |
| Initialize P&R | `saxoflow pnr init --platform PLATFORM --top TOP` |
| Run P&R | `saxoflow pnr run --synthesize --show-log` |
| View P&R status | `saxoflow pnr status` |
| Open OpenROAD GUI | `saxoflow pnr gui --stage finish` |
| Diagnose environment | `saxoflow diagnose summary` |
| Diagnose P&R | `saxoflow diagnose pnr --platform PLATFORM` |
| List lessons | `saxoflow teach list` |
| Start lesson | `saxoflow teach start PACK_ID` |
| Inspect agent log | `agentlog show` inside the TUI |

This reference should be updated in the same change that modifies any public command, generated project structure, supported platform, agent registry, installer definition, or supported test command.
