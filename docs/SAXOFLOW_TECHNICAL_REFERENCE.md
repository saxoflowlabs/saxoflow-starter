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
   - 6.1 Entrypoint & Launcher (`app.py`, `start.py`)
   - 6.2 AI Buddy (`ai_buddy.py`, `agentic.py`)
   - 6.3 Panel System (`panels.py`)
   - 6.4 State Management (`state.py`)
   - 6.5 Bootstrap & LLM Setup (`bootstrap.py`)
   - 6.6 Shell Integration (`shell.py`, `completers.py`, `editors.py`)
   - 6.7 Constants (`constants.py`)
7. [EDA Tool Ecosystem Integration](#7-eda-tool-ecosystem-integration)
8. [Project Scaffold & Makefile Template](#8-project-scaffold--makefile-template)
9. [Full Design Flow Walkthrough](#9-full-design-flow-walkthrough)
10. [Technology Stack](#10-technology-stack)
11. [Key Design Decisions & Novelties](#11-key-design-decisions--novelties)
12. [Quantitative Metrics & Scope](#12-quantitative-metrics--scope)
13. [Limitations & Future Work](#13-limitations--future-work)
14. [Glossary](#14-glossary)

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
- **Entry points**: `python3 start.py` (Rich TUI) or `saxoflow <cmd>` (headless CLI)

---

## 2. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      SaxoFlow Platform                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                cool_cli  (Rich TUI)                      │    │
│  │  start.py ──► app.py ──► AI Buddy | Agentic | Shell     │    │
│  └────────────────────────┬────────────────────────────────┘    │
│                           │  delegates                          │
│  ┌────────────────────────▼────────────────────────────────┐    │
│  │              saxoflow  (Unified CLI)                     │    │
│  │  init-env | install | unit | simulate | synth | formal   │    │
│  │  diagnose | check_tools | wave | clean | agenticai       │    │
│  └──────┬────────────────────────┬───────────────────────  ┘    │
│         │                        │                               │
│  ┌──────▼───────┐    ┌───────────▼──────────────────────────┐   │
│  │  Installer   │    │    saxoflow_agenticai  (LLM engine)   │   │
│  │  - presets   │    │  AgentManager                         │   │
│  │  - runner    │    │  ├─ RTLGenAgent + RTLReviewAgent       │   │
│  │  - env.json  │    │  ├─ TBGenAgent  + TBReviewAgent        │   │
│  └──────┬───────┘    │  ├─ FormalPropGenAgent + FPropReview  │   │
│         │            │  ├─ DebugAgent + ReportAgent           │   │
│  ┌──────▼───────┐    │  └─ SimAgent (Icarus via makeflow)     │   │
│  │ EDA Toolchain│    │  AgentOrchestrator (full_pipeline)     │   │
│  │ iverilog     │    │  ModelSelector (LangChain adapters)    │   │
│  │ verilator    │    │  FeedbackCoordinator (review loops)    │   │
│  │ yosys        │◄───┤                                        │   │
│  │ symbiyosys   │    └───────────────────────────────────────┘   │
│  │ openroad     │                                                 │
│  │ gtkwave ...  │                                                 │
│  └──────────────┘                                                 │
└──────────────────────────────────────────────────────────────────┘
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
├── start.py                        # TUI entry point (installs deps, launches cool_cli.app)
├── pyproject.toml                  # Package metadata; entry point: saxoflow = saxoflow.cli:cli
├── requirements.txt                # Editable install (-e .)
├── pytest.ini                      # Test configuration
├── templates/
│   └── Makefile                    # Universal Makefile scaffold for all EDA flows
│
├── saxoflow/                       # Core CLI + EDA flow automation
│   ├── cli.py                      # Click group + all sub-commands
│   ├── makeflow.py                 # simulate, wave, formal, synth, clean, check_tools
│   ├── unit_project.py             # Project scaffold (directory tree + Makefile + scripts)
│   ├── diagnose.py                 # 'diagnose' Click group
│   ├── diagnose_tools.py           # env probes, health scoring, WSL detection
│   ├── tools/
│   │   └── definitions.py         # APT_TOOLS, SCRIPT_TOOLS, TOOL_DESCRIPTIONS, MIN_TOOL_VERSIONS
│   └── installer/
│       ├── presets.py              # SIM/FORMAL/FPGA/ASIC/BASE/IDE groups + PRESETS dict
│       ├── runner.py               # install_apt(), install_script(), install_all(), etc.
│       └── interactive_env.py      # Questionary-based interactive wizard + headless path
│
├── saxoflow_agenticai/             # LLM-driven design automation
│   ├── cli.py                      # Click commands: rtlgen, tbgen, fpropgen, report, debug, fullpipeline
│   ├── config/
│   │   └── model_config.yaml       # Provider/model/temperature defaults + per-agent overrides
│   ├── core/
│   │   ├── base_agent.py           # Abstract BaseAgent (prompt render + LLM query)
│   │   ├── agent_manager.py        # Factory registry keyed by string (9 agents)
│   │   ├── model_selector.py       # Auto-detects provider from API keys; builds LangChain LLMs
│   │   ├── prompt_manager.py       # Jinja2 rendering wrapper
│   │   └── log_manager.py          # Centralized named logger
│   ├── agents/
│   │   ├── sim_agent.py            # SimAgent: invokes Icarus via makeflow; returns status dict
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
│   │   ├── verilog_guidelines.txt  # Prepended to rtlgen + rtlreview prompts
│   │   ├── verilog_constructs.txt  # Prepended to rtlgen + rtlreview prompts
│   │   ├── tb_guidelines.txt       # Prepended to tbgen + tbreview prompts
│   │   └── tb_constructs.txt       # Prepended to tbgen + tbreview prompts
│   └── utils/
│       └── file_utils.py           # write_output(), base_name_from_path()
│
├── cool_cli/                       # Rich terminal UI
│   ├── app.py                      # Interactive prompt loop + routing
│   ├── agentic.py                  # run_quick_action(), ai_buddy_interactive()
│   ├── ai_buddy.py                 # ask_ai_buddy(), detect_action(), ACTION_KEYWORDS
│   ├── bootstrap.py                # .env creation + LLM key setup wizard
│   ├── state.py                    # Global: console, runner, conversation_history, config
│   ├── panels.py                   # Rich Panel builders (welcome, user, ai, agent, output)
│   ├── commands.py                 # Built-in 'help' command renderer
│   ├── completers.py               # HybridShellCompleter (fuzzy + path)
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
| `agenticai` | Optional: `saxoflow_agenticai.cli.cli` | Agentic sub-commands (if installed) |

The CLI gracefully degrades if `saxoflow_agenticai` is not installed (the `agenticai` sub-group simply does not appear).

### 4.2 Tool Taxonomy (`saxoflow/tools/definitions.py`)

Centralized tool metadata used throughout the system:

```
APT_TOOLS   = [gtkwave, iverilog, klayout, magic, netgen, openfpgaloader]
SCRIPT_TOOLS = {
  verilator → scripts/recipes/verilator.sh,
  openroad  → scripts/recipes/openroad.sh,
  nextpnr   → scripts/recipes/nextpnr.sh,
  symbiyosys→ scripts/recipes/symbiyosys.sh,
  vscode    → scripts/recipes/vscode.sh,
  yosys     → scripts/recipes/yosys.sh,
  vivado    → scripts/recipes/vivado.sh,
  bender    → scripts/recipes/bender.sh,
}
```

`TOOL_DESCRIPTIONS` is a flat dict `{tool_name: "[Category] Short description"}` used by questionary selection menus.

`MIN_TOOL_VERSIONS` maps each tool to its minimum supported version string (used by the `diagnose` health check).

### 4.3 Preset System (`saxoflow/installer/presets.py`)

Six reusable tool groups:

| Group | Tools |
|---|---|
| `SIM_TOOLS` | iverilog, verilator |
| `FORMAL_TOOLS` | symbiyosys |
| `FPGA_TOOLS` | nextpnr, openfpgaloader, vivado, bender |
| `ASIC_TOOLS` | openroad, klayout, magic, netgen, bender |
| `BASE_TOOLS` | gtkwave, yosys |
| `IDE_TOOLS` | vscode |

Five high-level presets:

| Preset | Composition |
|---|---|
| `minimal` | IDE + iverilog + gtkwave |
| `fpga` | IDE + verilator + FPGA_TOOLS + BASE_TOOLS |
| `asic` | IDE + verilator + ASIC_TOOLS + BASE_TOOLS |
| `formal` | IDE + yosys + FORMAL_TOOLS |
| `full` | IDE + SIM + FORMAL + FPGA + ASIC + BASE |

The `PRESETS` dict is the **single source of truth** consumed by both `interactive_env.py` and `cli.py`.

### 4.4 Tool Installer (`saxoflow/installer/runner.py`)

- `install_apt(tool)` — runs `sudo apt-get install -y <pkg> && apt-mark hold <pkg>` 
- `install_script(tool)` — sources the corresponding `scripts/recipes/<tool>.sh` via `bash`
- `install_tool(tool)` — dispatches to APT or script installer; appends binary path to `.venv/bin/activate`
- `install_all()` — iterates `ALL_TOOLS`
- `install_selected()` — reads `.saxoflow_tools.json`; installs each tool
- `install_preset(preset)` — resolves preset → calls `install_tool` for each
- `install_single_tool(tool)` — validates against known tools then calls `install_tool`

Binary paths for script-installed tools (BIN_PATH_MAP):
```
verilator  → $HOME/.local/verilator/bin
openroad   → $HOME/.local/openroad/bin
nextpnr    → $HOME/.local/nextpnr/bin
symbiyosys → $HOME/.local/sby/bin
yosys      → $HOME/.local/yosys/bin
bender     → $HOME/.local/bender/bin
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
- `extract_version(tool, path)` — runs tool `--version` / `-V` / `--version` and parses via regex
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

`start.py`:
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
   - Agentic commands (from `AGENTIC_COMMANDS` tuple): routed via `subprocess` to the agenticai CLI
   - Shell commands (`!` prefix or known UNIX alias): `process_command()` or raw tty
   - AI Buddy: `ai_buddy_interactive(user_input, history)`
5. Each response is printed as a Rich `Panel` and appended to `conversation_history`

### 6.2 AI Buddy (`ai_buddy.py`, `agentic.py`)

`ask_ai_buddy(user_input, history, file_to_review=None)`:

1. `detect_action(user_input)` → checks `ACTION_KEYWORDS` dict for substring match → returns action key or None
2. If **no action detected** → chat via LLM (uses `ModelSelector`; keeps last `MAX_HISTORY_TURNS=5` turns)
3. If **action detected without code** → returns `{"type": "need_file"}`
4. If **file provided** → invokes appropriate review agent (e.g., `RTLReviewAgent`) → returns `{"type": "review_result"}`
5. Otherwise → returns `{"type": "action", "action": <key>}` for downstream CLI invocation

`ai_buddy_interactive(user_input, history)` in `agentic.py`:
- Handles `need_file` → prompts user to paste code or path
- `review_result` → renders as white `Text`
- `action` → asks confirmation → on yes calls `_invoke_agent_cli_safely([cmd])`
- `chat` → renders LLM response as white `Text`, `Markdown`

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

`reset_state()` and `get_state_snapshot()` are provided for test isolation.

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
- `is_unix_command(cmd)`: checks if first token is a known system binary
- `process_command(cmd)`: dispatches SHELL_COMMANDS aliases or `subprocess.run`
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

## 7. EDA Tool Ecosystem Integration

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

## 8. Project Scaffold & Makefile Template

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

## 9. Full Design Flow Walkthrough

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
python3 start.py
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

## 10. Technology Stack

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
| Testing | pytest | — |
| EDA backend | iverilog, verilator, yosys, symbiyosys, openroad, gtkwave, ... | see §7 |
| Build automation | GNU Make | — |

---

## 11. Key Design Decisions & Novelties

### 11.1 Multi-Agent LLM Pipeline with Iterative Healing
Unlike direct LLM-to-code approaches, SaxoFlow implements a **generate → review → improve** loop with a configurable `max_iters`. The feedback coordinator detects "no action needed" responses (11 regex patterns) to avoid unnecessary improvement rounds. Crucially, the pipeline **actually simulates the generated code** and uses a DebugAgent to diagnose failures, enabling **self-healing RTL/TB generation**.

### 11.2 Tool-Consistent Prompt Engineering
Prompt layers prepend tool-specific guidelines (iverilog/Verilator/Yosys/OpenROAD constraints) before task instructions. This grounds the LLM in the actual tool chain's capabilities and limitations — preventing constructs that compile in ModelSim but fail in Icarus or cannot be synthesized by Yosys.

### 11.3 Provider-Agnostic LLM Interface
`ModelSelector` supports 13 providers with auto-detection via environment variables. OpenAI-compatible providers use `ChatOpenAI` with custom `base_url`, while Anthropic/Gemini use native adapters. The YAML config allows per-agent model overrides.

### 11.4 Integrated EDA Toolchain Management
The preset system and shell recipe infrastructure provide a reproducible, tested installation path for 14 EDA tools — combining APT packages with from-source builds — that previously required hours of independent setup.

### 11.5 Unified Project Scaffold
`saxoflow unit` creates a deterministic directory layout compatible with both the Makefile automation and the agentic AI file writing paths. The Yosys synthesis script template includes ASIC, FPGA, and timing annotation stubs.

### 11.6 Rich TUI with AI-First Interaction Model
The TUI routes inputs based on intent detection (keyword matching over 40 intents), allowing natural-language control of EDA workflows without remembering exact command syntax. The AI Buddy maintains a 5-turn conversation context.

### 11.7 Graceful Degradation
All major components provide shims or silent fallbacks — AgentManager, AgentOrchestrator, ModelSelector, and the agentic CLI group all have fallback shims so the tool remains partially functional even when the AI module is not configured.

---

## 12. Quantitative Metrics & Scope

| Metric | Value |
|---|---|
| Python source lines (approx.) | ~8,000 |
| Number of modules | ~45 Python files |
| Number of agents | 9 (6 LLM + 1 non-LLM sim + 2 optional) |
| Supported LLM providers | 13 |
| EDA tools supported | 14 |
| Preset profiles | 5 (minimal, fpga, asic, formal, full) |
| Prompt files | 14 (task + improve + guidelines + constructs) |
| Project scaffold directories | 20 |
| Makefile targets | 12 |
| Test modules | ~22 |
| CLI commands (top-level) | 14 + subgroups |
| Lines in Makefile template | 109 |

---

## 13. Limitations & Future Work

### Current Limitations
1. **Single-clock, Verilog-2001 only**: RTL generation is constrained to `Verilog-2001` for Icarus/Yosys compatibility. SystemVerilog constructs (interfaces, packages, OOP) are not generated.
2. **Formal property phase disabled**: `fpropgen` is runnable standalone but is commented out in `full_pipeline` to reduce runtime.
3. **No multi-project management**: each invocation targets one project directory.
4. **APT-only system packages**: the installer assumes Ubuntu/Debian; no Fedora/Arch support.
5. **No async execution**: agents execute serially; no parallel LLM calls.
6. **Simulation healing limited**: only `RTLGenAgent` and `TBGenAgent` are healed; no automated synthesis or formal error healing.

### Future Work (from TODOs in code)
- Re-enable Agentic AI preset in installer (`AGENTIC_TOOLS`)
- Re-enable formal property pipeline phase in orchestrator
- Regex-based action token detection in AI Buddy (replacing substring matching)
- Conda / fedora / multi-distro installer support
- Multi-threaded parallel LLM calls for gen+review
- Structured output (Pydantic) for LLM responses
- LCEL runnables for composable agent chains
- Extended diagnose flow (venv detection, disk space, WSL X11 config)

---

## 14. Glossary

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

---

*Documentation version: 1.0 — March 2026*  
*Prepared from: SaxoFlow `saxoflow-starter` repository (HEAD as of analysis date)*  
*Purpose: Research paper reference for SMACD 2026 EDA competition*
