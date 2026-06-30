"""Inventory tests for the public SaxoFlow Click command tree."""

from __future__ import annotations


def test_cli_exposes_expected_top_level_commands():
    """Phase-0 inventory lock: the root Click tree exposes the documented commands."""
    from saxoflow.cli import cli

    expected = {
        "init-env",
        "install",
        "diagnose",
        "unit",
        "sim",
        "sim-verilator",
        "sim-verilator-run",
        "wave",
        "wave-verilator",
        "simulate",
        "simulate-verilator",
        "formal",
        "lint",
        "synth",
        "schematic",
        "pdk",
        "pnr",
        "clean",
        "check-tools",
        "agenticai",
        "teach",
    }

    assert expected.issubset(set(cli.commands))


def test_cli_alias_inventory_includes_agenticai_and_teach_groups():
    """Phase-0 inventory lock: agentic and teach groups stay mounted on the root CLI."""
    from saxoflow.cli import cli

    assert cli.commands["agenticai"].name == "cli"
    assert cli.commands["teach"].name == "teach"
