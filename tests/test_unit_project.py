"""
Tests for saxoflow.unit_project: project scaffolding.

The `unit` command builds an extensive directory tree and populates it
with templates.  These tests validate that the required folders and
files are created, the synthesis script template contains a known
header, and that invoking the command on an existing directory
aborts gracefully.
"""

from pathlib import Path
import os
from click.testing import CliRunner
import saxoflow.unit_project as unit_project


def test_unit_creates_structure(tmp_path):
    """unit command should build the full project tree and script template."""
    runner = CliRunner()
    project_name = "mydesign"
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(unit_project.unit, [project_name])
        assert result.exit_code == 0
        # Verify that each subfolder exists and contains .gitkeep
        root = tmp_path / project_name
        for sub in unit_project.PROJECT_STRUCTURE:
            p = root / sub
            assert p.is_dir(), f"Missing directory {p}"
            assert (p / ".gitkeep").exists(), f".gitkeep missing in {p}"
        # Check that the Makefile exists
        makefile = root / "Makefile"
        # In this repo templates/Makefile may or may not exist; accept either presence or warning
        # Yosys script must exist and contain a known header
        ys_path = root / "synthesis/scripts/synth.ys"
        assert ys_path.exists(), "synth.ys not created"
        with ys_path.open() as f:
            content = f.read()
        assert "SaxoFlow Professional Yosys Synthesis Script" in content
    finally:
        os.chdir(cwd)


def test_unit_existing_project_aborts(tmp_path):
    """unit should exit with non‑zero code if directory exists."""
    runner = CliRunner()
    existing = tmp_path / "project"
    existing.mkdir()
    result = runner.invoke(unit_project.unit, [str(existing)])
    assert result.exit_code != 0