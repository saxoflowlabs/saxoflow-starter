# tests/test_saxoflow/test_teach/test_pack.py
"""Tests for saxoflow.teach.pack — pack and lesson YAML loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from saxoflow.teach.pack import PackLoadError, load_pack


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_pack(tmp_path: Path, pack_data: dict, lessons: dict | None = None) -> Path:
    """Write a minimal pack directory structure and return the pack path."""
    pack_dir = tmp_path / "mypack"
    (pack_dir / "docs").mkdir(parents=True)
    lessons_dir = pack_dir / "lessons"
    lessons_dir.mkdir(parents=True)

    with open(pack_dir / "pack.yaml", "w") as f:
        yaml.dump(pack_data, f)

    if lessons:
        for filename, data in lessons.items():
            with open(lessons_dir / filename, "w") as f:
                yaml.dump(data, f)

    return pack_dir


MINIMAL_LESSON = {
    "id": "step1",
    "title": "First Step",
    "goal": "Do something",
    "commands": [{"native": "echo hello"}],
    "success": [],
}

MINIMAL_PACK = {
    "id": "mypack",
    "name": "My Test Pack",
    "version": "1.0",
    "authors": ["Tester"],
    "description": "A test pack",
    "docs": [],
    "lessons": ["step1.yaml"],
}


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------

class TestLoadPackHappyPath:
    def test_returns_packdef(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": MINIMAL_LESSON})
        pack = load_pack(pack_dir)
        assert pack.id == "mypack"
        assert pack.name == "My Test Pack"

    def test_step_loaded(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": MINIMAL_LESSON})
        pack = load_pack(pack_dir)
        assert len(pack.steps) == 1
        assert pack.steps[0].id == "step1"
        assert pack.steps[0].title == "First Step"

    def test_command_parsed(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, commands=[{"native": "echo hello", "preferred": "s echo", "use_preferred_if_available": True}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        pack = load_pack(pack_dir)
        cmd = pack.steps[0].commands[0]
        assert cmd.native == "echo hello"
        assert cmd.preferred == "s echo"

    def test_success_check_parsed(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, success=[{"kind": "file_exists", "file": "out.v"}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        pack = load_pack(pack_dir)
        chk = pack.steps[0].success[0]
        assert chk.kind == "file_exists"
        assert chk.file == "out.v"

    def test_agent_inv_parsed(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, agent_invocations=[{"agent_key": "rtlgen", "args": {"spec": "counter"}}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        pack = load_pack(pack_dir)
        inv = pack.steps[0].agent_invocations[0]
        assert inv.agent_key == "rtlgen"
        assert inv.args["spec"] == "counter"

    def test_bare_string_command(self, tmp_path):
        """Commands may be bare strings."""
        lesson = dict(MINIMAL_LESSON, commands=["iverilog -V"])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        pack = load_pack(pack_dir)
        assert pack.steps[0].commands[0].native == "iverilog -V"


# ---------------------------------------------------------------------------
# Error-path tests
# ---------------------------------------------------------------------------

class TestLoadPackErrors:
    def test_missing_pack_yaml(self, tmp_path):
        empty_dir = tmp_path / "nopack"
        empty_dir.mkdir()
        with pytest.raises(FileNotFoundError):
            load_pack(empty_dir)

    def test_missing_required_keys(self, tmp_path):
        bad_pack = {"id": "broken"}  # missing name, version, authors, etc.
        pack_dir = _write_pack(tmp_path, bad_pack, {})
        with pytest.raises(PackLoadError, match="Required key"):
            load_pack(pack_dir)

    def test_missing_lesson_file(self, tmp_path):
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {})  # no lesson file written
        with pytest.raises(PackLoadError, match="not found"):
            load_pack(pack_dir)

    def test_empty_lessons_list(self, tmp_path):
        pack_data = dict(MINIMAL_PACK, lessons=[])
        pack_dir = _write_pack(tmp_path, pack_data, {})
        with pytest.raises(PackLoadError, match="no lessons"):
            load_pack(pack_dir)

    def test_lesson_missing_required_keys(self, tmp_path):
        bad_lesson = {"id": "s1"}  # missing title + goal
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": bad_lesson})
        with pytest.raises(PackLoadError, match="Required key"):
            load_pack(pack_dir)

    def test_invalid_command_type(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, commands=[42])  # int is invalid
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="string or mapping"):
            load_pack(pack_dir)


# ---------------------------------------------------------------------------
# Parser error paths — _parse_question, _parse_agent_inv, _parse_check, _as_list
# ---------------------------------------------------------------------------

class TestParseErrorPaths:
    def test_parse_question_missing_text(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, questions=[{"after_command": 0}])  # no text
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="text"):
            load_pack(pack_dir)

    def test_parse_question_bad_after_command_type(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, questions=[{"text": "Q?", "after_command": "bad"}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="after_command"):
            load_pack(pack_dir)

    def test_parse_question_non_dict(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, questions=["just a string"])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="mapping"):
            load_pack(pack_dir)

    def test_parse_agent_inv_non_dict(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, agent_invocations=["bad"])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="mapping"):
            load_pack(pack_dir)

    def test_parse_agent_inv_missing_agent_key(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, agent_invocations=[{"args": {}}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="agent_key"):
            load_pack(pack_dir)

    def test_parse_agent_inv_bad_args_type(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, agent_invocations=[{"agent_key": "sim", "args": "not-a-dict"}])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="mapping"):
            load_pack(pack_dir)

    def test_parse_check_non_dict(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, success=["not-a-dict"])
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="mapping"):
            load_pack(pack_dir)

    def test_parse_check_missing_kind(self, tmp_path):
        lesson = dict(MINIMAL_LESSON, success=[{"pattern": "x"}])  # no kind
        pack_dir = _write_pack(tmp_path, MINIMAL_PACK, {"step1.yaml": lesson})
        with pytest.raises(PackLoadError, match="kind"):
            load_pack(pack_dir)

    def test_as_list_non_list_raises(self, tmp_path):
        """A non-list field in docs should raise PackLoadError."""
        pack_data = dict(MINIMAL_PACK, docs="not-a-list")
        pack_dir = _write_pack(tmp_path, pack_data, {"step1.yaml": MINIMAL_LESSON})
        with pytest.raises(PackLoadError, match="list"):
            load_pack(pack_dir)


# ---------------------------------------------------------------------------
# docs_dir override
# ---------------------------------------------------------------------------

class TestDocsDir:
    def test_custom_docs_dir_resolved(self, tmp_path):
        """docs_dir key is resolved relative to pack_path."""
        pack_dir = tmp_path / "mypack"
        (pack_dir / "docs").mkdir(parents=True)
        (pack_dir / "lessons").mkdir(parents=True)
        (pack_dir / "alt_docs").mkdir(parents=True)  # the custom docs dir
        (pack_dir / "lessons" / "step1.yaml").write_text(
            "id: step1\ntitle: T\ngoal: G\n", encoding="utf-8"
        )
        pack_data = dict(MINIMAL_PACK, docs_dir="alt_docs")
        with open(pack_dir / "pack.yaml", "w") as f:
            import yaml as _yaml
            _yaml.dump(pack_data, f)
        result = load_pack(pack_dir)
        assert result.docs_dir == (pack_dir / "alt_docs").resolve()
