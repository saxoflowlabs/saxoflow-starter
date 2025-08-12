# saxoflow/diagnostics/diagnose_tools.py
"""
Environment health and diagnostics for SaxoFlow.

This module inspects the user's environment to:
- Infer the active design flow (fpga/asic/formal/minimal) from their saved
  tool selection (``.saxoflow_tools.json``).
- Locate tool binaries in PATH or common ``~/.local`` install locations.
- Extract best‑effort version strings from installed tools.
- Compute a health score for required/optional tools per flow.
- Analyze PATH, WSL presence, and provide actionable tips.

Notes
-----
- Virtual environment detection is **currently disabled** by request.
  The code is kept commented for potential future re‑enablement.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from saxoflow.tools.definitions import ALL_TOOLS

__all__ = [
    "FLOW_PROFILES",
    "tool_details",
    "load_user_selection",
    "infer_flow",
    "find_tool_binary",
    "extract_version",
    "compute_health",
    "analyze_env",
    "detect_wsl",
    "pro_diagnostics",
]

# ---------------------------------------------------------------------------
# Flow profiles (required/optional tools)
# ---------------------------------------------------------------------------

FLOW_PROFILES: Dict[str, Dict[str, List[str]]] = {
    "fpga": {
        "required": ["iverilog", "yosys", "gtkwave", "nextpnr", "openfpgaloader"],
        "optional": ["verilator", "vivado", "vscode"],
    },
    "asic": {
        "required": [
            "verilator",
            "yosys",
            "gtkwave",
            "openroad",
            "klayout",
            "magic",
            "netgen",
        ],
        "optional": ["iverilog", "vscode"],
    },
    "formal": {
        "required": ["yosys", "gtkwave", "symbiyosys"],
        "optional": ["iverilog", "vscode"],
    },
    "minimal": {
        "required": ["iverilog", "yosys", "gtkwave"],
        "optional": ["verilator", "vscode"],
    },
}

# ---------------------------------------------------------------------------
# Regex patterns pre-compiled for version parsing
# ---------------------------------------------------------------------------

_RE_IVERILOG = re.compile(r"Icarus Verilog version ([\d\.]+(?:[^\)]*\))?)")
_RE_NEXTPNR = re.compile(r"\(Version ([^)]+)\)")
_RE_GTKWAVE = re.compile(r"GTKWave Analyzer v?([^\s]+)")
_RE_GENERIC = re.compile(r"(\d+\.\d+(?:[\w\.\-\+]*))")

# Type alias for readability: (tool, present, path, version, in_path)
ToolCheck = Tuple[str, bool, Optional[str], Optional[str], bool]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def tool_details(tool: str) -> str:
    """Return a human-readable short description for a tool.

    Parameters
    ----------
    tool
        Tool identifier (e.g., ``"iverilog"``).

    Returns
    -------
    str
        Short description or empty string if unknown.
    """
    details = {
        "yosys": "Synthesizer, required for all flows.",
        "iverilog": "Simulation (FPGA/minimal), optional for ASIC.",
        "verilator": "Fast SystemVerilog simulator (ASIC/formal/FPGA).",
        "gtkwave": "Waveform viewer, used across all flows.",
        "nextpnr": "FPGA place-and-route tool.",
        "openfpgaloader": "FPGA programmer, e.g. for Lattice boards.",
        "vivado": "Proprietary FPGA toolchain (optional).",
        "vscode": "Recommended IDE integration.",
        "openroad": "Digital ASIC P&R.",
        "klayout": "Layout viewer for ASIC.",
        "magic": "ASIC layout editor.",
        "netgen": "LVS/DRC for ASIC.",
        "symbiyosys": "Formal property verification.",
    }
    return details.get(tool, "")


def load_user_selection() -> List[str]:
    """Load the saved tool selection from ``.saxoflow_tools.json``.

    Returns
    -------
    list of str
        List of tool identifiers. Empty list if the file doesn't exist or is
        invalid.

    Notes
    -----
    The function is intentionally forgiving; callers handle "no selection".
    """
    json_path = Path(".saxoflow_tools.json")
    if not json_path.exists():
        return []
    try:
        with json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data] if isinstance(data, list) else []
    except Exception:
        # TODO: consider logging a warning if file is corrupt.
        return []


def infer_flow(selection: Iterable[str]) -> str:
    """Infer the active flow profile based on the user's tool selection.

    Parameters
    ----------
    selection
        Selected tools.

    Returns
    -------
    str
        One of ``{"fpga", "asic", "formal", "minimal"}``.
    """
    sel = set(selection)
    if "nextpnr" in sel:
        return "fpga"
    if "openroad" in sel or "magic" in sel:
        return "asic"
    if "symbiyosys" in sel:
        return "formal"
    return "minimal"


def find_tool_binary(tool: str) -> Tuple[Optional[str], bool, Optional[str]]:
    """Find a tool's executable path, checking PATH and common install locations.

    Parameters
    ----------
    tool
        Base tool name (e.g., ``"nextpnr"``, ``"openfpgaloader"``, ``"iverilog"``).

    Returns
    -------
    tuple
        ``(path, in_path, variant)``:
        - ``path``: resolved executable path or ``None`` if not found.
        - ``in_path``: True if found via PATH, False if found via common
          install locations.
        - ``variant``: actual executable name used (e.g., ``"nextpnr-ice40"``),
          or the original ``tool`` name.

    Notes
    -----
    Search order:
    1) PATH (``shutil.which``)
    2) ``~/.local/<tool>/bin/<tool>``
    3) nextpnr variants (``nextpnr-ice40``/``ecp5``/``xilinx``)
    4) openfpgaloader alternate capitalization in common bins
    """
    # 1) Standard PATH search
    path = shutil.which(tool)
    if path:
        return path, True, tool

    # 2) Common ~/.local/<tool>/bin/<tool>
    user_bin = Path.home() / ".local" / tool / "bin" / tool
    if user_bin.exists() and os.access(str(user_bin), os.X_OK):
        return str(user_bin), False, tool

    # 3) Special case: nextpnr family
    if tool == "nextpnr":
        for variant in ("nextpnr-ice40", "nextpnr-ecp5", "nextpnr-xilinx"):
            alt = shutil.which(variant)
            if alt:
                return alt, True, variant
        np_dir = Path.home() / ".local" / "nextpnr" / "bin"
        if np_dir.exists():
            for file in np_dir.glob("nextpnr*"):
                if file.is_file() and os.access(str(file), os.X_OK):
                    return str(file), False, file.name

    # 4) Special case: openfpgaloader (two spellings)
    if tool == "openfpgaloader":
        for name in ("openfpgaloader", "openFPGALoader"):
            path2 = shutil.which(name)
            if path2:
                return path2, True, tool
        for base in (
            Path.home() / ".local" / "bin",
            Path("/usr/bin"),
            Path("/usr/local/bin"),
        ):
            for name in ("openfpgaloader", "openFPGALoader"):
                candidate = base / name
                if candidate.exists() and os.access(str(candidate), os.X_OK):
                    return str(candidate), False, tool

    return None, False, None


def extract_version(tool: str, path: Optional[str]) -> str:
    """Extract a version string for a tool executable (best effort).

    Parameters
    ----------
    tool
        Tool name or variant (e.g., ``"nextpnr-ice40"``).
    path
        Executable path.

    Returns
    -------
    str
        Version string like ``"5.0"`` or ``"(unknown)"``. On parsing failure,
        returns a message ``"(parse error: <reason>)"``.

    Notes
    -----
    - Uses tool‑specific parsing heuristics when available.
    - Falls back to a generic version regex.
    - Times out subprocess calls to avoid hangs.
    """
    if not path:
        return "(unknown)"

    def _run_and_collect(args: List[str]) -> str:
        """Run a command and collect combined stdout+stderr as a string."""
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return (proc.stdout or "") + " " + (proc.stderr or "")

    try:
        if tool == "iverilog":
            text = _run_and_collect([path, "-v"])
            m = _RE_IVERILOG.search(text)
            return (
                m.group(1).strip()
                if m
                else (_RE_GENERIC.search(text) or _noop_match()).group(0)
            )

        if tool.startswith("nextpnr"):
            for flag in ("--version", "-v", "--help"):
                try:
                    text = _run_and_collect([path, flag])
                    m = _RE_NEXTPNR.search(text)
                    if m:
                        return m.group(1).strip()
                except Exception:
                    # Try next flag
                    continue
            return "(unknown)"

        if tool == "gtkwave":
            text = _run_and_collect([path, "--version"])
            m = _RE_GTKWAVE.search(text) or _RE_GENERIC.search(text)
            return m.group(1).strip() if m else "(unknown)"

        if tool == "yosys":
            text = _run_and_collect([path, "-V"])
            m = _RE_GENERIC.search(text)
            return m.group(1).strip() if m else "(unknown)"

        if tool == "verilator":
            text = _run_and_collect([path, "--version"])
            m = _RE_GENERIC.search(text)
            return m.group(1).strip() if m else "(unknown)"

        if tool == "openfpgaloader":
            for flag in ("--version", "-V"):
                try:
                    text = _run_and_collect([path, flag])
                    m = _RE_GENERIC.search(text)
                    if m:
                        return m.group(1).strip()
                except Exception:
                    continue
            return "(unknown)"

        # Generic fallback
        text = _run_and_collect([path, "--version"])
        m = _RE_GENERIC.search(text)
        return m.group(1).strip() if m else "(unknown)"

    except Exception as exc:  # keep behavior: return parse error string
        return f"(parse error: {exc})"


def compute_health() -> Tuple[str, int, List[ToolCheck], List[ToolCheck]]:
    """Compute environment health for the inferred flow.

    Returns
    -------
    tuple
        ``(flow, score, required_results, optional_results)``:
        - ``flow``: inferred flow profile name.
        - ``score``: percentage (0–100) of required tools found.
        - ``required_results``: list of ``ToolCheck`` tuples.
        - ``optional_results``: list of ``ToolCheck`` tuples.

    Notes
    -----
    The shape and semantics mirror the original implementation.
    """
    user_selection = load_user_selection()
    flow = infer_flow(user_selection)
    profile = FLOW_PROFILES[flow]

    required = profile["required"]
    optional = profile["optional"]

    result: List[ToolCheck] = []
    ok = 0

    # Required tools
    for tool in required:
        path, in_path, variant = find_tool_binary(tool)
        version = extract_version(variant or tool, path) if path else None
        if path:
            result.append((tool, True, path, version, in_path))
            ok += 1
        else:
            result.append((tool, False, None, None, False))

    # Optional tools
    opt_result: List[ToolCheck] = []
    for tool in optional:
        path, in_path, variant = find_tool_binary(tool)
        version = extract_version(variant or tool, path) if path else None
        if path:
            opt_result.append((tool, True, path, version, in_path))
        else:
            opt_result.append((tool, False, None, None, False))

    score = int(ok / len(required) * 100) if required else 100
    return flow, score, result, opt_result


def analyze_env() -> Dict[str, object]:
    """Analyze environment properties and PATH layout.

    Returns
    -------
    dict
        Summary fields:
        - ``platform`` (str)
        - ``python_version`` (str)
        - ``wsl`` (bool)
        - ``path`` (str)
        - ``project_root`` (str)
        - ``user`` (str)
        - ``home`` (str)
        - ``path_duplicates`` (List[Tuple[path_str, List[tools]]])
        - ``bins_missing_in_path`` (List[Tuple[bin_path, tool]])

    Notes
    -----
    - PATH duplicates are collected in order of appearance after the first
      occurrence (to preserve original UX).
    - ``bins_missing_in_path`` only lists bins that exist on disk but aren't
      in PATH.
    """
    summary: Dict[str, object] = {}
    summary["platform"] = platform.platform()
    summary["python_version"] = platform.python_version()
    # summary["venv"] = os.getenv("VIRTUAL_ENV")  # Disabled for now
    summary["wsl"] = detect_wsl()
    summary["path"] = os.getenv("PATH", "")
    summary["project_root"] = str(Path.cwd())
    summary["user"] = os.getenv("USER") or os.getenv("USERNAME") or "unknown"
    summary["home"] = str(Path.home())

    paths = str(summary["path"]).split(":") if summary["path"] else []

    # Build mapping: which tools are in each path entry
    path_tool_map: Dict[str, List[str]] = {}
    for tool in ALL_TOOLS:
        for p in paths:
            tp = Path(p) / tool
            if tp.exists() and os.access(str(tp), os.X_OK):
                path_tool_map.setdefault(p, []).append(tool)

    # Duplicates: show all associated tools for each duplicate path
    seen = set()
    duplicates: List[Tuple[str, List[str]]] = []
    for p in paths:
        if p in seen:
            assoc_tools = path_tool_map.get(p, [])
            duplicates.append((p, assoc_tools))
        seen.add(p)
    summary["path_duplicates"] = duplicates

    # Tool bins not in PATH, with context: ~/.local/<tool>/bin
    toolbins = [str(Path.home() / ".local" / t / "bin") for t in ALL_TOOLS]
    toolbin_map = {str(Path.home() / ".local" / t / "bin"): t for t in ALL_TOOLS}
    summary["bins_missing_in_path"] = [
        (tb, toolbin_map.get(tb))
        for tb in toolbins
        if tb not in paths and os.path.isdir(tb)
    ]

    return summary


def detect_wsl() -> bool:
    """Detect whether running under Windows Subsystem for Linux (WSL).

    Returns
    -------
    bool
        True if WSL detected; False otherwise.
    """
    try:
        if "WSL" in platform.uname().release:
            return True
        if os.path.exists("/proc/version"):
            with open("/proc/version", "r", encoding="utf-8") as f:
                if "Microsoft" in f.read():
                    return True
        return False
    except Exception:
        # Be conservative if detection fails.
        return False


def pro_diagnostics() -> Dict[str, object]:
    """Produce a full diagnostics report dictionary for higher-level UIs.

    Returns
    -------
    dict
        {
            "env": <analyze_env() dict>,
            "health": {
                "flow": <str>,
                "score": <int>,
                "required": <list of ToolCheck>,
                "optional": <list of ToolCheck>,
            },
            "tips": <List[str]>,
        }

    Notes
    -----
    - This function only assembles data; it doesn't print or mutate state.
    - Virtualenv tip is disabled (kept as comments for future use).
    """
    env = analyze_env()
    flow, score, required, optional = compute_health()

    tips: List[str] = []

    if score < 100:
        tips.append(
            "Not all required tools installed. Run `saxoflow diagnose repair` "
            "or `saxoflow diagnose repair-interactive`."
        )

    # if not env.get("venv"):
    #     tips.append(
    #         "Virtual environment not active. Run `source .venv/bin/activate`."
    #     )

    # PATH duplicates
    dup_list = env.get("path_duplicates") or []
    if isinstance(dup_list, list) and dup_list:
        for dup_path, tools in dup_list:
            if tools:
                tips.append(
                    "Duplicate PATH entry: "
                    f"{dup_path} (used by: {', '.join(tools)}). "
                    "Remove for cleaner environment."
                )
            else:
                tips.append(
                    f"Duplicate PATH entry: {dup_path}. "
                    "Remove for cleaner environment."
                )
        tips.append(
            "To clean PATH duplicates (advanced): "
            r"export PATH=$(echo $PATH | tr ':' '\n' | awk '!x[$0]++' | paste -sd:)"
        )

    # Bins not in PATH
    bins_missing = env.get("bins_missing_in_path") or []
    if isinstance(bins_missing, list) and bins_missing:
        for tb, tool in bins_missing:
            if tool:
                tips.append(
                    f"Tool bin not in PATH: {tb} (needed for: {tool}). "
                    "Add this to your PATH."
                )
            else:
                tips.append(
                    f"Tool bin not in PATH: {tb}. "
                    "Add this to your PATH for best results."
                )

    if env.get("wsl"):
        tips.append(
            "Detected WSL environment. Make sure Windows/WSL paths are set up "
            "correctly for tools and VSCode."
        )

    return {
        "env": env,
        "health": {
            "flow": flow,
            "score": score,
            "required": required,
            "optional": optional,
        },
        "tips": tips,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _noop_match():
    """Return a dummy regex match object with an empty ``group(0)``."""
    return re.match(r".*", "")
