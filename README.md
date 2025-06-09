# 🧰 SaxoFlow: Beginner-Friendly RTL Development Flow

**SaxoFlow** is a modular, CLI-based open-source environment for simulating, verifying, synthesizing, and implementing digital logic designs — tailored for students, self-learners, and new digital designers.
It supports **both FPGA and ASIC flows**, and comes pre-integrated with industry-grade open-source tools.

---

## 🌟 Why SaxoFlow?

> “Learning Verilog shouldn’t require mastering 10 tools just to simulate a simple AND gate.”

SaxoFlow simplifies the toolchain by:

* 🧱 Providing a modular install system — choose only what you need (FPGA/ASIC)
* 🔧 Offering CLI access for every stage: simulation, synthesis, waveform, formal, and implementation
* 🧠 Auto-configuring an environment that works well with **Linux or WSL**
* 🖋 Asking separately for VSCode as your RTL text editor
* 📦 Creating a consistent project layout, ready for labs, homework, or personal exploration

---

## 🎯 Goals

| ✅ Feature               | 🔍 Description                                                      |
| ----------------------- | ------------------------------------------------------------------- |
| Easy Simulation         | Icarus Verilog and Verilator supported                              |
| Formal Verification     | Uses SymbiYosys for bug hunting and proofs                          |
| RTL Synthesis           | Via Yosys for both FPGA & ASIC targets                              |
| Waveform Viewing        | Seamless GTKWave integration                                        |
| Full VSCode Integration | IDE extensions, syntax highlighting, `.venv` detection              |
| Modular Install via CLI | You choose: minimal, FPGA, ASIC, and text editor separately         |
| LLM-Ready Architecture  | Built to support future use cases like testbench generation with AI |

---

## 📦 Open Source Tools Included

| **Tool**                                                       | **Stage**                        | **Target**  | **Description**                                                                  |
| -------------------------------------------------------------- | -------------------------------- | ----------- | -------------------------------------------------------------------------------- |
| [VSCode](https://code.visualstudio.com/)                       | IDE                              | FPGA & ASIC | Modern editor with support for HDL extensions, Python, and integrated terminals. |
| [Icarus Verilog](http://iverilog.icarus.com/)                  | RTL Simulation                   | FPGA & ASIC | Compile-and-run Verilog simulation tool.                                         |
| [Verilator](https://www.veripool.org/verilator/)               | Fast Simulation (Cycle-Accurate) | FPGA & ASIC | Converts Verilog to C++ for high-performance testing.                            |
| [GTKWave](http://gtkwave.sourceforge.net/)                     | Waveform Viewing                 | FPGA & ASIC | View `.vcd` or `.fst` files to debug simulation behavior.                        |
| [Yosys](https://yosyshq.net/yosys/)                            | Synthesis                        | FPGA & ASIC | RTL-to-gate synthesis tool, works with nextpnr and formal verification.          |
| [SymbiYosys](https://symbiyosys.readthedocs.io/)               | Formal Verification              | FPGA & ASIC | Framework for property checking with back-end SMT solvers.                       |
| [nextpnr](https://github.com/YosysHQ/nextpnr)                  | Place & Route                    | FPGA        | Architecture-neutral PnR tool for FPGAs.                                         |
| [openFPGALoader](https://github.com/trabucayre/openFPGALoader) | Bitstream Upload                 | FPGA        | Upload bitstreams to boards like iCE40 or Lattice.                               |
| [Magic](http://opencircuitdesign.com/magic/)                   | Physical Layout (Full Custom)    | ASIC        | Layout editor for VLSI designs with DRC and routing.                             |
| [KLayout](https://www.klayout.de/)                             | GDS Layout Viewer                | ASIC        | View and edit GDSII/OASIS files.                                                 |
| [Netgen](http://opencircuitdesign.com/netgen/)                 | LVS Netlist Checker              | ASIC        | Perform logical equivalence between schematic and layout.                        |
| [OpenROAD](https://openroad.readthedocs.io/)                   | Digital Backend (PnR to GDSII)   | ASIC        | Complete digital implementation flow for ASICs.                                  |

---

## 🚀 Quickstart

```bash
git clone git@github.com:saxoflowlabs/saxoflow-starter.git
cd saxoflow-starter
./scripts/dev_setup.sh           # Creates virtualenv + CLI install
source .venv/bin/activate        # Activate your Python environment
saxoflow init-env                # Choose tools for FPGA/ASIC + VSCode
```

Then scaffold a new project:

```bash
saxoflow init myproj
cd myproj
saxoflow sim                   # Compile and run simulation
saxoflow wave                  # View waveforms in GTKWave
```

---

## 🧱 Default Project Structure

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

## 🧪 Choose Your Verification Strategy

When running `saxoflow init-env`, you'll be asked:

> **What is your verification strategy?**

You can choose:

* 🔁 **Simulation-Based Verification** (Icarus Verilog or Verilator)
* 🔍 **Formal Verification** (SymbiYosys)
* ✅ **Hybrid** workflows supported

---

## 💻 VSCode Integration

* Auto-suggested extensions:
  * Verilog HDL
  * Verilator Syntax + Lint
  * Python
* `.venv` automatically recognized
* Clickable Make targets
* Built-in terminal for all `saxoflow` commands
* Chosen during `saxoflow init-env` instead of bundled blindly

---

## 🤖 Future-Proof Design

SaxoFlow is ready for:

* Integration with LLMs (e.g., prompt → testbench)
* Online course environments or labs
* Custom flows for embedded SoCs or RISCV cores
* Reproducible verification & synthesis flows

---

## 🛠 Contributing

We welcome:

* More tool integrations (e.g., VUnit, SystemC)
* Board-specific templates (Lattice, ECP5)
* Better waveform handling
* Multi-language support

✅ PRs from students, professors, and beginners are encouraged.

---

## 📚 Learn More

* [ASIC World Verilog Guide](https://www.asic-world.com/verilog/)
* [OpenROAD Docs](https://openroad.readthedocs.io/)
* [SymbiYosys Docs](https://symbiyosys.readthedocs.io/)
* [GTKWave](http://gtkwave.sourceforge.net/)
* [YosysHQ Synthesis Docs](https://yosyshq.net/yosys/documentation.html)
* [Clifford Wolf’s FPGA CAD Flow](https://yosyshq.readthedocs.io/en/latest/cad_flow.html)

---

> © 2025 **SaxoFlow Labs** — MIT Licensed.
> Built by students. For students.
> Powered by open-source. Ready for the future.

---
