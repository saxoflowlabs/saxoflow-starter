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
    expected_keys = {"simulation", "formal", "fpga", "asic", "base", "ide", "ethz_ic_design"}
    assert set(P.ALL_TOOL_GROUPS.keys()) == expected_keys

    expected_map = {
        "simulation": P.SIM_TOOLS,
        "formal": P.FORMAL_TOOLS,
        "fpga": P.FPGA_TOOLS,
        "asic": P.ASIC_TOOLS,
        "base": P.BASE_TOOLS,
        "ide": P.IDE_TOOLS,
        "ethz_ic_design": P.ETHZ_IC_DESIGN_TOOLS,
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


def test_presets_ide_first_and_dup_policy():
    """
    Presets must start with IDE tools; duplicates are only allowed when they
    arise from cross-group overlap (e.g., a tool present in multiple groups).

    Exception: 'ethz_ic_design_tools' is a tool-only preset (no IDE entry),
    intentionally starting with verilator to match the VLSI2 course flow.
    """
    # Presets that intentionally do NOT start with IDE_TOOLS
    IDE_EXEMPT = {"ethz_ic_design_tools"}

    for name, tools in P.PRESETS.items():
        if name in IDE_EXEMPT:
            # Just verify it's a non-empty list of unique strings
            _assert_list_of_unique_str(tools)
            continue

        # IDE first: all other presets must declare IDE_TOOLS at the head
        assert tools[: len(P.IDE_TOOLS)] == P.IDE_TOOLS

        # Compute duplicates (preserving order uniqueness set)
        dedup = list(dict.fromkeys(tools))
        has_dupes = len(dedup) != len(tools)

        if name not in {"full"}:
            # Non-full presets should remain duplicate-free (given current design)
            assert not has_dupes, f"{name} unexpectedly has duplicates"
        else:
            # 'full' is a concatenation of all groups; duplicates may occur when
            # a tool appears in multiple groups. Validate duplicates are exactly
            # the intersection of group sets (currently 'bender').
            dup_set = {t for t in tools if tools.count(t) > 1}
            overlap = set(P.FPGA_TOOLS) & set(P.ASIC_TOOLS)
            assert dup_set == overlap, (
                f"'full' duplicates must match cross-group overlap. "
                f"Found {dup_set}, expected {overlap}"
            )


def test_deprecated_agentic_tools_absent():
    """Ensure 'agentic-ai' is not present per the current release notes."""
    assert "agentic-ai" not in P.ALL_TOOL_GROUPS
    assert "agentic-ai" not in P.PRESETS


def test_bender_present_in_fpga_and_asic_groups():
    assert "bender" in P.FPGA_TOOLS
    assert "bender" in P.ASIC_TOOLS


def test_fusesoc_present_in_fpga_and_asic_groups():
    assert "fusesoc" in P.FPGA_TOOLS
    assert "fusesoc" in P.ASIC_TOOLS


def test_opensta_present_in_asic_group():
    assert "opensta" in P.ASIC_TOOLS


def test_surelog_present_in_base_group():
    assert "surelog" in P.BASE_TOOLS


def test_ghdl_present_in_sim_group():
    assert "ghdl" in P.SIM_TOOLS


def test_cocotb_present_in_sim_group():
    assert "cocotb" in P.SIM_TOOLS


def test_full_preset_duplicates_are_from_group_overlap_only():
    tools = P.PRESETS["full"]
    dup_set = {t for t in tools if tools.count(t) > 1}
    # Compute all cross-group overlaps that could cause duplicates
    overlaps = (
        set(P.SIM_TOOLS) & set(P.FORMAL_TOOLS) |
        set(P.SIM_TOOLS) & set(P.FPGA_TOOLS)   |
        set(P.SIM_TOOLS) & set(P.ASIC_TOOLS)   |
        set(P.SIM_TOOLS) & set(P.BASE_TOOLS)   |
        set(P.FORMAL_TOOLS) & set(P.FPGA_TOOLS)|
        set(P.FORMAL_TOOLS) & set(P.ASIC_TOOLS)|
        set(P.FORMAL_TOOLS) & set(P.BASE_TOOLS)|
        set(P.FPGA_TOOLS) & set(P.ASIC_TOOLS)  |
        set(P.FPGA_TOOLS) & set(P.BASE_TOOLS)  |
        set(P.ASIC_TOOLS) & set(P.BASE_TOOLS)
    )
    assert dup_set <= overlaps


def test_ethz_ic_design_tools_preset():
    """ethz_ic_design_tools must contain the four open-source tools for the VLSI2 flow."""
    required = {"verilator", "yosys", "openroad", "klayout", "bender"}
    tools = P.PRESETS["ethz_ic_design_tools"]
    assert set(tools) == required, (
        f"PRESETS['ethz_ic_design_tools'] must contain exactly {required}, got {set(tools)}"
    )
    # Must equal the ETHZ_IC_DESIGN_TOOLS constant (single source of truth)
    assert tools == P.ETHZ_IC_DESIGN_TOOLS
    # No duplicates
    _assert_list_of_unique_str(tools)
