![SaxoFlow Rich UI](docs/images/saxoflow_cool_cli.png)

SaxoFlow is a beginner-friendly **hardware design suite** that unifies open-source EDA tools with an intelligent, Rich UI. It's built to help learners and new designers move from **spec → RTL → sim/formal/synth** without hand-wiring a dozen utilities. The project targets **Linux and WSL** and ships with a clean workflow:

* a **Rich UI terminal app** (`saxoflow`) with panels, shell-like UX, an **AI Buddy** for natural-language help, and **Agentic AI** quick actions (`rtlgen`, `tbgen`, `fpropgen`, `report`, `debug`, `fullpipeline`);
* a **unified CLI** (`saxoflow`) for environment initialization, tool installation, diagnostics, and make-style build helpers (simulation, waveforms, formal, synthesis, housekeeping).

Tool installers use **APT** and scripts in `scripts/recipes/`.

---

## ✅ Prerequisites

* **OS**: **WSL** or Linux (Ubuntu recommended)
* **Python**: 3.9+
* **System packages**: `git`, `build-essential`, `cmake` (typical dev stack)
* **Disk space**: several GB if you install the full toolchain (sim, formal, FPGA, ASIC)
* **LLM access for AI features**
Add an LLM API key. The supported providers are:
  - openai
  - anthropic
  - gemini
  - groq
  - mistral
  - fireworks
  - together
  - perplexity
  - deepseek
  - dashscope
  - openrouter

---

## 🚀 Install & First Run

```bash
# 1) Clone
git clone https://github.com/saxoflowlabs/saxoflow-starter.git
cd saxoflow-starter

# 2) Create & activate venv
python3 -m venv .venv
source .venv/bin/activate

# 3) Install SaxoFlow
python3 -m pip install -e .
```

### Start the Rich UI

```bash
saxoflow
```

The TUI starts in `~/SaxoFlow` by default, so users see their projects, copied examples, and SaxoFlow state instead of the application source tree. Override the workspace with `saxoflow --workspace /path/to/workspace` or `SAXOFLOW_WORKSPACE=/path/to/workspace saxoflow`.

---

## 🧭 Standard Workflow (CLI)

1. **Initialize environment (choose a preset)**
   Presets are defined in `saxoflow/installer/presets.py`:

   * `minimal` – IDE + a basic simulator + waveform viewer
   * `fpga` – Verilator + FPGA toolchain + base tools
   * `asic` – Verilator + ASIC P\&R/layout stack + base tools
   * `formal` – Yosys + SymbiYosys + IDE
   * `full` – IDE + SIM + FORMAL + FPGA + ASIC + BASE

   ```bash
   saxoflow init-env --preset <minimal|fpga|asic|formal|full>   # add --headless to skip prompts
   ```

2. **Install tools**

   ```bash
   saxoflow install selected   # from your last init-env selection
   saxoflow install all        # everything
   saxoflow install <tool>     # e.g., yosys, iverilog, verilator, openroad, gtkwave, ...
   ```

3. **Create a unit (project scaffold)**

   ```bash
   saxoflow unit <unitname>
   ```

   Add your **specification** (Markdown/text) to the unit’s **spec** folder. You’ll use this spec with the agentic generators.

4. **Build & run (from your project root)**

   ```bash
   saxoflow simulate
   saxoflow wave
   saxoflow formal
   saxoflow synth
   saxoflow clean
   saxoflow check_tools

   # Also available:
   saxoflow sim | sim_verilator | sim_verilator_run
   saxoflow wave_verilator
   saxoflow simulate_verilator
   ```

---

## 🤖 AI Features (in the Rich UI)

**Agentic quick actions** (from `saxoflow_agenticai`, integrated into the UI). Type a command + spec path:

```
rtlgen <spec.md>                # generate RTL
tbgen <spec.md>                 # generate testbench
fpropgen <spec.md>              # generate formal properties
report | debug                  # review/analysis
fullpipeline -i <spec.md> [--iters N]
```

**AI Buddy**
Open-ended chat right in the terminal—use it for design Q\&A, code reviews, or small refactors.

---

## 🔧 Supported Tools (current)

* **IDE**: `vscode`
* **Simulation / verification**: `icarus-verilog`, `verilator`, `nvc`, `cocotb`, `covered`
* **Waveforms / debugging**: `gtkwave`, `surfer`
* **Synthesis / Frontend**: `yosys`, `surelog`, `sv2v`
* **Formal verification**: `symbiyosys`, `z3`, `boolector`, `bitwuzla`, `vices`, `cvc5`
* **FPGA / SoC orchestration**: `nextpnr`, `openfpgaloader`, `vivado` (vendor/optional), `fusesoc`, `rggen`
* **ASIC / Physical design**: `openroad`, `opensta`, `klayout`, `magic`, `netgen`, `riggen`
* **Embedded software / RISC-V**: `riscv-toolchain`, `spike`, `qemu`
* **Dependency / Flow orchestration**: `bender`, `fusesoc`, `edalize`, `kact2`, `silicon-compiler`, `risc-v-gnu-toolchain`, `pyphpips`, `ccola-system-sim`, `opentus`, `genie`

Install recipes live in `scripts/recipes/`. Tool groups & presets are in `saxoflow/installer/presets.py`.

---

## 🪪 License

Apache-2.0 (see `LICENSE`).

---

## 🧑‍💻 Maintainers

Built by [SaxoFlow Labs](https://github.com/saxoflowlabs)
