#!/usr/bin/env python3

import os
import subprocess
import sys
from pathlib import Path
import platform

def run_command(command, check=True, **kwargs):
    print(f"🔧 Running: {' '.join(command)}")
    subprocess.run(command, check=check, **kwargs)

def create_venv():
    if not Path(".venv").exists():
        print("📦 Creating virtual environment...")
        run_command([sys.executable, "-m", "venv", ".venv"])
    else:
        print("ℹ️  Virtual environment already exists.")

def activate_venv():
    if platform.system() == "Windows":
        activate_script = Path(".venv/Scripts/activate_this.py")
    else:
        activate_script = Path(".venv/bin/activate_this.py")

    if not activate_script.exists():
        raise FileNotFoundError("❌ Could not find activate script for virtualenv.")

    with open(activate_script) as f:
        exec(f.read(), {'__file__': str(activate_script)})

def install_deps():
    print("📥 Installing Python dependencies...")
    run_command([str(Path(".venv/bin/pip")), "install", "--upgrade", "pip"])
    run_command([str(Path(".venv/bin/pip")), "install", "-r", "requirements.txt"])

def make_executable(path: Path):
    if not path.exists():
        print(f"❌ File not found: {path}")
        return
    path.chmod(path.stat().st_mode | 0o111)
    print(f"✅ Made {path} executable.")

def link_cli_scripts():
    usr_local_bin = Path("/usr/local/bin")
    if not usr_local_bin.exists():
        print("⚠️  /usr/local/bin does not exist or is not writable.")
        return

    for script in ["saxoflow", "launch_saxoflow.sh"]:
        src = Path("bin") / script
        dest = usr_local_bin / script
        if not dest.exists():
            print(f"⚙️ Linking {script} to /usr/local/bin")
            try:
                run_command(["sudo", "ln", "-s", str(src.resolve()), str(dest)])
            except subprocess.CalledProcessError:
                print(f"❌ Failed to link {script}. Try running manually: sudo ln -s {src.resolve()} {dest}")

def main():
    print("\n🚀 Bootstrapping SaxoFlow environment...\n")
    create_venv()
    activate_venv()
    install_deps()
    make_executable(Path("bin/saxoflow"))
    make_executable(Path("bin/launch_saxoflow.sh"))
    link_cli_scripts()

    print("\n✅ SaxoFlow environment is ready.")
    print("👉 You can now run: saxoflow init-env")
    print("🎯 Happy RTL hacking!")

if __name__ == "__main__":
    main()
