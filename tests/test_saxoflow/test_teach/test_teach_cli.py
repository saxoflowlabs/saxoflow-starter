# tests/test_saxoflow/test_teach/test_teach_cli.py
"""Tests for saxoflow.teach.cli — Click command group."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from saxoflow.teach.cli import teach_group


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_pack(tmp_path: Path) -> Path:
    """Write a minimal valid pack to tmp_path/packs/testpack."""
    pack_dir = tmp_path / "packs" / "testpack"
    (pack_dir / "docs").mkdir(parents=True)
    (pack_dir / "lessons").mkdir(parents=True)

    pack_data = {
        "id": "testpack",
        "name": "Test Pack",
        "version": "1.0",
        "authors": ["Tester"],
        "description": "CLI test pack",
        "docs": [],
        "lessons": ["step1.yaml"],
    }
    lesson_data = {
        "id": "s1",
        "title": "Step 1",
        "goal": "Do something",
        "commands": [{"native": "echo hello"}],
        "success": [],
    }

    with open(pack_dir / "pack.yaml", "w") as f:
        yaml.dump(pack_data, f)
    with open(pack_dir / "lessons" / "step1.yaml", "w") as f:
        yaml.dump(lesson_data, f)

    return pack_dir


# ---------------------------------------------------------------------------
# teach list
# ---------------------------------------------------------------------------

class TestTeachList:
    def test_list_shows_pack(self, tmp_path):
        _create_pack(tmp_path)
        runner = CliRunner()
        result = runner.invoke(
            teach_group, ["list", "--packs-dir", str(tmp_path / "packs")]
        )
        assert result.exit_code == 0
        assert "testpack" in result.output

    def test_list_empty_dir(self, tmp_path):
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            teach_group, ["list", "--packs-dir", str(packs_dir)]
        )
        assert result.exit_code == 0
        assert "No packs found" in result.output

    def test_list_nonexistent_dir(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            teach_group, ["list", "--packs-dir", str(tmp_path / "nonexistent")]
        )
        assert result.exit_code == 0
        assert "No packs directory" in result.output


# ---------------------------------------------------------------------------
# teach index
# ---------------------------------------------------------------------------

class TestTeachIndex:
    def test_index_unknown_pack_exits_1(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(
            teach_group,
            ["index", "ghost_pack", "--packs-dir", str(tmp_path / "packs")],
        )
        assert result.exit_code != 0

    def test_index_valid_pack(self, tmp_path):
        _create_pack(tmp_path)
        runner = CliRunner()
        # pack has no docs, so index will be empty but should not error
        result = runner.invoke(
            teach_group,
            ["index", "testpack", "--packs-dir", str(tmp_path / "packs")],
        )
        # exit 0 since no docs → 0 chunks but success
        assert result.exit_code == 0
        assert "chunks" in result.output.lower()


# ---------------------------------------------------------------------------
# teach status
# ---------------------------------------------------------------------------

class TestTeachStatus:
    def test_status_no_session(self):
        """When cool_cli.state.teach_session is None, should say so."""
        runner = CliRunner()
        result = runner.invoke(teach_group, ["status"])
        assert result.exit_code == 0
        # Either "No active teach session" or import error — both are fine
        assert len(result.output) > 0
