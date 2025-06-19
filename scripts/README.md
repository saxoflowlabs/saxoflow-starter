# SaxoFlow Installer — Professional Toolchain Setup

This directory provides a fully modular, maintainable and reusable installation system for the entire SaxoFlow open-source EDA stack.

---

## ✅ Features

- Fully modular per-tool recipes (`recipes/`)
- Shared reusable components (`common/`)
- Universal installer entrypoint (`install_tool.sh`)
- Re-runnable, safe, idempotent — detects existing installs
- Supports partial or full toolchain setup
- Clean separation of dependencies, sources, and build trees

---

## 🔧 Quick Start

### To install any individual tool:

```bash
bash scripts/install_tool.sh <toolname>

# Example:
bash scripts/install_tool.sh verilator
bash scripts/install_tool.sh openroad
bash scripts/install_tool.sh nextpnr
bash scripts/install_tool.sh symbiyosys
bash scripts/install_tool.sh vscode
