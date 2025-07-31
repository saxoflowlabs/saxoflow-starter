"""
Tests for saxoflow.tools.definitions module.

This module contains simple data structures enumerating the toolchains
and descriptions used throughout the SaxoFlow CLI.  The tests below
verify that key groups and dictionaries are well‐formed and contain
expected entries.  These checks ensure that downstream code relying on
these constants (e.g. installer presets or diagnose routines) does not
break when editing the definitions.
"""

import importlib


def test_tool_groups_have_expected_members():
    """The high level tool groups should include specific known tools."""
    defs = importlib.import_module("saxoflow.tools.definitions")
    # Basic sanity: groups are lists and contain at least one element
    assert isinstance(defs.SIM_TOOLS, list) and defs.SIM_TOOLS, "SIM_TOOLS must be a non‑empty list"
    assert isinstance(defs.FORMAL_TOOLS, list) and defs.FORMAL_TOOLS, "FORMAL_TOOLS must be a non‑empty list"
    assert isinstance(defs.FPGA_TOOLS, list) and defs.FPGA_TOOLS, "FPGA_TOOLS must be a non‑empty list"
    assert isinstance(defs.ASIC_TOOLS, list) and defs.ASIC_TOOLS, "ASIC_TOOLS must be a non‑empty list"
    assert isinstance(defs.BASE_TOOLS, list) and defs.BASE_TOOLS, "BASE_TOOLS must be a non‑empty list"
    assert isinstance(defs.IDE_TOOLS, list) and defs.IDE_TOOLS, "IDE_TOOLS must be a non‑empty list"

    # Check for presence of some canonical tools
    assert "yosys" in defs.BASE_TOOLS
    assert "iverilog" in defs.SIM_TOOLS
    assert "symbiyosys" in defs.FORMAL_TOOLS
    assert "nextpnr" in defs.FPGA_TOOLS
    assert "openroad" in defs.ASIC_TOOLS
    assert "vscode" in defs.IDE_TOOLS


def test_tool_descriptions_map_to_categories():
    """TOOL_DESCRIPTIONS should generate a readable label for each tool."""
    defs = importlib.import_module("saxoflow.tools.definitions")
    # Pick a few tools to check description formatting
    desc = defs.TOOL_DESCRIPTIONS["verilator"]
    assert desc.startswith("[Simulation]") or desc.startswith("[simulation]"), desc
    desc = defs.TOOL_DESCRIPTIONS["openroad"]
    assert desc.startswith("[Asic]"), desc


def test_min_tool_versions_non_empty():
    """Ensure that minimum tool versions are declared for key tools."""
    defs = importlib.import_module("saxoflow.tools.definitions")
    # Check a handful of known tools appear in the version map
    for tool in ["yosys", "iverilog", "verilator", "gtkwave"]:
        assert tool in defs.MIN_TOOL_VERSIONS, f"{tool} missing from MIN_TOOL_VERSIONS"
        version = defs.MIN_TOOL_VERSIONS[tool]
        # Version strings should be non‑empty strings containing at least one dot
        assert isinstance(version, str) and "." in version