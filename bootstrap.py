import subprocess
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"

def run(cmd, **kwargs):
    print(f"▶️ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def main():
    print("🚀 SaxoFlow Professional Bootstrap Starting...\n")

    # Host dependency check (APT check should be documented manually or wrapped separately if needed)
    print("🔍 Ensuring Python3, venv, pip are available...")
    for cmd in ["python3", "python3 -m venv", "pip3"]:
        if not shutil.which(cmd.split()[0]):
            print(f"❌ Required command not found: {cmd}")
            sys.exit(1)

    # Create venv
    if not VENV_DIR.exists():
        print(f"📦 Creating virtual environment at {VENV_DIR}")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
    else:
        print("ℹ️ Virtual environment already exists.")

    # Activate and install dependencies
    pip_bin = VENV_DIR / "bin" / "pip"
    print("📦 Upgrading pip and installing required Python dependencies...")
    run([pip_bin, "install", "--upgrade", "pip"])
    run([pip_bin, "install", "packaging"])        # <--- Added line: ensure packaging is present
    run([pip_bin, "install", "-e", str(ROOT)])

    print("\n✅ Bootstrap complete!")
    print("👉 Next steps:")
    print("   1️⃣  source .venv/bin/activate")
    print("   2️⃣  saxoflow init-env")
    print("   3️⃣  saxoflow install")
    print("   4️⃣  saxoflow diagnose")

if __name__ == "__main__":
    import shutil
    main()
