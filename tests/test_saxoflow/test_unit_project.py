"""
Tests for saxoflow.unit_project: project scaffolding & CLI.

This suite is hermetic:
- Uses tmp_path for all FS ops.
- No network or subprocess calls.
- Asserts both happy paths and exception branches.

Why these tests exist:
- Prevent regressions in CLI behavior and on-disk layout.
- Ensure robust error handling when FS operations fail.
- Guarantee the Yosys template is generated deterministically.
"""

from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

import saxoflow.unit_project as unit_project


# -----------------------------
# Helpers
# -----------------------------

def _chdir(path: Path):
    """Context manager to temporarily chdir into a path."""
    class _Ctx:
        def __enter__(self):
            self._old = Path.cwd()
            os.chdir(path)
            return path

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self._old)
    return _Ctx()


# -----------------------------
# Template coverage
# -----------------------------

def test_template_join_equivalence():
    """YOSYS_SYNTH_TEMPLATE must be exactly the join() of _yosys_template_lines."""
    lines = unit_project._yosys_template_lines()
    joined = "\n".join(lines)
    assert unit_project.YOSYS_SYNTH_TEMPLATE == joined
    # Sanity: a few known tokens must be present
    assert "SaxoFlow Professional Yosys Synthesis Script" in joined
    assert "write_verilog ../synthesis/out/synthesized.v" in joined
    assert "write_verilog ../pnr/synth2openroad.v" in joined
    # The template includes tips AFTER 'exit' (production behavior). Assert ordering, not suffix.
    idx_exit = joined.find("\nexit\n")
    idx_tips = joined.find("TIPS & GUIDELINES")
    assert idx_exit != -1, "expected 'exit' command in template"
    assert idx_tips != -1 and idx_exit < idx_tips, "'TIPS' section should follow 'exit'"


# -----------------------------
# Low-level helpers
# -----------------------------

def test_create_directories_creates_gitkeep(tmp_path):
    """_create_directories should make subdirs and drop a .gitkeep file in each."""
    root = tmp_path / "proj"
    root.mkdir()
    unit_project._create_directories(root, unit_project.PROJECT_STRUCTURE)
    for sub in unit_project.PROJECT_STRUCTURE:
        p = root / sub
        assert p.is_dir(), f"Missing directory {p}"
        assert (p / ".gitkeep").exists(), f".gitkeep missing in {p}"


def test_write_yosys_template_writes_and_announces(tmp_path, capsys):
    """_write_yosys_template should write the expected content and secho a message."""
    root = tmp_path / "p"
    (root / "synthesis/scripts").mkdir(parents=True)
    unit_project._write_yosys_template(root, "ABC\nDEF")
    ys = root / "synthesis/scripts" / "synth.ys"
    assert ys.exists()
    assert ys.read_text(encoding="utf-8") == "ABC\nDEF"
    out = capsys.readouterr().out
    assert "Yosys synthesis script template added" in out


def test_copy_makefile_template_exists(tmp_path, monkeypatch):
    """
    _copy_makefile_template copies file if templates/Makefile exists.

    The SUT computes: Path(__file__).parent.parent / 'templates' / 'Makefile'
    So we must set __file__ two levels below the fake repo root.
    """
    repo_root = tmp_path / "repo"
    (repo_root / "templates").mkdir(parents=True)
    (repo_root / "templates" / "Makefile").write_text("FAKE", encoding="utf-8")

    # Put __file__ at <repo_root>/pkg/dummy.py so parent.parent == repo_root
    monkeypatch.setattr(unit_project, "__file__", str(repo_root / "pkg" / "dummy.py"))

    root = tmp_path / "proj"
    root.mkdir()

    unit_project._copy_makefile_template(root)
    mf = root / "Makefile"
    assert mf.exists() and mf.read_text(encoding="utf-8") == "FAKE"


def test_copy_makefile_template_missing_warns(tmp_path, capsys, monkeypatch):
    """_copy_makefile_template warns if template missing."""
    # Put __file__ in <tmp>/pkg/dummy.py -> parent.parent == <tmp>
    monkeypatch.setattr(unit_project, "__file__", str(tmp_path / "pkg" / "dummy.py"))
    root = tmp_path / "x"
    root.mkdir()
    unit_project._copy_makefile_template(root)
    out = capsys.readouterr().out
    assert "Makefile template not found" in out
    assert not (root / "Makefile").exists()


# -----------------------------
# CLI happy path
# -----------------------------

def test_unit_creates_structure_unicode_name(tmp_path):
    """unit creates full tree and writes synth.ys for unicode/special project names."""
    runner = CliRunner()
    project_name = "mydësign_测试"
    with _chdir(tmp_path):
        result = runner.invoke(unit_project.unit, [project_name])
    assert result.exit_code == 0, result.output

    root = tmp_path / project_name
    # Verify all subdirs + .gitkeep
    for sub in unit_project.PROJECT_STRUCTURE:
        p = root / sub
        assert p.is_dir(), f"Missing directory {p}"
        assert (p / ".gitkeep").exists(), f".gitkeep missing in {p}"

    # Yosys template exists and contains known header token
    ys = root / "synthesis/scripts" / "synth.ys"
    assert ys.exists()
    txt = ys.read_text(encoding="utf-8")
    assert "SaxoFlow Professional Yosys Synthesis Script" in txt

    # Friendly next-steps hint
    assert f"Next: cd {project_name} && make sim-icarus" in result.output


def test_unit_help_shows_summary():
    """Click help for unit should print a useful summary sentence."""
    runner = CliRunner()
    result = runner.invoke(unit_project.unit, ["--help"])
    assert result.exit_code == 0
    assert "Create a new SaxoFlow professional project structure" in result.output


# -----------------------------
# CLI abort conditions
# -----------------------------

def test_unit_existing_directory_aborts(tmp_path):
    """unit aborts (non-zero) when directory already exists."""
    runner = CliRunner()
    existing = tmp_path / "project"
    existing.mkdir()
    result = runner.invoke(unit_project.unit, [str(existing)])
    assert result.exit_code != 0
    assert "already exists" in result.output


def test_unit_existing_file_aborts(tmp_path):
    """unit aborts (non-zero) when a file with the given name already exists."""
    runner = CliRunner()
    existing = tmp_path / "file"
    existing.write_text("x", encoding="utf-8")
    result = runner.invoke(unit_project.unit, [str(existing)])
    assert result.exit_code != 0
    assert "already exists" in result.output


# -----------------------------
# CLI exception branches
# -----------------------------

def test_unit_fails_when_create_directories_raises(tmp_path, monkeypatch):
    """unit should print a clear error and exit non-zero if _create_directories fails."""
    runner = CliRunner()
    monkeypatch.setattr(unit_project, "_create_directories", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    with _chdir(tmp_path):
        result = runner.invoke(unit_project.unit, ["proj"])
    assert result.exit_code != 0
    assert "Failed to initialize project: boom" in result.output


def test_unit_fails_when_copy_makefile_raises(tmp_path, monkeypatch):
    """
    unit should handle OSError from shutil.copy via the try/except in unit().

    As with the earlier test, ensure __file__ resolves to a repo root that
    actually contains templates/Makefile so copy() is invoked.
    """
    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    (repo / "templates" / "Makefile").write_text("OK", encoding="utf-8")

    # <repo>/pkg/dummy.py -> parent.parent == <repo>
    monkeypatch.setattr(unit_project, "__file__", str(repo / "pkg" / "dummy.py"))

    # Patch the EXACT attribute used by the SUT
    monkeypatch.setattr(unit_project.shutil, "copy", lambda *a, **k: (_ for _ in ()).throw(OSError("copy-fail")))

    runner = CliRunner()
    with _chdir(tmp_path):
        result = runner.invoke(unit_project.unit, ["p"])
    assert result.exit_code != 0
    assert "Failed to initialize project: copy-fail" in result.output
