# SaxoFlow 🔧📐

**Student‑friendly RTL design flow for Linux/WSL using open-source tools.**

---

## 🎯 Goals

- ✅ Easy Verilog/SystemVerilog simulation with Icarus or Verilator
- ✅ Formal checking using SymbiYosys
- ✅ Waveform viewing with GTKWave
- ✅ Simple `saxoflow` CLI for all operations
- ✅ Modular setup: students can choose FPGA or ASIC toolchains
- ✅ Beginner-friendly VSCode IDE integration
- ✅ Future-ready: supports LLM-driven design/verification workflows

---

## 📦 What Tools Are Supported?

| Stage             | Tools                                                                 |
|------------------|-----------------------------------------------------------------------|
| **IDE**          | VSCode (with Verilog/SystemVerilog extensions)                        |
| **Simulation**   | Icarus Verilog, Verilator (student can choose)                        |
| **Wave Viewer**  | GTKWave                                                               |
| **Synthesis**    | Yosys                                                                 |
| **Formal**       | SymbiYosys                                                            |
| **FPGA Tools**   | nextpnr, openFPGALoader                                               |
| **ASIC Tools**   | Magic, KLayout, Netgen, OpenROAD                                      |

---

## 🚀 Quickstart

```bash
git clone https://github.com/your-org/saxoflow-starter.git
cd saxoflow-starter
./scripts/setup.sh       # Creates Python virtualenv + installs saxoflow CLI
saxoflow init-env        # Choose your target flow and tools
```

Then to start a new project:

```bash
saxoflow init myproj     # Sets up a new RTL project
cd myproj
saxoflow sim             # Runs simulation
```

---

## 🛠 Project Layout

```
myproj/
├── rtl/                # Your design files (.v, .sv)
├── sim/                # Testbenches
├── formal/             # Formal specs and .sby files
├── build/              # Build artifacts
├── Makefile            # Unified flow entry point (sim, formal, wave)
└── dump.vcd            # Waveform dump (after sim)
```

---

## 🧠 Beginner Concepts

- ✅ **Simulation**: Run your design with a testbench and see results.
- ✅ **Formal**: Prove properties (e.g., no overflow, correctness) using solvers.
- ✅ **Waveform**: See how signals behave over time using GTKWave.
- ✅ **saxoflow CLI**: Use `saxoflow sim`, `saxoflow formal`, `saxoflow wave`.

---

## ✍️ Customize Your Flow

Run:

```bash
saxoflow init-env
```

Choose:
- 🎯 Target device: **FPGA** or **ASIC**
- 🧪 Tools: iverilog, verilator, openroad, vscode, etc.

Only the tools you select will be installed. Ideal for students with limited space or specific goals.

---

## 🧩 VSCode Support

When you open this folder in VSCode:
- 💡 Recommended extensions will be suggested (Verilog, Python, etc.)
- ⚙️ Auto-configured Python virtualenv
- 🧠 `.v` and `.sv` files have syntax highlighting and linting

---

## 🙌 Contributing / Feedback

If you’re a student, educator, or hardware enthusiast:
- Fork this repo
- Add new Makefile targets
- Extend the CLI
- Suggest better defaults or examples

---

## 📚 Learn More

- [Verilog HDL Tutorial (ASIC World)](https://www.asic-world.com/verilog/)
- [SymbiYosys Guide](https://symbiyosys.readthedocs.io/)
- [OpenROAD Docs](https://openroad.readthedocs.io/)
