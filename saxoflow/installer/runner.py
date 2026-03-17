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
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import List

import click

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
    "install_preset",
    "install_group",
    # "prompt_reinstall",  # intentionally commented; currently unused
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOLS_FILE = Path(".saxoflow_tools.json")
VENV_ACTIVATE = Path(".venv/bin/activate")
REPO_ROOT = Path(__file__).resolve().parents[2]

# Temp file used to pass per-tool install results to the shell UI layer.
_INSTALL_RESULT_PATH = Path("/tmp/saxoflow_install_result.json")


def _write_install_summary(data: dict) -> None:
    """Write install result data to a temp JSON file for the UI layer to read."""
    try:
        _INSTALL_RESULT_PATH.write_text(json.dumps(data), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _extract_error_tail(output: str, max_lines: int = 10) -> str:
    """Return the most relevant error lines from captured output.

    Works on combined stdout/stderr because shell recipes using logger.sh
    redirect stderr into stdout.

    Prefers actionable error lines (APT/CMake/compiler/linker/shell failures),
    strips bash xtrace noise, and returns a compact summary suitable for the UI.
    """
    if not output:
        return "(no error details captured)"

    ansi_re = re.compile(r"\x1b\[[0-9;]*m")
    lines = [ansi_re.sub("", ln).strip() for ln in output.splitlines() if ln.strip()]

    # Filter bash set -x trace lines
    lines = [ln for ln in lines if not ln.startswith("+")]

    keywords = (
        "error:",
        "fatal error",
        "failed",
        "not found",
        "cannot",
        "undefined",
        "no such",
        "cmake error",
        "could not find",
        "permission denied",
        "unable to locate package",
        "no rule to make target",
        "returned non-zero exit status",
        "command failed with exit code",
        "make:",
        "ld:",
        "collect2:",
        "traceback",
        "fatal:",
        "e:",
    )

    error_lines = [ln for ln in lines if any(kw in ln.lower() for kw in keywords)]

    chosen = error_lines[-max_lines:] if error_lines else lines[-max_lines:]
    return " | ".join(chosen) if chosen else "(no error details captured)"


def _extract_logfile_path(output: str) -> str | None:
    """Extract the logger.sh logfile path from combined script output."""
    if not output:
        return None

    match = re.search(r"Logfile:\s*(.+)", output)
    if match:
        return match.group(1).strip()

    match = re.search(r"Log:\s*(.+)", output)
    if match:
        return match.group(1).strip()

    return None


def _tail_logfile(log_path: str | None, max_lines: int = 80) -> str:
    """Return the tail of a logfile if it exists."""
    if not log_path:
        return ""

    try:
        path = Path(log_path).expanduser()
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:  # noqa: BLE001
        return ""


def _extract_logfile_path(output: str) -> str | None:
    """Extract the logger.sh logfile path from combined script output."""
    if not output:
        return None

    match = re.search(r"Logfile:\s*(.+)", output)
    if match:
        return match.group(1).strip()

    match = re.search(r"Log:\s*(.+)", output)
    if match:
        return match.group(1).strip()

    return None


def _tail_logfile(log_path: str | None, max_lines: int = 80) -> str:
    """Return the tail of a logfile if it exists."""
    if not log_path:
        return ""

    try:
        path = Path(log_path).expanduser()
        if not path.exists():
            return ""
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:  # noqa: BLE001
        return ""
    

def _run_cmd_tee_stderr(cmd: list) -> None:
    """Run *cmd*, streaming stdout/stderr live to the terminal while also
    capturing both streams for failure reporting.

    This is necessary because SaxoFlow shell recipes use logger.sh, which
    redirects stderr into stdout. Capturing stderr alone is therefore not
    enough to diagnose failures.

    Raises
    ------
    subprocess.CalledProcessError
        If the command exits non-zero. ``exc.stderr`` contains a compact
        human-readable error summary, and ``exc.output`` contains combined
        captured output.
    """
    stdout_lines: List[str] = []
    stderr_lines: List[str] = []
    combined_lines: List[str] = []
    lock = threading.Lock()

    proc = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    def _drain(stream, target_fd: int, sink: List[str]) -> None:
        assert stream is not None  # noqa: S101
        for line in stream:
            os.write(target_fd, line.encode("utf-8", errors="replace"))
            sink.append(line)
            with lock:
                combined_lines.append(line)
        stream.close()

    out_thread = threading.Thread(
        target=_drain, args=(proc.stdout, 1, stdout_lines), daemon=True
    )
    err_thread = threading.Thread(
        target=_drain, args=(proc.stderr, 2, stderr_lines), daemon=True
    )

    out_thread.start()
    err_thread.start()
    proc.wait()
    out_thread.join()
    err_thread.join()

    combined_output = "".join(combined_lines)
    log_path = _extract_logfile_path(combined_output)
    log_tail = _tail_logfile(log_path, max_lines=120)

    if proc.returncode != 0:
        summary_source = log_tail if log_tail else combined_output
        error_summary = _extract_error_tail(summary_source)

        if log_path:
            error_summary = f"{error_summary} | Log: {log_path}"

        raise subprocess.CalledProcessError(
            proc.returncode,
            cmd,
            output=combined_output,
            stderr=error_summary,
        )


def _run_script_tee_stderr(script_path: str) -> None:
    """Convenience wrapper — run a bash script via _run_cmd_tee_stderr."""
    _run_cmd_tee_stderr(["bash", script_path])


def _probe_tool_version(tool_key: str) -> str:
    """Return the installed version string for a tool, or '(version unknown)'.

    For script-installed tools, checks BIN_PATH_MAP first so the freshly
    installed binary is found rather than a stale one still on PATH.
    """
    try:
        from saxoflow import diagnose_tools as _dt
        # For script-installed tools, resolve via BIN_PATH_MAP before PATH
        # so the version matches the binary just installed.
        path, variant = _resolve_script_binary(tool_key)
        if path:
            return _dt.extract_version(variant or tool_key, path)
        # Fallback for apt tools (not in BIN_PATH_MAP)
        tool_path, _, variant2 = _dt.find_tool_binary(tool_key)
        if tool_path:
            return _dt.extract_version(variant2 or tool_key, tool_path)
    except Exception:  # noqa: BLE001
        pass
    return "(version unknown)"

# Default bin path hints for script-installed tools. If a tool isn't present
# here, we fallback to "$HOME/.local/<tool>/bin".
BIN_PATH_MAP = {
    "bitwuzla": "$HOME/.local/bitwuzla/bin",
    "cocotb": "$HOME/.local/cocotb/bin",
    "covered": "$HOME/.local/covered/bin",
    "cvc5": "$HOME/.local/cvc5/bin",
    "fusesoc": "$HOME/.local/fusesoc/bin",
    "verilator": "$HOME/.local/verilator/bin",
    "openroad": "$HOME/.local/openroad/bin",
    "opensta": "$HOME/.local/opensta/bin",
    "nextpnr": "$HOME/.local/nextpnr/bin",
    "rggen": "$HOME/.local/rggen/bin",
    "riscv-toolchain": "$HOME/.local/riscv-toolchain/bin",
    "spike": "$HOME/.local/spike/bin",
    "surelog": "$HOME/.local/surelog/bin",
    "sv2v": "$HOME/.local/sv2v/bin",
    "symbiyosys": "$HOME/.local/sby/bin",   # sby installs to sby/, not symbiyosys/
    "yices": "$HOME/.local/yices/bin",
    "yosys": "$HOME/.local/yosys/bin",
    "bender": "$HOME/.local/bender/bin",
    # vivado: installs to /opt/Xilinx/Vivado/<version>/bin — handled separately
    # vscode:  installs via apt to /usr/bin — already on PATH, no entry needed
}

# Some tools install under a different binary name than their tool key.
_SCRIPT_BINARY_NAMES: dict = {
    "cocotb": "cocotb-config",
    "opensta": "sta",
    "riscv-toolchain": "riscv64-unknown-elf-gcc",
    "symbiyosys": "sby",
    "vscode": "code",
    "yices": "yices",
}


def _resolve_script_binary(tool_key: str) -> tuple:
    """Return (path_or_None, binary_name) for a script-installed tool.

    Tries in order:
    1. expand BIN_PATH_MAP entry and look for the binary there directly
       (works right after install even before PATH is reloaded);
    2. shutil.which (works when the session PATH is already updated);
    3. diagnose_tools.find_tool_binary for special-variant tools (nextpnr).
    """
    import os as _os
    binary_name = _SCRIPT_BINARY_NAMES.get(tool_key, tool_key)

    # 1. Direct path from BIN_PATH_MAP (most reliable right after install)
    bin_dir_str = BIN_PATH_MAP.get(tool_key, f"$HOME/.local/{tool_key}/bin")
    bin_dir = Path(_os.path.expandvars(_os.path.expanduser(bin_dir_str)))

    # vivado: non-standard install path /opt/Xilinx/Vivado/<version>/bin/vivado
    if tool_key == "vivado":
        from glob import glob as _glob  # noqa: PLC0415
        for candidate in sorted(_glob("/opt/Xilinx/Vivado/*/bin/vivado"), reverse=True):
            if _os.access(candidate, _os.X_OK):
                return candidate, "vivado"

    # For nextpnr, scan the directory for any nextpnr-* variant
    if tool_key == "nextpnr" and bin_dir.is_dir():
        for candidate in sorted(bin_dir.glob("nextpnr*")):
            if candidate.is_file() and _os.access(str(candidate), _os.X_OK):
                return str(candidate), candidate.name

    direct = bin_dir / binary_name
    if direct.exists() and _os.access(str(direct), _os.X_OK):
        return str(direct), binary_name

    # 2. PATH lookup (works when the venv was already re-activated)
    from_path = shutil_which(binary_name)
    if from_path:
        return from_path, binary_name

    # 3. Fall back to the richer diagnose_tools search (handles nextpnr variants etc.)
    try:
        from saxoflow import diagnose_tools as _dt  # local import avoids circular dep
        found_path, _, variant = _dt.find_tool_binary(tool_key)
        if found_path:
            return found_path, variant or binary_name
    except Exception:  # noqa: BLE001
        pass

    return None, binary_name


def _show_post_install_info(tool_key: str, tool_display: str, *, is_apt: bool = False) -> None:
    """Print the installed path and version of a tool right after installation.

    Uses diagnose_tools.extract_version for per-tool version parsing (the same
    logic used by 'saxoflow diagnose summary') so the output is accurate and
    consistent across subcommands.
    """
    try:
        from saxoflow import diagnose_tools as _dt  # local import — avoids circular dep
        if is_apt:
            path = shutil_which(tool_key)
            variant = tool_key
        else:
            path, variant = _resolve_script_binary(tool_key)

        if path:
            version = _dt.extract_version(variant, path)
            click.secho(f"SUCCESS: {tool_display} installed at: {path}", fg="green")
            click.secho(f"         Version : {version}", fg="green")
        else:
            # Binary not found yet — PATH update requires session reload
            click.secho(
                f"SUCCESS: {tool_display} installed. "
                "Run '. .venv/bin/activate' (or open a new shell) to reload PATH.",
                fg="green",
            )
    except Exception:  # noqa: BLE001 — always non-fatal
        click.secho(f"SUCCESS: {tool_display} installed successfully.", fg="green")


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
    """Make a tool's bin directory available immediately and persistently.

    1. Prepends the expanded path to ``os.environ["PATH"]`` right now so the
       tool is usable in the same SaxoFlow session without any restart.
    2. Appends an ``export PATH=…`` line to ``~/.bashrc`` (once) so the tool
       is available in every future terminal session.

    Parameters
    ----------
    tool_name : str
        Human-readable tool identifier (used in log messages).
    bin_path : str
        Path string to add; may contain ``$HOME`` or ``~``.
    """
    import os as _os

    expanded = _os.path.expandvars(_os.path.expanduser(bin_path))

    # 1) Live PATH — effective immediately, no restart needed.
    current_path = _os.environ.get("PATH", "")
    if expanded not in current_path.split(_os.pathsep):
        _os.environ["PATH"] = expanded + _os.pathsep + current_path

    # 2) ~/.bashrc — persists across new terminal sessions.
    export_line = f"export PATH={bin_path}:$PATH"
    marker = f"# Added by SaxoFlow for {tool_name}"
    bashrc = Path.home() / ".bashrc"
    try:
        existing = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
        if bin_path not in existing:
            with bashrc.open("a", encoding="utf-8") as f:
                f.write(f"\n{marker}\n{export_line}\n")
    except OSError:
        pass  # best-effort; live PATH above already covers this session


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
    """Check if a script-based tool is already installed.

    Uses BIN_PATH_MAP for the correct install directory so tools that install
    under a different name (e.g. symbiyosys → ~/.local/sby/) are detected
    correctly.  Special-cases vscode (apt) and vivado (opt path).
    """
    import os as _os
    binary_name = _SCRIPT_BINARY_NAMES.get(tool, tool)

    # vscode installs via apt/snap to /usr/bin/code — check PATH only.
    if tool == "vscode":
        return bool(shutil_which("code") or shutil_which("vscode"))

    # vivado installs to /opt/Xilinx/Vivado/<version>/bin/vivado.
    if tool == "vivado":
        from glob import glob as _glob  # noqa: PLC0415
        return bool(_glob("/opt/Xilinx/Vivado/*/bin/vivado")) or bool(shutil_which("vivado"))

    # All other script tools: use BIN_PATH_MAP for the correct install dir.
    _home = Path.home()
    if tool in BIN_PATH_MAP:
        bin_dir = Path(BIN_PATH_MAP[tool].replace("$HOME", str(_home)).replace("~", str(_home)))
    else:
        bin_dir = _home / ".local" / tool / "bin"

    # nextpnr installs as nextpnr-ice40/ecp5/etc., not a plain 'nextpnr' binary.
    if tool == "nextpnr" and bin_dir.is_dir():
        return any(
            f.is_file() and _os.access(str(f), _os.X_OK)
            for f in bin_dir.glob("nextpnr*")
        )

    # yices may install as yices, yices-smt2, or yices_smt2 depending on package/source.
    if tool == "yices":
        local_variants = [bin_dir / "yices", bin_dir / "yices-smt2", bin_dir / "yices_smt2"]
        if any(p.exists() for p in local_variants):
            return True
        return bool(shutil_which("yices") or shutil_which("yices-smt2") or shutil_which("yices_smt2"))

    # Generic fallback: local install dir OR already visible in PATH.
    return (bin_dir / binary_name).exists() or bool(shutil_which(binary_name))


def _is_wsl() -> bool:
    """Return True when running under Windows Subsystem for Linux."""
    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            ver = f.read().lower()
        return "microsoft" in ver or "wsl" in ver
    except Exception:
        return False


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

        # For apt-installed GUI tools (klayout, magic, netgen) that don't support
        # --version and hang in headless environments — use dpkg instead.
        if tool in ("klayout", "magic", "netgen"):
            dpkg = subprocess.run(
                ["dpkg", "-l", tool],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=5, check=False,
            )
            for line in dpkg.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[1] == tool and parts[0] in ("ii", "hi"):
                    m = re.search(r"(\d+\.\d+[\w.\-+]*)", parts[2])
                    if m:
                        return m.group(1).strip()
            # Fallback for klayout: try -v flag
            if tool == "klayout":
                try:
                    proc2 = subprocess.run(
                        [path, "-v"],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, timeout=5, check=False,
                    )
                    m = re.search(r"(\d+\.\d+[\w.\-+]*)", proc2.stdout or "")
                    if m:
                        return m.group(1).strip()
                except Exception:
                    pass
            return "(version unknown)"

        # Default to `--version`, override for specific tools.
        version_cmd: List[str]
        if tool == "iverilog":
            version_cmd = [path, "-v"]
        elif tool == "covered":
            version_cmd = [path, "-v"]
        elif tool == "spike":
            version_cmd = [path, "--help"]
        elif tool == "openroad":
            version_cmd = [path, "-version"]  # OpenROAD uses single-dash flag
        else:
            version_cmd = [path, "--version"]

        # OpenROAD can take longer than 5 s to initialise; give it more headroom.
        _timeout = 15 if tool == "openroad" else 5

        proc = subprocess.run(
            version_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=_timeout,
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
            if tool == "openroad" and "OpenROAD" in line:
                return line
            if tool == "covered" and line.lower().startswith("covered-"):
                return line
            if tool == "spike" and "Spike RISC-V ISA Simulator" in line:
                return line

        # Generic fallback: any line with a version-like pattern
        for line in output.splitlines():
            if re.search(r"\d+\.\d+", line):
                return line.strip()

        # OpenROAD bare-version fallback: -version prints only the build-id
        # (e.g. "26Q1-1805-g362a91a058") — no dot, no prefix, so all patterns
        # above miss it.  Return the first non-empty line.
        if tool == "openroad" and output:
            first = output.splitlines()[0].strip()
            if first:
                return first

        # Covered commonly reports version as "covered-YYYYMMDD" (no dot).
        # Preserve that first-line output instead of reporting unknown.
        if tool == "covered" and output:
            first = output.splitlines()[0].strip()
            if first:
                return first
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
        click.secho(
            f"SUCCESS: {tool} already installed via apt: {tool_path} - {version_info}",
            fg="green",
        )
        return  # Preserve original behavior: no reinstall prompt

    click.secho(f"INFO: Installing {tool} via apt...", fg="cyan")
    _run_cmd_tee_stderr(["sudo", "apt", "install", "-y", tool])

    # Show installed location and version using the same rich parser as diagnose
    _show_post_install_info(tool, tool, is_apt=True)

    if tool == "code":
        click.secho("TIP: You can run VSCode using 'code' from your terminal.", fg="cyan")


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
        # Resolve the actual binary (may not be in PATH if venv not yet activated)
        existing_path, binary_name = _resolve_script_binary(tool_key)
        if not existing_path:
            existing_path = shutil_which(tool_key)
        version_info = get_version_info(binary_name, existing_path)
        display_path = existing_path or f"~/.local/{tool_key}/bin/{binary_name}"
        click.secho(
            f"SUCCESS: {tool} already installed: {display_path} - {version_info}",
            fg="green",
        )
        return  # Preserve original behavior: no reinstall prompt

    script_rel = SCRIPT_TOOLS.get(tool, "")
    script_path = Path(script_rel)
    if not script_path.is_absolute():
        script_path = (REPO_ROOT / script_path).resolve()
    if not script_path.exists():
        click.secho(f"ERROR: Missing installer script: {script_path}", fg="red")
        raise FileNotFoundError(f"Missing installer script: {script_path}")

    # Refine messaging for VSCode under WSL (the script does a check-only path)
    if tool_key == "vscode" and _is_wsl():
        click.secho("INFO: Checking VSCode/WSL integration (no Linux install attempted)...", fg="cyan")
    else:
        click.secho(f"INFO: Installing {tool} via {script_path}...", fg="cyan")

    _run_script_tee_stderr(str(script_path))

    # Show installed location and version using the same rich parser as diagnose
    _show_post_install_info(tool_key, tool, is_apt=False)

    # vscode installs via apt/snap to /usr/bin — already on PATH, nothing to persist.
    if tool_key == "vscode":
        return

    # vivado: glob for the actual versioned install path under /opt/Xilinx.
    if tool_key == "vivado":
        from glob import glob as _glob  # noqa: PLC0415
        matches = sorted(_glob("/opt/Xilinx/Vivado/*/bin"), reverse=True)
        if matches:
            # Use the literal path so bashrc export is version-independent via glob.
            persist_tool_path("vivado", matches[0])
        return

    # All other script tools: use BIN_PATH_MAP for the correct bin directory.
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
        click.secho(f"WARNING: Skipping: No installer defined for '{tool}'", fg="yellow")


def install_all() -> None:
    """Install all known tools (apt + script-based)."""
    click.secho("INFO: Installing ALL known tools...", fg="cyan")
    full: List[str] = list(APT_TOOLS) + list(SCRIPT_TOOLS.keys())
    results: List[dict] = []

    for tool in full:
        try:
            install_tool(tool)
            results.append({"tool": tool, "status": "ok", "version": _probe_tool_version(tool)})
        except subprocess.CalledProcessError as exc:
            click.secho(f"WARNING: Failed installing {tool}", fg="yellow")
            _err = (
                getattr(exc, "stderr", None)
                or _extract_error_tail(getattr(exc, "output", "") or "")
                or f"Script exited with code {exc.returncode}"
            )
            results.append({"tool": tool, "status": "failed", "error": _err})
        except Exception as exc:  # noqa: BLE001
            click.secho(f"WARNING: Failed installing {tool}: {exc}", fg="yellow")
            results.append({"tool": tool, "status": "failed", "error": str(exc)})

    _write_install_summary({"mode": "all", "label": "all tools", "results": results})
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        sys.exit(1)


def install_selected() -> None:
    """Install tools from a previously saved user selection."""
    selection = load_user_selection()
    if not selection:
        click.secho("WARNING: No saved tool selection found. Run 'saxoflow init-env' first.", fg="yellow")
        return

    click.secho(f"INFO: Installing user-selected tools: {selection}", fg="cyan")
    results: List[dict] = []
    for tool in selection:
        try:
            install_tool(tool)
            results.append({"tool": tool, "status": "ok", "version": _probe_tool_version(tool)})
        except subprocess.CalledProcessError as exc:
            click.secho(f"WARNING: Failed installing {tool}", fg="yellow")
            _err = (
                getattr(exc, "stderr", None)
                or _extract_error_tail(getattr(exc, "output", "") or "")
                or f"Script exited with code {exc.returncode}"
            )
            results.append({"tool": tool, "status": "failed", "error": _err})
        except Exception as exc:  # noqa: BLE001
            click.secho(f"WARNING: Failed installing {tool}: {exc}", fg="yellow")
            results.append({"tool": tool, "status": "failed", "error": str(exc)})

    _write_install_summary({"mode": "selected", "label": "selected tools", "results": results})
    failed = [r for r in results if r["status"] == "failed"]
    if failed:
        sys.exit(1)


def install_preset(preset_name: str) -> None:
    """Install all tools belonging to a named preset.

    Parameters
    ----------
    preset_name : str
        A key from ``saxoflow.installer.presets.PRESETS``
        (e.g. ``"ethz_ic_design_tools"``, ``"asic"``, ``"fpga"``).

    Behavior
    --------
    - Resolves the preset's tool list from ``PRESETS``.
    - Calls ``install_tool`` for each tool in order.
    - Prints a summary on completion.
    - Unknown presets emit a warning and return without error.
    """
    from saxoflow.installer.presets import PRESETS  # local import avoids circular deps

    tools = PRESETS.get(preset_name, [])
    if not tools:
        click.secho(
            f"WARNING: Preset '{preset_name}' not found or contains no tools.",
            fg="yellow",
        )
        return

    click.secho(
        f"INFO: Installing preset '{preset_name}' ({len(tools)} tools): "
        + ", ".join(tools),
        fg="cyan",
    )
    results: List[dict] = []
    for tool in tools:
        try:
            install_tool(tool)
            results.append({"tool": tool, "status": "ok", "version": _probe_tool_version(tool)})
        except subprocess.CalledProcessError as exc:
            click.secho(f"WARNING: Failed installing {tool}", fg="yellow")
            _err = getattr(exc, "stderr", None) or f"Script exited with code {exc.returncode} (see output above)"
            results.append({"tool": tool, "status": "failed", "error": _err})
        except Exception as exc:  # noqa: BLE001
            click.secho(f"WARNING: Failed installing {tool}: {exc}", fg="yellow")
            results.append({"tool": tool, "status": "failed", "error": str(exc)})

    _write_install_summary({"mode": "preset", "label": preset_name, "results": results})
    failed = [r["tool"] for r in results if r["status"] == "failed"]
    if failed:
        click.secho(
            f"WARNING: Preset '{preset_name}' completed with errors: {failed}",
            fg="yellow",
        )
        sys.exit(1)
    else:
        click.secho(
            f"SUCCESS: All tools for preset '{preset_name}' installed successfully.",
            fg="green",
        )


def install_group(group_name: str) -> None:
    """Install all tools belonging to a named tool group.

    Parameters
    ----------
    group_name : str
        A key from ``saxoflow.installer.presets.ALL_TOOL_GROUPS``
        (e.g. ``"formal-solvers"``, ``"simulation"``).

    Behavior
    --------
    - Resolves the group's tool list from ``ALL_TOOL_GROUPS``.
    - Calls ``install_tool`` for each tool in order.
    - Prints a summary on completion.
    - Unknown groups emit a warning and return without error.
    """
    from saxoflow.installer.presets import ALL_TOOL_GROUPS  # local import avoids circular deps

    tools = ALL_TOOL_GROUPS.get(group_name, [])
    if not tools:
        click.secho(
            f"WARNING: Group '{group_name}' not found or contains no tools.",
            fg="yellow",
        )
        return

    click.secho(
        f"INFO: Installing group '{group_name}' ({len(tools)} tools): "
        + ", ".join(tools),
        fg="cyan",
    )
    results: List[dict] = []
    for tool in tools:
        try:
            install_tool(tool)
            results.append({"tool": tool, "status": "ok", "version": _probe_tool_version(tool)})
        except subprocess.CalledProcessError as exc:
            click.secho(f"WARNING: Failed installing {tool}", fg="yellow")
            _err = getattr(exc, "stderr", None) or f"Script exited with code {exc.returncode} (see output above)"
            results.append({"tool": tool, "status": "failed", "error": _err})
        except Exception as exc:  # noqa: BLE001
            click.secho(f"WARNING: Failed installing {tool}: {exc}", fg="yellow")
            results.append({"tool": tool, "status": "failed", "error": str(exc)})

    _write_install_summary({"mode": "group", "label": group_name, "results": results})
    failed = [r["tool"] for r in results if r["status"] == "failed"]
    if failed:
        click.secho(
            f"WARNING: Group '{group_name}' completed with errors: {failed}",
            fg="yellow",
        )
        sys.exit(1)
    else:
        click.secho(
            f"SUCCESS: All tools for group '{group_name}' installed successfully.",
            fg="green",
        )


def install_single_tool(tool: str) -> None:
    """Install a single tool by name and report errors gracefully.

    Parameters
    ----------
    tool : str
        Tool identifier.
    """
    click.secho(f"INFO: Installing tool: {tool}", fg="cyan")
    try:
        install_tool(tool)
        version = _probe_tool_version(tool)
        _write_install_summary({"mode": "single", "label": tool, "results": [{"tool": tool, "status": "ok", "version": version}]})
    except subprocess.CalledProcessError as exc:
        click.secho(f"ERROR: Failed to install {tool}", fg="red")
        _err = getattr(exc, "stderr", None) or f"Script exited with code {exc.returncode} (see output above)"
        _write_install_summary({"mode": "single", "label": tool, "results": [{"tool": tool, "status": "failed", "error": _err}]})
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.secho(f"ERROR: Failed to install {tool}: {exc}", fg="red")
        _write_install_summary({"mode": "single", "label": tool, "results": [{"tool": tool, "status": "failed", "error": str(exc)}]})
        sys.exit(1)


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

