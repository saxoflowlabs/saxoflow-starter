# 🧰 SaxoFlow: Beginner-Friendly RTL Development Flow (v0.3)

**SaxoFlow** is a modular, CLI-based open-source environment for simulating, verifying, synthesizing, and implementing digital logic designs — tailored for students, self-learners, and new digital designers.
It supports **both FPGA and ASIC flows**, and comes pre-integrated with industry-grade open-source tools.

---

## 🌟 Why SaxoFlow?

> “Learning Verilog shouldn’t require mastering 10 tools just to simulate a simple AND gate.”

SaxoFlow simplifies the toolchain by:

* 🧱 Modular installer: choose FPGA / ASIC / IDE components interactively
* 🔧 Unified CLI for simulation, synthesis, waveform viewing, formal, and implementation
* 🧠 Clean Linux/WSL support
* 🖋 Independent VSCode integration
* 📦 Standardized directory structure for labs, courses, personal exploration
* 🤖 Built to enable future AI/LLM integrations

---

## 🔧 SaxoFlow Installation Overview (v0.3)

SaxoFlow decouples installation into two clean stages:

1. **Python environment setup** (isolated, non-invasive)
2. **Interactive tool installation** (safe, user-controlled)

---

## 🚀 Quickstart Installation

### 1⃣  Clone SaxoFlow Repository

```bash
git clone https://github.com/YOUR_ORG/saxoflow.git
cd saxoflow
```

### 2⃣  Bootstrap Python Environment

```bash
python3 bootstrap_venv.py
```

This will:

* Create `.venv/`
* Install all Python dependencies
* Register `saxoflow` CLI

### 3⃣  Activate Environment (if not auto-activated)

```bash
source .venv/bin/activate
```

### 4⃣  Launch Interactive Tool Selection

```bash
saxoflow init-env
```

Choose FPGA, ASIC, simulation, verification, and IDE components.

### 5⃣  Install Tools

```bash
# Install everything you selected:
saxoflow install all

# OR install individual tools:
saxoflow install verilator
saxoflow install openroad
```

### 6⃣  Verify Installation Health (Optional)

```bash
saxoflow doctor
```

---

## 🧪 Supported Open Source Tools

| **Tool**       | **Stage**                        | **Target**  | **Description**                                          |
| -------------- | -------------------------------- | ----------- | -------------------------------------------------------- |
| VSCode         | IDE                              | FPGA & ASIC | Modern editor with HDL extensions and Python integration |
| Icarus Verilog | RTL Simulation                   | FPGA & ASIC | Open-source Verilog simulator                            |
| Verilator      | Fast Simulation (Cycle-Accurate) | FPGA & ASIC | High-performance synthesizable subset simulator          |
| GTKWave        | Waveform Viewing                 | FPGA & ASIC | VCD waveform viewer                                      |
| Yosys          | Synthesis                        | FPGA & ASIC | RTL-to-gate open-source synthesis tool                   |
| SymbiYosys     | Formal Verification              | FPGA & ASIC | Property checking via SMT solvers                        |
| nextpnr        | Place & Route                    | FPGA        | Architecture-neutral PnR engine                          |
| openFPGALoader | Bitstream Upload                 | FPGA        | Upload bitstreams to physical FPGA boards                |
| Magic          | Physical Layout (Full Custom)    | ASIC        | Layout editor, DRC & routing                             |
| KLayout        | GDS Layout Viewer                | ASIC        | GDSII/OASIS layout viewer                                |
| Netgen         | LVS Netlist Checker              | ASIC        | Netlist equivalence checker                              |
| OpenROAD       | Digital Backend (PnR to GDSII)   | ASIC        | Digital implementation flow                              |

---

## 📊 Default Project Structure

```text
myproj/
├── rtl/                # HDL source (Verilog/SystemVerilog)
├── sim/                # Testbenches
├── formal/             # .sby specs, formal files
├── synth/              # Synthesis results
├── pnr/                # FPGA PnR or ASIC GDS
├── constraints/        # .xdc/.sdc etc.
├── output/             # Final generated outputs
├── logs/               # Timing reports, DRC, errors
├── scripts/            # Local helper scripts
├── docs/               # Markdown, diagrams
└── Makefile            # Unified interface
```

---

## 🔮 Verification Strategies

During interactive environment setup, SaxoFlow supports:

* **Simulation-Based Verification** (Icarus Verilog / Verilator)
* **Formal Verification** (SymbiYosys)
* **Hybrid Workflows** fully supported

---

## 📁 VSCode Integration

* Recommended extensions auto-installed:

  * Verilog HDL
  * Verilator Linter
  * Python
* `.venv` fully detected by VSCode
* Works seamlessly under both Linux and WSL
* Terminal-based `saxoflow` CLI integrated

---

## 🤖 Future-Proof Design Goals

* 🎯 LLM testbench generation
* 🏭 Course or university lab environments
* 💻 Board-specific FPGA flows
* 🔄 Full reproducible synthesis and verification

---

## 🔧 Contributing

We welcome contributors of all levels:

* Additional open-source tools (e.g. VUnit, CoCoTB)
* Board-specific FPGA templates
* ASIC flow optimizations
* Bug fixes and packaging improvements
* Full support for beginners and students

---

## 🔍 References

* [ASIC World Verilog Guide](https://www.asic-world.com/verilog/)
* [OpenROAD Docs](https://openroad.readthedocs.io/)
* [SymbiYosys Docs](https://symbiyosys.readthedocs.io/)
* [GTKWave](http://gtkwave.sourceforge.net/)
* [YosysHQ Docs](https://yosyshq.net/yosys/documentation.html)
* [OpenFPGA Flow](https://github.com/YosysHQ/nextpnr)

---

> © 2025 **SaxoFlow Labs** — MIT Licensed.
> Built by students. For students.
> Powered by open-source. Future-ready.
