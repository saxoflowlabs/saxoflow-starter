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
        ("FORMAL_SOLVER_TOOLS", P.FORMAL_SOLVER_TOOLS),
        ("FORMAL_SOLVER_TOOLS_TIER2", P.FORMAL_SOLVER_TOOLS_TIER2),
        ("FPGA_TOOLS", P.FPGA_TOOLS),
        ("ASIC_TOOLS", P.ASIC_TOOLS),
        ("BASE_TOOLS", P.BASE_TOOLS),
        ("SW_TOOLS", P.SW_TOOLS),
        ("VHDL_CROSSCHECK_TOOLS", P.VHDL_CROSSCHECK_TOOLS),
        ("IPXACT_EDU_TOOLS", P.IPXACT_EDU_TOOLS),
        ("IDE_TOOLS", P.IDE_TOOLS),
    ]
    for name, group in groups:
        assert isinstance(group, list), f"{name} must be a list"
        _assert_list_of_unique_str(group)


def test_all_tool_groups_mapping_matches_constants():
    """ALL_TOOL_GROUPS must expose exactly the documented keys and values."""
    expected_keys = {
        "simulation",
        "formal",
        "formal-solvers",
        "formal-solvers-tier2",
        "fpga",
        "asic",
        "base",
        "software",
        "ide",
        "lint",
        "ethz_ic_design",
        "advanced-flow",
        "vhdl-crosscheck",
        "ipxact-edu",
        "orchestration",
        "research-platform",
        "research-arch",
        "research-memory",
    }
    assert set(P.ALL_TOOL_GROUPS.keys()) == expected_keys

    expected_map = {
        "simulation": P.SIM_TOOLS,
        "formal": P.FORMAL_TOOLS,
        "formal-solvers": P.FORMAL_SOLVER_TOOLS,
        "formal-solvers-tier2": P.FORMAL_SOLVER_TOOLS_TIER2,
        "fpga": P.FPGA_TOOLS,
        "asic": P.ASIC_TOOLS,
        "base": P.BASE_TOOLS,
        "software": P.SW_TOOLS,
        "ide": P.IDE_TOOLS,
        "lint": P.LINT_TOOLS,
        "ethz_ic_design": P.ETHZ_IC_DESIGN_TOOLS,
        "advanced-flow": P.ADVANCED_FLOW_TOOLS,
        "vhdl-crosscheck": P.VHDL_CROSSCHECK_TOOLS,
        "ipxact-edu": P.IPXACT_EDU_TOOLS,
        "orchestration": P.ORCHESTRATION_TOOLS,
        "research-platform": P.RESEARCH_PLATFORM_TOOLS,
        "research-arch": P.RESEARCH_ARCH_TOOLS,
        "research-memory": P.RESEARCH_MEMORY_TOOLS,
    }
    for k, v in expected_map.items():
        assert P.ALL_TOOL_GROUPS[k] == v, f"Group {k} must equal constant list"


def test_presets_expand_to_expected_concatenation():
    """Each preset equals the exact concatenation described in the module."""
    expected_minimal = P.IDE_TOOLS + ["iverilog", "gtkwave"]
    expected_fpga = P.IDE_TOOLS + ["verilator"] + P.FPGA_TOOLS + P.BASE_TOOLS
    expected_asic = P.IDE_TOOLS + ["verilator"] + P.ASIC_TOOLS + P.BASE_TOOLS
    expected_formal = P.IDE_TOOLS + ["yosys"] + P.FORMAL_TOOLS
    expected_formal_plus = P.IDE_TOOLS + ["yosys"] + P.FORMAL_TOOLS + P.FORMAL_SOLVER_TOOLS
    expected_full = (
        P.IDE_TOOLS
        + P.SIM_TOOLS
        + P.FORMAL_TOOLS
        + P.FPGA_TOOLS
        + P.ASIC_TOOLS
        + P.BASE_TOOLS
        + P.SW_TOOLS
    )
    expected_advanced_flow = P.IDE_TOOLS + P.BASE_TOOLS + ["fusesoc", "bender"] + P.ADVANCED_FLOW_TOOLS
    expected_vhdl_crosscheck = P.IDE_TOOLS + ["gtkwave", "ghdl"] + P.VHDL_CROSSCHECK_TOOLS
    expected_ipxact_edu = P.IDE_TOOLS + P.IPXACT_EDU_TOOLS
    expected_orchestration = P.IDE_TOOLS + P.BASE_TOOLS + P.ORCHESTRATION_TOOLS
    expected_research_platform = P.IDE_TOOLS + P.SW_TOOLS + P.RESEARCH_PLATFORM_TOOLS
    expected_research_arch = P.IDE_TOOLS + P.SW_TOOLS + P.RESEARCH_ARCH_TOOLS
    expected_research_memory = P.IDE_TOOLS + P.ASIC_TOOLS + P.RESEARCH_MEMORY_TOOLS

    assert P.PRESETS["minimal"] == expected_minimal
    assert P.PRESETS["fpga"] == expected_fpga
    assert P.PRESETS["asic"] == expected_asic
    assert P.PRESETS["formal"] == expected_formal
    assert P.PRESETS["formal-plus"] == expected_formal_plus
    assert P.PRESETS["full"] == expected_full
    assert P.PRESETS["advanced-flow"] == expected_advanced_flow
    assert P.PRESETS["vhdl-crosscheck"] == expected_vhdl_crosscheck
    assert P.PRESETS["ipxact-edu"] == expected_ipxact_edu
    assert P.PRESETS["orchestration"] == expected_orchestration
    assert P.PRESETS["research-platform"] == expected_research_platform
    assert P.PRESETS["research-arch"] == expected_research_arch
    assert P.PRESETS["research-memory"] == expected_research_memory


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

        if name not in {"full", "full-with-quality"}:
            # Non-full presets should remain duplicate-free (given current design)
            assert not has_dupes, f"{name} unexpectedly has duplicates"
        else:
            # Full-stack presets are concatenations of multiple groups; duplicates
            # may occur when a tool appears in more than one group.
            dup_set = {t for t in tools if tools.count(t) > 1}
            overlap = (
                set(P.SIM_TOOLS) & set(P.FORMAL_TOOLS) |
                set(P.SIM_TOOLS) & set(P.FPGA_TOOLS) |
                set(P.SIM_TOOLS) & set(P.ASIC_TOOLS) |
                set(P.SIM_TOOLS) & set(P.BASE_TOOLS) |
                set(P.SIM_TOOLS) & set(P.SW_TOOLS) |
                set(P.SIM_TOOLS) & set(P.LINT_TOOLS) |
                set(P.FORMAL_TOOLS) & set(P.FPGA_TOOLS) |
                set(P.FORMAL_TOOLS) & set(P.ASIC_TOOLS) |
                set(P.FORMAL_TOOLS) & set(P.BASE_TOOLS) |
                set(P.FORMAL_TOOLS) & set(P.SW_TOOLS) |
                set(P.FORMAL_TOOLS) & set(P.LINT_TOOLS) |
                set(P.FPGA_TOOLS) & set(P.ASIC_TOOLS) |
                set(P.FPGA_TOOLS) & set(P.BASE_TOOLS) |
                set(P.FPGA_TOOLS) & set(P.SW_TOOLS) |
                set(P.FPGA_TOOLS) & set(P.LINT_TOOLS) |
                set(P.ASIC_TOOLS) & set(P.BASE_TOOLS) |
                set(P.ASIC_TOOLS) & set(P.SW_TOOLS) |
                set(P.ASIC_TOOLS) & set(P.LINT_TOOLS) |
                set(P.BASE_TOOLS) & set(P.SW_TOOLS) |
                set(P.BASE_TOOLS) & set(P.LINT_TOOLS) |
                set(P.SW_TOOLS) & set(P.LINT_TOOLS)
            )
            assert dup_set == overlap, (
                f"'{name}' duplicates must match cross-group overlap. "
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


def test_edalize_present_in_advanced_flow_group_and_preset():
    assert "edalize" in P.ADVANCED_FLOW_TOOLS
    assert "advanced-flow" in P.PRESETS
    assert "edalize" in P.PRESETS["advanced-flow"]


def test_nvc_present_in_vhdl_crosscheck_group_and_preset():
    assert "nvc" in P.VHDL_CROSSCHECK_TOOLS
    assert "vhdl-crosscheck" in P.PRESETS
    assert "nvc" in P.PRESETS["vhdl-crosscheck"]


def test_kactus2_present_in_ipxact_edu_group_and_preset():
    assert "kactus2" in P.IPXACT_EDU_TOOLS
    assert "ipxact-edu" in P.PRESETS
    assert "kactus2" in P.PRESETS["ipxact-edu"]


def test_phase3_phase4_groups_present_in_presets():
    assert "siliconcompiler" in P.ORCHESTRATION_TOOLS
    assert "renode" in P.RESEARCH_PLATFORM_TOOLS
    assert "gem5" in P.RESEARCH_ARCH_TOOLS
    assert "riscv-vp-plusplus" in P.RESEARCH_ARCH_TOOLS
    assert "openram" in P.RESEARCH_MEMORY_TOOLS

    assert "siliconcompiler" in P.PRESETS["orchestration"]
    assert "renode" in P.PRESETS["research-platform"]
    assert "gem5" in P.PRESETS["research-arch"]
    assert "riscv-vp-plusplus" in P.PRESETS["research-arch"]
    assert "openram" in P.PRESETS["research-memory"]


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


# ---------------------------------------------------------------------------
# Second-batch tool assertions
# ---------------------------------------------------------------------------

def test_covered_in_sim_tools():
    assert "covered" in P.SIM_TOOLS


def test_sv2v_in_base_tools():
    assert "sv2v" in P.BASE_TOOLS


def test_rggen_in_fpga_and_asic_tools():
    assert "rggen" in P.FPGA_TOOLS
    assert "rggen" in P.ASIC_TOOLS


def test_sw_tools_contains_riscv_and_spike():
    assert "riscv-toolchain" in P.SW_TOOLS
    assert "spike" in P.SW_TOOLS
    assert "qemu-system-riscv64" in P.SW_TOOLS
    assert "openocd" in P.SW_TOOLS
    _assert_list_of_unique_str(P.SW_TOOLS)


def test_sw_tools_in_all_tool_groups():
    assert "software" in P.ALL_TOOL_GROUPS
    assert P.ALL_TOOL_GROUPS["software"] == P.SW_TOOLS


def test_sw_tools_in_full_preset():
    full = P.PRESETS["full"]
    assert "riscv-toolchain" in full
    assert "spike" in full
    assert "qemu-system-riscv64" in full
    assert "openocd" in full


def test_software_bringup_preset_contains_optional_riscv_pk():
    sb = P.PRESETS["software-bringup"]
    assert "riscv-toolchain" in sb
    assert "spike" in sb
    assert "qemu-system-riscv64" in sb
    assert "openocd" in sb
    assert "riscv-pk" in sb


def test_waveform_ux_preset_contains_surfer_optional_tool():
    """waveform-ux preset should include IDE tools, GTKWave baseline, and surfer."""
    wx = P.PRESETS["waveform-ux"]
    assert wx[: len(P.IDE_TOOLS)] == P.IDE_TOOLS
    assert "gtkwave" in wx
    assert "surfer" in wx
    assert wx == P.IDE_TOOLS + ["gtkwave"] + P.WAVEFORM_UX_TOOLS
