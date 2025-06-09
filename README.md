# SaxoFlow 🔧📐

**A modular, beginner-friendly RTL design and verification environment for students, hobbyists, and new digital designers — built entirely using open-source tools.**

---

## 🌟 Why SaxoFlow?

Learning digital design is exciting — but getting started can feel overwhelming.

New learners often face challenges like:
- ❌ Confusing installation steps across tools
- ❌ No single flow for both FPGA & ASIC learning
- ❌ Lack of integration between simulation, synthesis, formal, and IDEs
- ❌ Difficulty setting up a working project quickly

**SaxoFlow is a unified, open-source CLI environment** that solves this by combining best-in-class tools into a simple Linux/WSL-compatible development flow.

Perfect for:
- 🎓 **University students** in VLSI, digital design, or FPGA courses
- 🧠 **Self-learners** diving into Verilog or SystemVerilog
- 🛠️ **FPGA/ASIC beginners** building and verifying simple designs
- 🧪 **Researchers & tinkerers** who want an open lab setup

---

## 🎯 Goals

- ✅ Easy Verilog/SystemVerilog simulation with Icarus or Verilator
- ✅ Formal checking using SymbiYosys
- ✅ Waveform viewing with GTKWave
- ✅ One-liner CLI for each stage via `saxoflow`
- ✅ Modular: choose **FPGA**, **ASIC**, or **minimal** flows
- ✅ VSCode integration for code, wave, and testbench workflows
- ✅ Supports future **LLM-powered design/verification workflows**

## 📦 Open Source Tools Included

| **Stage**        | **Tools**                                                                                                                                             | **Description**                                                                                   |
|------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------|
| **IDE**          | - [VSCode](https://code.visualstudio.com/)                                                                                                             | Lightweight IDE with HDL syntax highlighting and extensions                                       |
| **Simulation**   | - [Icarus Verilog](http://iverilog.icarus.com/)  
|                  | - [Verilator](https://www.veripool.org/verilator/)                                                                                                     | RTL simulation for Verilog/SystemVerilog designs                                                  |
| **Wave Viewer**  | - [GTKWave](http://gtkwave.sourceforge.net/)                                                                                                           | Graphical waveform viewer for `.vcd` and `.fst` files                                             |
| **Synthesis**    | - [Yosys](https://yosyshq.net/yosys/)                                                                                                                  | RTL-to-gate synthesis supporting Verilog and part of SystemVerilog                               |
| **Formal**       | - [SymbiYosys](https://symbiyosys.readthedocs.io/)                                                                                                     | Formal verification with assertions, safety/liveness properties via SMT solvers                  |
| **FPGA Tools**   | - [nextpnr](https://github.com/YosysHQ/nextpnr)  
|                  | - [openFPGALoader](https://github.com/trabucayre/openFPGALoader)                                                                                       | Place & route, bitstream generation, and uploading for supported FPGAs                           |
| **ASIC Tools**   | - [Magic](http://opencircuitdesign.com/magic/)  
|                  | - [KLayout](https://www.klayout.de/)  
|                  | - [Netgen](http://opencircuitdesign.com/netgen/)  
|                  | - [OpenROAD](https://openroad.readthedocs.io/)                                                                                                         | Digital PnR, layout, LVS, and GDSII generation for ASIC flows                                    |


## 🚀 Quickstart

```bash
git clone https://github.com/your-org/saxoflow-starter.git
cd saxoflow-starter
./scripts/setup.sh             # Creates Python virtualenv + installs saxoflow CLI
source .venv/bin/activate
saxoflow init-env              # Choose your target device & tools (FPGA, ASIC, Minimal)
```

Then start a project:

```bash
saxoflow init myproj           # Scaffolds a new HDL project with Makefile
cd myproj
saxoflow sim                   # Run simulation using Icarus
saxoflow wave                  # View waveforms
```

---

## 📁 Project Layout

```
myproj/
├── rtl/                # HDL source (Verilog/SystemVerilog)
├── sim/                # Testbenches
├── formal/             # Formal specs and .sby files
├── synth/              # Synthesized netlists/reports
├── pnr/                # Layout/Bitstream
├── constraints/        # .xdc, .sdc etc.
├── output/             # Final GDS/bit files
├── results/            # Post-tool results
├── logs/               # Logs & timing reports
├── scripts/            # Local design-specific scripts
├── docs/               # Markdown notes, diagrams
└── Makefile            # Main entry point (sim, synth, formal)
```

---

## 🧪 Verification Strategy (When Running `init-env`)

You’ll be asked:
> What is your verification strategy?

Choose:
- 🔁 **Simulation-based**: Icarus Verilog or Verilator (good for waveform debug)
- 🔍 **Formal**: SymbiYosys for assertions, exhaustive proof, bug hunting
- 🛠️ You can mix both (multi-tool setup is supported)

---

## 💻 VSCode Integration

When using VSCode inside your project:
- 🔌 HDL extensions auto-suggested (`.v`, `.sv`, `.sby`)
- 🐍 Uses `.venv/` for Python extensions
- 🧠 Syntax highlighting, linting, and click-to-run support for `Makefile`
- 🧪 Run `saxoflow sim` in integrated terminal

---

## 💡 Advanced Use Cases

- ✅ Great base for **FPGA/ASIC labs**
- ✅ Can be extended for **CI pipelines** using `make sim`, `make formal`
- ✅ Integrate with LLM APIs for future flows (e.g., auto-generate testbenches)
- ✅ Beginner-safe: no accidental pushes of build artifacts or `.vcd`

---

## 🙌 How to Contribute

You can:
- Add more Makefile rules (e.g., `pnr`, `bitgen`)
- Add new CLI subcommands (`saxoflow lint`, `check`, `docgen`)
- Improve simulation templates
- Translate flow for non-English speakers

PRs welcome from:
- 🎓 Students
- 🧑‍🏫 Instructors
- 🧑‍🔧 Engineers learning RTL
- 🧪 Formal verification learners

---

## 📚 Learning Resources

- [ASIC World Verilog Guide](https://www.asic-world.com/verilog/)
- [SymbiYosys ReadTheDocs](https://symbiyosys.readthedocs.io/)
- [YosysHQ Verilog Synthesis Docs](https://yosyshq.net/yosys/documentation.html)
- [GTKWave Waveform Viewer](http://gtkwave.sourceforge.net/)
- [OpenROAD Docs](https://openroad.readthedocs.io/)
- [FPGA CAD Flow Explained (Clifford Wolf)](https://yosyshq.readthedocs.io/en/latest/cad_flow.html)

---

> © 2025 SaxoFlow Labs Contributors — MIT License. This project is student-built, community-driven, and 100% open-source.