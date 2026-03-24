"""Legacy command resolution and semantic completion helpers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from saxoflow.command_registry import (
    get_bare_saxoflow_compat_commands,
    get_legacy_alias_hints,
)


@dataclass(frozen=True)
class ResolutionResult:
    """Resolution output for a user-entered command line."""

    input_command: str
    is_legacy: bool
    canonical_hint: Optional[str] = None


class CommandResolver:
    """Resolves legacy command hints and provides semantic completions."""

    def __init__(self, alias_hints: Optional[Dict[str, str]] = None) -> None:
        self._alias_hints = alias_hints or get_legacy_alias_hints()
        self._ordered_legacy_keys = sorted(self._alias_hints.keys(), key=len, reverse=True)
        self._semantic_catalog = {
            "saxoflow flow run": [
                "rtl_to_sim",
                "rtl_to_formal",
                "rtl_to_netlist",
                "rtl_to_gds_openroad",
                "rtl_to_fpga_bitstream",
                "hw_sw_codesign_bringup",
            ],
            "saxoflow action run": [
                "sim.icarus",
                "sim.verilator.build",
                "sim.verilator.run",
                "wave.gtkwave",
                "formal.symbiyosys",
                "synth.yosys",
            ],
            "saxoflow tool op run": [
                "compile",
                "run",
                "report",
                "lint",
                "synth",
                "place-route",
                "timing",
                "drc",
                "lvs",
            ],
            "saxoflow ai": [
                "plan",
                "run",
                "resume",
                "explain",
                "review",
            ],
            "saxoflow workspace": [
                "init",
                "validate",
                "migrate",
                "lock",
                "clean",
            ],
            "saxoflow teach": [
                "pack",
                "import",
                "build",
                "validate",
                "preview",
                "run",
                "session",
            ],
            "saxoflow env": [
                "init",
                "audit",
                "show",
                "repair",
                "enter",
            ],
            "saxoflow tool": [
                "list",
                "install",
                "use",
                "lock",
                "resolve",
                "audit",
                "bundle",
                "op",
            ],
        }

    @property
    def bare_saxoflow_commands(self) -> Sequence[str]:
        """First-token compatibility commands for TUI auto-prefix behavior."""
        return tuple(get_bare_saxoflow_compat_commands())

    def resolve_legacy_command(self, command: str) -> ResolutionResult:
        """Resolve a potential legacy command to a canonical migration hint."""
        normalized = " ".join((command or "").strip().split())
        if not normalized:
            return ResolutionResult(input_command=command, is_legacy=False)

        for legacy in self._ordered_legacy_keys:
            if normalized == legacy or normalized.startswith(legacy + " "):
                return ResolutionResult(
                    input_command=command,
                    is_legacy=True,
                    canonical_hint=self._alias_hints[legacy],
                )

        return ResolutionResult(input_command=command, is_legacy=False)

    def semantic_suggestions(self, text_before_cursor: str) -> List[str]:
        """Return semantic (non-path) completion suggestions for a command line."""
        line = (text_before_cursor or "").rstrip()
        if not line:
            return []

        try:
            parts = shlex.split(line)
        except ValueError:
            return []

        if not parts:
            return []

        line_ends_with_space = text_before_cursor.endswith(" ")

        # For single token inputs, fuzzy completion already handles suggestions.
        if len(parts) == 1 and not line_ends_with_space:
            return []

        prefix_parts = parts[:] if line_ends_with_space else parts[:-1]
        fragment = "" if line_ends_with_space else parts[-1]
        prefix = " ".join(prefix_parts)

        for root, choices in self._semantic_catalog.items():
            if prefix == root:
                if not fragment:
                    return choices
                lowered = fragment.lower()
                return [choice for choice in choices if choice.lower().startswith(lowered)]

        return []
