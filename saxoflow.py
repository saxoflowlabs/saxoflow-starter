#!/usr/bin/env python3
"""
Launcher for the SaxoFlow Cool CLI Shell.

- Ensures the project root is on sys.path so local `cool_cli` is importable.
- Installs the local package in editable mode (optional convenience).
- Loads the new entrypoint `cool_cli.app:main`, with a fallback shim
  `cool_cli.coolcli.shell:main` for legacy imports.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Put the PROJECT ROOT on sys.path so `import cool_cli` resolves to ./cool_cli
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# -----------------------------
# Minimal ANSI color helpers
# -----------------------------
_RESET = "\033[0m"
_BLUE = "\033[1;34m"
_GREEN = "\033[1;32m"
_YELLOW = "\033[1;33m"
_RED = "\033[1;31m"
_CYAN = "\033[1;36m"


def _log(tag: str, color: str, message: str) -> None:
    print(f"{color}[{tag}]{_RESET} {message}")


def run(cmd, **kwargs):
    """Run a command with check=True and echo."""
    _log("RUN", _BLUE, " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def install_dependencies():
    """Install local package in editable mode (optional convenience)."""
    _log("INFO", _BLUE, "Installing dependencies into the current environment...")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "packaging"])
    # If pyproject.toml/setup.cfg exists in ROOT this installs `cool_cli` in editable mode.
    run([sys.executable, "-m", "pip", "install", "-e", str(ROOT)])
    _log("OK", _GREEN, "Environment ready.\n")


def main():
    install_dependencies()

    _log("START", _CYAN, "Launching SaxoFlow Cool CLI Shell...\n")

    # Preload CLIs (optional; warn but don't fail if unavailable)
    try:
        import saxoflow.cli  # noqa: F401
        import saxoflow_agenticai.cli  # noqa: F401
    except Exception as exc:
        _log("WARN", _YELLOW, f"Could not preload CLIs: {exc}")

    # Import the interactive entrypoint (new path first, then legacy shim)
    try:
        from cool_cli.app import main as cool_cli_main
    except Exception as exc_new:
        try:
            # Legacy fallback (shim re-exports new main)
            from cool_cli.shell import main as cool_cli_main  # type: ignore
        except Exception as exc_old:
            _log("ERROR", _RED, "Unable to import the Cool CLI entrypoint.\n")
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
        _log("ERROR", _RED, f"Error while running CLI: {e}")


if __name__ == "__main__":
    main()
