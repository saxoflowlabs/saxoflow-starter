# SaxoFlow — Comprehensive Technical Reference
### Prepared for SMACD 2026 Research Paper

---

## Table of Contents

1. [Project Identity & Motivation](#1-project-identity--motivation)
2. [High-Level Architecture](#2-high-level-architecture)
3. [Repository Map & File Inventory](#3-repository-map--file-inventory)
4. [Module 1 — `saxoflow` (Unified CLI & EDA Flow Engine)](#4-module-1--saxoflow-unified-cli--eda-flow-engine)
   - 4.1 CLI (`saxoflow/cli.py`)
   - 4.2 Tool Taxonomy (`saxoflow/tools/definitions.py`)
   - 4.3 Preset System (`saxoflow/installer/presets.py`)
   - 4.4 Tool Installer (`saxoflow/installer/runner.py`)
   - 4.5 Interactive Environment Setup (`saxoflow/installer/interactive_env.py`)
   - 4.6 Make-Based EDA Flow (`saxoflow/makeflow.py`)
   - 4.7 Project Scaffolding (`saxoflow/unit_project.py`)
   - 4.8 Diagnostics (`saxoflow/diagnose.py`, `diagnose_tools.py`)
5. [Module 2 — `saxoflow_agenticai` (LLM-Driven Design Automation)](#5-module-2--saxoflow_agenticai-llm-driven-design-automation)
   - 5.1 Architecture Overview
   - 5.2 Agent Catalog
   - 5.3 Base Agent (`core/base_agent.py`)
   - 5.4 Agent Manager (`core/agent_manager.py`)
   - 5.5 Model Selector (`core/model_selector.py`)
   - 5.6 Feedback Coordinator (`orchestrator/feedback_coordinator.py`)
   - 5.7 Agent Orchestrator (`orchestrator/agent_orchestrator.py`)
   - 5.8 Generator Agents (RTL, TB, FProp, Report)
   - 5.9 Reviewer Agents (RTL, TB, FProp, Debug)
   - 5.10 Simulation Agent (`agents/sim_agent.py`)
   - 5.11 Prompt Engineering
   - 5.12 Model Configuration (`config/model_config.yaml`)
   - 5.13 CLI Commands (`saxoflow_agenticai/cli.py`)
6. [Module 3 — `cool_cli` (Rich Terminal UI)](#6-module-3--cool_cli-rich-terminal-ui)
  - 6.1 Entrypoint & Launcher (`app.py`, `saxoflow.py`)
   - 6.2 AI Buddy (`ai_buddy.py`, `agentic.py`)
   - 6.3 Panel System (`panels.py`)
   - 6.4 State Management (`state.py`)
   - 6.5 Bootstrap & LLM Setup (`bootstrap.py`)
   - 6.6 Shell Integration (`shell.py`, `completers.py`, `editors.py`)
   - 6.7 Constants (`constants.py`)
   - 6.8 File Operations (`file_ops.py`)
7. [Module 4 — `saxoflow/teach/` (Interactive Tutoring Platform)](#7-module-4--saxoflowteach-interactive-tutoring-platform)
   - 7.1 Architecture & Design Contract
   - 7.2 Data Model (`session.py`)
   - 7.3 Pack Loader (`pack.py`)
   - 7.4 Document Indexer (`indexer.py`)
   - 7.5 Retrieval Layer (`retrieval.py`)
   - 7.6 TUI Bridge (`_tui_bridge.py`)
   - 7.7 Step Runner (`runner.py`)
   - 7.8 Checks Framework (`checks.py`)
   - 7.9 Agent Dispatcher (`agent_dispatcher.py`)
   - 7.10 CLI Commands (`teach/cli.py`)
   - 7.11 ETH Zurich Pack (`packs/ethz_ic_design/`)
8. [EDA Tool Ecosystem Integration](#8-eda-tool-ecosystem-integration)
9. [Project Scaffold & Makefile Template](#9-project-scaffold--makefile-template)
10. [Full Design Flow Walkthrough](#10-full-design-flow-walkthrough)
11. [Technology Stack](#11-technology-stack)
12. [Key Design Decisions & Novelties](#12-key-design-decisions--novelties)
13. [Quantitative Metrics & Scope](#13-quantitative-metrics--scope)
14. [Limitations & Future Work](#14-limitations--future-work)
15. [Glossary](#15-glossary)

---

## 1. Project Identity & Motivation

**SaxoFlow** is an open-source, beginner-friendly RTL design suite released under the Apache-2.0 license by **SaxoFlow Labs**, a student-led initiative at **TU Dresden**. It targets learners and new designers who need to move from a natural-language or Markdown *specification* through RTL design, functional simulation, formal verification, and logic synthesis without hand-wiring a dozen independent EDA utilities.

### Core Pain Points Addressed

| Pain Point | SaxoFlow's Answer |
|---|---|
| Dozens of disjoint open-source EDA tools with unknown install steps | Unified installer with preset profiles and tested shell recipes |
| No standard project folder layout for open-source flows | `saxoflow unit` scaffolds a professional directory tree + Makefile |
| LLM-based code generation untethered from an executable flow | Agentic AI pipeline that generates, reviews, *simulates*, and iteratively heals RTL and testbenches |
| Steep CLI learning curve for students | Rich terminal UI with fuzzy completion, panels, AI Buddy chatbot |
| Multiple LLM providers, no unified API | `ModelSelector` auto-detects available API keys and configures LangChain adapters |

### Platform

- **OS**: WSL / Linux (Ubuntu 20.04+)
- **Python**: 3.9+
- **Entry points**: `python3 saxoflow.py` (Rich TUI) or `saxoflow <cmd>` (headless CLI)

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      SaxoFlow Platform                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                cool_cli  (Rich TUI)                      │    │
│  │  saxoflow.py ──► app.py ──► AI Buddy | Agentic | Shell  │    │
│  │                    │                                     │    │
│  │              Teach Mode Routing                          │    │
│  └──────────────────┬─┴──────────────────────────┬─────────┘    │
│                     │ delegates                   │ teach mode   │
│  ┌──────────────────▼──────────────────────────┐  │              │
│  │              saxoflow  (Unified CLI)         │  │              │
│  │  init-env | install | unit | simulate        │  │              │
│  │  synth | formal | diagnose | wave | teach    │  │              │
│  └──────┬───────────────────────────────────┬──┘  │              │
│         │                                   │     │              │
│  ┌──────▼───────┐    ┌──────────────────────▼──┐  │              │
│  │  Installer   │    │  saxoflow_agenticai       │  │              │
│  │  - presets   │    │  AgentManager            │  │              │
│  │  - runner    │    │  ├─ RTLGenAgent           │◄─┤              │
│  │  - env.json  │    │  ├─ TBGenAgent            │  │              │
│  └──────┬───────┘    │  ├─ FormalPropGenAgent    │  │              │
│         │            │  ├─ DebugAgent            │  │              │
│         │            │  ├─ SimAgent              │  │              │
│  ┌──────▼───────┐    │  └─ TutorAgent (NEW) ◄────┼──┤              │
│  │ EDA Toolchain│    │  AgentOrchestrator         │  │              │
│  │ iverilog     │    │  ModelSelector             │  │              │
│  │ verilator    │◄───┤  FeedbackCoordinator       │  │              │
│  │ yosys        │    └────────────────────────────┘  │              │
│  │ symbiyosys   │                                     │              │
│  │ openroad     │    ┌────────────────────────────────▼────────┐    │
│  │ gtkwave ...  │    │  saxoflow/teach/  (Tutoring Platform)    │    │
│  └──────────────┘    │  DocIndex (BM25) | TeachSession          │    │
│                      │  _tui_bridge | runner | checks           │    │
│                      │  AgentDispatcher | pack loader           │    │
│                      │  packs/ethz_ic_design/ (10 lessons)      │    │
│                      └─────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

### Data Flow in Agentic Pipeline

```
spec.md
  │
  ▼
RTLGenAgent ──► RTLReviewAgent ──(review loop, max N iters)──► final RTL
                                            │
                                            ▼
                              TBGenAgent ──► TBReviewAgent ──► final TB
                                            │
                                            ▼
                                      SimAgent (Icarus)
                                            │
                              sim fails? ──► DebugAgent
                                            │
                              iterate healing (RTLGen / TBGen)
                                            │
                                            ▼
                                      ReportAgent ──► pipeline_report
```

---

## 3. Repository Map & File Inventory

```
saxoflow-starter/
│
├── saxoflow.py                     # TUI entry point (installs deps, launches cool_cli.app)
├── start.py                        # Backward-compatible launcher wrapper
├── pyproject.toml                  # Package metadata; entry point: saxoflow = saxoflow.cli:cli
├── requirements.txt                # Editable install (-e .)
├── pytest.ini                      # Test configuration
├── templates/
│   └── Makefile                    # Universal Makefile scaffold for all EDA flows
│
├── packs/                          # Teaching packs (content + lesson YAMLs)
│   └── ethz_ic_design/
│       ├── pack.yaml               # Pack metadata + lesson list
│       ├── docs/                   # PDF/Markdown source documents (gitignored)
│       └── lessons/                # Per-lesson step YAML files (10 lessons)
│           ├── 01_environment_croc_setup.yaml
│           ├── 02_rtl_croc_exploration.yaml
│           └── ...  (03-10)
│
├── saxoflow/                       # Core CLI + EDA flow automation
│   ├── cli.py                      # Click group + all sub-commands (incl. `teach`)
│   ├── makeflow.py                 # simulate, wave, formal, synth, clean, check_tools
│   ├── unit_project.py             # Project scaffold (directory tree + Makefile + scripts)
│   ├── diagnose.py                 # 'diagnose' Click group
│   ├── diagnose_tools.py           # env probes, health scoring, WSL detection
│   ├── tools/
│   │   ├── definitions.py         # APT_TOOLS, SCRIPT_TOOLS, TOOL_DESCRIPTIONS, MIN_TOOL_VERSIONS
│   │   └── registry.yaml          # Native command → saxoflow wrapper mapping
│   ├── installer/
│   │   ├── presets.py              # SIM/FORMAL/FPGA/ASIC/BASE/IDE groups + PRESETS dict
│   │   ├── runner.py               # install_apt(), install_script(), install_all(), etc.
│   │   └── interactive_env.py      # Questionary-based interactive wizard + headless path
│   └── teach/                      # ★ Interactive tutoring subsystem (NEW)
│       ├── __init__.py
│       ├── session.py              # TeachSession + StepDef + PackDef dataclasses
│       ├── pack.py                 # YAML pack/lesson loader → PackDef
│       ├── indexer.py              # DocIndex: BM25 over PDF/Markdown chunks
│       ├── retrieval.py            # retrieve_chunks() + get_index() public API
│       ├── _tui_bridge.py          # Adapter: cool_cli ↔ teach (only coupling point)
│       ├── runner.py               # Step command executor (YAML-declared only)
│       ├── checks.py               # Deterministic step validation checks
│       ├── agent_dispatcher.py     # Dispatch AgentManager agents from step YAML
│       ├── command_map.py          # Native cmd → saxoflow wrapper translation
│       └── cli.py                  # `saxoflow teach` Click group + subcommands
│
├── saxoflow_agenticai/             # LLM-driven design automation
│   ├── cli.py                      # Click commands: rtlgen, tbgen, fpropgen, report, debug, fullpipeline
│   ├── config/
│   │   └── model_config.yaml       # Provider/model/temperature defaults + per-agent overrides
│   ├── core/
│   │   ├── base_agent.py           # Abstract BaseAgent (prompt render + LLM query)
│   │   ├── agent_manager.py        # Factory registry keyed by string (10 agents incl. tutor)
│   │   ├── model_selector.py       # Auto-detects provider from API keys; builds LangChain LLMs
│   │   ├── prompt_manager.py       # Jinja2 rendering wrapper
│   │   └── log_manager.py          # Centralized named logger
│   ├── agents/
│   │   ├── sim_agent.py            # SimAgent: invokes Icarus via makeflow; returns status dict
│   │   ├── tutor_agent.py          # ★ TutorAgent: document-grounded step-bound tutor (NEW)
│   │   ├── generators/
│   │   │   ├── rtl_gen.py          # RTLGenAgent + rtlgen_tool (LangChain Tool)
│   │   │   ├── tb_gen.py           # TBGenAgent + tbgen_tool
│   │   │   ├── fprop_gen.py        # FormalPropGenAgent + fpropgen_tool
│   │   │   └── report_agent.py     # ReportAgent
│   │   └── reviewers/
│   │       ├── rtl_review.py       # RTLReviewAgent
│   │       ├── tb_review.py        # TBReviewAgent
│   │       ├── fprop_review.py     # FormalPropReviewAgent
│   │       └── debug_agent.py      # DebugAgent (sim failure analysis + suggested_agents)
│   ├── orchestrator/
│   │   ├── agent_orchestrator.py   # AgentOrchestrator.full_pipeline()
│   │   └── feedback_coordinator.py # AgentFeedbackCoordinator.iterate_improvements()
│   ├── prompts/                    # Jinja2/LangChain prompt text files
│   │   ├── rtlgen_prompt.txt
│   │   ├── rtlgen_improve_prompt.txt
│   │   ├── tbgen_prompt.txt
│   │   ├── tbgen_improve_prompt.txt
│   │   ├── fpropgen_prompt.txt
│   │   ├── fpropgen_improve_prompt.txt
│   │   ├── rtlreview_prompt.txt
│   │   ├── tbreview_prompt.txt
│   │   ├── fpropreview_prompt.txt
│   │   ├── debug_prompt.txt
│   │   ├── report_prompt.txt
│   │   ├── tutor_prompt.txt        # ★ TutorAgent 5-section context bundle prompt (NEW)
│   │   ├── tutor_agent_result.txt  # ★ Post-agent-invocation explanation prompt (NEW)
│   │   ├── verilog_guidelines.txt  # Prepended to rtlgen + rtlreview prompts
│   │   ├── verilog_constructs.txt  # Prepended to rtlgen + rtlreview prompts
│   │   ├── tb_guidelines.txt       # Prepended to tbgen + tbreview prompts
│   │   └── tb_constructs.txt       # Prepended to tbgen + tbreview prompts
│   └── utils/
│       └── file_utils.py           # write_output(), base_name_from_path()
│
├── cool_cli/                       # Rich terminal UI
│   ├── app.py                      # Interactive prompt loop + routing (incl. teach mode)
│   ├── agentic.py                  # run_quick_action(), ai_buddy_interactive(), _run_clarification_flow()
│   ├── ai_buddy.py                 # ask_ai_buddy(), detect_action(), detect_incomplete_request(),
│   │                               #   plan_clarification(), build_enriched_spec(), ACTION_KEYWORDS
│   ├── file_ops.py                 # handle_save_file(), scaffold_unit_if_needed(), _verify_placement(),
│   │                               #   determine_dest_path(), write_artifact(), handle_edit_file(),
│   │                               #   handle_multi_file(), handle_read_file(), run_post_hook()
│   ├── bootstrap.py                # .env creation + LLM key setup wizard
│   ├── state.py                    # Global: console, runner, conversation_history, teach_session
│   ├── panels.py                   # Rich Panel builders (welcome, user, ai, agent, output)
│   ├── commands.py                 # Built-in 'help' command renderer
│   ├── completers.py               # HybridShellCompleter (fuzzy + path + teach commands)
│   ├── constants.py                # SHELL_COMMANDS, AGENTIC_COMMANDS, DEFAULT_CONFIG
│   ├── editors.py                  # blocking vs. non-blocking editor detection
│   ├── exporters.py                # Conversation export (Markdown / JSON)
│   ├── persistence.py              # Save/load conversation sessions
│   ├── messages.py                 # ascii_sanitize, error/success/warning helpers
│   ├── banner.py                   # ASCII-art banner via pyfiglet
│   └── shell.py                    # is_unix_command(), process_command(), requires_raw_tty()
│
├── scripts/
│   ├── common/                     # logger.sh, paths.sh, clone_or_update.sh, check_deps.sh
│   └── recipes/                    # Per-tool install scripts
│       ├── verilator.sh
│       ├── yosys.sh
│       ├── symbiyosys.sh
│       ├── openroad.sh
│       ├── nextpnr.sh
│       ├── vivado.sh
│       ├── vscode.sh
│       └── bender.sh
│
└── tests/                          # Pytest suite
    ├── conftest.py
    ├── test_start.py
    ├── test_coolcli/               # Unit tests for cool_cli (18 test modules)
    ├── test_saxoflow/              # Unit tests for saxoflow CLI + tools
    └── test_saxoflow_agenticai/    # Unit tests for agentic AI module
```

---

## 4. Module 1 — `saxoflow` (Unified CLI & EDA Flow Engine)

### 4.1 CLI (`saxoflow/cli.py`)

The top-level **Click group** named `cli` is the entry point registered as `saxoflow` in `pyproject.toml`.

**Commands registered:**

| Command | Handler | Purpose |
|---|---|---|
| `init-env` | `interactive_env.run_interactive_env()` | Interactive or headless environment setup |
| `install <mode>` | `runner.*` | Install tools: selected / all / preset / single |
| `unit <name>` | `unit_project.unit` | Scaffold a new project directory |
| `simulate` | `makeflow.simulate` | Icarus sim + GTKWave |
| `sim` | `makeflow.sim` | Icarus sim only |
| `sim_verilator` | `makeflow.sim_verilator` | Verilator C++ build |
| `sim_verilator_run` | `makeflow.sim_verilator_run` | Run compiled Verilator binary |
| `wave` | `makeflow.wave` | GTKWave for Icarus VCDs |
| `wave_verilator` | `makeflow.wave_verilator` | GTKWave for Verilator VCDs |
| `simulate_verilator` | `makeflow.simulate_verilator` | Full Verilator flow |
| `formal` | `makeflow.formal` | SymbiYosys formal verification |
| `synth` | `makeflow.synth` | Yosys synthesis |
| `clean` | `makeflow.clean` | Remove build artifacts |
| `check_tools` | `makeflow.check_tools` | Verify tool presence in PATH |
| `diagnose` | `diagnose.diagnose` | Sub-group: env health + scoring |
| `teach` | `saxoflow.teach.cli.teach` | Sub-group: interactive tutoring commands |
| `agenticai` | Optional: `saxoflow_agenticai.cli.cli` | Agentic sub-commands (if installed) |

The CLI gracefully degrades if `saxoflow_agenticai` is not installed (the `agenticai` sub-group simply does not appear).

### 4.2 Tool Taxonomy (`saxoflow/tools/definitions.py`)

Centralized tool metadata used throughout the system:

```
APT_TOOLS   = [ghdl, gtkwave, iverilog, klayout, magic, netgen, openfpgaloader]
SCRIPT_TOOLS = {
  cocotb         → scripts/recipes/cocotb.sh,
  covered        → scripts/recipes/covered.sh,
  fusesoc        → scripts/recipes/fusesoc.sh,
  verilator      → scripts/recipes/verilator.sh,
  openroad       → scripts/recipes/openroad.sh,
  opensta        → scripts/recipes/opensta.sh,
  nextpnr        → scripts/recipes/nextpnr.sh,
  rggen          → scripts/recipes/rggen.sh,
  riscv-toolchain→ scripts/recipes/riscv-toolchain.sh,
  spike          → scripts/recipes/spike.sh,
  surelog        → scripts/recipes/surelog.sh,
  sv2v           → scripts/recipes/sv2v.sh,
  symbiyosys     → scripts/recipes/symbiyosys.sh,
  vscode         → scripts/recipes/vscode.sh,
  yosys          → scripts/recipes/yosys.sh,
  vivado         → scripts/recipes/vivado.sh,
  bender         → scripts/recipes/bender.sh,
}
```

`TOOL_DESCRIPTIONS` is a flat dict `{tool_name: "[Category] Short description"}` used by questionary selection menus.

`MIN_TOOL_VERSIONS` maps each tool to its minimum supported version string (used by the `diagnose` health check).

### 4.3 Preset System (`saxoflow/installer/presets.py`)

Six reusable tool groups:

| Group | Tools |
|---|---|
| `SIM_TOOLS` | iverilog, verilator, ghdl, cocotb, covered |
| `FORMAL_TOOLS` | symbiyosys |
| `FPGA_TOOLS` | nextpnr, openfpgaloader, vivado, bender, fusesoc, rggen |
| `ASIC_TOOLS` | openroad, opensta, klayout, magic, netgen, bender, fusesoc, rggen |
| `BASE_TOOLS` | gtkwave, yosys, surelog, sv2v |
| `SW_TOOLS` | riscv-toolchain, spike |
| `IDE_TOOLS` | vscode |

Five high-level presets:

| Preset | Composition |
|---|---|
| `minimal` | IDE + iverilog + gtkwave |
| `fpga` | IDE + verilator + FPGA_TOOLS + BASE_TOOLS |
| `asic` | IDE + verilator + ASIC_TOOLS + BASE_TOOLS |
| `formal` | IDE + yosys + FORMAL_TOOLS |
| `full` | IDE + SIM + FORMAL + FPGA + ASIC + BASE + SW |

The `PRESETS` dict is the **single source of truth** consumed by both `interactive_env.py` and `cli.py`.

### 4.4 Tool Installer (`saxoflow/installer/runner.py`)

- `install_apt(tool)` — runs `sudo apt-get install -y <pkg> && apt-mark hold <pkg>` 
- `install_script(tool)` — sources the corresponding `scripts/recipes/<tool>.sh` via `bash`
- `install_tool(tool)` — dispatches to APT or script installer; appends binary path to `.venv/bin/activate`
- `install_all()` — iterates `ALL_TOOLS`
- `install_selected()` — reads `.saxoflow_tools.json`; installs each tool
- `install_preset(preset)` — resolves preset → calls `install_tool` for each
- `install_single_tool(tool)` — validates against known tools then calls `install_tool`

**`get_version_info(tool, path)` — tool-specific version probe:**
- `klayout`, `magic`, `netgen` → `dpkg -l <tool>` (these tools hang in headless environments with `--version`)
- `iverilog` → `iverilog -v`
- `openroad` → `openroad -version` **(single dash — `--version` is not recognized by OpenROAD)**
- All others → `<tool> --version`
- OpenROAD bare-version fallback: some builds emit only a build ID like `26Q1-1805-g362a91a058` with no `"OpenROAD"` prefix and no dot — after both regex patterns fail, the first non-empty line of output is returned verbatim
- Timeout: 15 s for OpenROAD (slow startup); 5 s for all others
- All exceptions are non-fatal; returns `"(version unknown)"` on failure

Binary paths for script-installed tools (BIN_PATH_MAP):
```
cocotb          → $HOME/.local/cocotb/bin
covered         → $HOME/.local/covered/bin
fusesoc         → $HOME/.local/fusesoc/bin
verilator       → $HOME/.local/verilator/bin
openroad        → $HOME/.local/openroad/bin
opensta         → $HOME/.local/opensta/bin
nextpnr         → $HOME/.local/nextpnr/bin
rggen           → $HOME/.local/rggen/bin
riscv-toolchain → $HOME/.local/riscv-toolchain/bin  (binary: riscv64-unknown-elf-gcc)
spike           → $HOME/.local/spike/bin
surelog         → $HOME/.local/surelog/bin
sv2v            → $HOME/.local/sv2v/bin
symbiyosys      → $HOME/.local/sby/bin
yosys           → $HOME/.local/yosys/bin
bender          → $HOME/.local/bender/bin
```

### 4.5 Interactive Environment Setup (`saxoflow/installer/interactive_env.py`)

`run_interactive_env(preset=None, headless=False)` handles three modes:

1. **Preset mode** (`--preset <name>`): validates preset, resolves tool list, persists to `.saxoflow_tools.json`
2. **Headless mode** (`--headless`): uses `minimal` preset without prompts
3. **Interactive wizard**: Questionary-driven → asks Target (FPGA/ASIC), Verification strategy (Sim/Formal), IDE inclusion, Bender inclusion, then tool group checkboxes

The wizard saves the selection to `.saxoflow_tools.json`.

### 4.6 Make-Based EDA Flow (`saxoflow/makeflow.py`)

`makeflow.py` provides 11 Click commands that orchestrate the project `Makefile` via `make <target>`:

#### Testbench Resolution
`_resolve_testbench(tb, prompt_action)`:
- Scans `source/tb/verilog/*.v`, `source/tb/systemverilog/*.sv`, `source/tb/vhdl/*.vhd`
- 0 files → error; 1 file → auto-select; >1 files → numbered prompt

#### Simulation Commands
```
sim              → make sim-icarus TOP_TB=<stem>   → simulation/icarus/*.vvp + *.vcd
sim_verilator    → make sim-verilator              → simulation/verilator/obj_dir/*
sim_verilator_run→ executes V<tb> binary           → dump.vcd
wave             → gtkwave simulation/icarus/*.vcd
wave_verilator   → gtkwave simulation/verilator/obj_dir/*.vcd
simulate         → sim + wave (one-step)
simulate_verilator → sim_verilator + sim_verilator_run + wave_verilator
```

#### Other Commands
```
formal    → checks for formal/scripts/*.sby → make formal → formal/reports/ + formal/out/
synth     → checks synthesis/scripts/synth.ys → make synth → synthesis/reports/yosys.log + synthesis/out/*
clean     → make clean (with confirmation prompt)
check_tools → shutil.which for every tool in TOOL_DESCRIPTIONS
```

### 4.7 Project Scaffolding (`saxoflow/unit_project.py`)

`saxoflow unit <unitname>` creates:

```
<unitname>/
├── source/
│   ├── specification/          ← paste your spec.md here
│   ├── rtl/{include,verilog,vhdl,systemverilog}/
│   └── tb/{verilog,vhdl,systemverilog}/
├── simulation/{icarus,verilator}/
├── synthesis/{src,scripts,reports,out}/
├── formal/{src,scripts,reports,out}/
├── constraints/
├── pnr/
└── Makefile                    ← copied from templates/Makefile
```

Additionally generates a pre-filled `synthesis/scripts/synth.ys` Yosys script with:
- Technology library read stubs (liberty)
- `read_verilog` for the RTL directory
- `hierarchy -check -top <EDIT_HERE>`
- `proc / opt / flatten`
- `synth_<target>` coarse pass stubs
- `write_verilog` / `write_json` / `write_edif` output stubs
- Timing/power estimation annotations

### 4.8 Diagnostics (`saxoflow/diagnose_tools.py`)

`diagnose_tools.py` provides a full environment health check system:

**FLOW_PROFILES** — per-flow required/optional tool sets:
```
fpga:   required=[iverilog, yosys, gtkwave, nextpnr, openfpgaloader]
asic:   required=[verilator, yosys, gtkwave, openroad, klayout, magic, netgen]
formal: required=[yosys, gtkwave, symbiyosys]
minimal:required=[iverilog, yosys, gtkwave]
```

**Key functions:**
- `infer_flow(selection)` — heuristic: nextpnr→fpga, openroad/magic→asic, symbiyosys→formal, else minimal
- `find_tool_binary(tool)` — searches PATH → `~/.local/<tool>/bin` → nextpnr variants → openfpgaloader aliases
- `extract_version(tool, path)` — per-tool version probe:
  - Most tools: `<tool> --version` parsed by `_RE_GENERIC` (`\d+\.\d+...`)
  - `openroad`: **`openroad -version`** (single dash); checks `_RE_OPENROAD` (`OpenROAD v<ver>`) then `_RE_GENERIC` then first non-empty line (for bare build IDs like `26Q1-1805-g362a91a058`); 15 s timeout
  - `klayout`, `magic`, `netgen`: `dpkg -l <tool>` to avoid headless GUI hang
  - `symbiyosys` / `sby`: tries both aliases
  - `openfpgaloader`: tries `--version` and `-v`
- `compute_health(tools, flow)` — scores: 100 × (required_present/required_total) adjusted by optional bonus
- `analyze_env(selection)` — builds a full report dict: tool check table, PATH analysis, WSL flag, actionable tips
- `detect_wsl()` — checks `/proc/version` for "microsoft"
- `pro_diagnostics(selection)` — rich-formatted professional diagnostics output

---

## 5. Module 2 — `saxoflow_agenticai` (LLM-Driven Design Automation)

### 5.1 Architecture Overview

The agentic AI module implements a **multi-agent LLM pipeline** for automated IC design:

```
ModelSelector ──────────────────────── LangChain LLM instance
      │                                         │
      ▼                                         ▼
AgentManager ──► get_agent(name) ──► BaseAgent subclass
                                          │
                         ┌────────────────┴──────────────────┐
                         │                                   │
              Generator Agents                    Reviewer / Tool Agents
            RTLGenAgent                           RTLReviewAgent
            TBGenAgent                            TBReviewAgent
            FormalPropGenAgent                    FormalPropReviewAgent
            ReportAgent                           DebugAgent
                                                  SimAgent (no LLM)
                         │
                         ▼
              AgentFeedbackCoordinator
              (iterative gen→review loops)
                         │
                         ▼
              AgentOrchestrator.full_pipeline()
```

### 5.2 Agent Catalog

| Key | Class | Type | LLM? | Purpose |
|---|---|---|---|---|
| `rtlgen` | `RTLGenAgent` | Generator | Yes | Generate synthesizable Verilog-2001 RTL |
| `tbgen` | `TBGenAgent` | Generator | Yes | Generate Verilog-2001 testbench |
| `fpropgen` | `FormalPropGenAgent` | Generator | Yes | Generate SVA formal properties |
| `report` | `ReportAgent` | Generator | Yes | Summarize full pipeline results |
| `rtlreview` | `RTLReviewAgent` | Reviewer | Yes | Structured critique of RTL Verilog |
| `tbreview` | `TBReviewAgent` | Reviewer | Yes | Structured critique of testbench |
| `fpropreview` | `FormalPropReviewAgent` | Reviewer | Yes | Critique of formal properties |
| `debug` | `DebugAgent` | Reviewer | Yes | Analyze sim failures; suggest healing agents |
| `sim` | `SimAgent` | Tool | No | Run Icarus simulation; return status dict |
| `tutor` | `TutorAgent` | Tutor | Yes | ★ Document-grounded step-bound interactive tutor |

### 5.3 Base Agent (`core/base_agent.py`)

`BaseAgent` is an ABC providing:

- **Prompt Template Loading**: reads `<prompts_dir>/<template_name>` (LangChain `PromptTemplate` with `template_format="jinja2"`, or Jinja2 via `PromptManager` if `use_jinja=True` / `.j2` extension)
- **`render_prompt(context: dict)`**: fills in Jinja2/LangChain template variables; caches template after first load
- **`query_model(prompt: str) → str`**: calls `llm.invoke(prompt)` and coerces result to string; raises `MissingLLMError` if `llm` is None
- **Optional verbose colorized logging**: `click.secho` with color theme (blue prompt, magenta response, yellow review)
- **Optional file logging**: `log_to_file` appends to a session log
- **Abstract methods**: `run(...)` (required), `improve(...)` (default raises `NotImplementedError`)
- **LCEL / structured output / tools** (optional, guarded by availability checks)

Custom exceptions: `MissingLLMError`, `TemplateNotFoundError`, `PromptRenderError`

### 5.4 Agent Manager (`core/agent_manager.py`)

`AgentManager.get_agent(agent_name, verbose=False, llm=None, **kwargs)`:

1. Looks up `agent_name` in `AGENT_MAP` dict → raises `UnknownAgentError` if missing
2. For non-`sim` agents: calls `ModelSelector.get_model(agent_type=agent_name)` if `llm` is not provided; accepts `provider` and `model_name` kwargs to override config
3. Applies quiet/verbose defaults to constructor kwargs (manages `emit_stdout`, `quiet`, `silent`, `log_level` params via `inspect.signature`)
4. Instantiates and returns the agent

`AgentManager.all_agent_names()` returns the list of registered keys.

### 5.5 Model Selector (`core/model_selector.py`)

Provides a unified LangChain LLM interface to 13 providers:

**PROVIDERS** (ProviderSpec dataclass: env_var, base_url, optional headers, kind):

| Provider | Kind | Env Var |
|---|---|---|
| openai | openai | OPENAI_API_KEY |
| groq | openai | GROQ_API_KEY |
| fireworks | openai | FIREWORKS_API_KEY |
| together | openai | TOGETHER_API_KEY |
| mistral | openai | MISTRAL_API_KEY |
| perplexity | openai | PPLX_API_KEY |
| deepseek | openai | DEEPSEEK_API_KEY |
| dashscope | openai | DASHSCOPE_API_KEY |
| openrouter | openai | OPENROUTER_API_KEY |
| anthropic | anthropic | ANTHROPIC_API_KEY |
| gemini | gemini | GOOGLE_API_KEY |

**Resolution logic** (`get_model(agent_type=None)`):
1. Load `model_config.yaml` (cached)
2. If per-agent override in `agent_models`, use that
3. If `default_provider=auto`: scan `autodetect_priority` list, pick first provider whose env key is set in environment
4. Build `ChatOpenAI`, `ChatAnthropic`, or `ChatGoogleGenerativeAI` via LangChain adapters
5. For OpenAI-compatible providers with a `base_url`, construct `ChatOpenAI(base_url=..., api_key=..., default_headers=...)`

`get_provider_and_model(agent_type=None)` returns `(provider_str, model_str)` without constructing an LLM.

### 5.6 Feedback Coordinator (`orchestrator/feedback_coordinator.py`)

`AgentFeedbackCoordinator.iterate_improvements(agent, initial_spec, feedback_agent, max_iters=1, feedback=None)`:

**Algorithm:**
```
output = agent.run(*unpack(initial_spec))
for i in range(max_iters):
    review = feedback_agent.run(spec, output)
    if is_no_action_feedback(review):
        break
    output = agent.improve(..., review=review)
return (output, review)
```

- `is_no_action_feedback(text)`: regex patterns on 11 phrases (e.g., "no issues", "looks good", "approved", "passed", "clean") → stops early if reviewer approves
- Supports different argument signatures for RTLGen vs TBGen vs FPropGen via `_build_review_args` / `_build_improve_args`

### 5.7 Agent Orchestrator (`orchestrator/agent_orchestrator.py`)

`AgentOrchestrator.full_pipeline(spec_file, project_path, verbose=False, max_iters=3)`:

**Phases:**

1. **Load spec** — reads `spec_file`; raises `FileNotFoundError` if missing
2. **Prepare directories** — creates `source/rtl/verilog/`, `source/tb/verilog/`, `formal/`, `output/report/`, `source/specification/`
3. **RTL Gen + Review** — `iterate_improvements(rtlgen, spec, rtlreview, max_iters)`
4. **TB Gen + Review** — `iterate_improvements(tbgen, (spec, rtl_code, base), tbreview, max_iters)`
5. **Write initial artifacts** — `write_output(rtl_code, ...)` and `write_output(tb_code, ...)`
6. **Simulation & Debug Loop** (up to `max_iters`):
   - `sim_agent.run(project_root, base)` → status dict `{status, stdout, stderr, error_message}`
   - On success + VCD present: break
   - On failure: `debug_agent.run(rtl_code, tb_code, sim_stdout, sim_stderr, sim_error_message)` → `(debug_output, suggested_agents)`
   - Heal: if `suggested_agents` includes `RTLGenAgent` → re-run RTL loop; if `TBGenAgent` → re-run TB loop
   - If `suggested_agents == ["UserAction"]` → cannot auto-heal, break
7. **Formal properties** — currently commented out (placeholder returns)
8. **Report** — `report_agent.run(phase_outputs_dict)` → narrative summary
9. **Return** results dict (12 keys: rtl_code, testbench_code, formal_properties, review reports, sim status/stdout/stderr, debug_report, pipeline_report)

### 5.8 Generator Agents

#### RTLGenAgent (`agents/generators/rtl_gen.py`)

- Prompts: `rtlgen_prompt.txt` + optional prepended `verilog_guidelines.txt` + `verilog_constructs.txt`
- `run(spec: str) → str` — renders prompt with `{spec, review=""}`, queries LLM, calls `extract_verilog_code()`
- `improve(spec, prev_rtl_code, review) → str` — uses `rtlgen_improve_prompt.txt`
- `extract_verilog_code(text)` — regex strips markdown fences; extracts between `module`…`endmodule`
- Exposes LangChain `Tool`: `rtlgen_tool` (name="RTLGen"), `rtlgen_improve_tool` (name="RTLGenImprove")

**RTL Prompt contracts:**
- Output: single Verilog-2001 block only, `module`…`endmodule`, no SystemVerilog keywords
- Synthesizable for iverilog / Verilator / Yosys / OpenROAD
- No `initial`, no `#` delays, no `$display/$finish`
- Explicit port list, parameters, named resets only if spec requires

#### TBGenAgent (`agents/generators/tb_gen.py`)

- Prompts: `tbgen_prompt.txt` + optional `tb_guidelines.txt` + `tb_constructs.txt`
- `run(spec, rtl_code, top_module_name) → str`
- `improve(spec, prev_tb_code, review, rtl_code, top_module_name) → str`
- `extract_verilog_tb_code(text)` — similar regex extractor

**TB Prompt contracts:**
- Verilog-2001 only; `reg` for DUT inputs, `wire` for outputs
- No SystemVerilog types; `integer` only for loop counters
- Adds `$dumpfile("tb.vcd"); $dumpvars(0, tb);`
- Clock: `always #(PERIOD/2)` in `initial`
- Verification via `$display`/`$monitor` (no assertions)
- Ends with `$finish`

#### FormalPropGenAgent (`agents/generators/fprop_gen.py`)

- Prompts: `fpropgen_prompt.txt`
- `run(spec, rtl_code) → str`
- `improve(spec, rtl_code, prev_fprops, review) → str`
- Returns raw SVA text

#### ReportAgent (`agents/generators/report_agent.py`)

- `run(phase_outputs: dict) → str` — generates a human-readable narrative from all pipeline artifacts

### 5.9 Reviewer Agents

#### RTLReviewAgent (`agents/reviewers/rtl_review.py`)

- `run(spec, rtl_code) → str` — structured critique; prepends `verilog_guidelines.txt` + `verilog_constructs.txt`
- Post-processing: `extract_structured_rtl_review(text)` normalizes output into sections
- `improve(spec, rtl_code, feedback) → str` — proxies to `run()`

#### TBReviewAgent, FormalPropReviewAgent

- Mirror pattern of `RTLReviewAgent` with TB/FProp-specific prompts

#### DebugAgent (`agents/reviewers/debug_agent.py`)

- `run(rtl_code, tb_code, sim_stdout, sim_stderr, sim_error_message) → (str, List[str])`
- Returns `(debug_report_text, suggested_agents)` where `suggested_agents ∈ {"RTLGenAgent", "TBGenAgent", "UserAction"}`
- Used by orchestrator to choose which agent to heal

### 5.10 Simulation Agent (`agents/sim_agent.py`)

`SimAgent.run(project_path, top_module) → dict`:
1. Uses `_pushd(project_path)` context manager to `os.chdir`
2. Invokes `saxoflow.makeflow.sim` via Click `CliRunner().invoke()`
3. Captures stdout/stderr via `_capture_stdio()`
4. Checks for `simulation/icarus/*.vcd` existence to confirm success
5. Returns `{status: "success"|"failed", stage, stdout, stderr, error_message}`

### 5.11 Prompt Engineering

SaxoFlow uses a two-layer prompt strategy:

**Layer 1 — Guidelines (prepended):**
- `verilog_guidelines.txt`: tool-specific Verilog rules (iverilog, Verilator, Yosys, OpenROAD compatibility)
- `verilog_constructs.txt`: allowed/forbidden Verilog-2001 construct policy
- `tb_guidelines.txt`: testbench-specific rules (Icarus/Verilator compliance)
- `tb_constructs.txt`: TB construct policy

**Layer 2 — Task prompt:**
- Jinja2 templates with `{{ spec }}`, `{{ rtl_code }}`, `{% if review %}...{% endif %}` blocks
- Template format set to `"jinja2"` in LangChain `PromptTemplate`
- All prompts request the LLM **output only code** — no markdown fences, no explanations, no extra text

**Improve-path prompts** mirror the base prompts but additionally pass `{{ prev_rtl_code }}` / `{{ prev_tb_code }}` / `{{ prev_fprops }}` and `{{ review }}`.

### 5.12 Model Configuration (`config/model_config.yaml`)

```yaml
default_provider: auto        # auto-detect from env
default_temperature: 0.3
default_max_tokens: 8192
autodetect_priority: [openai, anthropic, gemini, groq, mistral, ...]

agent_models:
  sim:                        # sim agent needs no LLM
    provider: none
    model: none

providers:
  openai:    model: gpt-4o-mini,    temperature: 0.3
  groq:      model: llama3-8b-8192, temperature: 0.3
  mistral:   model: mistral-large-latest, max_tokens: null
  deepseek:  model: deepseek-chat
  openrouter:model: anthropic/claude-3.5-sonnet
  anthropic: model: claude-3-5-sonnet-latest, max_tokens: 4096
  gemini:    model: gemini-1.5-pro, max_tokens: null
  ...
```

Per-agent overrides are supported via `agent_models.<agent_name>` block.

### 5.13 CLI Commands (`saxoflow_agenticai/cli.py`)

The standalone CLI is also accessible under `saxoflow agenticai` via the mounted Click group:

| Command | Key arguments | Behavior |
|---|---|---|
| `rtlgen` | `--input spec.md`, `--output dir`, `--provider`, `--model` | Run RTLGenAgent; write `<base>_rtl_gen.v` |
| `tbgen` | `--input spec.md`, `--rtl file.v`, `--output dir` | Run TBGenAgent; write `<base>_tb_gen.v` |
| `fpropgen` | `--input spec.md`, `--rtl file.v`, `--output dir` | Run FormalPropGenAgent |
| `report` | `--input artifacts...` | Run ReportAgent |
| `debug` | `--rtl`, `--tb`, `--stdout`, `--stderr` | Run DebugAgent |
| `fullpipeline` | `-i spec.md`, `--project-path dir`, `--iters N` | AgentOrchestrator.full_pipeline() |

All commands:
- Load `.env` for API keys
- Use `ModelSelector` with `--provider` / `--model` overrides
- Capture output, print phase headers, write artifacts to disk

---

## 6. Module 3 — `cool_cli` (Rich Terminal UI)

### 6.1 Entrypoint & Launcher

`saxoflow.py`:
1. Adds project root to `sys.path`
2. Calls `install_dependencies()` (pip install -e .)
3. Pre-imports `saxoflow.cli` and `saxoflow_agenticai.cli`
4. Imports `cool_cli.app:main` (fallback: `cool_cli.shell:main`)
5. Calls `cool_cli_main()`

`cool_cli/app.py:main()`:
1. Calls `ensure_first_run_setup()` (bootstrap LLM key check)
2. Creates `PromptSession` with `InMemoryHistory` and `HybridShellCompleter`
3. Renders banner + welcome panel
4. **Main loop**: reads input → routes to:
   - Built-in: `help`, `quit`/`exit`, `clear`, `init-env` hints
   - **Teach mode guard** (NEW): if `_state.teach_session is not None`, routes to `_teach_handle(user_input, session, llm=_state._teach_llm)` in `_tui_bridge` — bypasses AI Buddy entirely
   - **Teach unix command capture**: when teach mode is active and the user types a unix/shell command (not a teach command), `app.py` extracts plain text from the Rich renderable output and calls `session.add_terminal_entry(user_input, plain_text)` so the TutorAgent can see what the student ran. It also calls `record_manual_command(user_input, session)` from `_tui_bridge` to auto-advance `current_command_index` if the typed command matches the next declared step command.
   - Agentic commands (from `AGENTIC_COMMANDS` tuple): routed via `subprocess` to the agenticai CLI
   - Shell commands (`!` prefix or known UNIX alias): `process_command()` or raw tty
   - AI Buddy: `ai_buddy_interactive(user_input, history)`
5. Each response is printed via `_print_and_record()` so it persists in `conversation_history` and survives screen redraws

**Teach session startup** (`_start_teach_session_inproc`):
- Loads pack and builds `TeachSession`; stores in `_state.teach_session`
- Builds LLM via `ModelSelector` and stores in `_state._teach_llm`
- Calls `prepare_step_for_display(session)` to immediately show the **first content chunk** of lesson 1

### 6.2 AI Buddy (`ai_buddy.py`, `agentic.py`)

`ask_ai_buddy(user_input, history, file_to_review=None)`:

1. `detect_action(user_input)` → checks `ACTION_KEYWORDS` dict for substring match → returns action key or None
2. If **no action detected** → chat via LLM (uses `ModelSelector`; keeps last `MAX_HISTORY_TURNS=5` turns)
3. If **action detected without code** → returns `{"type": "need_file"}`
4. If **file provided** → invokes appropriate review agent (e.g., `RTLReviewAgent`) → returns `{"type": "review_result"}`
5. Otherwise → returns `{"type": "action", "action": <key>}` for downstream CLI invocation

`ai_buddy_interactive(user_input, history, skip_clarification=False)` in `agentic.py`:
- Handles `need_file` → prompts user to paste code or path
- `review_result` → renders as white `Text`
- `action` → asks confirmation → on yes calls `_invoke_agent_cli_safely([cmd])`
- `chat` → renders LLM response as white `Text`, `Markdown`
- `skip_clarification=True` bypasses the clarification Q&A gate (used by `app.py` after the gate has already run before the spinner)

**ACTION_KEYWORDS** (40+ entries):
```python
"generate rtl"    → "rtlgen"
"rtlgen"          → "rtlgen"
"generate testbench" → "tbgen"
"simulate"        → "sim"
"synth"           → "synth"
"review rtl"      → "rtlreview"
"debug"           → "debug"
"pipeline"        → "fullpipeline"
...
```

#### Clarification Q&A Pipeline

Before invoking the LLM for any file-creation request, the shell runs a multi-step clarification flow to ensure the spec is complete. The flow is architecturally positioned **before** the `console.status("Thinking…")` spinner in `app.py` so that interactive `input()` prompts never interleave with the Rich Live context.

**Stage 1 — Planning** (determine whether to ask anything):

| Function | Source | Behaviour |
|---|---|---|
| `plan_clarification(message, context, prefs)` | `ai_buddy.py` | LLM-driven: sends the user message to the buddy model with a planning prompt; returns a list of question dicts or `None` if nothing to ask. Always includes a `create_unit` question for RTL/TB requests. |
| `detect_incomplete_request(message, prefs)` | `ai_buddy.py` | Hardcoded fallback (no LLM): fires on `_CREATION_INTENT_RE` match when filename+unit are absent; returns a fixed question list. |

Both return the same structure — a list of question dicts:
```python
[
  {
    "key":      "hdl",
    "question": "Which HDL language should I write this in?",
    "choices":  ["SystemVerilog", "Verilog", "VHDL"],
    "default":  "SystemVerilog",
  },
  {
    "key":      "create_unit",
    "question": "Create a unit project folder for this design?",
    "choices":  ["yes", "no"],
    "default":  "yes",          # ← always defaults to yes
    "hint":     "Suggested folder name: 'alu'. A unit folder keeps RTL, TB, and Makefiles in one place.",
    "_candidate_unit": "alu",  # private: carried forward on yes
  },
  {
    "key":      "requirements",
    "question": "Any specific requirements?",
    "choices":  [],
    "default":  "",
    "hint":     "e.g. 32-bit, synchronous reset, 4 operations. Press Enter to skip.",
  },
]
```

`app.py` calls `plan_clarification()` first; if it returns `None` it falls back to `detect_incomplete_request()`.

**`create_unit` question behaviour:**
- Default is always `"yes"`; choosing yes creates a scaffolded unit structure in the correct directory
- A candidate folder name derived from the design name in the message is stored in `_candidate_unit` and shown in the hint
- `detect_incomplete_request()` skips the `create_unit` question when the unit name is already present in the message

**Stage 2 — Interactive Q&A** (`_run_clarification_flow(original, questions, context)` in `agentic.py`):
- Renders a Rich panel with all questions in sequence; collects answers via `input()`
- When user answers `"yes"` to `create_unit`, the candidate unit name is automatically injected into `answers["unit_name"]` — no extra prompt needed
- If the user presses `Ctrl-C` → returns `None` (cancelled; `app.py` prints a yellow "Cancelled." message and loops)

**Stage 3 — Spec synthesis** (`build_enriched_spec(original, answers, context)` in `ai_buddy.py`):
- Calls the LLM to synthesise a single, complete natural-language instruction combining the original request with all Q&A answers
- Must include `"save as <file>.<ext>"` and — when `create_unit=yes` — `"in unit <name>"`
- **Mechanical fallback** (when LLM is unavailable): constructs the enriched spec programmatically:
  - Derives filename stem from design name regex; ext from HDL answer
  - Adds `"in unit <name>"` when `create_unit=yes` (uses `unit_name` or falls back to the derived stem)
  - Omits `"in unit"` when `create_unit=no`
  - This ensures `detect_save_intent()` can always parse the unit name even without an LLM

### 6.8 File Operations (`file_ops.py`)

`cool_cli/file_ops.py` orchestrates LLM-generated file creation inside SaxoFlow unit projects.

**Key public functions:**

| Function | Description |
|---|---|
| `scaffold_unit_if_needed(unit_name, cwd)` | Creates (or reuses) a full unit project scaffold; calls `saxoflow.unit_project` internals directly — no subprocess |
| `determine_dest_path(unit_root, filename, content_type)` | Maps `(content_type, extension)` → correct unit subdirectory; creates dirs |
| `write_artifact(content, dest_path)` | Writes text to `dest_path`; creates parent dirs |
| `read_artifact(path)` | Reads and returns file content as UTF-8 |
| `find_file_in_unit(unit_root, filename)` | Recursive search for a bare filename inside a unit tree |
| `run_post_hook(unit_root, hook_type, dest_path, content_type, auto_fix)` | Runs `saxoflow sim/lint/synth` inside unit; LLM auto-fix loop on failure (up to 2 retries) |
| `handle_save_file(buddy_result, history)` | Full orchestration: generate → scaffold → place → verify → (optional post-hook) → Rich panel |
| `handle_edit_file(buddy_result, history)` | LLM patch + write-back for existing files |
| `handle_multi_file(buddy_result, history)` | Generates RTL + TB (and optionally formal) in one shot |
| `handle_read_file(buddy_result, history)` | Finds file on disk; generates LLM explanation |

**Content type → subdirectory mapping (`_DEST_DIRS`):**

| `content_type` | Extension | Subdirectory |
|---|---|---|
| `rtl` | `.sv` / `.svh` | `source/rtl/systemverilog/` |
| `rtl` | `.v` / `.vh` | `source/rtl/verilog/` |
| `rtl` | `.vhd` / `.vhdl` | `source/rtl/vhdl/` |
| `tb` | `.sv` | `source/tb/systemverilog/` |
| `tb` | `.v` | `source/tb/verilog/` |
| `formal` | `.sva` / `.sv` | `formal/src/` |
| `formal` | `.sby` | `formal/scripts/` |
| `synth` | `.tcl` | `synthesis/scripts/` |

**`handle_save_file()` pipeline (6 steps):**

```
Step 1: generate_code_for_save(spec, content_type, rtl_context, top_module)
          │
          │  (for tb/formal: probe unit_root for existing RTL to give DUT context)
          ▼
Step 2: scaffold_unit_if_needed(unit_name)   [if unit requested]
          ▼
Step 3: determine_dest_path(unit_root, filename, content_type)
          ▼
Step 4: write_artifact(code, dest)
          ▼
Step 4a: _verify_placement(written, unit_root, filename, content_type)   ← NEW
          ▼
Step 5: detect_companion_files() + generate_companion_file()   [optional]
          ▼
Step 6: run_post_hook()   [if requested in message: "and then simulate"]
```

**`_verify_placement(written, unit_root, filename, content_type)` — placement guard:**

Called immediately after every file write. Guarantees the generated file ends up in the correct unit subdirectory even when the enriched spec was produced by the mechanical LLM fallback (which could omit or mis-parse the unit clause).

| Condition | Action | Message shown |
|---|---|---|
| `unit_root is None` | No-op (cwd placement is correct by design) | `✓ Placement OK` |
| File already at `determine_dest_path(...)` | No-op | `✓ Placement verified` |
| File anywhere else (e.g. cwd) | `shutil.move(written, expected_dest)` | `⚠ Relocated to correct unit path` |

Returns `(final_path, rich_markup_string)`. The markup string is appended as the next line in the success panel.

---

### 6.3 Panel System (`panels.py`)

Rich panel builders used throughout the TUI:

| Function | Border color | Content |
|---|---|---|
| `welcome_panel(text)` | blue | Welcome message on startup |
| `user_input_panel(msg)` | green | Echoes the user's input |
| `ai_panel(renderable)` | cyan | AI Buddy responses |
| `agent_panel(renderable)` | magenta | Agentic command outputs |
| `output_panel(renderable)` | white | General command output |
| `error_panel(msg)` | red | Error messages |
| `saxoflow_panel(renderable)` | blue | Generic SaxoFlow panel |

All panels use `_default_panel_width()` (80% of terminal, min 80 chars) and `_coerce_text()` (fold overflow, no-wrap normalization).

### 6.4 State Management (`state.py`)

Global singletons (importable from `cool_cli.state`):

| Name | Type | Purpose |
|---|---|---|
| `console` | `_SoftWrapConsole` | Rich Console (guaranteed `options.soft_wrap`) |
| `runner` | `CliRunner` | Click test runner for agentic invocations |
| `conversation_history` | `List[HistoryTurn]` | All user/assistant turns |
| `attachments` | `List[Attachment]` | File blobs attached this session |
| `system_prompt` | `Optional[str]` | Global system instruction |
| `config` | `Dict` | Runtime config (model, temperature, etc.) |
| `teach_session` | `Optional[TeachSession]` | ★ Active tutoring session; `None` outside teach mode |
| `_teach_llm` | `Optional[LLM]` | ★ Pre-built LangChain LLM passed to TutorAgent |

`reset_state()` clears `teach_session` and `_teach_llm` to `None`. `get_state_snapshot()` is provided for test isolation.

### 6.5 Bootstrap & LLM Setup (`bootstrap.py`)

`ensure_first_run_setup()`:
1. `load_dotenv()` 
2. `_ensure_env_file_exists(cwd)` → creates `.env` template if missing
3. `_resolve_target_provider_env()` → calls `ModelSelector.get_provider_and_model()`
4. Checks if required API key is set in env
5. If missing and TTY: runs `run_key_setup_wizard(provider, env_var)`
   - Prompts `getpass()` for API key
   - Writes `KEY=value` to `.env` idempotently
   - Reloads `.env`; verifies
6. If missing and non-TTY / `SAXOFLOW_NONINTERACTIVE=1`: prints instructions only

### 6.6 Shell Integration (`shell.py`, `completers.py`, `editors.py`)

`HybridShellCompleter` (from `completers.py`): combines:
- Static command list completion (built-ins + agentic + shell)
- `PathCompleter` for file paths triggered after space

`shell.py`:
- `is_unix_command(cmd)`: returns `True` when the first token is a known system binary, begins with `./`, `../`, or `/` (relative/absolute executable path), or is prefixed with `!`; also delegates to `_needs_real_shell()` for compound shell syntax
- `_needs_real_shell(raw)`: detects compound shell syntax (`&&`, `||`, `|`, `;`, redirects, `$(`, `cd `, `export `, `source `) — forces execution through `bash -c`
- `process_command(cmd)`: dispatches `SHELL_COMMANDS` aliases or `subprocess.run`; the `cd` branch is guarded with `not _needs_real_shell(cmd)` so that compound commands like `cd dir && ./binary` fall through to `bash -c` rather than updating the virtual CWD
- `run_shell_command(cmd)`: PATH-resolved execution; accepts relative (`./binary`) and absolute (`/path/to/exe`) executables in addition to commands found on `PATH`
- `requires_raw_tty(cmd)`: detects blocking editors or raw-mode commands

`editors.py`:
- `is_blocking_editor_command(cmd)`: checks BLOCKING_EDITORS (`nano`,`vim`,`vi`,`micro`)
- Blocking editors: TUI suspends, restores after editor exits

### 6.7 Constants (`constants.py`)

```python
SHELL_COMMANDS = {"ls", "ll", "pwd", "whoami", "date"}
BLOCKING_EDITORS = ("nano", "vim", "vi", "micro")
NONBLOCKING_EDITORS = ("code", "subl", "gedit")
AGENTIC_COMMANDS = ("rtlgen", "tbgen", "fpropgen", "report", 
                    "rtlreview", "tbreview", "fpropreview", 
                    "debug", "sim", "fullpipeline")
DEFAULT_CONFIG = {"model": "placeholder", "temperature": 0.7, "top_k": 1, "top_p": 1.0}
CUSTOM_PROMPT_HTML = "<ansibrightwhite>✦</ansibrightwhite> ..."
```

---

## 7. Module 4 — `saxoflow/teach/` (Interactive Tutoring Platform)

> **Status: Fully implemented.** The tutoring subsystem was designed and built in full after the core SaxoFlow platform was stable. It adds an interactive, document-grounded, step-by-step teaching layer on top of the existing EDA automation stack.

### 7.1 Architecture & Design Contract

The `saxoflow/teach/` package implements a **content-first tutoring platform** where:

- A pack author uploads PDFs/Markdown files into `packs/<pack_id>/docs/`
- A `pack.yaml` + per-lesson YAML files define the curriculum (steps, commands, checks, hints, agent invocations)
- Running `saxoflow teach start <pack_id>` indexes the documents (BM25), starts a `TeachSession`, and immediately presents the first PDF content chunk to the student
- The student reads through the material chunk by chunk, asks natural-language questions (answered by TutorAgent grounded in the current chunk + retrieved context), and eventually reaches a command phase where they execute the declared tool commands
- All EDA agents (RTLGenAgent, TBGenAgent, etc.) are callable from within a step via `agent_invocations` YAML field

**Four non-negotiable architecture rules:**

| # | Rule | Enforcement |
|---|---|---|
| 1 | LLM always receives step + doc chunks + conversation turns | `TeachSession` injected into every `TutorAgent.run()` call |
| 2 | LLM never decides which command to execute | Commands come only from step YAML; `runner.py` executes |
| 3 | Context is never lost between turns | `TeachSession` lives as `_state.teach_session` singleton |
| 4 | `_tui_bridge.py` is the **only** file in `saxoflow/teach/` that may import from `cool_cli` | Enforced by architecture contract comment in the module |

**Content display state machine:**

```
Session start
     │
     ▼
prepare_step_for_display(session)
     │
     ├── mode == "sequential" ──► _render_chunk_panel(session)   [chunk 1/N]
     │                                   │
     │                            next ──► chunk 2/N … chunk N/N
     │                                   │
     │                          (after last chunk)
     │                                   │
     │                            next ──► _render_command_phase_panel()
     │                                   │
     │                            next ──► advance to next lesson
     │
     └── mode == "index"  ──► _render_index_panel(session)   [numbered topic list]
                                         │
                              type <N> ──► jump to chunk N (then sequential)
                              next ──► read sequentially from chunk 1
```

**Q&A scope:** When a student types a free-text question, the context injected into the TutorAgent depends on the current phase:
- *Content phase*: the currently-displayed chunk text (up to 400 characters) is prepended, followed by BM25 retrieval from the full pack index. Questions about what is on screen are answered from that exact content first.
- *Question phase*: the active reflection question text is prepended so the tutor can evaluate or expand the student's answer.
- *All phases*: the last 3 entries from `session.terminal_log` (manually typed commands + outputs) are prepended when non-empty, giving the tutor immediate visibility into recent shell activity without the student needing to copy-paste.

---

### 7.2 Data Model (`session.py`)

All tutoring state is held in immutable leaf dataclasses and one mutable session:

#### `QuestionDef` (frozen)
| Field | Type | Description |
|---|---|---|
| `text` | `str` | Question text displayed in the TUI panel |
| `after_command` | `int` | `-1` = shown after last content chunk (pre-command); `N` = after command N (reserved) |
| `kind` | `str` | `"reflection"` (open-ended, no automated answer check) |

#### `CheckDef` (frozen)
| Field | Type | Description |
|---|---|---|
| `kind` | `str` | `"file_exists"` \| `"file_contains"` \| `"stdout_contains"` \| `"exit_code_0"` \| `"user_confirms"` \| `"always"` |
| `pattern` | `str` | Regex / glob / substring / confirmation prompt text |
| `file` | `str` | File path for `file_exists` / `file_contains` checks |

#### `CommandDef` (frozen)
| Field | Type | Description |
|---|---|---|
| `native` | `str` | Exact command from the tutorial (e.g. `iverilog -g2012 -o sim.out tb.v dut.v`) |
| `preferred` | `Optional[str]` | SaxoFlow wrapper if available (e.g. `saxoflow sim`) |
| `use_preferred_if_available` | `bool` | Select wrapper when registry confirms availability |
| `background` | `bool` | When `True`, runner launches with `Popen` (non-blocking); used for GUI tools like GTKWave |

#### `AgentInvocationDef` (frozen)
| Field | Type | Description |
|---|---|---|
| `agent_key` | `str` | `AgentManager` key (e.g. `"rtlgen"`, `"tbgen"`, `"fullpipeline"`) |
| `args` | `Dict[str, str]` | Keyword arguments forwarded to the agent |
| `description` | `str` | Human-readable summary shown to student |

#### `StepDef`
| Field | Type | Description |
|---|---|---|
| `id` | `str` | Unique step identifier (e.g. `"sim_run"`) |
| `title` | `str` | Short step title |
| `goal` | `str` | One-paragraph learning objective |
| `read` | `List[Dict]` | `[{"doc": filename, "pages": "...", "section": "..."}]` |
| `commands` | `List[CommandDef]` | Ordered commands to execute |
| `agent_invocations` | `List[AgentInvocationDef]` | AI agents callable from this step |
| `success` | `List[CheckDef]` | All must pass for step completion |
| `hints` | `List[str]` | Common-failure hint strings |
| `questions` | `List[QuestionDef]` | Reflection questions shown after the last content chunk |
| `notes` | `str` | Instructor notes (not shown in tutor prompt) |
| `mode` | `str` | `"sequential"` (default) \| `"index"` (lecture topic chooser) |

#### `PackDef`
| Field | Type | Description |
|---|---|---|
| `id` | `str` | Pack directory name (e.g. `"ethz_ic_design"`) |
| `name` | `str` | Human-readable pack name |
| `version` | `str` | SemVer string |
| `authors` | `List[str]` | Author / institution list |
| `description` | `str` | Multi-line pack description |
| `docs` | `List[Dict]` | `[{"filename": str, "type": str}]` documents to index |
| `steps` | `List[StepDef]` | Ordered curriculum steps |
| `docs_dir` | `Path` | Absolute path to `<pack_path>/docs/` |
| `pack_path` | `Path` | Absolute path to pack root |

#### `TeachSession`
The active session singleton stored in `_state.teach_session`:

| Field | Type | Persisted | Description |
|---|---|---|---|
| `pack` | `PackDef` | — | Loaded pack |
| `current_step_index` | `int` | ✓ | Zero-based step index |
| `conversation_turns` | `List[Dict]` | — | Rolling turn buffer (capped at `MAX_HISTORY_TURNS*2 = 12`) |
| `last_run_log` | `str` | — | stdout+stderr of last executed command |
| `last_run_exit_code` | `int` | — | Exit code of last command (`-1` = none run) |
| `last_run_command` | `str` | — | Exact command string last executed |
| `workspace_snapshot` | `Dict[str, bool]` | — | Expected artefact existence map |
| `checks_passed` | `Dict[str, bool]` | ✓ | `{step_id: True}` for completed steps |
| `agent_results` | `Dict[str, str]` | ✓ (capped) | Agent output keyed by step id |
| `current_chunk_index` | `int` | — | Active chunk within `step_chunks` |
| `step_chunks` | `List[Chunk]` | — | Chunks loaded for current step |
| `in_content_phase` | `bool` | — | `True` = reading content; `False` = command phase |
| `chunk_mode` | `str` | — | `"sequential"` or `"index"` (copied from `step.mode`) |
| `pending_questions` | `List[QuestionDef]` | — | Queue of unanswered reflection questions |
| `question_phase` | `bool` | — | `True` when a reflection question is active |
| `current_question` | `Optional[QuestionDef]` | — | The reflection question currently displayed; injected into TutorAgent context so it can evaluate the student's answer |
| `current_command_index` | `int` | ✓ | Which command the student runs next (`run` press); reset on step change |
| `cwd` | `str` | ✓ | Effective working directory relative to `project_root`; updated by standalone `cd` commands |
| `user_confirms_acknowledged` | `bool` | ✓ | Set `True` by `confirm` command; gates the `next` command for `user_confirms` steps; reset on step change |
| `terminal_log` | `List[str]` | ✗ | Rolling buffer (last 5) of manually typed commands + output; injected into TutorAgent prompt; not persisted |

**Class variables:**
- `_TERMINAL_LOG_MAX = 5` — maximum rolling entries in `terminal_log`
- `_TERMINAL_LOG_CAP = 800` — character cap per `terminal_log` entry (excess truncated with `"... [truncated]"`)

**Key methods:**
- `advance() → bool` — moves to next step; resets `current_command_index`, `cwd`, `user_confirms_acknowledged`; returns `False` at end
- `go_back() → bool` — moves to previous step; same three resets; returns `False` at first step
- `reset_chunk_state()` — resets all chunk/question fields when step changes; intentionally does **not** reset `current_command_index`
- `add_turn(role, content)` — appends turn and enforces history window
- `add_terminal_entry(cmd, output)` — appends `"$ cmd\noutput"` to `terminal_log`; caps output at 800 chars; evicts oldest beyond 5 entries
- `save_progress()` / `load_progress()` — JSON persistence under `.saxoflow/teach/progress.json`; persists `current_step_index`, `current_command_index`, `cwd`, `user_confirms_acknowledged`, `checks_passed`, `agent_results`
- `update_workspace_snapshot(root)` — probes filesystem for expected artefacts

---

### 7.3 Pack Loader (`pack.py`)

`load_pack(pack_id, packs_dir="packs") → PackDef`

1. Resolves `<packs_dir>/<pack_id>/pack.yaml`
2. Reads top-level metadata fields (id, name, version, authors, description, docs)
3. Sets `docs_dir = pack_path / "docs"` (created if missing)
4. Iterates `lessons:` list → loads each `<pack_path>/lessons/<filename>.yaml` via `_load_step()`
5. Returns fully-populated `PackDef` with `StepDef` list

`_load_step(path) → StepDef` parses:
- `commands:` → `CommandDef(native, preferred, use_preferred_if_available)`
- `agent_invocations:` → `AgentInvocationDef(agent_key, args, description)`
- `success:` → `CheckDef(kind, pattern, file)`
- `mode:` → `str` defaulting to `"sequential"`

All YAML schema violations raise `ValueError` with human-readable messages.

---

### 7.4 Document Indexer (`indexer.py`)

**`Chunk` dataclass:**
| Field | Description |
|---|---|
| `text` | Passage text (cleaned, no excess whitespace) |
| `source_doc` | Originating filename (e.g. `"ethz_vlsi2.pdf"`) |
| `page_num` | 1-based page number; `-1` for Markdown |
| `section_hint` | Nearest heading above the chunk |
| `chunk_index` | Sequential position in the full document |

**`DocIndex` class:**

`DocIndex(pack: PackDef)`:
- `INDEX_DIR = Path(".saxoflow/teach/index")`
- `cache_path = INDEX_DIR / f"{pack.id}.pkl"`

**`build() → "DocIndex"`**:
1. For each doc in `pack.docs`:
   - `.pdf` → `pypdf.PdfReader`, page-by-page text extraction
   - `.md` / `.markdown` → heading-boundary split
2. Paragraph-based chunking: split on `\n\n`; target 250–400 words; sentence-boundary splits for oversized paragraphs; minimum 60-word merge
3. Tokenise each chunk: `re.findall(r'\w+', text.lower())`
4. Build `BM25Okapi` from `rank_bm25` on tokenised corpus
5. Pickle `(chunks, bm25, tokenised_corpus)` → `cache_path`

**`retrieve(query: str, top_k: int = 5) → List[Chunk]`**:
- Tokenises query; calls `bm25.get_top_n(tokens, corpus, n=top_k)`; returns corresponding `Chunk` objects

**`get_chunks_for_docs(doc_names: List[str]) → List[Chunk]`** ★ NEW:
- Filters `self._chunks` to only those whose `source_doc` is in `doc_names`
- Returns in original index order (stable document-order traversal)
- Used by `_tui_bridge._load_step_chunks()` to restrict content chunks to the current step's `read:` list

**Load path** (called at runtime):
- `DocIndex.load(pack) → DocIndex` — reads pickle; raises `IndexBuildError` if missing
- Auto-loads on `retrieve()` if not explicitly loaded

---

### 7.5 Retrieval Layer (`retrieval.py`)

```python
def retrieve_chunks(session: TeachSession, query: str, top_k: int = 5) -> List[Chunk]
def get_index(session: TeachSession) -> DocIndex   # ★ NEW
```

`retrieve_chunks()`:
- Checks `_INDEX_CACHE` for existing `DocIndex` keyed by `session.pack.id`
- On miss: calls `DocIndex.load(session.pack)`; caches result
- Returns `index.retrieve(query, top_k=top_k)`

`get_index()` ★:
- Same cache lookup; returns the raw `DocIndex` object
- Used by `_tui_bridge` to call `get_chunks_for_docs()` directly without rebuilding

Both functions are in `__all__`.

---

### 7.6 TUI Bridge (`_tui_bridge.py`)

The **only file** that imports from both `saxoflow/teach/` and `cool_cli`. All other teach modules are TUI-agnostic.

**Public API:**

| Function | Called by | Returns |
|---|---|---|
| `handle_input(user_input, session, project_root, llm, verbose)` | `app.py` main loop | `Panel` |
| `start_session_panel(session)` | `app.py` on session start | `Panel` |
| `session_end_panel()` | `app.py` when all steps done | `Panel` |
| `prepare_step_for_display(session)` | `app.py` after session created | `Panel` (first chunk + nav) |
| `record_manual_command(user_input, session)` | `app.py` after unix cmd in teach mode | `Panel` or `None` |

**Teach-mode command constants:**

```python
_CMD_RUN = "run"    _CMD_NEXT = "next"    _CMD_BACK = "back"    _CMD_SKIP = "skip"
_CMD_HINT = "hint"  _CMD_STATUS = "status" _CMD_AGENTS = "agents" _CMD_QUIT = "quit"
_CMD_CONFIRM = "confirm"
```

**Command routing in `handle_input()`:**

`handle_input()` tracks `_was_question_phase = session.question_phase` before dispatch.  
**In question phase**, the student can type `run`, `skip`, `back`, `hint`, `status`, `agents`, `quit`, or `confirm` and they are dispatched normally — only free text (answers or follow-up questions) is forwarded to the tutor.  
**Outside question phase**, all nine commands are dispatched as usual; anything else goes to `_handle_tutor_query()`.

| Input | Handler | Effect |
|---|---|---|
| `run` | `_handle_run()` | Execute ONE YAML-declared command (per `current_command_index`); show stdout; pwd hint on path errors |
| `next` | `_handle_next()` | Advance chunk → question phase → command phase → next lesson |
| `back` | `_handle_back()` | Go back chunk → back to content from commands → previous lesson |
| `skip` | `_handle_skip()` | Skip all remaining commands and advance to next step |
| `hint` | `_handle_hint()` | Shows all hints for current step |
| `status` | `_handle_status()` | Shows step index, chunk position, phase |
| `agents` | `_handle_agents()` | Runs all `agent_invocations` for current step |
| `quit` | `_handle_quit()` | Returns quit panel (no nav appended) |
| `confirm` | `_handle_confirm()` | Acknowledge `user_confirms` tasks; sets `user_confirms_acknowledged = True` |
| `<digit>` (index mode) | `_handle_index_select()` | Jumps to that topic's chunk |
| anything else | `_handle_tutor_query()` | TutorAgent with current chunk or question context + terminal log |

**Nav suppression after question panels:**  
After a question is newly rendered (either entering question phase or pressing `next` to advance to the next question), the nav panel is suppressed — returning `_inner` only — so the student can respond naturally. The nav panel reappears alongside the tutor's next reply.

**`_handle_run()` — one command per press:**
- Executes only the command at `session.current_command_index`; increments cursor; calls `save_progress()`
- When all commands done: if `user_confirms` checks are unacknowledged, shows manual task list with `confirm` instruction instead of a success message
- Appends a `⚠ Path not found` hint line when stdout contains `"no such file or directory"` or `"cannot access"`

**`_handle_next()` — two-gate advance:**
1. **Unrun commands gate**: if `session.current_command_index < total_cmds`, blocks with yellow warning (`run` or `skip`)
2. **user_confirms gate**: if `user_confirms` checks exist and `not session.user_confirms_acknowledged`, blocks with yellow "Manual Tasks Required" panel, instructs student to `confirm` first

**`_handle_confirm()`:**
- If no `user_confirms` checks for the step → info panel
- If already acknowledged → green panel
- Otherwise: sets `session.user_confirms_acknowledged = True`, calls `save_progress()`, renders green "Tasks Confirmed" panel

**`_handle_tutor_query()` — context enrichment:**
```
_terminal_ctx:
  If session.terminal_log is non-empty:
    take last 3 entries → prepend "[Recent terminal commands the student ran]:\n<entries>\n\n"

Branch A (question phase):
  enriched_input = "[Active reflection question]: {q.text}\n\nStudent response / follow-up: {user_input}"

Branch B (content phase):
  enriched_input = "[Currently reading: {doc}, p.{page}]\n{chunk.text[:400]}\n\nStudent question: {user_input}"

Branch C (command phase / default):
  enriched_input = user_input

All branches: if _terminal_ctx → enriched_input = _terminal_ctx + enriched_input
```

**Content rendering helpers:**

- `_load_step_chunks(session)` — calls `get_index(session).get_chunks_for_docs(doc_names)`; applies section filtering (case-insensitive exact match on `section_hint`); graceful fallback to BM25 for steps with no `read:` list; calls `session.reset_chunk_state()`; merges consecutive same-section chunks via `_merge_chunks_by_section()`
- `_render_chunk_panel(session)` — displays `chunks[current_chunk_index].text` with source citation and nav footer; progress label `[i/N]`; paragraph-aware wrapping via `_format_chunk_for_display()`
- `_render_index_panel(session)` — numbered list of unique `section_hint` headings for lecture-mode steps
- `_render_question_panel(session, q)` — saves `session.current_question = q`; renders reflection question with instructions
- `_render_command_phase_panel(session)` — shows current command with visual checklist of all step commands; "Done" state shows `confirm` task list when `user_confirms` checks are unacknowledged; footer reminder about relative paths
- `_render_nav_panel(session)` — persistent "Available Options" panel; in command phase shows `confirm → Acknowledge manual tasks to unlock next` when `user_confirms` tasks remain and commands are all done
- `_handle_index_select(session, number)` — maps display number to `chunks` index; switches `chunk_mode` to `"sequential"` after selection

**`record_manual_command(user_input, session) → Optional[Panel]`:**  
Called by `app.py` after a unix command executes in teach mode. Normalises whitespace and compares the typed command against `step.commands[current_command_index].native`. On match: increments `current_command_index`, calls `save_progress()`, and returns the updated command panel + nav panel. Returns `None` when there is no match or the student is in content phase.

---

### 7.7 Step Runner (`runner.py`)

`run_step_commands(session: TeachSession, project_root: Path, timeout: int = 120, cmd_index: Optional[int] = None) → List[RunResult]`

When `cmd_index` is given (as it always is from `_tui_bridge._handle_run()`), only that single command is executed. When `cmd_index` is `None` all step commands run in order.

For each `CommandDef`:
1. Calls `command_map.resolve_command(cmd)` to check for a SaxoFlow wrapper
2. Selects `resolution.preferred` if `available=True` and `cmd.use_preferred_if_available`, else uses `cmd.native`
3. Computes effective CWD: `project_root / session.cwd` when `session.cwd` is non-empty and the directory exists; falls back to `project_root`
4. Background commands (`cmd_def.background = True`) — launches via `subprocess.Popen` without waiting; returns `RunResult(exit_code=0, stdout="[Launching in background — the application window is opening now, interact with it when it appears]")`
5. Foreground commands — `subprocess.run(cmd_str, shell=True, cwd=effective_cwd, capture_output=True, timeout=120)`
6. Updates `session.last_run_log`, `session.last_run_exit_code`, `session.last_run_command`
7. Logs to `.saxoflow/teach/runs/<step_id>.log`
8. Stops on first failure (non-zero exit code)

**CWD tracking (pure `cd` only):**  
`_execute_single` detects a standalone `cd <path>` (no `&&`, `||`, `;` operators) and — on success — resolves the absolute destination, then stores `destination.relative_to(project_root)` back into `session.cwd`. Compound commands like `cd dir && ./binary` are not interpreted for CWD tracking; they are run by bash in full.

Returns list of `RunResult(command_str, exit_code, stdout, timed_out, resolved_wrapper)`.

---

### 7.8 Checks Framework (`checks.py`)

`evaluate_step_success(session: TeachSession, project_root: Path) → bool`

Runs all `CheckDef` entries in `session.current_step.success`:

| `kind` | Behavior |
|---|---|
| `file_exists` | `glob(pattern)` or `(root / check.file).exists()` |
| `file_contains` | `re.search(pattern, (root / check.file).read_text())` |
| `stdout_contains` | `re.search(pattern, session.last_run_log)` |
| `exit_code_0` | `session.last_run_exit_code == 0` |
| `user_confirms` | **Always passes** at evaluation time. The gate is enforced by `_handle_next()` in `_tui_bridge.py` — the student must type `confirm` to set `session.user_confirms_acknowledged = True` before `next` is allowed to advance. `CheckDef.pattern` is used as a human-readable description of the manual task shown to the student. |
| `always` | Always passes. Used for review-only steps with no shell command. |

Returns `True` only when all checks pass. Individual `(passed, message)` pairs available via `run_check(check, session, root)`.

---

### 7.9 Agent Dispatcher (`agent_dispatcher.py`)

`dispatch_step_agents(session: TeachSession, verbose: bool = False) → List[str]`

For each `AgentInvocationDef` in `session.current_step.agent_invocations`:
1. Looks up `inv.agent_key` in `AgentManager.AGENT_MAP`
2. For `"fullpipeline"` → delegates to `AgentOrchestrator.full_pipeline()`
3. For any other registered agent → `AgentManager.get_agent(key); agent.run(**inv.args)`
4. Stores result in `session.agent_results[session.current_step.id]`
5. Returns list of result strings (one per invocation)

`available_agents() → List[str]` — returns `AgentManager.all_agent_names()` for the `agents` command display.

---

### 7.10 CLI Commands (`teach/cli.py`)

`saxoflow teach` Click group with subcommands:

| Command | Description |
|---|---|
| `teach add-pack <path>` | Index a teaching pack (run once after adding documents) |
| `teach start <pack_id>` | Start a tutoring session (in-process, routes to TUI bridge) |
| `teach status` | Show current step and progress summary |
| `teach run [--cmd-index N]` | Execute this step's command |
| `teach check` | Run all success checks for current step |
| `teach next` | Advance to next step/chunk |
| `teach back` | Go back to previous step/chunk |
| `teach hint` | Show hints for current step |
| `teach agents` | Invoke all agent_invocations for current step |
| `teach invoke-agent <key>` | Invoke a specific agent by key |
| `teach quit` | End the tutoring session |

All teach subcommands that require an active session call `_require_session()` which raises `click.ClickException("No active teach session")` if `_state.teach_session is None`.

---

### 7.11 ETH Zurich Pack (`packs/ethz_ic_design/`)

The reference teaching pack for university IC design courses, built on ETH Zurich's VLSI-2 curriculum:

**`pack.yaml` metadata:**
- `id: ethz_ic_design`
- `name: "ETH Zurich IC Design Tutorial"`
- 10 lessons covering the full CROC SoC design flow

**10 Lessons:**

| Lesson | File | Title |
|---|---|---|
| 1 | `01_environment_croc_setup.yaml` | Environment Setup & Tool Verification |
| 2 | `02_rtl_croc_exploration.yaml` | RTL Exploration of CROC SoC |
| 3 | `03_simulation_croc.yaml` | RTL Simulation with Questasim / Verilator |
| 4 | `04_synthesis_croc.yaml` | Logic Synthesis with Yosys |
| 5 | `05_floorplan_croc.yaml` | Floorplanning in OpenROAD |
| 6 | `06_placement_croc.yaml` | Placement & Optimization |
| 7 | `07_cts_croc.yaml` | Clock Tree Synthesis |
| 8 | `08_routing_croc.yaml` | Global & Detail Routing |
| 9 | `09_signoff_croc.yaml` | Timing Signoff & DRC |
| 10 | `10_gds_croc.yaml` | GDS Export & Tape-out Checklist |

**Lesson YAML schema (key fields):**
```yaml
id: env_setup
title: "Environment Setup & Tool Verification"
mode: sequential          # "sequential" (default) | "index" (lecture chooser)
goal: >
  Verify that all required open-source EDA tools are installed ...
read:
  - doc: ethz_vlsi2_lab1.pdf
    section: "Environment Setup"   # optional: exact section_hint match
commands:
  - native: "verilator --version"
  - native: "gtkwave --version"
    background: false              # false = foreground (default)
  - native: "gtkwave ."
    background: true               # true = Popen, non-blocking GUI
agent_invocations: []
questions:
  - text: "Why is it important to pin tool versions with apt-mark hold?"
    after_command: -1              # -1 = show after last content chunk
success:
  - kind: exit_code_0
  - kind: user_confirms
    pattern: "Confirm the GTKWave window opened correctly"
hints:
  - "If verilator not found: run saxoflow install verilator"
```

**Document indexing:**
- Pack documents live in `packs/ethz_ic_design/docs/` (gitignored)
- Index built to `.saxoflow/teach/index/ethz_ic_design.pkl` via `saxoflow teach add-pack packs/ethz_ic_design`
- Index contains ~870 BM25 chunks across all ETH VLSI-2 PDF documents
- Index is cached; `get_index()` returns the same `DocIndex` object across all requests

---

## 8. EDA Tool Ecosystem Integration

### Supported Tools Summary

| Category | Tool | Install Method | Purpose |
|---|---|---|---|
| Simulation | iverilog | APT | Verilog-2001/2005 event-driven simulation |
| Simulation | verilator | Script | Cycle-accurate SystemVerilog → C++ simulation |
| Waveform | gtkwave | APT | VCD/FST waveform viewer |
| Synthesis | yosys (+slang) | Script | RTL-to-gate synthesis with extended SV frontend |
| Formal | symbiyosys | Script | Formal property verification frontend (wraps Yosys + solvers) |
| FPGA PnR | nextpnr | Script | Place-and-route for ECP5, ICE40, Nexus |
| FPGA prog | openfpgaloader | APT | Open-source FPGA programmer |
| FPGA vendor | vivado | Script | Xilinx Vivado (optional, vendor) |
| ASIC PD | openroad | Script | Full digital ASIC backend (floorplan → signoff) |
| ASIC layout | klayout | APT | GDS/OASIS viewer and scripting |
| ASIC layout | magic | APT | VLSI layout editor + extraction |
| ASIC LVS | netgen | APT | Netlist comparison (LVS) |
| HDL deps | bender | Script | HDL dependency manager (filelists/scripts) |
| IDE | vscode | Script | VS Code with HDL extensions |

### Script Recipe Structure

Each recipe in `scripts/recipes/<tool>.sh`:
- Sources `scripts/common/logger.sh`, `paths.sh`
- Calls `clone_or_update.sh` for git-based tools
- Builds from source or downloads binary
- Installs to `$HOME/.local/<tool>/`

---

## 9. Project Scaffold & Makefile Template

### Directory Layout (post `saxoflow unit`)

```
source/
  specification/         ← spec.md lives here (used by agentic commands)
  rtl/verilog/           ← RTL .v files (agentic writes here)
  rtl/systemverilog/     ← .sv files
  rtl/vhdl/              ← .vhd files
  tb/verilog/            ← testbench .v files (agentic writes here)
  tb/systemverilog/
  tb/vhdl/
simulation/icarus/       ← *.vvp, *.vcd (Icarus outputs)
simulation/verilator/    ← obj_dir/ (Verilator outputs)
synthesis/src/
synthesis/scripts/synth.ys  ← Yosys script
synthesis/reports/
synthesis/out/           ← *.json, *.edif, *.blif
formal/scripts/          ← *.sby files
formal/reports/
formal/out/
constraints/             ← timing, power, DRC constraints
pnr/                     ← place-and-route scripts
output/report/           ← pipeline_report.md
```

### Makefile Targets

| Target | Description |
|---|---|
| `make sim-icarus TOP_TB=<name>` | Compile + run Icarus VVP; generate VCD |
| `make sim-verilator TOP_TB=<name>` | Verilator C++ build with trace |
| `make sim-verilator-run` | Run compiled binary; generate dump.vcd |
| `make wave` | Open GTKWave on Icarus VCD |
| `make wave-verilator` | Open GTKWave on Verilator VCD |
| `make simulate` | One-step: simu + wave (Icarus) |
| `make simulate-verilator` | One-step: build + run + wave (Verilator) |
| `make synth` | Run Yosys with synthesis/scripts/synth.ys |
| `make formal` | Run SymbiYosys with formal/scripts/spec.sby |
| `make clean` | Remove all generated files |

---

## 10. Full Design Flow Walkthrough

### Flow 1: Manual CLI-Driven Flow

```bash
# 1. Setup
saxoflow init-env --preset fpga
saxoflow install selected

# 2. Create project
saxoflow unit my_adder
cd my_adder
# Place spec in source/specification/my_adder.md
# Write RTL in source/rtl/verilog/adder.v
# Write TB  in source/tb/verilog/adder_tb.v

# 3. Simulate
saxoflow simulate   # Icarus + GTKWave in one step

# 4. Synthesize
saxoflow synth      # calls make synth → synthesis/reports/yosys.log

# 5. Formal
saxoflow formal     # calls make formal → formal/reports/

# 6. Health check
saxoflow diagnose
```

### Flow 2: Fully Automated Agentic Flow

```bash
# From project root (unit already created):
saxoflow agenticai fullpipeline \
  -i source/specification/my_adder.md \
  --project-path . \
  --iters 3
```

This triggers `AgentOrchestrator.full_pipeline()`:
1. RTLGenAgent generates `source/rtl/verilog/my_adder_rtl_gen.v`
2. RTLReviewAgent critiques it; loop up to 3 times until "no issues"
3. TBGenAgent generates `source/tb/verilog/my_adder_tb_gen.v`
4. TBReviewAgent critiques; loop
5. SimAgent runs `saxoflow sim` inside the project
6. DebugAgent diagnoses failures; selects healing agent(s)
7. Iterates healing for up to 3 simulation attempts
8. ReportAgent generates `output/report/pipeline_report.md`

### Flow 3: Rich TUI (Interactive)

```bash
python3 saxoflow.py
```

Inside the TUI:
```
✦ rtlgen source/specification/my_adder.md
[Agentic panel: generated RTL displayed]

✦ simulate
[Output panel: simulation log]

✦ review the RTL I just generated
[AI Buddy detects "review" keyword → asks for file → shows RTLReviewAgent output]

✦ fix the timing issue in the counter RTL
[AI Buddy detects intent → confirms action → invokes rtlgen improve]
```

---

## 11. Technology Stack

| Layer | Technology | Version / Notes |
|---|---|---|
| Language | Python | 3.9+ |
| CLI framework | Click | 8.x |
| Interactive prompts | questionary | — |
| TUI | Rich | — |
| Input completion | prompt_toolkit | — |
| LLM orchestration | LangChain | ≥0.2 |
| OpenAI adapter | langchain-openai | ≥0.1.7 |
| Anthropic adapter | langchain-anthropic | — |
| Google adapter | langchain-google-genai | — |
| Templating | Jinja2 | — |
| Config | PyYAML | — |
| Banner | pyfiglet | — |
| Env management | python-dotenv | — |
| HTTP | requests | — |
| Packaging | setuptools / pyproject.toml | PEP 517 |
| Build / install | pip editable (`-e .`) | — |
| PDF extraction | pypdf | ≥3.x |
| BM25 retrieval | rank-bm25 | — |
| Testing | pytest | — |
| EDA backend | iverilog, verilator, yosys, symbiyosys, openroad, gtkwave, ... | see §7 |
| Build automation | GNU Make | — |

---

## 12. Key Design Decisions & Novelties

### 12.1 Multi-Agent LLM Pipeline with Iterative Healing
Unlike direct LLM-to-code approaches, SaxoFlow implements a **generate → review → improve** loop with a configurable `max_iters`. The feedback coordinator detects "no action needed" responses (11 regex patterns) to avoid unnecessary improvement rounds. Crucially, the pipeline **actually simulates the generated code** and uses a DebugAgent to diagnose failures, enabling **self-healing RTL/TB generation**.

### 12.2 Tool-Consistent Prompt Engineering
Prompt layers prepend tool-specific guidelines (iverilog/Verilator/Yosys/OpenROAD constraints) before task instructions. This grounds the LLM in the actual tool chain's capabilities and limitations — preventing constructs that compile in ModelSim but fail in Icarus or cannot be synthesized by Yosys.

### 12.3 Provider-Agnostic LLM Interface
`ModelSelector` supports 13 providers with auto-detection via environment variables. OpenAI-compatible providers use `ChatOpenAI` with custom `base_url`, while Anthropic/Gemini use native adapters. The YAML config allows per-agent model overrides.

### 12.4 Integrated EDA Toolchain Management
The preset system and shell recipe infrastructure provide a reproducible, tested installation path for 14 EDA tools — combining APT packages with from-source builds — that previously required hours of independent setup.

### 12.5 Unified Project Scaffold
`saxoflow unit` creates a deterministic directory layout compatible with both the Makefile automation and the agentic AI file writing paths. The Yosys synthesis script template includes ASIC, FPGA, and timing annotation stubs.

### 12.6 Rich TUI with AI-First Interaction Model
The TUI routes inputs based on intent detection (keyword matching over 40 intents), allowing natural-language control of EDA workflows without remembering exact command syntax. The AI Buddy maintains a 5-turn conversation context.

### 12.8 Graceful Degradation
All major components provide shims or silent fallbacks — AgentManager, AgentOrchestrator, ModelSelector, and the agentic CLI group all have fallback shims so the tool remains partially functional even when the AI module is not configured.

### 12.7 Document-Grounded Interactive Tutoring
The tutoring platform addresses a gap no existing open-source EDA tool fills: **presenting the actual course PDF content to students as a navigable chunk stream inside a terminal**, with every question answered by a domain-specific LLM grounded in the currently-displayed content. The key novelties are:
- **Content-first design**: students see PDF passages before commands, matching the natural read-before-do learning pattern
- **Chunk-scoped Q&A**: the currently-displayed chunk is prepended to every LLM query, ensuring "what does this mean?" questions are answered from what is on screen
- **Reflection questions**: configurable `QuestionDef` list in step YAML shown between the last content chunk and the command phase; active question is injected into the tutor prompt so it can evaluate the student's answer in context
- **Terminal log injection**: the last 3 manually typed commands (e.g. `cat file.sv`, `ls`, `pwd`) and their outputs are prepended into every tutor invocation — the tutor has live shell context without the student needing to paste output
- **`user_confirms` gate**: interactive GUI steps (GTKWave, waveform analysis) declare a `user_confirms` check; the student types `confirm` to acknowledge completion; `next` is blocked until this is done, preventing premature step advancement
- **One-command-per-press execution**: `run` executes exactly one YAML-declared command each press, with `current_command_index` persisted; manually typing the same command also advances the cursor
- **Two lesson modes**: `sequential` (tutorial, read in order) and `index` (lecture, choose any topic by number)
- **Strict command provenance**: the LLM never decides what to execute; only YAML-declared commands run via `runner.py`
- **Full agent bridge**: any existing SaxoFlow agent (RTLGen, TBGen, formal, sim) is callable from a lesson step via `agent_invocations`, bridging tutorial instruction with AI-assisted design

---

## 13. Quantitative Metrics & Scope

| Metric | Value |
|---|---|
| Python source lines (approx.) | ~10,500 |
| Number of modules | ~57 Python files |
| Number of agents | 10 (7 LLM + 1 non-LLM sim + TutorAgent + 1 optional) |
| Supported LLM providers | 13 |
| EDA tools supported | 14 |
| Preset profiles | 5 (minimal, fpga, asic, formal, full) |
| Prompt files | 16 (+ 2 tutor prompts) |
| Project scaffold directories | 20 |
| Makefile targets | 12 |
| Test modules | ~25 |
| CLI commands (top-level) | 14 + subgroups (incl. `teach` group with 11 subcommands) |
| Lines in Makefile template | 109 |
| Teaching packs | 1 (ethz\_ic\_design, 10 lessons) |
| BM25 index chunks (ETH pack) | ~870 |
| Lesson YAML files | 10 |
| Passing tests | 1168 |

---

## 14. Limitations & Future Work

### Current Limitations
1. **Single-clock, Verilog-2001 only**: RTL generation is constrained to `Verilog-2001` for Icarus/Yosys compatibility. SystemVerilog constructs (interfaces, packages, OOP) are not generated.
2. **Formal property phase disabled**: `fpropgen` is runnable standalone but is commented out in `full_pipeline` to reduce runtime.
3. **No multi-project management**: each invocation targets one project directory.
4. **APT-only system packages**: the installer assumes Ubuntu/Debian; no Fedora/Arch support.
5. **No async execution**: agents execute serially; no parallel LLM calls.
6. **Simulation healing limited**: only `RTLGenAgent` and `TBGenAgent` are healed; no automated synthesis or formal error healing.
7. **BM25 retrieval only**: the tutoring indexer uses keyword-based BM25; no dense embedding / semantic similarity yet.
8. **No persistent chunk-level reading position**: the student's content-reading position (`current_chunk_index`) is not saved to disk across sessions; the session restarts content from the first chunk of the current step. Command execution position (`current_command_index`) and working directory (`cwd`) **are** persisted.

### Future Work (from TODOs in code)
- Re-enable Agentic AI preset in installer (`AGENTIC_TOOLS`)
- Re-enable formal property pipeline phase in orchestrator
- Regex-based action token detection in AI Buddy (replacing substring matching)
- Conda / fedora / multi-distro installer support
- Multi-threaded parallel LLM calls for gen+review
- Structured output (Pydantic) for LLM responses
- LCEL runnables for composable agent chains
- Extended diagnose flow (venv detection, disk space, WSL X11 config)
- Dense embedding retrieval (sentence-transformers / FAISS) to complement BM25 in the tutoring indexer
- Persistent chunk-level reading progress across TUI restarts
- `mode: index` lessons for the 10 ETH lecture PDFs that have structured headings
- Multi-pack support: student can switch packs without restarting the TUI
- Pack authoring wizard: CLI to scaffold a new `pack.yaml` + lesson stubs from a PDF

---

## 15. Glossary

| Term | Definition |
|---|---|
| **RTL** | Register-Transfer Level — hardware description at the data-path/control abstraction |
| **DUT** | Design Under Test |
| **TB** | Testbench — simulation harness for a DUT |
| **SVA** | SystemVerilog Assertions — property specifications for formal verification |
| **VCD** | Value Change Dump — waveform file format |
| **SBY** | SymbiYosys specification file format |
| **ASIC** | Application-Specific Integrated Circuit |
| **FPGA** | Field-Programmable Gate Array |
| **PnR** | Place and Route — physical implementation step |
| **Jinja2** | Python templating engine (used for prompt templates) |
| **LangChain** | Python framework for LLM application development |
| **LCEL** | LangChain Expression Language — composable runnable chains |
| **APT** | Advanced Package Tool — Debian/Ubuntu package manager |
| **WSL** | Windows Subsystem for Linux |
| **TUI** | Terminal User Interface |
| **LVS** | Layout vs. Schematic — physical design verification step |
| **GDS** | Graphic Database System — VLSI layout format |
| **Bender** | HDL dependency manager (by lowRISC) — manages filelists and IP dependencies |
| **Auto-detect priority** | Ordered list of LLM providers scanned for valid API keys |
| **Pack** | A teaching pack: a directory with `pack.yaml`, `docs/`, and `lessons/` YAML files |
| **Chunk** | A 250–400-word text passage extracted from a pack document; the unit of BM25 retrieval |
| **DocIndex** | BM25 index built from all chunks of a teaching pack; persisted as a pickle file |
| **TeachSession** | Active tutoring session singleton: holds step position, chunks, conversation history |
| **Sequential mode** | Default lesson mode: student reads chunks 1→N in document order |
| **Index mode** | Lecture lesson mode: student sees a numbered topic list and jumps to any section |
| **Content phase** | The reading stage of a lesson: student is viewing PDF chunk content |
| **Command phase** | The execution stage: all chunks read; student sees declared tool commands |
| **Question phase** | Intermediate phase between content and commands: active `QuestionDef` displayed for reflection |
| **user_confirms** | `CheckDef.kind` for interactive steps that cannot be auto-verified; student types `confirm` to acknowledge before `next` is allowed |
| **terminal_log** | Rolling buffer (last 5 entries) of manually typed commands + outputs recorded by `app.py` and injected into TutorAgent context |

---

*Documentation version: 2.2 — March 2026*  
*Prepared from: SaxoFlow `saxoflow-starter` repository (HEAD as of analysis date)*  
*Purpose: Research paper reference for SMACD 2026 EDA competition*  
*Changes in v2.0: Added Module 4 — Interactive Tutoring Platform (`saxoflow/teach/`), TutorAgent, ETH Zurich VLSI-2 pack, content-display chunk navigation, BM25 document indexer, TUI bridge rewrite*  
*Changes in v2.1: TeachSession fields (`current_command_index`, `cwd`, `user_confirms_acknowledged`, `terminal_log`, `current_question`); one-command-per-press `run`; `confirm` gate for `user_confirms` steps; reflection question phase and `QuestionDef`; terminal log context injection into TutorAgent; nav suppression after question panels; `record_manual_command()` public API; `shell.py` relative/absolute executable detection; `runner.py` background present-tense message and pure-`cd` CWD tracking; full `CheckDef.kind` catalog*  
*Changes in v2.2: Clarification Q&A pipeline (`detect_incomplete_request`, `plan_clarification`, `build_enriched_spec`, `_run_clarification_flow`); `create_unit` yes/no question with default yes; spinner-vs-input architecture fix (clarification runs before `console.status`); `skip_clarification` param on `ai_buddy_interactive`; mechanical `build_enriched_spec` fallback that preserves `in unit X` clause; `_verify_placement()` post-write placement guard with auto-relocation via `shutil.move`; new §6.8 File Operations section; OpenROAD version detection fix: `-version` flag (single dash), bare build-ID first-line fallback; test count updated to 1168*
