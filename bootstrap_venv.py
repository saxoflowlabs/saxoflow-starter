#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path

def run(cmd):
    print(f"▶️ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True)

def create_virtualenv():
    venv_dir = Path(".venv")
    if not venv_dir.exists():
        print("📦 Creating Python virtual environment...")
        run([sys.executable, "-m", "venv", str(venv_dir)])
    else:
        print("ℹ️ Virtualenv already exists.")

def install_requirements():
    pip_bin = Path(".venv/bin/pip")
    run([pip_bin, "install", "--upgrade", "pip"])
    run([pip_bin, "install", "-r", "requirements.txt"])
    run([pip_bin, "install", "-e", "."])

def show_completion():
    print("\n✅ Python virtual environment ready!")
    print("------------------------------------------------")
    print("👉 Next steps:")
    print("  1️⃣  source .venv/bin/activate")
    print("  2️⃣  ./scripts/bootstrap.sh all      # Install all EDA tools")
    print("  3️⃣  saxoflow init-env               # Begin SaxoFlow")
    print("------------------------------------------------")

def main():
    print("🚀 SaxoFlow Python Bootstrap Starting...")
    create_virtualenv()
    install_requirements()
    show_completion()

if __name__ == "__main__":
    main()
