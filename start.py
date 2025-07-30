
#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Add cool_cli to sys.path
sys.path.insert(0, str(ROOT / "cool_cli"))

def run(cmd, **kwargs):
    print(f"▶️ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)

def install_dependencies():
    print("📦 Installing dependencies into the current environment...")
    # You can also check for requirements.txt or pyproject.toml and install from there
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "packaging"])
    run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)])
    print("✅ Environment ready.\n")

def main():
    install_dependencies()

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


# #!/usr/bin/env python3
# import sys
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent

# # Add cool_cli to sys.path
# sys.path.insert(0, str(ROOT / "cool_cli"))

# def main():
#     print("🌀 Launching SaxoFlow Cool CLI Shell...\n")

#     # Preload CLIs to ensure modules are importable
#     try:
#         import saxoflow.cli
#         import saxoflow_agenticai.cli
#     except ImportError as e:
#         print(f"❌ Error: Required SaxoFlow modules not found: {e}")
#         print("Please ensure you have installed SaxoFlow in your environment.")
#         sys.exit(1)

#     # Launch CLI
#     from coolcli.shell import main as cool_cli_main
#     try:
#         cool_cli_main()
#     except Exception as e:
#         print(f"❌ Error while running CLI: {e}")

# if __name__ == "__main__":
#     main()
