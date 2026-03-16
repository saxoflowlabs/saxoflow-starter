# saxoflow/teach/command_map.py
"""
Command translation layer: maps native EDA tool commands to their
SaxoFlow wrapper equivalents using :file:`saxoflow/tools/registry.yaml`.

Design rules
------------
- Read-only at runtime: the YAML is parsed once and cached.
- Callers receive a :class:`ResolvedCommand` with the string that should
  actually be executed and a flag indicating whether it is a wrapper.
- The ``shutil.which`` check is used to test wrapper availability; it
  can be overridden in tests via the ``_availability_checker`` seam.

Python: 3.9+
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Optional

import yaml

from saxoflow.teach.session import CommandDef

__all__ = ["resolve_command", "ResolvedCommand", "ToolEntry"]

logger = logging.getLogger("saxoflow.teach.command_map")

_REGISTRY_PATH = Path(__file__).parent.parent / "tools" / "registry.yaml"

# Seam for unit tests: replace with a lambda that returns True/False.
_availability_checker: Callable[[str], bool] = lambda cmd: shutil.which(cmd.split()[0]) is not None


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolEntry:
    """One entry from ``registry.yaml``.

    Attributes
    ----------
    key:
        Snake-case tool identifier, e.g. ``"iverilog"``.
    native:
        Bare native command, e.g. ``"iverilog"``.
    saxoflow_cmd:
        Equivalent SaxoFlow CLI invocation, e.g. ``"saxoflow sim iverilog"``.
    check_cmd:
        Command used to probe installation, e.g. ``"iverilog -V"``.
    description:
        One-line human description.
    """

    key: str
    native: str
    saxoflow_cmd: str
    check_cmd: str
    description: str


@dataclass(frozen=True)
class ResolvedCommand:
    """Result of :func:`resolve_command`.

    Attributes
    ----------
    command_str:
        The command string that should be executed.
    is_wrapper:
        ``True`` if the SaxoFlow wrapper was selected; ``False`` for native.
    is_available:
        ``True`` if the resolved command's executable is present on PATH.
    tool_entry:
        The matching :class:`ToolEntry` if found; ``None`` if no match.
    """

    command_str: str
    is_wrapper: bool
    is_available: bool
    tool_entry: Optional[ToolEntry]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_command(cmd_def: CommandDef) -> ResolvedCommand:
    """Translate a :class:`CommandDef` to the command string to execute.

    Decision logic:

    1. If ``cmd_def.preferred`` is set **and** ``cmd_def.use_preferred_if_available``
       is ``True`` **and** the preferred command is available on PATH → use preferred.
    2. If a SaxoFlow wrapper exists in the registry for the native command
       **and** the wrapper is available → use the wrapper.
    3. Otherwise fall back to ``cmd_def.native``.

    Parameters
    ----------
    cmd_def:
        The :class:`CommandDef` from a lesson step.

    Returns
    -------
    ResolvedCommand
        The resolved command string plus metadata.
    """
    registry = _load_registry()

    # -- Explicit preferred override ------------------------------------------
    if cmd_def.preferred and cmd_def.use_preferred_if_available:
        pref_available = _availability_checker(cmd_def.preferred)
        if pref_available:
            return ResolvedCommand(
                command_str=cmd_def.preferred,
                is_wrapper=True,
                is_available=True,
                tool_entry=_find_entry(registry, cmd_def.native),
            )

    # -- Look up native command in registry -----------------------------------
    entry = _find_entry(registry, cmd_def.native)
    if entry is not None:
        # Only substitute the SaxoFlow wrapper when the command is a *bare*
        # invocation (no extra flags or arguments), because wrappers like
        # ``saxoflow sim verilator`` do not accept the full Verilator CLI.
        # Commands such as ``verilator --version``, ``verilator --binary -j 0
        # --trace …``, or shell pipelines must always run natively.
        is_bare_invocation = cmd_def.native.strip() == entry.native
        if is_bare_invocation:
            wrapper_available = _availability_checker(entry.saxoflow_cmd)
            if wrapper_available:
                return ResolvedCommand(
                    command_str=entry.saxoflow_cmd,
                    is_wrapper=True,
                    is_available=True,
                    tool_entry=entry,
                )

    # -- Fall back to native ---------------------------------------------------
    native_available = _availability_checker(cmd_def.native)
    return ResolvedCommand(
        command_str=cmd_def.native,
        is_wrapper=False,
        is_available=native_available,
        tool_entry=entry,
    )


def get_all_tool_entries() -> Dict[str, ToolEntry]:
    """Return a ``{key: ToolEntry}`` dict for all registered tools."""
    return dict(_load_registry())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_registry() -> Dict[str, ToolEntry]:
    """Parse ``registry.yaml`` once and cache the result."""
    if not _REGISTRY_PATH.exists():
        logger.warning("Tool registry not found at: %s", _REGISTRY_PATH)
        return {}

    try:
        raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        logger.error("Failed to parse tool registry: %s", exc)
        return {}

    result: Dict[str, ToolEntry] = {}
    for item in raw.get("tools", []):
        key = item.get("key", "")
        if not key:
            continue
        result[key] = ToolEntry(
            key=key,
            native=str(item.get("native", "")),
            saxoflow_cmd=str(item.get("saxoflow_cmd", "")),
            check_cmd=str(item.get("check_cmd", "")),
            description=str(item.get("description", "")),
        )
    return result


def _find_entry(
    registry: Dict[str, ToolEntry], native_cmd: str
) -> Optional[ToolEntry]:
    """Find the registry entry whose ``native`` field matches *native_cmd*.

    Matches on the first token of *native_cmd* to handle commands like
    ``"iverilog -g2012 -o out.vcd tb.v"``.
    """
    first_token = native_cmd.strip().split()[0] if native_cmd.strip() else ""
    for entry in registry.values():
        if entry.native == first_token or entry.key == first_token:
            return entry
    return None
