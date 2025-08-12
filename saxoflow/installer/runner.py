# saxoflow/installer/runner.py
"""
Tool installation helpers for SaxoFlow.

This module implements installers for tools distributed via both the system
package manager (apt) and project-provided shell scripts. It also exposes
thin orchestration helpers to install:
- all known tools,
- a previously saved user selection,
- or a single tool by name.

Behavior is intentionally print/IO oriented to match existing CLI flows.

Notes
-----
- The "reinstall" prompt is kept as commented code for future use and to
  comply with the requirement of retaining unused features without removal.
- All functions aim to fail safely and emit user-friendly messages.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Sequence

from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

__all__ = [
    "load_user_selection",
    "persist_tool_path",
    "is_apt_installed",
    "is_script_installed",
    "get_version_info",
    "install_apt",
    "install_script",
    "install_tool",
    "install_all",
    "install_selected",
    "install_single_tool",
    # "prompt_reinstall",  # intentionally commented; currently unused
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOLS_FILE = Path(".saxoflow_tools.json")
VENV_ACTIVATE = Path(".venv/bin/activate")

# Default bin path hints for script-installed tools. If a tool isn't present
# here, we fallback to "$HOME/.local/<tool>/bin".
BIN_PATH_MAP = {
    "verilator": "$HOME/.local/verilator/bin",
    "openroad": "$HOME/.local/openroad/bin",
    "nextpnr": "$HOME/.local/nextpnr/bin",
    "symbiyosys": "$HOME/.local/sby/bin",
    "vivado": "$HOME/.local/vivado/bin",
    "yosys": "$HOME/.local/yosys/bin",
}


# ---------------------------------------------------------------------------
# Persistence / selection utilities
# ---------------------------------------------------------------------------


def load_user_selection() -> List[str]:
    """Load the saved tool selection from disk.

    Returns
    -------
    List[str]
        The list of tool names. Returns an empty list if the file does not exist
        or cannot be parsed.

    Notes
    -----
    This behavior mirrors the original implementation and is intentionally
    forgiving—callers handle the "no selection" case.
    """
    try:
        with TOOLS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        # Defensive normalization
        return [str(x) for x in data] if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError):
        # TODO: Consider surfacing a warning if JSON is corrupt.
        return []


def persist_tool_path(tool_name: str, bin_path: str) -> None:
    """Append an export PATH line to the virtualenv activate script, if present.

    Parameters
    ----------
    tool_name : str
        The human-readable tool identifier (for message context).
    bin_path : str
        The path to add to PATH (often a $HOME-based path).

    Notes
    -----
    - Matches original behavior (print messages and no exceptions).
    - Only appends if the activate file exists and does not already contain
      the `bin_path` string.
    """
    export_line = f"export PATH={bin_path}:$PATH"

    if VENV_ACTIVATE.exists():
        # r+ to read current content and append only when needed
        try:
            with VENV_ACTIVATE.open("r+", encoding="utf-8") as f:
                contents = f.read()
                if bin_path not in contents:
                    f.write(f"\n# Added by SaxoFlow for {tool_name}\n{export_line}\n")
                    print(
                        f"✅ {tool_name} path added to virtual environment activation script."
                    )
        except OSError:
            # Preserve original "best-effort" semantics; just don't crash.
            print(
                f"⚠  Could not persist {tool_name} path due to an I/O error on {VENV_ACTIVATE}."
            )
    else:
        print("⚠  Virtual environment not found — could not persist "
              f"{tool_name} path.")


# ---------------------------------------------------------------------------
# Optional reinstall prompt (currently unused; retained for future use)
# ---------------------------------------------------------------------------

# def prompt_reinstall(tool: str, version_info: str) -> bool:
#     """Ask the user whether to reinstall a tool that appears to be present.
#
#     Parameters
#     ----------
#     tool : str
#         Tool name for display.
#     version_info : str
#         Detected tool version string to present to the user.
#
#     Returns
#     -------
#     bool
#         True if the user explicitly chooses to reinstall ('y'), otherwise False.
#
#     Notes
#     -----
#     This is currently unused to preserve non-interactive install flows.
#     Retained for future enhancement where a forced reinstall might be desired.
#     """
#     response = input(
#         f"🔁 {tool} is already installed ({version_info}). Reinstall anyway? [y/N]: "
#     ).strip().lower()
#     return response == "y"


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def is_apt_installed(package: str) -> bool:
    """Check if a Debian package is installed via dpkg.

    Parameters
    ----------
    package : str
        Package name to query with `dpkg -s`.

    Returns
    -------
    bool
        True if installed, else False.
    """
    result = subprocess.run(
        ["dpkg", "-s", package],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def is_script_installed(tool: str) -> bool:
    """Check if a script-based tool is installed in ~/.local/<tool>/bin.

    Parameters
    ----------
    tool : str
        Tool key name (lowercase), used to form the expected install path.

    Returns
    -------
    bool
        True if the expected directory exists, else False.
    """
    install_dir = Path.home() / ".local" / tool / "bin"
    return install_dir.exists()


def get_version_info(tool: str, path: str | None) -> str:
    """Best-effort tool version extraction.

    Parameters
    ----------
    tool : str
        Tool name (used to customize the version flag parsing).
    path : str | None
        Executable path to run for version probing.

    Returns
    -------
    str
        A human-readable version line if detected; "(version unknown)" otherwise.

    Notes
    -----
    - Uses `--version` by default; some tools prefer a different flag.
    - Falls back to the first line containing a semantic version pattern.
    - All exceptions are swallowed to preserve the original, non-fatal behavior.
    """
    if not path:
        return "(version unknown)"

    try:
        import re

        # Default to `--version`, override for specific tools.
        version_cmd: List[str]
        if tool == "iverilog":
            version_cmd = [path, "-v"]
        else:
            version_cmd = [path, "--version"]

        proc = subprocess.run(
            version_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
            check=False,
        )
        output = (proc.stdout or "").strip()

        # Tool-specific recognizable lines
        for line in output.splitlines():
            line = line.strip()
            if tool == "gtkwave" and "GTKWave Analyzer v" in line:
                return line
            if tool == "iverilog" and "Icarus Verilog version" in line:
                return line
            if tool == "klayout" and "KLayout" in line:
                return line
            if tool == "magic" and "Magic" in line:
                return line
            if tool == "netgen" and "Netgen" in line:
                return line
            if tool == "openfpgaloader" and "openFPGALoader" in line:
                return line

        # Generic fallback: any line with a version-like pattern
        for line in output.splitlines():
            if re.search(r"\d+\.\d+", line):
                return line.strip()
    except (OSError, subprocess.TimeoutExpired):  # keep behavior: non-fatal
        pass

    return "(version unknown)"


# ---------------------------------------------------------------------------
# Installers
# ---------------------------------------------------------------------------


def install_apt(tool: str) -> None:
    """Install a tool via `apt`, unless it already exists.

    Parameters
    ----------
    tool : str
        The apt package name (and binary name) to install.

    Behavior
    --------
    - If already installed, prints the path and version and returns.
    - Otherwise runs `sudo apt install -y <tool>`.
    - Prints a tip for VS Code after install.
    """
    if is_apt_installed(tool):
        tool_path = shutil_which(tool)
        version_info = get_version_info(tool, tool_path)
        print(f"✅ {tool} already installed via apt: {tool_path} — {version_info}")
        return  # Preserve original behavior: no reinstall prompt

    print(f"🔧 Installing {tool} via apt...")
    subprocess.run(["sudo", "apt", "install", "-y", tool], check=True)

    if tool == "code":
        print("💡 Tip: You can run VSCode using 'code' from your terminal.")


def install_script(tool: str) -> None:
    """Install a tool via project-provided shell script.

    Parameters
    ----------
    tool : str
        The *display* name as used by callers (typically matches keys in
        SCRIPT_TOOLS). This function lowercases the tool to construct standard
        user-local install paths.

    Behavior
    --------
    - Skips install if the expected ~/.local/<tool>/bin exists.
    - Executes the script via `bash`.
    - Persists the recommended PATH augmentation to the venv activate file.
    - Adds extra PATH for 'yosys' to include `slang` (preserving original logic).
    """
    tool_key = tool.lower()

    if is_script_installed(tool_key):
        existing_path = shutil_which(tool_key)
        version_info = get_version_info(tool_key, existing_path)
        default_path = f"~/.local/{tool_key}/bin"
        print(
            f"✅ {tool} already installed: {existing_path or default_path} — {version_info}"
        )
        return  # Preserve original behavior: no reinstall prompt

    script_path = Path(SCRIPT_TOOLS.get(tool, ""))
    if not script_path.exists():
        print(f"❌ Missing installer script: {script_path}")
        return

    print(f"🚀 Installing {tool} via {script_path}...")
    subprocess.run(["bash", str(script_path)], check=True)

    persist_tool_path(tool_key, BIN_PATH_MAP.get(tool_key, f"$HOME/.local/{tool_key}/bin"))
    if tool_key == "yosys":
        # Preserve original side-effect: ensure slang is also on PATH.
        persist_tool_path("slang", "$HOME/.local/slang/bin")


def install_tool(tool: str) -> None:
    """Install a single tool by name using the appropriate strategy.

    Parameters
    ----------
    tool : str
        Tool identifier. If it is present in APT_TOOLS, apt is used.
        If in SCRIPT_TOOLS, shell installer is used. Otherwise, a warning is printed.
    """
    if tool in APT_TOOLS:
        install_apt(tool)
    elif tool in SCRIPT_TOOLS:
        install_script(tool)
    else:
        print(f"⚠ Skipping: No installer defined for '{tool}'")


def install_all() -> None:
    """Install all known tools (apt + script-based)."""
    print("🚀 Installing ALL known tools...")
    # APT_TOOLS is a sequence; SCRIPT_TOOLS.keys() yields dict_keys
    full: List[str] = list(APT_TOOLS) + list(SCRIPT_TOOLS.keys())

    for tool in full:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            # Preserve original failure reporting
            print(f"⚠ Failed installing {tool}")


def install_selected() -> None:
    """Install tools from a previously saved user selection."""
    selection = load_user_selection()
    if not selection:
        print("⚠ No saved tool selection found. Run 'saxoflow init-env' first.")
        return

    print(f"🚀 Installing user-selected tools: {selection}")
    for tool in selection:
        try:
            install_tool(tool)
        except subprocess.CalledProcessError:
            print(f"⚠ Failed installing {tool}")


def install_single_tool(tool: str) -> None:
    """Install a single tool by name and report errors gracefully.

    Parameters
    ----------
    tool : str
        Tool identifier.
    """
    print(f"🚀 Installing tool: {tool}")
    try:
        install_tool(tool)
    except subprocess.CalledProcessError:
        print(f"❌ Failed to install {tool}")


# ---------------------------------------------------------------------------
# Small compatibility shim (isolated to ease testing)
# ---------------------------------------------------------------------------


def shutil_which(cmd: str) -> str | None:
    """Wrapper for shutil.which to isolate for easier testing/mocking."""
    # Kept local to avoid a global import solely for a single call site.
    # This also makes it straightforward to monkeypatch during tests.
    try:
        import shutil

        return shutil.which(cmd)
    except Exception:
        # Extremely defensive; should not normally occur.
        return None
