
# #!/usr/bin/env python3
# import os
# import sys
# import subprocess
# from pathlib import Path

# ROOT = Path(__file__).resolve().parent

# # Add cool_cli to sys.path
# sys.path.insert(0, str(ROOT))

# def run(cmd, **kwargs):
#     print(f"▶️ {' '.join(str(c) for c in cmd)}")
#     subprocess.run(cmd, check=True, **kwargs)

# def install_dependencies():
#     print("📦 Installing dependencies into the current environment...")
#     # You can also check for requirements.txt or pyproject.toml and install from there
#     run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
#     run([sys.executable, "-m", "pip", "install", "packaging"])
#     run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)])
#     print("✅ Environment ready.\n")

# def main():
#     install_dependencies()

#     print("🌀 Launching SaxoFlow Cool CLI Shell...\n")

#     # Preload CLIs
#     import saxoflow.cli
#     import saxoflow_agenticai.cli

#     # Launch CLI
#     from cool_cli.app import main as cool_cli_main
#     try:
#         cool_cli_main()
#     except Exception as e:
#         print(f"❌ Error while running CLI: {e}")

# if __name__ == "__main__":
#     main()


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

#!/usr/bin/env python3
"""
Launcher for the SaxoFlow Cool CLI Shell.

- Ensures the project root is on sys.path so local `cool_cli` is importable.
- Installs the local package in editable mode (optional convenience).
- Loads the new entrypoint `cool_cli.app:main`, with a fallback shim
  `cool_cli.coolcli.shell:main` for legacy imports.
"""

import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Put the PROJECT ROOT on sys.path so `import cool_cli` resolves to ./cool_cli
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(cmd, **kwargs):
    """Run a command with check=True and echo."""
    print(f"▶️ {' '.join(str(c) for c in cmd)}")
    subprocess.run(cmd, check=True, **kwargs)


def install_dependencies():
    """Install local package in editable mode (optional convenience)."""
    print("📦 Installing dependencies into the current environment...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "packaging"])
    # If pyproject.toml/setup.cfg exists in ROOT this installs `cool_cli` in editable mode.
    run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)])
    print("✅ Environment ready.\n")


def main():
    install_dependencies()

    print("🌀 Launching SaxoFlow Cool CLI Shell...\n")

    # Preload CLIs (optional; warn but don't fail if unavailable)
    try:
        import saxoflow.cli  # noqa: F401
        import saxoflow_agenticai.cli  # noqa: F401
    except Exception as exc:
        print(f"⚠️  Warning: could not preload CLIs: {exc}")

    # Import the interactive entrypoint (new path first, then legacy shim)
    try:
        from cool_cli.app import main as cool_cli_main
    except Exception as exc_new:
        try:
            # Legacy fallback (shim re-exports new main)
            from cool_cli.shell import main as cool_cli_main  # type: ignore
        except Exception as exc_old:
            print("❌ Unable to import the Cool CLI entrypoint.\n")
            print("Diagnostics:")
            print(f"- sys.path[0]: {sys.path[0]}")
            print(f"- ROOT: {ROOT}")
            print(f"- New path import error: {exc_new}")
            print(f"- Legacy shim import error: {exc_old}")
            print(
                "\nCommon fixes:\n"
                "  • Ensure there is a file: cool_cli/__init__.py\n"
                "  • Ensure there is a file: cool_cli/app.py (contains `def main()`)\n"
                "  • If you rely on the old import, ensure the shim exists at "
                "cool_cli/coolcli/shell.py"
            )
            sys.exit(1)

    try:
        cool_cli_main()
    except Exception as e:
        print(f"❌ Error while running CLI: {e}")


if __name__ == "__main__":
    main()

