"""Unit tests for saxoflow.installer.presets.

These tests are intentionally hermetic and assert:
- Tool groups are lists of strings with stable order and no duplicates.
- ALL_TOOL_GROUPS maps names to the exact group constants.
- PRESETS expand to the documented concatenation in a deterministic order.
- Deprecated/disabled "agentic-ai" is not present (per release notes).
"""

from __future__ import annotations

from typing import Iterable, List

import saxoflow.installer.presets as P


def _assert_list_of_unique_str(items: Iterable[str]) -> None:
    """Helper: every item is str, and no duplicates while preserving order."""
    seen: List[str] = []
    for x in items:
        assert isinstance(x, str)
        assert x not in seen, "duplicate item would break deterministic ordering"
        seen.append(x)


def test_tool_groups_are_lists_of_str_and_unique():
    """Each exported group must be a list[str] with no duplicates, stable order."""
    groups = [
        ("SIM_TOOLS", P.SIM_TOOLS),
        ("FORMAL_TOOLS", P.FORMAL_TOOLS),
        ("FPGA_TOOLS", P.FPGA_TOOLS),
        ("ASIC_TOOLS", P.ASIC_TOOLS),
        ("BASE_TOOLS", P.BASE_TOOLS),
        ("IDE_TOOLS", P.IDE_TOOLS),
    ]
    for name, group in groups:
        assert isinstance(group, list), f"{name} must be a list"
        _assert_list_of_unique_str(group)


def test_all_tool_groups_mapping_matches_constants():
    """ALL_TOOL_GROUPS must expose exactly the documented keys and values."""
    expected_keys = {"simulation", "formal", "fpga", "asic", "base", "ide"}
    assert set(P.ALL_TOOL_GROUPS.keys()) == expected_keys

    expected_map = {
        "simulation": P.SIM_TOOLS,
        "formal": P.FORMAL_TOOLS,
        "fpga": P.FPGA_TOOLS,
        "asic": P.ASIC_TOOLS,
        "base": P.BASE_TOOLS,
        "ide": P.IDE_TOOLS,
    }
    for k, v in expected_map.items():
        assert P.ALL_TOOL_GROUPS[k] == v, f"Group {k} must equal constant list"


def test_presets_expand_to_expected_concatenation():
    """Each preset equals the exact concatenation described in the module."""
    expected_minimal = P.IDE_TOOLS + ["iverilog", "gtkwave"]
    expected_fpga = P.IDE_TOOLS + ["verilator"] + P.FPGA_TOOLS + P.BASE_TOOLS
    expected_asic = P.IDE_TOOLS + ["verilator"] + P.ASIC_TOOLS + P.BASE_TOOLS
    expected_formal = P.IDE_TOOLS + ["yosys"] + P.FORMAL_TOOLS
    expected_full = (
        P.IDE_TOOLS
        + P.SIM_TOOLS
        + P.FORMAL_TOOLS
        + P.FPGA_TOOLS
        + P.ASIC_TOOLS
        + P.BASE_TOOLS
    )

    assert P.PRESETS["minimal"] == expected_minimal
    assert P.PRESETS["fpga"] == expected_fpga
    assert P.PRESETS["asic"] == expected_asic
    assert P.PRESETS["formal"] == expected_formal
    assert P.PRESETS["full"] == expected_full


def test_presets_have_no_duplicates_and_ide_is_first():
    """Presets should be unique lists with IDE first to preserve UX order."""
    for name, tools in P.PRESETS.items():
        # Uniqueness while preserving order
        assert len(tools) == len(dict.fromkeys(tools)), f"{name} has duplicates"
        # IDE first: all presets declare IDE_TOOLS at the head
        assert tools[: len(P.IDE_TOOLS)] == P.IDE_TOOLS


def test_deprecated_agentic_tools_absent():
    """Ensure 'agentic-ai' is not present per the current release notes."""
    assert "agentic-ai" not in P.ALL_TOOL_GROUPS
    assert "agentic-ai" not in P.PRESETS
