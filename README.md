# 🧰 SaxoFlow: Beginner-Friendly RTL Development Flow

**SaxoFlow** is a modular, CLI-driven open-source environment for simulating, verifying, synthesizing, and implementing digital hardware—designed for students, self-learners, and aspiring digital designers.
It streamlines **FPGA and ASIC flows** with pre-integrated open-source tools, unified setup, and robust diagnostics.

---

## 🌟 Why SaxoFlow?

> “Learning Verilog shouldn’t require mastering 10 tools just to simulate a simple AND gate.”

**SaxoFlow lets you:**

* 🧱 Interactively choose toolchains (FPGA, ASIC, simulation, IDE, and AI/agentic flows)
* 🔧 Use a unified CLI for simulation, synthesis, waveform viewing, formal verification, and implementation
* 🧠 Work smoothly on Linux or WSL
* 🖋 Seamlessly integrate with VSCode
* 🤖 Future-proof your setup for AI-based flows (LLMs, agentic AI)
* 📦 Organize all your hardware projects with a standardized directory layout

---

## 🚀 Quickstart Installation

### 1️⃣ Clone the Repository

```bash
git clone https://github.com/saxoflowlabs/saxoflow-starter.git
cd saxoflow-starter
```

### 2️⃣ Bootstrap the Python Environment

```bash
python3 bootstrap.py
```

This sets up a virtual environment and installs all Python dependencies.

### 3️⃣ Activate the Environment

```bash
source .venv/bin/activate
```

### 4️⃣ Launch Interactive Environment Setup

Use the interactive preset system to select your flow:

```bash
saxoflow init-env
```

**Presets available:**

* `fpga`     → Minimal FPGA toolchain (simulation, synthesis, PnR)
* `asic`     → Digital ASIC flow (synthesis, PnR, layout, DRC)
* `formal` → Formal verification-centric tools
* `minimal` → Smallest environment for learning/basic simulation
* `agentic-ai` → (Optional) Experimental LLM/AI workflow integration

**Example usage:**

```bash
# Launch with a specific preset:
saxoflow init-env --preset fpga
# For agentic AI features:
saxoflow init-env --preset agentic-ai
```

### 5️⃣ Install Tools

```bash
# Install all selected tools:
saxoflow install all

# Or install individual tools:
saxoflow install verilator
saxoflow install openroad
```

---

## 🩺 Diagnosing Your Setup

SaxoFlow has a built-in doctor for environment health checks and repair:

* **Full System Check:**

  ```bash
  saxoflow doctor summary
  ```

* **Auto-Repair Missing Tools:**

  ```bash
  saxoflow doctor repair
  ```

* **Environment Info:**

  ```bash
  saxoflow doctor env
  ```

* **Interactive Repair (choose what to fix):**

  ```bash
  saxoflow doctor repair-interactive
  ```

* **Export Diagnostic Log:**

  ```bash
  saxoflow doctor summary --export
  ```

---

## 🛠️ How SaxoFlow Works

* **Project initialization:** Guides you interactively to select the tools and workflows you need for your target flow.
* **Tool installation:** Uses recipes or system packages to fetch, build, and install tools in a user-local, non-intrusive way.
* **Health checking:** Runs diagnostics to ensure everything (PATH, tools, extensions) is correctly configured and gives actionable tips.
* **Unified workflow:** Supports all major open-source EDA tools for simulation, synthesis, waveform viewing, place-and-route, and formal verification.
* **AI/Agentic Integration:** Optional flows for AI-based hardware design or verification.

---

## ⚙️ Supported Open Source Tools

| Tool           | Stage/Feature       | Target | Description                              |
| -------------- | ------------------- | ------ | ---------------------------------------- |
| VSCode         | IDE                 | All    | Modern editor with HDL/AI extensions     |
| Icarus Verilog | RTL Simulation      | All    | Open-source Verilog simulator            |
| Verilator      | Fast Simulation     | All    | High-performance SystemVerilog simulator |
| GTKWave        | Waveform Viewing    | All    | VCD waveform viewer                      |
| Yosys          | Synthesis           | All    | RTL-to-gate synthesis                    |
| SymbiYosys     | Formal Verification | All    | Property checking via SMT solvers        |
| nextpnr        | Place & Route       | FPGA   | Architecture-neutral PnR engine          |
| openFPGALoader | Bitstream Upload    | FPGA   | Upload bitstreams to physical FPGAs      |
| Magic          | Physical Layout     | ASIC   | Layout editor, DRC, routing              |
| KLayout        | GDS Layout Viewer   | ASIC   | GDS/OASIS layout viewer                  |
| Netgen         | LVS Checking        | ASIC   | Netlist equivalence checker              |
| OpenROAD       | Digital Backend     | ASIC   | Digital implementation flow              |

---

## 📁 Recommended Project Structure

```
myproj/
├── rtl/         # HDL sources (Verilog, SystemVerilog)
├── sim/         # Testbenches
├── formal/      # Formal specs (e.g., .sby)
├── synth/       # Synthesis results
├── pnr/         # Place-and-route (FPGA/ASIC)
├── constraints/ # Pin/clock constraints
├── output/      # Final outputs (bitstreams, GDS)
├── logs/        # Reports, DRC, errors
├── scripts/     # Custom scripts
├── docs/        # Documentation, diagrams
└── Makefile     # Unified build interface
```

---

## 🤖 Agentic AI Integration (Experimental)

* LLM-assisted code generation and verification
* AI-powered property and assertion synthesis
* Agentic workflow: automatic iterative RTL refinement

---

## 🤝 Contributing

* New tools, recipes, and FPGA board templates welcome!
* Help with AI/LLM integrations
* Optimizations, bug fixes, docs, and community support
* Designed to be accessible for beginners and advanced users alike

---

## 📚 References

* [ASIC World Verilog Guide](https://www.asic-world.com/verilog/)
* [OpenROAD Docs](https://openroad.readthedocs.io/)
* [SymbiYosys Docs](https://symbiyosys.readthedocs.io/)
* [GTKWave](http://gtkwave.sourceforge.net/)
* [YosysHQ Docs](https://yosyshq.net/yosys/documentation.html)
* [nextpnr](https://github.com/YosysHQ/nextpnr)

---

## 📜 License

Apache-2.0 Licensed.

---

Built by SaxoFlow Labs — a student-led initiative from TU Dresden.


