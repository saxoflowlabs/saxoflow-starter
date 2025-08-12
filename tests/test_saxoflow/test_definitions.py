"""
Unit tests for `saxoflow.tools.definitions`.

These tests are hermetic and validate:
- Re-exported tool groups (from presets) exist and are sane.
- Aggregate `ALL_TOOLS` preserves deterministic order.
- `APT_TOOLS` and `SCRIPT_TOOLS` are disjoint and non-empty.
- `TOOLS` is well-formed and `TOOL_DESCRIPTIONS` formatting is correct.
- `MIN_TOOL_VERSIONS` contains key tools with plausible version strings.
- `__all__` exports are present and of expected shapes.

No network / file IO / subprocess is performed.
"""

from __future__ import annotations

import importlib
from typing import Dict, Iterable


def _reload_defs():
    """Helper to import (or reload) the module under test."""
    mod = importlib.import_module("saxoflow.tools.definitions")
    return importlib.reload(mod)


def test_group_reexports_sanity() -> None:
    """Ensure re-exported groups exist, are lists, and are non-empty."""
    defs = _reload_defs()
    for name in (
        "SIM_TOOLS",
        "FORMAL_TOOLS",
        "FPGA_TOOLS",
        "ASIC_TOOLS",
        "BASE_TOOLS",
        "IDE_TOOLS",
    ):
        val = getattr(defs, name)
        assert isinstance(val, list) and val, f"{name} must be a non-empty list"

    # Check for presence of canonical tools in expected groups
    assert "iverilog" in defs.SIM_TOOLS
    assert "symbiyosys" in defs.FORMAL_TOOLS
    assert "nextpnr" in defs.FPGA_TOOLS
    assert "openroad" in defs.ASIC_TOOLS
    assert "gtkwave" in defs.BASE_TOOLS
    assert "vscode" in defs.IDE_TOOLS


def test_all_tools_is_deterministic_concat() -> None:
    """`ALL_TOOLS` must equal the concatenation of groups in the documented order."""
    defs = _reload_defs()
    expected = (
        defs.SIM_TOOLS
        + defs.FORMAL_TOOLS
        + defs.FPGA_TOOLS
        + defs.ASIC_TOOLS
        + defs.BASE_TOOLS
        + defs.IDE_TOOLS
    )
    assert defs.ALL_TOOLS == expected, "ALL_TOOLS must be deterministic and ordered"


def test_apt_and_script_tools_non_overlapping_and_non_empty() -> None:
    """
    APT-managed and script-managed tool sets should be disjoint,
    and should not be empty.
    """
    defs = _reload_defs()
    apt = set(defs.APT_TOOLS)
    scripts = set(defs.SCRIPT_TOOLS.keys())
    assert apt, "APT_TOOLS is unexpectedly empty"
    assert scripts, "SCRIPT_TOOLS is unexpectedly empty"
    assert apt.isdisjoint(scripts), "APT_TOOLS and SCRIPT_TOOLS must be disjoint"


def test_script_recipe_paths_shape() -> None:
    """Each script recipe should look like a shell script path under scripts/recipes/."""
    defs = _reload_defs()
    for tool, path in defs.SCRIPT_TOOLS.items():
        assert isinstance(path, str), f"{tool} path must be a string"
        assert path.startswith("scripts/recipes/"), f"{tool} path has unexpected prefix: {path}"
        assert path.endswith(".sh"), f"{tool} recipe should be a .sh script: {path}"


def test_tool_descriptions_format_and_coverage() -> None:
    """
    `TOOL_DESCRIPTIONS` should cover every tool in `TOOLS` and have the
    "[Category] description" prefix with capitalized category.
    """
    defs = _reload_defs()
    # Coverage
    expected_keys = {t for grp in defs.TOOLS.values() for t in grp.keys()}
    assert set(defs.TOOL_DESCRIPTIONS.keys()) == expected_keys

    # Format: "[Category] ..." where Category is capitalized
    for category, mapping in defs.TOOLS.items():
        expected_prefix = f"[{category.capitalize()}]"
        for tool, desc in mapping.items():
            label = defs.TOOL_DESCRIPTIONS[tool]
            assert isinstance(label, str) and label, f"Empty label for {tool}"
            assert label.startswith(expected_prefix), (
                f"Label for {tool!r} should start with {expected_prefix!r}, got {label!r}"
            )
            # Ensure the raw description text from TOOLS appears in the label (preserving content).
            assert desc in label, f"Raw description for {tool!r} missing in label"


def test_described_tools_exist_in_known_sets() -> None:
    """
    Every described tool must be represented somewhere in either:
    - the grouped `ALL_TOOLS`, or
    - the install maps (APT_TOOLS or SCRIPT_TOOLS).
    """
    defs = _reload_defs()
    described = {t for grp in defs.TOOLS.values() for t in grp.keys()}
    known = set(defs.ALL_TOOLS) | set(defs.APT_TOOLS) | set(defs.SCRIPT_TOOLS.keys())
    missing = sorted(described - known)
    assert not missing, f"Described tools not represented in known sets: {missing}"


def test_min_tool_versions_presence_and_format() -> None:
    """
    Ensure that minimum versions are declared for key tools and
    are non-empty strings containing a dot (e.g. '1.2').
    """
    defs = _reload_defs()
    critical = ["yosys", "iverilog", "verilator", "gtkwave"]
    for tool in critical:
        assert tool in defs.MIN_TOOL_VERSIONS, f"{tool} missing from MIN_TOOL_VERSIONS"
        version = defs.MIN_TOOL_VERSIONS[tool]
        assert isinstance(version, str) and "." in version and version.strip(), (
            f"Invalid version format for {tool!r}: {version!r}"
        )


def test_all_exported_symbols_exist() -> None:
    """All names in `__all__` should correspond to attributes on the module."""
    defs = _reload_defs()
    for name in defs.__all__:
        assert hasattr(defs, name), f"Exported name {name!r} not found in module"

    # Spot-check types of a few exports
    assert isinstance(defs.APT_TOOLS, list)
    assert isinstance(defs.SCRIPT_TOOLS, dict)
    assert isinstance(defs.TOOLS, dict)
    assert isinstance(defs.TOOL_DESCRIPTIONS, dict)
    assert isinstance(defs.MIN_TOOL_VERSIONS, dict)
    assert isinstance(defs.ALL_TOOLS, list)


def test_import_reload_is_idempotent() -> None:
    """
    Re-importing should not change the values of simple constants.
    This guards against accidental mutation at import-time.
    """
    first = _reload_defs()
    snapshot = {
        "ALL_TOOLS": list(first.ALL_TOOLS),
        "APT_TOOLS": list(first.APT_TOOLS),
        "SCRIPT_TOOLS": dict(first.SCRIPT_TOOLS),
        "TOOL_DESCRIPTIONS": dict(first.TOOL_DESCRIPTIONS),
        "MIN_TOOL_VERSIONS": dict(first.MIN_TOOL_VERSIONS),
    }

    second = _reload_defs()
    assert list(second.ALL_TOOLS) == snapshot["ALL_TOOLS"]
    assert list(second.APT_TOOLS) == snapshot["APT_TOOLS"]
    assert dict(second.SCRIPT_TOOLS) == snapshot["SCRIPT_TOOLS"]
    assert dict(second.TOOL_DESCRIPTIONS) == snapshot["TOOL_DESCRIPTIONS"]
    assert dict(second.MIN_TOOL_VERSIONS) == snapshot["MIN_TOOL_VERSIONS"]
