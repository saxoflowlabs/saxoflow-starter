# tests/test_coolcli/test_file_ops.py
"""Tests for the file creation / save-intent pipeline.

Covers:
- detect_save_intent() — intent detection and field extraction
- ask_ai_buddy() — returns save_file type when save intent found
- file_ops.py — scaffold_unit_if_needed, determine_dest_path, write_artifact, handle_save_file
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from rich.panel import Panel
from rich.text import Text


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ai_buddy_mod():
    return importlib.import_module("cool_cli.ai_buddy")


@pytest.fixture(scope="session")
def file_ops_mod():
    return importlib.import_module("cool_cli.file_ops")


# ---------------------------------------------------------------------------
# detect_save_intent tests
# ---------------------------------------------------------------------------

class TestDetectSaveIntent:
    """Unit tests for detect_save_intent()."""

    def test_basic_sv_with_unit(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "create a mux design in SV and save it as mux.sv in a unit named mux"
        )
        assert result is not None
        assert result["filename"] == "mux.sv"
        assert result["unit"] == "mux"
        assert result["content_type"] == "rtl"

    def test_store_as_verilog(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "generate a 4-bit adder and store it as adder.v in unit adder"
        )
        assert result is not None
        assert result["filename"] == "adder.v"
        assert result["unit"] == "adder"

    def test_write_to_no_unit(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "write a D flip-flop to dff.sv"
        )
        assert result is not None
        assert result["filename"] == "dff.sv"
        assert result["unit"] == ""  # no unit specified

    def test_in_the_unit_syntax(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "create counter.sv in the counter_lib unit"
        )
        assert result is not None
        assert result["filename"] == "counter.sv"
        assert result["unit"] == "counter_lib"

    def test_formal_extension(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "generate formal properties and save as arb.sva in unit arb"
        )
        assert result is not None
        assert result["filename"] == "arb.sva"
        assert result["content_type"] == "formal"

    def test_testbench_name_override(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_save_intent(
            "create a testbench and save it as tb_mux.sv in unit mux"
        )
        assert result is not None
        assert result["content_type"] == "tb"

    def test_no_intent_pure_chat(self, ai_buddy_mod):
        """Messages with no save keyword should return None."""
        assert ai_buddy_mod.detect_save_intent("generate rtl for a mux") is None
        assert ai_buddy_mod.detect_save_intent("what is a flip-flop?") is None

    def test_no_filename_returns_none(self, ai_buddy_mod):
        """Save intent without a recognizable filename returns None."""
        assert ai_buddy_mod.detect_save_intent("save this somewhere") is None

    def test_spec_is_original_message(self, ai_buddy_mod):
        msg = "write a FIFO to fifo.sv in unit fifo_lib"
        result = ai_buddy_mod.detect_save_intent(msg)
        assert result is not None
        assert result["spec"] == msg


# ---------------------------------------------------------------------------
# ask_ai_buddy save_file path tests
# ---------------------------------------------------------------------------

class TestAskAiBuddySaveFile:
    """ask_ai_buddy() returns save_file type when save intent detected."""

    def test_returns_save_file_type(self, ai_buddy_mod):
        res = ai_buddy_mod.ask_ai_buddy(
            "create a mux and save it as mux.sv in unit mux"
        )
        assert res["type"] == "save_file"
        assert res["filename"] == "mux.sv"
        assert res["unit"] == "mux"

    def test_save_file_bypasses_llm_call(self, ai_buddy_mod, monkeypatch):
        """LLM should NOT be called for save intent — that happens in file_ops."""
        called = []
        monkeypatch.setattr(
            ai_buddy_mod.ModelSelector, "get_model",
            lambda **_: (_ for _ in ()).throw(AssertionError("LLM called unexpectedly"))
        )
        # Should not raise; detection happens before LLM invocation
        res = ai_buddy_mod.ask_ai_buddy("save a counter as counter.sv in unit cnt")
        assert res["type"] == "save_file"
        assert not called


# ---------------------------------------------------------------------------
# file_ops helper unit tests (no LLM, no disk side-effects)
# ---------------------------------------------------------------------------

class TestDetermineDestPath:
    """determine_dest_path() maps (filename, content_type) → correct subdir."""

    @pytest.mark.parametrize("filename,content_type,expected_subdir", [
        ("mux.sv",    "rtl",    "source/rtl/systemverilog"),
        ("mux.v",     "rtl",    "source/rtl/verilog"),
        ("mux.vhd",   "rtl",    "source/rtl/vhdl"),
        ("tb_mux.sv", "tb",     "source/tb/systemverilog"),
        ("arb.sva",   "formal", "formal/src"),
        ("synth.tcl", "synth",  "synthesis/scripts"),
    ])
    def test_subdir_mapping(self, file_ops_mod, tmp_path, filename, content_type, expected_subdir):
        dest = file_ops_mod.determine_dest_path(tmp_path, filename, content_type)
        assert dest == tmp_path / expected_subdir / filename
        assert dest.parent.exists()  # directory was created


class TestWriteArtifact:
    """write_artifact() creates the file with the correct content."""

    def test_writes_file(self, file_ops_mod, tmp_path):
        dest = tmp_path / "source" / "rtl" / "systemverilog" / "mux.sv"
        code = "module mux(input a, b, sel, output y); endmodule"
        written = file_ops_mod.write_artifact(code, dest)
        assert written == dest
        assert dest.read_text(encoding="utf-8") == code

    def test_creates_parent_dirs(self, file_ops_mod, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "out.sv"
        file_ops_mod.write_artifact("// code", deep)
        assert deep.exists()

    def test_overwrites_existing(self, file_ops_mod, tmp_path):
        dest = tmp_path / "mux.sv"
        dest.write_text("old content", encoding="utf-8")
        file_ops_mod.write_artifact("new content", dest)
        assert dest.read_text(encoding="utf-8") == "new content"


class TestScaffoldUnitIfNeeded:
    """scaffold_unit_if_needed() creates unit structure on first call, reuses on second."""

    def test_creates_unit_structure(self, file_ops_mod, tmp_path):
        unit_root = file_ops_mod.scaffold_unit_if_needed("myunit", cwd=tmp_path)
        assert unit_root.exists()
        assert (unit_root / "source" / "rtl" / "systemverilog").exists()
        assert (unit_root / "source" / "tb" / "systemverilog").exists()
        assert (unit_root / "formal" / "src").exists()

    def test_does_not_recreate_existing(self, file_ops_mod, tmp_path):
        root1 = file_ops_mod.scaffold_unit_if_needed("u1", cwd=tmp_path)
        # Write a sentinel file
        sentinel = root1 / "sentinel.txt"
        sentinel.write_text("preserved")
        # Second call should return existing root without touching it
        root2 = file_ops_mod.scaffold_unit_if_needed("u1", cwd=tmp_path)
        assert root1 == root2
        assert sentinel.read_text() == "preserved"

    def test_returns_absolute_path(self, file_ops_mod, tmp_path):
        root = file_ops_mod.scaffold_unit_if_needed("abs_test", cwd=tmp_path)
        assert root.is_absolute()


# ---------------------------------------------------------------------------
# handle_save_file integration tests (LLM mocked)
# ---------------------------------------------------------------------------

class TestHandleSaveFile:
    """handle_save_file() end-to-end with mocked LLM generation."""

    def _buddy_result(self, filename="mux.sv", unit="mux",
                      content_type="rtl",
                      spec="create a mux design and save as mux.sv in unit mux"):
        return {
            "type": "save_file",
            "spec": spec,
            "filename": filename,
            "unit": unit,
            "content_type": content_type,
        }

    def test_creates_file_and_returns_success_panel(self, file_ops_mod, tmp_path, monkeypatch):
        generated_code = "module mux(input a, b, sel, output y);\nendmodule"

        # Mock generate_code_for_save to avoid real LLM call
        # monkeypatch.chdir sets cwd to tmp_path so scaffold_unit_if_needed uses it naturally
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save", return_value=generated_code):
            result = file_ops_mod.handle_save_file(self._buddy_result(), history=[])

        assert isinstance(result, Panel)
        assert (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv").exists()
        written = (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv")
        assert "module mux" in written.read_text(encoding="utf-8")

    def test_strips_code_fences_before_writing(self, file_ops_mod, tmp_path, monkeypatch):
        fenced = "```systemverilog\nmodule mux(); endmodule\n```"
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save", return_value=fenced):
            file_ops_mod.handle_save_file(self._buddy_result(), history=[])

        written = (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv")
        content = written.read_text(encoding="utf-8")
        assert "```" not in content
        assert "module mux" in content

    def test_missing_filename_returns_error_text(self, file_ops_mod):
        result = file_ops_mod.handle_save_file(
            {"type": "save_file", "spec": "...", "filename": "", "unit": "", "content_type": "rtl"},
            history=[],
        )
        assert isinstance(result, Text)
        assert "filename" in result.plain.lower()

    def test_empty_llm_response_returns_warning(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save", return_value="   "):
            result = file_ops_mod.handle_save_file(self._buddy_result(), history=[])
        assert isinstance(result, Text)
        assert "no content" in result.plain.lower() or "rephrase" in result.plain.lower()

    def test_llm_failure_returns_error_text(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save",
                   side_effect=RuntimeError("LLM timeout")):
            result = file_ops_mod.handle_save_file(self._buddy_result(), history=[])
        assert isinstance(result, Text)
        assert "failed" in result.plain.lower() or "timeout" in result.plain.lower()

    def test_no_unit_writes_to_cwd(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        generated_code = "module dff(); endmodule"
        with patch("cool_cli.file_ops.generate_code_for_save", return_value=generated_code):
            result = file_ops_mod.handle_save_file(
                {**self._buddy_result(), "unit": "", "filename": "dff.sv"},
                history=[],
            )
        assert isinstance(result, Panel)
        assert (tmp_path / "dff.sv").exists()

    def test_post_hook_called_on_success(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save", return_value="module m; endmodule"):
            with patch("cool_cli.file_ops.run_post_hook", return_value="sim ok") as mock_hook:
                result = file_ops_mod.handle_save_file(
                    {**self._buddy_result(), "post_hook": "sim"},
                    history=[],
                )
        mock_hook.assert_called_once()
        assert isinstance(result, Panel)

    def test_no_post_hook_when_none(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save", return_value="module m; endmodule"):
            with patch("cool_cli.file_ops.run_post_hook") as mock_hook:
                file_ops_mod.handle_save_file(self._buddy_result(), history=[])
        mock_hook.assert_not_called()


# ---------------------------------------------------------------------------
# detect_edit_intent tests
# ---------------------------------------------------------------------------

class TestDetectEditIntent:
    """Unit tests for detect_edit_intent()."""

    def test_basic_edit_with_unit(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_edit_intent(
            "edit mux.sv in unit mux and add an async reset port"
        )
        assert result is not None
        assert result["filename"] == "mux.sv"
        assert result["unit"] == "mux"
        assert result["content_type"] == "rtl"

    def test_modify_verb(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_edit_intent(
            "modify counter.sv to change the reset to active-low"
        )
        assert result is not None
        assert result["filename"] == "counter.sv"

    def test_fix_verb(self, ai_buddy_mod):
        result = ai_buddy_mod.detect_edit_intent("fix the bug in dff.sv in unit reg_lib")
        assert result is not None
        assert result["filename"] == "dff.sv"
        assert result["unit"] == "reg_lib"

    def test_no_filename_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_edit_intent("edit the design") is None

    def test_no_edit_keyword_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_edit_intent("show me mux.sv") is None
        assert ai_buddy_mod.detect_edit_intent("what is in dff.sv?") is None

    def test_content_type_tb_for_tb_prefix(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_edit_intent("modify tb_mux.sv in unit mux")
        assert r is not None
        assert r["content_type"] == "tb"

    def test_post_hook_detected(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_edit_intent(
            "edit mux.sv in unit mux, add a reset, then simulate"
        )
        assert r is not None
        assert r["post_hook"] == "sim"

    def test_no_post_hook_when_absent(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_edit_intent("edit mux.sv in unit mux")
        assert r is not None
        assert r["post_hook"] is None

    def test_ask_ai_buddy_returns_edit_file_type(self, ai_buddy_mod):
        res = ai_buddy_mod.ask_ai_buddy("modify counter.sv in unit cnt to add reset")
        assert res["type"] == "edit_file"
        assert res["filename"] == "counter.sv"


# ---------------------------------------------------------------------------
# detect_multi_file_intent tests
# ---------------------------------------------------------------------------

class TestDetectMultiFileIntent:
    """Unit tests for detect_multi_file_intent()."""

    def test_rtl_and_testbench(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_multi_file_intent(
            "create RTL and testbench for a mux in unit mux"
        )
        assert r is not None
        filenames = [f["filename"] for f in r["files"]]
        assert any(fn.endswith(".sv") and not fn.startswith("tb_") for fn in filenames)
        assert any(fn.startswith("tb_") for fn in filenames)
        assert r["unit"] == "mux"

    def test_full_project(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_multi_file_intent(
            "generate full project for a counter in unit cnt"
        )
        assert r is not None
        types = {f["content_type"] for f in r["files"]}
        assert "rtl" in types
        assert "formal" in types  # full project includes formal

    def test_design_name_inferred(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_multi_file_intent(
            "generate RTL and testbench for a fifo in unit fifo_lib"
        )
        assert r is not None
        assert r["design_name"] == "fifo"

    def test_no_match_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_multi_file_intent("create mux.sv in unit mux") is None
        assert ai_buddy_mod.detect_multi_file_intent("what is RTL?") is None

    def test_post_hook_detected(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_multi_file_intent(
            "create RTL and testbench for a mux in unit mux and then simulate"
        )
        assert r is not None
        assert r["post_hook"] == "sim"

    def test_ask_ai_buddy_returns_multi_file_type(self, ai_buddy_mod):
        res = ai_buddy_mod.ask_ai_buddy(
            "create RTL and testbench for a counter in unit cnt"
        )
        assert res["type"] == "multi_file"
        assert len(res["files"]) >= 2


# ---------------------------------------------------------------------------
# read_artifact / find_file_in_unit tests
# ---------------------------------------------------------------------------

class TestReadArtifact:
    def test_reads_file_content(self, file_ops_mod, tmp_path):
        f = tmp_path / "mux.sv"
        f.write_text("module mux; endmodule", encoding="utf-8")
        assert file_ops_mod.read_artifact(f) == "module mux; endmodule"

    def test_raises_for_missing_file(self, file_ops_mod, tmp_path):
        with pytest.raises(OSError):
            file_ops_mod.read_artifact(tmp_path / "nonexistent.sv")


class TestFindFileInUnit:
    def test_finds_nested_file(self, file_ops_mod, tmp_path):
        deep = tmp_path / "source" / "rtl" / "systemverilog"
        deep.mkdir(parents=True)
        target = deep / "mux.sv"
        target.write_text("// mux", encoding="utf-8")
        found = file_ops_mod.find_file_in_unit(tmp_path, "mux.sv")
        assert found == target

    def test_returns_none_if_not_found(self, file_ops_mod, tmp_path):
        assert file_ops_mod.find_file_in_unit(tmp_path, "missing.sv") is None


# ---------------------------------------------------------------------------
# run_post_hook tests
# ---------------------------------------------------------------------------

class TestRunPostHook:
    def test_unknown_hook_type(self, file_ops_mod, tmp_path):
        out = file_ops_mod.run_post_hook(tmp_path, "foobar")
        assert "unknown" in out.lower()

    def test_valid_hook_runs_subprocess(self, file_ops_mod, tmp_path):
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="sim passed\n", stderr="")
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            out = file_ops_mod.run_post_hook(tmp_path, "sim")
        mock_sub.run.assert_called_once()
        assert "sim passed" in out

    def test_timeout_returns_friendly_message(self, file_ops_mod, tmp_path):
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.side_effect = subprocess.TimeoutExpired(cmd="saxoflow", timeout=120)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            out = file_ops_mod.run_post_hook(tmp_path, "sim")
        assert "timed out" in out.lower()


# ---------------------------------------------------------------------------
# handle_edit_file integration tests
# ---------------------------------------------------------------------------

class TestHandleEditFile:
    """handle_edit_file() end-to-end with mocked LLM and real disk."""

    def _setup_unit(self, tmp_path, unit="mux", filename="mux.sv",
                    content="module mux; endmodule"):
        unit_dir = tmp_path / unit / "source" / "rtl" / "systemverilog"
        unit_dir.mkdir(parents=True)
        f = unit_dir / filename
        f.write_text(content, encoding="utf-8")
        return f

    def test_edits_file_and_returns_panel(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        new_code = "module mux(input rst); endmodule"
        with patch("cool_cli.file_ops.generate_patch_for_edit", return_value=new_code):
            result = file_ops_mod.handle_edit_file(
                {"filename": "mux.sv", "unit": "mux", "edit_request": "add reset",
                 "content_type": "rtl", "post_hook": None},
                history=[],
            )
        assert isinstance(result, Panel)
        written = tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv"
        assert "rst" in written.read_text(encoding="utf-8")

    def test_strips_fences_before_writing(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        fenced = "```systemverilog\nmodule mux(input rst); endmodule\n```"
        with patch("cool_cli.file_ops.generate_patch_for_edit", return_value=fenced):
            file_ops_mod.handle_edit_file(
                {"filename": "mux.sv", "unit": "mux", "edit_request": "add reset",
                 "content_type": "rtl", "post_hook": None},
                history=[],
            )
        content = (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv").read_text()
        assert "```" not in content

    def test_missing_filename_returns_text(self, file_ops_mod):
        result = file_ops_mod.handle_edit_file(
            {"filename": "", "unit": "mux", "edit_request": "add reset",
             "content_type": "rtl", "post_hook": None},
            history=[],
        )
        assert isinstance(result, Text)
        assert "filename" in result.plain.lower()

    def test_unit_not_found_returns_text(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = file_ops_mod.handle_edit_file(
            {"filename": "mux.sv", "unit": "no_such_unit", "edit_request": "...",
             "content_type": "rtl", "post_hook": None},
            history=[],
        )
        assert isinstance(result, Text)
        assert "not found" in result.plain.lower()

    def test_file_not_found_in_unit_returns_text(self, file_ops_mod, tmp_path, monkeypatch):
        (tmp_path / "myunit").mkdir()
        monkeypatch.chdir(tmp_path)
        result = file_ops_mod.handle_edit_file(
            {"filename": "ghost.sv", "unit": "myunit", "edit_request": "...",
             "content_type": "rtl", "post_hook": None},
            history=[],
        )
        assert isinstance(result, Text)
        assert "not found" in result.plain.lower()

    def test_llm_failure_returns_error_text(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_patch_for_edit",
                   side_effect=RuntimeError("model unavailable")):
            result = file_ops_mod.handle_edit_file(
                {"filename": "mux.sv", "unit": "mux", "edit_request": "add reset",
                 "content_type": "rtl", "post_hook": None},
                history=[],
            )
        assert isinstance(result, Text)
        assert "failed" in result.plain.lower() or "unavailable" in result.plain.lower()

    def test_post_hook_invoked(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_patch_for_edit",
                   return_value="module mux; endmodule"):
            with patch("cool_cli.file_ops.run_post_hook", return_value="lint ok") as mhook:
                file_ops_mod.handle_edit_file(
                    {"filename": "mux.sv", "unit": "mux", "edit_request": "...",
                     "content_type": "rtl", "post_hook": "lint"},
                    history=[],
                )
        mhook.assert_called_once()

    def test_no_unit_edits_in_cwd(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "standalone.sv").write_text("module s; endmodule", encoding="utf-8")
        with patch("cool_cli.file_ops.generate_patch_for_edit",
                   return_value="module s2; endmodule"):
            result = file_ops_mod.handle_edit_file(
                {"filename": "standalone.sv", "unit": "", "edit_request": "rename module",
                 "content_type": "rtl", "post_hook": None},
                history=[],
            )
        assert isinstance(result, Panel)
        assert "s2" in (tmp_path / "standalone.sv").read_text()


# ---------------------------------------------------------------------------
# handle_multi_file integration tests
# ---------------------------------------------------------------------------

class TestHandleMultiFile:
    """handle_multi_file() end-to-end with mocked LLM."""

    def _buddy_result(self, unit="mux", design_name="mux",
                      files=None, post_hook=None):
        if files is None:
            files = [
                {"filename": "mux.sv", "content_type": "rtl"},
                {"filename": "tb_mux.sv", "content_type": "tb"},
            ]
        return {
            "type": "multi_file",
            "spec": "create RTL and testbench for a mux in unit mux",
            "unit": unit,
            "design_name": design_name,
            "files": files,
            "post_hook": post_hook,
        }

    def test_creates_all_files_and_returns_panel(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save",
                   return_value="module gen; endmodule"):
            result = file_ops_mod.handle_multi_file(self._buddy_result(), history=[])
        assert isinstance(result, Panel)
        assert (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv").exists()
        assert (tmp_path / "mux" / "source" / "tb" / "systemverilog" / "tb_mux.sv").exists()

    def test_empty_files_list_returns_text(self, file_ops_mod):
        result = file_ops_mod.handle_multi_file(
            {"type": "multi_file", "spec": "...", "unit": "u", "design_name": "d",
             "files": [], "post_hook": None},
            history=[],
        )
        assert isinstance(result, Text)
        assert "no files" in result.plain.lower()

    def test_partial_failure_still_writes_good_files(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        call_count = {"n": 0}

        def side_effect(spec, ct):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return "module rtl; endmodule"
            raise RuntimeError("TB LLM error")

        with patch("cool_cli.file_ops.generate_code_for_save", side_effect=side_effect):
            result = file_ops_mod.handle_multi_file(self._buddy_result(), history=[])

        # Panel returned even on partial failure
        assert isinstance(result, Panel)
        # RTL file written, TB file not
        assert (tmp_path / "mux" / "source" / "rtl" / "systemverilog" / "mux.sv").exists()
        assert not (tmp_path / "mux" / "source" / "tb" / "systemverilog" / "tb_mux.sv").exists()

    def test_post_hook_called(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save",
                   return_value="module g; endmodule"):
            with patch("cool_cli.file_ops.run_post_hook", return_value="synth ok") as mhook:
                file_ops_mod.handle_multi_file(
                    self._buddy_result(post_hook="synth"), history=[]
                )
        mhook.assert_called_once()

    def test_no_post_hook_when_none(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save",
                   return_value="module g; endmodule"):
            with patch("cool_cli.file_ops.run_post_hook") as mhook:
                file_ops_mod.handle_multi_file(self._buddy_result(), history=[])
        mhook.assert_not_called()

    def test_no_unit_writes_to_cwd(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_code_for_save",
                   return_value="module g; endmodule"):
            result = file_ops_mod.handle_multi_file(
                self._buddy_result(unit=""), history=[]
            )
        assert isinstance(result, Panel)
        assert (tmp_path / "mux.sv").exists()
        assert (tmp_path / "tb_mux.sv").exists()


# ---------------------------------------------------------------------------
# Post-hook in detect_save_intent
# ---------------------------------------------------------------------------

class TestDetectSaveIntentPostHook:
    def test_post_hook_sim_detected(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_save_intent(
            "create mux.sv in unit mux and then simulate"
        )
        assert r is not None
        assert r["post_hook"] == "sim"

    def test_post_hook_synth_detected(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_save_intent(
            "save adder.sv in unit adder and synth"
        )
        assert r is not None
        assert r["post_hook"] == "synth"

    def test_post_hook_lint_detected(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_save_intent(
            "write counter.sv to unit cnt and lint"
        )
        assert r is not None
        assert r["post_hook"] == "lint"

    def test_no_post_hook_when_absent(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_save_intent("create mux.sv in unit mux")
        assert r is not None
        assert r["post_hook"] is None


# ---------------------------------------------------------------------------
# detect_read_intent tests
# ---------------------------------------------------------------------------

class TestDetectReadIntent:
    """Unit tests for detect_read_intent()."""

    def test_explain_keyword(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("explain adder.sv to me")
        assert r is not None
        assert r["filename"] == "adder.sv"
        assert "explain" in r["question"].lower()

    def test_describe_keyword(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("describe the ports in mux.sv")
        assert r is not None
        assert r["filename"] == "mux.sv"

    def test_what_does_phrase(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("what does counter.sv do?")
        assert r is not None
        assert r["filename"] == "counter.sv"

    def test_summarize_spelling_variant(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("summarise dff.sv for me")
        assert r is not None
        assert r["filename"] == "dff.sv"

    def test_no_filename_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_read_intent("explain the design") is None

    def test_no_read_keyword_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_read_intent("save mux.sv in unit mux") is None

    def test_verilog_extension(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("walk me through adder.v")
        assert r is not None
        assert r["filename"] == "adder.v"

    def test_vhdl_extension(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_read_intent("explain alu.vhd")
        assert r is not None
        assert r["filename"] == "alu.vhd"

    def test_none_input_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_read_intent(None) is None

    def test_empty_input_returns_none(self, ai_buddy_mod):
        assert ai_buddy_mod.detect_read_intent("") is None

    def test_ask_ai_buddy_returns_read_file_type(self, ai_buddy_mod):
        res = ai_buddy_mod.ask_ai_buddy("explain adder.sv to me")
        assert res["type"] == "read_file"
        assert res["filename"] == "adder.sv"

    def test_read_intent_priority_over_edit(self, ai_buddy_mod):
        # "how does mux.sv work" should be read_file, not edit_file
        res = ai_buddy_mod.ask_ai_buddy("how does mux.sv work?")
        assert res["type"] == "read_file"


# ---------------------------------------------------------------------------
# project_context tests
# ---------------------------------------------------------------------------

class TestProjectContext:
    """Unit tests for project_context()."""

    def test_empty_dir_returns_empty_string(self, ai_buddy_mod, tmp_path):
        result = ai_buddy_mod.project_context(str(tmp_path))
        assert result == ""

    def test_detects_saxoflow_toml(self, ai_buddy_mod, tmp_path):
        (tmp_path / "saxoflow.toml").write_text("[project]", encoding="utf-8")
        result = ai_buddy_mod.project_context(str(tmp_path))
        assert "Project root" in result

    def test_detects_rtl_files(self, ai_buddy_mod, tmp_path):
        rtl_dir = tmp_path / "source" / "rtl" / "systemverilog"
        rtl_dir.mkdir(parents=True)
        (rtl_dir / "mux.sv").write_text("module mux; endmodule", encoding="utf-8")
        result = ai_buddy_mod.project_context(str(tmp_path))
        assert "mux.sv" in result
        assert "RTL" in result

    def test_detects_testbench_files(self, ai_buddy_mod, tmp_path):
        tb_dir = tmp_path / "source" / "tb" / "systemverilog"
        tb_dir.mkdir(parents=True)
        (tb_dir / "tb_mux.sv").write_text("// tb", encoding="utf-8")
        result = ai_buddy_mod.project_context(str(tmp_path))
        assert "tb_mux.sv" in result
        assert "Testbench" in result

    def test_detects_flat_hdl_files_without_unit_structure(self, ai_buddy_mod, tmp_path):
        (tmp_path / "adder.sv").write_text("// adder", encoding="utf-8")
        result = ai_buddy_mod.project_context(str(tmp_path))
        assert "adder.sv" in result

    def test_defaults_to_cwd(self, ai_buddy_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "test.sv").write_text("// x", encoding="utf-8")
        result = ai_buddy_mod.project_context()  # no cwd arg
        assert "test.sv" in result

    def test_context_injected_into_ask_ai_buddy(self, ai_buddy_mod, monkeypatch, tmp_path):
        """When context is passed to ask_ai_buddy, it appears in the prompt sent to the LLM."""
        (tmp_path / "mux.sv").write_text("module mux; endmodule", encoding="utf-8")
        ctx = ai_buddy_mod.project_context(str(tmp_path))
        assert "mux.sv" in ctx

        captured_prompts = []

        class FakeLLM:
            def invoke(self, prompt):
                captured_prompts.append(prompt)
                m = type("M", (), {"content": "pong"})()
                return m

        monkeypatch.setattr(
            ai_buddy_mod.ModelSelector, "get_model",
            lambda **_: FakeLLM(),
        )
        ai_buddy_mod.ask_ai_buddy("ping", context=ctx)
        assert any("mux.sv" in p for p in captured_prompts)


# ---------------------------------------------------------------------------
# handle_read_file integration tests
# ---------------------------------------------------------------------------

class TestHandleReadFile:
    """handle_read_file() end-to-end with mocked LLM."""

    def _setup_unit(self, tmp_path, unit="adder", filename="adder.sv",
                    content="module adder(input a, b, output c);\nassign c = a + b;\nendmodule"):
        unit_dir = tmp_path / unit / "source" / "rtl" / "systemverilog"
        unit_dir.mkdir(parents=True)
        f = unit_dir / filename
        f.write_text(content, encoding="utf-8")
        return f

    def test_returns_explanation_panel(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_explanation_for_file",
                   return_value="## Adder\nThis module adds two inputs."):
            result = file_ops_mod.handle_read_file(
                {"filename": "adder.sv", "question": "explain adder.sv"},
                history=[],
            )
        assert isinstance(result, Panel)

    def test_missing_filename_returns_text(self, file_ops_mod):
        result = file_ops_mod.handle_read_file(
            {"filename": "", "question": "explain"},
            history=[],
        )
        assert isinstance(result, Text)
        assert "filename" in result.plain.lower() or "not found" in result.plain.lower()

    def test_file_not_found_returns_yellow_text(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = file_ops_mod.handle_read_file(
            {"filename": "ghost.sv", "question": "explain ghost.sv"},
            history=[],
        )
        assert isinstance(result, Text)
        assert "not found" in result.plain.lower() or "ghost.sv" in result.plain

    def test_llm_failure_returns_error_text(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_explanation_for_file",
                   side_effect=RuntimeError("model timeout")):
            result = file_ops_mod.handle_read_file(
                {"filename": "adder.sv", "question": "explain adder.sv"},
                history=[],
            )
        assert isinstance(result, Text)
        assert "llm error" in result.plain.lower() or "timeout" in result.plain.lower()

    def test_finds_file_in_flat_cwd(self, file_ops_mod, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "standalone.sv").write_text("module s; endmodule", encoding="utf-8")
        with patch("cool_cli.file_ops.generate_explanation_for_file",
                   return_value="# Explanation"):
            result = file_ops_mod.handle_read_file(
                {"filename": "standalone.sv", "question": "explain standalone.sv"},
                history=[],
            )
        assert isinstance(result, Panel)

    def test_panel_title_contains_filename(self, file_ops_mod, tmp_path, monkeypatch):
        self._setup_unit(tmp_path)
        monkeypatch.chdir(tmp_path)
        with patch("cool_cli.file_ops.generate_explanation_for_file",
                   return_value="Short explanation."):
            result = file_ops_mod.handle_read_file(
                {"filename": "adder.sv", "question": "explain adder.sv"},
                history=[],
            )
        assert "adder.sv" in result.title


# ---------------------------------------------------------------------------
# Auto-fix loop in run_post_hook
# ---------------------------------------------------------------------------

class TestRunPostHookAutoFix:
    """Tests for the LLM-driven auto-fix loop in run_post_hook."""

    def _make_sv_file(self, tmp_path, content="module m; endmodule"):
        f = tmp_path / "module.sv"
        f.write_text(content, encoding="utf-8")
        return f

    def test_auto_fix_not_triggered_on_success(self, file_ops_mod, tmp_path):
        """When hook passes (exit 0), auto-fix loop must NOT fire."""
        import subprocess
        dest = self._make_sv_file(tmp_path)
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="pass\n", stderr="", returncode=0)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            with patch("cool_cli.file_ops.generate_patch_for_edit") as mock_patch:
                file_ops_mod.run_post_hook(tmp_path, "lint", dest_path=dest)
        mock_patch.assert_not_called()

    def test_auto_fix_triggers_on_error(self, file_ops_mod, tmp_path):
        """When hook fails, generate_patch_for_edit is called and file updated."""
        import subprocess
        original = "module m; endmodule"
        fixed = "module m_fixed; endmodule"
        dest = self._make_sv_file(tmp_path, original)

        call_count = {"runs": 0}

        def fake_run(cmd, cwd, capture_output, text, timeout):
            call_count["runs"] += 1
            if call_count["runs"] == 1:
                return MagicMock(stdout="ERROR: port missing\n", stderr="", returncode=1)
            return MagicMock(stdout="lint passed\n", stderr="", returncode=0)

        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.side_effect = fake_run
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            with patch("cool_cli.file_ops.generate_patch_for_edit",
                       return_value=fixed) as mock_patch:
                out = file_ops_mod.run_post_hook(
                    tmp_path, "lint", dest_path=dest, content_type="rtl"
                )

        mock_patch.assert_called_once()
        assert "fixed" in out.lower() or "attempt" in out.lower()
        assert dest.read_text(encoding="utf-8") == fixed

    def test_auto_fix_disabled_by_flag(self, file_ops_mod, tmp_path):
        """auto_fix=False must not trigger any LLM calls even on failure."""
        import subprocess
        dest = self._make_sv_file(tmp_path)
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="error\n", stderr="", returncode=1)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            with patch("cool_cli.file_ops.generate_patch_for_edit") as mock_patch:
                file_ops_mod.run_post_hook(
                    tmp_path, "sim", dest_path=dest, auto_fix=False
                )
        mock_patch.assert_not_called()

    def test_auto_fix_gives_up_after_max_retries(self, file_ops_mod, tmp_path):
        """If fix never works, report failure after max_retries attempts."""
        import subprocess
        dest = self._make_sv_file(tmp_path)
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(
                stdout="always fails\n", stderr="", returncode=1
            )
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            with patch("cool_cli.file_ops.generate_patch_for_edit",
                       return_value="module still_broken; endmodule"):
                out = file_ops_mod.run_post_hook(
                    tmp_path, "lint", dest_path=dest, _max_retries=2
                )
        assert "could not" in out.lower() or "attempt" in out.lower()

    def test_no_dest_path_no_auto_fix(self, file_ops_mod, tmp_path):
        """Without dest_path, auto-fix never activates (backward-compatible)."""
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="fail\n", stderr="", returncode=1)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            with patch("cool_cli.file_ops.generate_patch_for_edit") as mock_patch:
                file_ops_mod.run_post_hook(tmp_path, "lint")  # no dest_path
        mock_patch.assert_not_called()


# ---------------------------------------------------------------------------
# Git hook in run_post_hook
# ---------------------------------------------------------------------------

class TestRunPostHookGit:
    """Tests for the git snapshot hook."""

    def test_git_hook_success(self, file_ops_mod, tmp_path):
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.side_effect = [
                MagicMock(stdout="", stderr="", returncode=0),         # git add
                MagicMock(stdout="[main abc1234] ...", stderr="", returncode=0),  # git commit
            ]
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            out = file_ops_mod.run_post_hook(tmp_path, "git")
        assert "abc1234" in out or "main" in out

    def test_git_hook_add_fails(self, file_ops_mod, tmp_path):
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.return_value = MagicMock(stdout="", stderr="fatal: not a repo", returncode=1)
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            out = file_ops_mod.run_post_hook(tmp_path, "git")
        assert "git add failed" in out.lower() or "not a git repo" in out.lower()

    def test_git_not_found(self, file_ops_mod, tmp_path):
        import subprocess
        with patch("cool_cli.file_ops.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError
            mock_sub.TimeoutExpired = subprocess.TimeoutExpired
            out = file_ops_mod.run_post_hook(tmp_path, "git")
        assert "not found" in out.lower() or "git" in out.lower()


# ---------------------------------------------------------------------------
# Documentation export via detect_save_intent + generate_code_for_save
# ---------------------------------------------------------------------------

class TestDocExport:
    """Tests for the doc-export path: 'document X.sv' → Markdown spec."""

    def test_detect_save_intent_sets_doc_export_flag(self, ai_buddy_mod):
        r = ai_buddy_mod.detect_save_intent(
            "document mux.sv in unit mux"
        )
        assert r is not None
        assert r.get("doc_export") is True

    def test_ask_ai_buddy_sets_content_type_document(self, ai_buddy_mod):
        res = ai_buddy_mod.ask_ai_buddy("document adder.sv in unit adder")
        assert res["type"] == "save_file"
        assert res["content_type"] == "document"

    def test_generate_code_for_save_uses_doc_prompt(self, ai_buddy_mod, monkeypatch):
        """When content_type='document', the prompt mentions 'Markdown design spec'."""
        captured = []

        class FakeLLM:
            def invoke(self, prompt):
                captured.append(prompt)
                m = type("M", (), {"content": "# Spec\n| Port | ... |"})()
                return m

        monkeypatch.setattr(
            ai_buddy_mod.ModelSelector, "get_model",
            lambda **_: FakeLLM(),
        )
        ai_buddy_mod.generate_code_for_save(
            spec="document mux.sv in unit mux",
            content_type="document",
        )
        assert any("markdown" in p.lower() or "spec" in p.lower() for p in captured)
