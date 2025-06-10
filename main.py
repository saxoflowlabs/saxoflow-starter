#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

def run(cmd, description):
    print(f"🔧 {description}")
    print(f"▶️ Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

def create_virtualenv():
    venv_dir = Path(".venv")
    if not venv_dir.exists():
        print("📦 Creating virtual environment...")
        run([sys.executable, "-m", "venv", str(venv_dir)], "Creating Python venv")
    else:
        print("ℹ️  Virtual environment already exists.")

def activate_venv():
    activate_path = Path(".venv/bin/activate")
    if not activate_path.exists():
        raise FileNotFoundError("❌ Could not find activate script for virtualenv.")
    print(f"✅ Found virtualenv activate script at {activate_path}")
    os.environ["VIRTUAL_ENV"] = str(Path(".venv").resolve())
    os.environ["PATH"] = f"{Path('.venv/bin').resolve()}:{os.environ['PATH']}"

def install_dependencies():
    run([".venv/bin/pip", "install", "--upgrade", "pip"], "Upgrading pip")
    run([".venv/bin/pip", "install", "-r", "requirements.txt"], "Installing requirements")
    run([".venv/bin/pip", "install", "-e", "."], "Installing saxoflow as editable package")

def generate_saxoflow_launcher():
    bin_dir = Path("bin")
    saxoflow_script = bin_dir / "saxoflow"

    bin_dir.mkdir(exist_ok=True)
    contents = """#!/bin/bash
# bin/saxoflow — Launch SaxoFlow CLI from any location

SOURCE="${BASH_SOURCE[0]}"
while [ -h "$SOURCE" ]; do
  DIR="$( cd -P "$( dirname "$SOURCE" )" >/dev/null 2>&1 && pwd )"
  SOURCE="$(readlink "$SOURCE")"
  [[ $SOURCE != /* ]] && SOURCE="$DIR/$SOURCE"
done
PROJECT_ROOT="$( cd -P "$( dirname "$SOURCE" )/.." >/dev/null 2>&1 && pwd )"

source "$PROJECT_ROOT/.venv/bin/activate"
python -m saxoflow.cli "$@"
"""
    saxoflow_script.write_text(contents)
    os.chmod(saxoflow_script, 0o755)
    print("✅ bin/saxoflow launcher script generated and made executable.")

def link_cli_binaries():
    local_saxoflow = Path("bin/saxoflow").resolve()
    local_launcher = Path(__file__).resolve()

    print("🔗 Linking saxoflow → /usr/local/bin")
    run(["sudo", "ln", "-sf", str(local_saxoflow), "/usr/local/bin/saxoflow"], "Linking saxoflow")

    print("🔗 Linking launch_saxoflow → /usr/local/bin")
    run(["sudo", "ln", "-sf", str(local_launcher), "/usr/local/bin/launch_saxoflow"], "Linking launch_saxoflow")

def append_shell_rc():
    shell = os.environ.get("SHELL", "")
    shell_rc = Path.home() / (".zshrc" if "zsh" in shell else ".bashrc")
    activate_line = f"source {Path('.venv/bin/activate').resolve()}"
    with shell_rc.open("a+") as f:
        f.seek(0)
        content = f.read()
        if activate_line not in content:
            f.write(f"\n# Auto-activate SaxoFlow venv\n{activate_line}\n")
            print(f"✅ Added auto-activation to {shell_rc}")
        else:
            print(f"ℹ️  Auto-activation already present in {shell_rc}")

def print_welcome():
    print("\n✅ SaxoFlow environment is ready!")
    print("\n🌟 Welcome to SaxoFlow — your digital design playground!")
    print("\n💡 \"Design isn't just syntax, it's how you *think* in logic.\"")
    print("    — An RTL Engineer")
    print("\n📐 From simulation to synthesis, waveform debug to formal proofs,")
    print("   you're now equipped with a clean, modular, and powerful flow.")
    print("\n🚀 Run: saxoflow init-env")
    print("🧠  Then: saxoflow init my_project")
    print("\n🦾 Happy hacking — and remember: real logic is timeless.")

def main():
    print("🚀 Bootstrapping SaxoFlow environment...\n")
    create_virtualenv()
    activate_venv()
    install_dependencies()
    generate_saxoflow_launcher()
    link_cli_binaries()
    append_shell_rc()
    print_welcome()

if __name__ == "__main__":
    main()
