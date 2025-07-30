
#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
VENV_PIP = VENV_DIR / "bin" / "pip"

# Add cool_cli to sys.path
sys.path.insert(0, str(ROOT / "cool_cli"))

def run(cmd, **kwargs):
    print(f"▶️ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def bootstrap():
    print("🚀 SaxoFlow Bootstrap: Creating or activating virtual environment...\n")

    if not VENV_DIR.exists():
        print(f"📦 Creating virtual environment at {VENV_DIR}")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        print("ℹ️ Virtual environment already exists.")

    print("📦 Installing dependencies...")
    run([str(VENV_PIP), "install", "--upgrade", "pip"])
    run([str(VENV_PIP), "install", "packaging"])
    run([str(VENV_PIP), "install", "-e", str(ROOT)])

    print("✅ Environment ready.\n")

def main():
    bootstrap()

    print("🌀 Launching SaxoFlow Cool CLI Shell...\n")

    # Preload CLIs
    import saxoflow.cli
    import saxoflow_agenticai.cli

    # Launch CLI
    from coolcli.shell import main as cool_cli_main
    try:
        cool_cli_main()
    except Exception as e:
        print(f"❌ Error while running CLI: {e}")

if __name__ == "__main__":
    main()

