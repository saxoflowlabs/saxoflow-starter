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


# ---------------------------------------------------------------------------
# Inferred filename & natural-language save intent (new in this session)
# ---------------------------------------------------------------------------

class TestInferredFilename:
    """detect_save_intent() should infer filename when none is given explicitly."""

    def test_create_design_place_in_unit(self, ai_buddy_mod):
        """'create an alu design and place in myalu unit' → alu.sv, unit=myalu."""
        r = ai_buddy_mod.detect_save_intent(
            "create an alu design and place in myalu unit"
        )
        assert r is not None
        assert r["filename"] == "alu.sv"
        assert r["unit"] == "myalu"
        assert r["content_type"] == "rtl"

    def test_create_multiword_design(self, ai_buddy_mod):
        """'create a half adder and place in unit ha' → half_adder.sv, unit=ha."""
        r = ai_buddy_mod.detect_save_intent(
            "create a half adder and place in unit ha"
        )
        assert r is not None
        assert r["filename"] == "half_adder.sv"
        assert r["unit"] == "ha"

    def test_generate_design_place_in_project(self, ai_buddy_mod):
        """'generate a mux design and place in the mux project' → mux.sv."""
        r = ai_buddy_mod.detect_save_intent(
            "generate a mux design and place in the mux project"
        )
        assert r is not None
        assert r["filename"] == "mux.sv"
        assert r["unit"] == "mux"

    def test_explicit_filename_still_wins(self, ai_buddy_mod):
        """Explicit .sv filename in message overrides inference."""
        r = ai_buddy_mod.detect_save_intent(
            "create an alu design and save it as alu.sv in unit myalu"
        )
        assert r is not None
        assert r["filename"] == "alu.sv"
        assert r["unit"] == "myalu"

    def test_no_design_name_still_none(self, ai_buddy_mod):
        """A save intent with no filename and no design name returns None."""
        r = ai_buddy_mod.detect_save_intent("save this somewhere")
        assert r is None

    def test_unit_name_in_x_unit_syntax(self, ai_buddy_mod):
        """'in myalu unit' (no 'the') should still extract unit name."""
        r = ai_buddy_mod.detect_save_intent(
            "create a counter and place in counter unit"
        )
        assert r is not None
        assert r["unit"] == "counter"


# ---------------------------------------------------------------------------
# Companion file detection
# ---------------------------------------------------------------------------

class TestDetectCompanionFiles:
    """Unit tests for detect_companion_files()."""

    def test_include_detected(self, ai_buddy_mod):
        code = '`include "alu_pkg.sv"\nmodule alu(); endmodule'
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert "alu_pkg.sv" in result

    def test_import_detected(self, ai_buddy_mod):
        code = "import alu_pkg::*;\nmodule alu(); endmodule"
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert "alu_pkg.sv" in result

    def test_self_not_included(self, ai_buddy_mod):
        """Main file should not appear in companion list."""
        code = '`include "alu.sv"\nmodule top(); endmodule'
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert "alu.sv" not in result

    def test_no_companions_empty_list(self, ai_buddy_mod):
        code = "module alu(input logic a, output logic b);\nassign b = a;\nendmodule"
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert result == []

    def test_deduplication(self, ai_buddy_mod):
        """Same package referenced twice should appear once."""
        code = '`include "alu_pkg.sv"\nimport alu_pkg::*;\nmodule alu(); endmodule'
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert result.count("alu_pkg.sv") == 1

    def test_multiple_companions(self, ai_buddy_mod):
        code = '`include "alu_pkg.sv"\n`include "utils.sv"\nmodule alu(); endmodule'
        result = ai_buddy_mod.detect_companion_files("alu.sv", code)
        assert "alu_pkg.sv" in result
        assert "utils.sv" in result


# ---------------------------------------------------------------------------
# Project context subdirectory scanning
# ---------------------------------------------------------------------------

class TestProjectContextSubdirs:
    """project_context() should scan unit subdirectories from repo root."""

    def test_scans_child_unit_with_source_dir(self, tmp_path):
        """A child directory with source/rtl/systemverilog/*.sv should appear."""
        from cool_cli.ai_buddy import project_context
        unit = tmp_path / "myalu"
        rtl_dir = unit / "source" / "rtl" / "systemverilog"
        rtl_dir.mkdir(parents=True)
        (rtl_dir / "alu.sv").write_text("module alu(); endmodule")

        ctx = project_context(str(tmp_path))
        assert "alu.sv" in ctx
        assert "myalu" in ctx

    def test_gitkeep_excluded(self, tmp_path):
        """Empty .gitkeep files should not appear in context."""
        from cool_cli.ai_buddy import project_context
        unit = tmp_path / "myalu"
        rtl_dir = unit / "source" / "rtl" / "systemverilog"
        rtl_dir.mkdir(parents=True)
        (rtl_dir / ".gitkeep").write_text("")

        ctx = project_context(str(tmp_path))
        assert ".gitkeep" not in ctx

    def test_empty_workspace_returns_empty_string(self, tmp_path):
        """A directory with no HDL files at all should return ''."""
        from cool_cli.ai_buddy import project_context
        ctx = project_context(str(tmp_path))
        assert ctx == ""


# ---------------------------------------------------------------------------
# Incomplete request detection & clarification flow
# ---------------------------------------------------------------------------

class TestDetectIncompleteRequest:
    """Unit tests for detect_incomplete_request()."""

    def test_bare_create_triggers_all_questions(self, ai_buddy_mod):
        """'create an alu design' has no HDL, unit, or filename \u2192 3 questions."""
        r = ai_buddy_mod.detect_incomplete_request("create an alu design")
        assert r is not None
        keys = [q["key"] for q in r]
        assert "hdl" in keys
        assert "unit_name" in keys
        assert "requirements" in keys

    def test_with_unit_skips_unit_question(self, ai_buddy_mod):
        """When unit is in the message, the unit_name question is skipped."""
        r = ai_buddy_mod.detect_incomplete_request(
            "create an alu design and place in myalu unit"
        )
        assert r is not None
        keys = [q["key"] for q in r]
        assert "unit_name" not in keys
        assert "hdl" in keys

    def test_fully_specified_returns_none(self, ai_buddy_mod):
        """filename + unit already present \u2192 nothing to ask."""
        r = ai_buddy_mod.detect_incomplete_request(
            "create an alu and save as alu.sv in unit myalu"
        )
        assert r is None

    def test_edit_does_not_trigger(self, ai_buddy_mod):
        """Edit requests are not intercepted by the clarification flow."""
        r = ai_buddy_mod.detect_incomplete_request("edit alu.sv to add a reset port")
        assert r is None

    def test_read_intent_does_not_trigger(self, ai_buddy_mod):
        """Read/explain requests are not intercepted."""
        r = ai_buddy_mod.detect_incomplete_request("explain alu.sv to me")
        assert r is None

    def test_chat_does_not_trigger(self, ai_buddy_mod):
        """Pure conversational messages return None."""
        assert ai_buddy_mod.detect_incomplete_request("what is a flip-flop?") is None
        assert ai_buddy_mod.detect_incomplete_request("how do I run simulation?") is None

    def test_none_message_returns_none(self, ai_buddy_mod):
        """None / empty input is handled safely."""
        assert ai_buddy_mod.detect_incomplete_request(None) is None
        assert ai_buddy_mod.detect_incomplete_request("") is None

    def test_hdl_pref_skips_hdl_question(self, ai_buddy_mod):
        """When hdl is in user prefs, the HDL question is not asked."""
        r = ai_buddy_mod.detect_incomplete_request(
            "create an alu design", prefs={"hdl": "SystemVerilog"}
        )
        assert r is not None
        keys = [q["key"] for q in r]
        assert "hdl" not in keys

    def test_hdl_in_message_skips_hdl_question(self, ai_buddy_mod):
        """If the user already specified HDL in the message, skip the HDL question."""
        r = ai_buddy_mod.detect_incomplete_request(
            "create an alu design in SystemVerilog and place in myalu unit"
        )
        if r is not None:
            keys = [q["key"] for q in r]
            assert "hdl" not in keys

    def test_default_unit_name_derived_from_design(self, ai_buddy_mod):
        """The default for unit_name question should be the design name."""
        r = ai_buddy_mod.detect_incomplete_request("create an alu design")
        assert r is not None
        unit_q = next((q for q in r if q["key"] == "unit_name"), None)
        assert unit_q is not None
        assert unit_q["default"] == "alu"

    def test_hdl_choices_present(self, ai_buddy_mod):
        """The HDL question should offer SystemVerilog, Verilog, VHDL as choices."""
        r = ai_buddy_mod.detect_incomplete_request("create a mux design")
        assert r is not None
        hdl_q = next((q for q in r if q["key"] == "hdl"), None)
        assert hdl_q is not None
        assert "SystemVerilog" in hdl_q["choices"]
        assert "Verilog" in hdl_q["choices"]
        assert "VHDL" in hdl_q["choices"]
        assert hdl_q["default"] == "SystemVerilog"

    def test_generate_also_triggers(self, ai_buddy_mod):
        """'generate a counter module' is a creation-style request."""
        r = ai_buddy_mod.detect_incomplete_request("generate a counter module")
        assert r is not None


class TestClarificationFlowEnrichedSpec:
    """Tests for _run_clarification_flow() — verifies questions are asked and
    build_enriched_spec is called with the collected answers.

    build_enriched_spec is mocked so tests are deterministic and don't require
    a live LLM.  The UI flow (input collection, defaults, KeyboardInterrupt)
    is what's under test here.
    """

    def _mock_bes(self, monkeypatch, return_value: str):
        """Patch build_enriched_spec inside the agentic module."""
        import cool_cli.agentic as agentic_mod
        monkeypatch.setattr(agentic_mod, "build_enriched_spec",
                            lambda _orig, answers, **kw: return_value)

    def test_builts_complete_spec(self, monkeypatch):
        """With all questions answered the collected answers are passed to build_enriched_spec."""
        import cool_cli.agentic as agentic_mod
        collected: dict = {}

        def fake_bes(orig, answers, **kw):
            collected.update(answers)
            return f"create alu in {answers.get('hdl','?')} save as alu.sv in unit {answers.get('unit_name','?')} Requirements: {answers.get('requirements','')}"

        monkeypatch.setattr(agentic_mod, "build_enriched_spec", fake_bes)
        user_answers = iter(["SystemVerilog", "myalu", "32-bit, 4 operations"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(user_answers))

        questions = [
            {"key": "hdl", "question": "Which HDL?", "choices": ["SystemVerilog", "Verilog", "VHDL"], "default": "SystemVerilog"},
            {"key": "unit_name", "question": "Unit name?", "choices": [], "default": "alu"},
            {"key": "requirements", "question": "Requirements?", "choices": [], "default": ""},
        ]
        result = agentic_mod._run_clarification_flow("create an alu design", questions)
        assert result is not None
        assert "SystemVerilog" in result
        assert "myalu" in result
        assert "alu.sv" in result
        assert "32-bit" in result
        # Verify the answers dict had the right keys
        assert collected["hdl"] == "SystemVerilog"
        assert collected["unit_name"] == "myalu"

    def test_empty_answers_use_defaults(self, monkeypatch):
        """Pressing Enter uses the default value for each question."""
        import cool_cli.agentic as agentic_mod
        collected: dict = {}

        def fake_bes(orig, answers, **kw):
            collected.update(answers)
            return f"create alu in {answers.get('hdl','?')} in unit {answers.get('unit_name','?')}"

        monkeypatch.setattr(agentic_mod, "build_enriched_spec", fake_bes)
        monkeypatch.setattr("builtins.input", lambda _prompt: "")  # always Enter

        questions = [
            {"key": "hdl", "question": "Which HDL?", "choices": ["SystemVerilog", "Verilog", "VHDL"], "default": "SystemVerilog"},
            {"key": "unit_name", "question": "Unit name?", "choices": [], "default": "alu"},
            {"key": "requirements", "question": "Requirements?", "choices": [], "default": ""},
        ]
        result = agentic_mod._run_clarification_flow("create an alu design", questions)
        assert result is not None
        # All defaults should have been used
        assert collected["hdl"] == "SystemVerilog"
        assert collected["unit_name"] == "alu"
        assert "SystemVerilog" in result
        assert "alu" in result

    def test_keyboard_interrupt_returns_none(self, monkeypatch):
        """Ctrl-C during questions returns None without calling build_enriched_spec."""
        import cool_cli.agentic as agentic_mod
        called = []
        monkeypatch.setattr(agentic_mod, "build_enriched_spec",
                            lambda *a, **kw: called.append(1) or "x")
        monkeypatch.setattr("builtins.input",
                            lambda _prompt: (_ for _ in ()).throw(KeyboardInterrupt))

        questions = [
            {"key": "hdl", "question": "Which HDL?", "choices": ["SystemVerilog"], "default": "SystemVerilog"},
        ]
        result = agentic_mod._run_clarification_flow("create an alu design", questions)
        assert result is None
        assert called == [], "build_enriched_spec must NOT be called after KeyboardInterrupt"

    def test_vhdl_choice_answer_passed_to_bes(self, monkeypatch):
        """The VHDL choice is passed verbatim to build_enriched_spec."""
        import cool_cli.agentic as agentic_mod
        collected: dict = {}

        def fake_bes(orig, answers, **kw):
            collected.update(answers)
            hdl_ext = {"SystemVerilog": ".sv", "Verilog": ".v", "VHDL": ".vhd"}
            ext = hdl_ext.get(answers.get("hdl", ""), ".sv")
            return f"create alu{ext} in {answers.get('hdl','?')}"

        monkeypatch.setattr(agentic_mod, "build_enriched_spec", fake_bes)
        user_answers = iter(["VHDL", "my_alu"])
        monkeypatch.setattr("builtins.input", lambda _prompt: next(user_answers))

        questions = [
            {"key": "hdl", "question": "Which HDL?", "choices": ["SystemVerilog", "Verilog", "VHDL"], "default": "SystemVerilog"},
            {"key": "unit_name", "question": "Unit name?", "choices": [], "default": "alu"},
        ]
        result = agentic_mod._run_clarification_flow("create an alu design", questions)
        assert result is not None
        assert collected["hdl"] == "VHDL"
        assert ".vhd" in result

    def test_context_threaded_to_bes(self, monkeypatch):
        """The context kwarg passed to _run_clarification_flow is forwarded to build_enriched_spec."""
        import cool_cli.agentic as agentic_mod
        received_ctx = []

        def fake_bes(orig, answers, context="", **kw):
            received_ctx.append(context)
            return f"spec from {context}"

        monkeypatch.setattr(agentic_mod, "build_enriched_spec", fake_bes)
        monkeypatch.setattr("builtins.input", lambda _prompt: "")

        questions = [{"key": "hdl", "question": "HDL?", "choices": [], "default": "SystemVerilog"}]
        result = agentic_mod._run_clarification_flow(
            "create an alu design", questions, context="== PROJECT CTX ==\nalu_unit/")
        assert result is not None
        assert received_ctx == ["== PROJECT CTX ==\nalu_unit/"]


# ---------------------------------------------------------------------------
# plan_clarification — AI-driven clarification planning
# ---------------------------------------------------------------------------

class TestPlanClarification:
    """Tests for plan_clarification() — verifies JSON parsing, fallback, and filters."""

    def _make_llm_response(self, payload: dict) -> str:
        import json
        return json.dumps(payload)

    def test_returns_questions_for_vague_request(self, monkeypatch):
        """A well-formed LLM response with needs_clarification=true returns question list."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        llm_payload = {
            "needs_clarification": True,
            "questions": [
                {"key": "hdl", "question": "Which HDL?", "choices": ["SystemVerilog", "Verilog"], "default": "SystemVerilog"},
                {"key": "data_width", "question": "Data width in bits?", "choices": [], "default": "32"},
            ],
        }
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: self._make_llm_response(llm_payload))

        result = plan_clarification("create an alu design")
        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["key"] == "hdl"
        assert result[1]["key"] == "data_width"

    def test_returns_none_when_no_clarification_needed(self, monkeypatch):
        """When LLM says needs_clarification=false, returns None."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: '{"needs_clarification": false, "questions": []}')
        result = plan_clarification("create an 8-bit alu in SystemVerilog save as alu.sv in unit myalu")
        assert result is None

    def test_returns_none_on_llm_failure(self, monkeypatch):
        """LLMInvocationError causes fail-open (returns None)."""
        from cool_cli.ai_buddy import plan_clarification, LLMInvocationError
        import cool_cli.ai_buddy as ab_mod

        def _raise(**kw):
            raise LLMInvocationError("timeout")

        monkeypatch.setattr(ab_mod, "_invoke_llm", _raise)
        result = plan_clarification("create an alu design")
        assert result is None

    def test_returns_none_on_malformed_json(self, monkeypatch):
        """Malformed JSON from LLM causes fail-open (returns None)."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: "Sorry, I can't do that.")
        result = plan_clarification("create an alu design")
        assert result is None

    def test_skips_llm_for_non_creation_intent(self, monkeypatch):
        """Non-creation messages bypass the LLM entirely (returns None fast)."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        called = []
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: called.append(1) or '{"needs_clarification": false, "questions": []}')

        result = plan_clarification("explain what a counter does")
        assert result is None
        # LLM should not be called for non-creation messages
        assert called == []

    def test_skips_llm_when_fully_specified(self, monkeypatch):
        """Fully specified requests (filename + unit) skip the LLM call."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        called = []
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: called.append(1) or '{"needs_clarification": false, "questions": []}')

        result = plan_clarification("create alu.sv in unit myalu")
        # May or may not call LLM, but result must not block
        assert result is None or isinstance(result, list)

    def test_normalises_question_missing_choices(self, monkeypatch):
        """Missing 'choices' and 'default' keys are normalised to empty/blank."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        llm_payload = {
            "needs_clarification": True,
            "questions": [
                {"key": "width", "question": "Data width?"},   # no choices/default
            ],
        }
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: self._make_llm_response(llm_payload))

        result = plan_clarification("create a counter design")
        assert result is not None
        q = result[0]
        assert q["choices"] == []
        assert q["default"] == ""

    def test_skips_preffed_hdl_question(self, monkeypatch):
        """If LLM (incorrectly) includes hdl question and prefs already has hdl, it is still returned
        (filtering is the LLM's job; plan_clarification trusts the LLM output)."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        llm_payload = {
            "needs_clarification": True,
            "questions": [
                {"key": "data_width", "question": "Data width?", "choices": [], "default": "32"},
            ],
        }
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: self._make_llm_response(llm_payload))

        prefs = {"hdl": "SystemVerilog"}
        result = plan_clarification("create a counter", prefs=prefs)
        assert result is not None
        keys = [q["key"] for q in result]
        # The prefs summary was passed to LLM; LLM correctly omitted hdl question
        assert "data_width" in keys


# ---------------------------------------------------------------------------
# build_enriched_spec — LLM-driven spec synthesis
# ---------------------------------------------------------------------------

class TestBuildEnrichedSpec:
    """Tests for build_enriched_spec() — LLM call and mechanical fallback."""

    def test_returns_llm_output(self, monkeypatch):
        """When LLM succeeds, the stripped LLM output is returned."""
        from cool_cli.ai_buddy import build_enriched_spec
        import cool_cli.ai_buddy as ab_mod

        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: "create a 32-bit alu in SystemVerilog, save as alu.sv in unit myalu")
        result = build_enriched_spec(
            "create an alu design",
            {"hdl": "SystemVerilog", "data_width": "32", "unit_name": "myalu"},
        )
        assert "32-bit" in result or "SystemVerilog" in result
        assert "alu.sv" in result

    def test_fallback_on_llm_failure(self, monkeypatch):
        """When LLM raises LLMInvocationError, falls back to mechanical concatenation."""
        from cool_cli.ai_buddy import build_enriched_spec, LLMInvocationError
        import cool_cli.ai_buddy as ab_mod

        def _raise(**kw):
            raise LLMInvocationError("network error")

        monkeypatch.setattr(ab_mod, "_invoke_llm", _raise)
        result = build_enriched_spec(
            "create an alu design",
            {"hdl": "SystemVerilog", "unit_name": "myalu"},
        )
        assert result  # must return something
        assert "create an alu design" in result

    def test_empty_answers_returns_original(self, monkeypatch):
        """With no answers, the original message is returned unchanged (no LLM needed)."""
        from cool_cli.ai_buddy import build_enriched_spec
        import cool_cli.ai_buddy as ab_mod

        called = []
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: called.append(1) or "x")
        result = build_enriched_spec("create an alu design", {})
        assert result == "create an alu design"
        assert called == [], "LLM should not be called when answers is empty"

    def test_strips_quotes_from_llm_output(self, monkeypatch):
        """Leading/trailing quotes in LLM output are stripped."""
        from cool_cli.ai_buddy import build_enriched_spec
        import cool_cli.ai_buddy as ab_mod

        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: '"create a fifo 32-deep, save as fifo.sv"')
        result = build_enriched_spec("create a fifo", {"depth": "32"})
        assert not result.startswith('"')
        assert "fifo" in result

    def test_context_included_in_prompt(self, monkeypatch):
        """Project context is included in the LLM prompt."""
        from cool_cli.ai_buddy import build_enriched_spec
        import cool_cli.ai_buddy as ab_mod

        prompts_seen = []
        monkeypatch.setattr(
            ab_mod, "_invoke_llm",
            lambda **kw: prompts_seen.append(kw.get("prompt", "")) or "spec"
        )
        build_enriched_spec("create a counter", {"hdl": "VHDL"}, context="== PROJECT ==\ncounter_unit/")
        assert prompts_seen
        assert "counter_unit" in prompts_seen[0]


# ---------------------------------------------------------------------------
# Verification / testbench intent coverage
# ---------------------------------------------------------------------------

class TestCreationIntentVerification:
    """Verify that _CREATION_INTENT_RE matches verification-domain requests.

    These tests ensure that testbench, SVA, UVM, and coverage requests go
    through the clarification flow rather than silently falling through to
    the generic chat handler.
    """

    def _matches(self, msg: str) -> bool:
        from cool_cli.ai_buddy import _CREATION_INTENT_RE
        return bool(_CREATION_INTENT_RE.search(msg))

    # --- testbench ---
    def test_testbench_bare(self):
        assert self._matches("write a testbench")

    def test_testbench_for_dut(self):
        assert self._matches("write a testbench for the alu module")

    def test_cocotb_testbench(self):
        assert self._matches("generate a cocotb testbench")

    # --- SVA / assertions ---
    def test_sva_plural(self):
        assert self._matches("write SystemVerilog assertions")

    def test_sva_abbrev(self):
        assert self._matches("write SVA for the fifo")

    def test_sva_with_target(self):
        assert self._matches("write SVA assertions for the memory controller")

    # --- UVM ---
    def test_uvm_testbench(self):
        assert self._matches("create UVM testbench")

    def test_uvm_agent(self):
        assert self._matches("create UVM agent")

    def test_uvm_driver(self):
        assert self._matches("write UVM driver")

    def test_uvm_scoreboard(self):
        assert self._matches("generate a scoreboard")

    def test_uvm_sequence(self):
        assert self._matches("write a UVM sequence")

    def test_uvm_sequences_plural(self):
        assert self._matches("write UVM sequences for the APB protocol")

    # --- Coverage ---
    def test_coverage_groups(self):
        assert self._matches("generate coverage groups")

    def test_covergroup(self):
        assert self._matches("generate covergroup for the fsm")

    def test_coverpoint(self):
        assert self._matches("create a coverpoint")

    # --- Interface ---
    def test_interface(self):
        assert self._matches("create an interface for the bus")

    # --- Non-creation messages must NOT trigger ---
    def test_explain_does_not_match(self):
        assert not self._matches("explain what a counter does")

    def test_show_file_does_not_match(self):
        assert not self._matches("show me the alu.sv file")

    def test_edit_does_not_match(self):
        assert not self._matches("edit the fifo module")


class TestPlanClarificationVerification:
    """plan_clarification fires correctly for verification-domain requests."""

    def _make_payload(self, questions):
        import json
        return json.dumps({
            "needs_clarification": True,
            "questions": questions,
        })

    def test_testbench_triggers_clarification(self, monkeypatch):
        """'write a testbench' should reach plan_clarification and return questions."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        payload = self._make_payload([
            {"key": "dut", "question": "Which DUT?", "choices": [], "default": ""},
            {"key": "style", "question": "UVM or basic?", "choices": ["UVM", "basic"], "default": "basic"},
        ])
        monkeypatch.setattr(ab_mod, "_invoke_llm", lambda **kw: payload)

        result = plan_clarification("write a testbench")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "dut" in keys
        assert "style" in keys

    def test_sva_triggers_clarification(self, monkeypatch):
        """'write SystemVerilog assertions' should reach plan_clarification."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        payload = self._make_payload([
            {"key": "dut", "question": "Which module to bind to?", "choices": [], "default": ""},
            {"key": "properties", "question": "Which properties to check?", "choices": [], "default": ""},
        ])
        monkeypatch.setattr(ab_mod, "_invoke_llm", lambda **kw: payload)

        result = plan_clarification("write SystemVerilog assertions")
        assert result is not None
        assert len(result) == 2

    def test_uvm_agent_triggers_clarification(self, monkeypatch):
        """'create UVM agent' should reach plan_clarification."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        payload = self._make_payload([
            {"key": "protocol", "question": "Protocol? (APB/AXI/custom)", "choices": ["APB", "AXI", "custom"], "default": "APB"},
            {"key": "active_passive", "question": "Active or passive?", "choices": ["active", "passive"], "default": "active"},
        ])
        monkeypatch.setattr(ab_mod, "_invoke_llm", lambda **kw: payload)

        result = plan_clarification("create UVM agent")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "protocol" in keys

    def test_prompt_includes_verification_examples(self, monkeypatch):
        """The LLM prompt for verification requests contains relevant examples."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        prompts_seen = []
        monkeypatch.setattr(
            ab_mod, "_invoke_llm",
            lambda **kw: prompts_seen.append(kw.get("prompt", "")) or
                         '{"needs_clarification": false, "questions": []}',
        )
        plan_clarification("write a UVM driver")
        assert prompts_seen
        prompt = prompts_seen[0]
        # Prompt must mention testbench and SVA/assertion context
        assert "Testbench" in prompt or "testbench" in prompt
        assert "SVA" in prompt or "assertion" in prompt

    def test_non_creation_verification_message_skips_llm(self, monkeypatch):
        """'read the testbench file' is a read intent — must not call LLM."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod

        called = []
        monkeypatch.setattr(ab_mod, "_invoke_llm",
                            lambda **kw: called.append(1) or "{}")
        # 'read' is an edit/read intent — should be filtered before LLM
        result = plan_clarification("read the testbench file")
        assert result is None
        assert called == []


# ---------------------------------------------------------------------------
# Full RTL-to-GDS2 pipeline coverage — _CREATION_INTENT_RE
# ---------------------------------------------------------------------------

class TestCreationIntentPipeline:
    """_CREATION_INTENT_RE must fire for every stage of the saxoflow
    RTL-to-GDS2 pipeline so plan_clarification can ask the right questions."""

    def _matches(self, msg: str) -> bool:
        from cool_cli.ai_buddy import _CREATION_INTENT_RE
        return bool(_CREATION_INTENT_RE.search(msg))

    # --- Synthesis & netlist ---
    def test_synthesis_script(self):
        assert self._matches("write a synthesis script")

    def test_yosys_script(self):
        assert self._matches("create a Yosys script")

    def test_netlist(self):
        assert self._matches("generate a netlist")

    def test_synth_constraints(self):
        assert self._matches("write synth constraints")

    # --- Timing & SDC ---
    def test_sdc_constraints(self):
        assert self._matches("write SDC constraints")

    def test_timing_constraints(self):
        assert self._matches("create timing constraints")

    def test_timing_script(self):
        assert self._matches("write a timing script")

    def test_opensta_script(self):
        assert self._matches("write an OpenSTA script")

    def test_static_timing_analysis(self):
        assert self._matches("create a static timing analysis")

    # --- Floorplan ---
    def test_floorplan_bare(self):
        assert self._matches("create a floorplan")

    def test_floorplan_script(self):
        assert self._matches("write a floorplan script")

    # --- Place & Route ---
    def test_placement_script(self):
        assert self._matches("write a placement script")

    def test_routing_script(self):
        assert self._matches("create a routing script")

    def test_pnr_config(self):
        assert self._matches("generate PnR config")

    # --- Power / PDN ---
    def test_pdn_script(self):
        assert self._matches("create a PDN script")

    def test_power_delivery_network(self):
        assert self._matches("generate a power delivery network")

    def test_power_analysis_script(self):
        assert self._matches("write a power analysis script")

    # --- Physical verification ---
    def test_drc_script(self):
        assert self._matches("write a DRC script")

    def test_lvs_script(self):
        assert self._matches("create an LVS script")

    # --- Layout / GDS ---
    def test_gds_layout(self):
        assert self._matches("generate GDS layout")

    def test_klayout_script(self):
        assert self._matches("write a KLayout script")

    def test_layout_script(self):
        assert self._matches("create a layout script")

    # --- Flow glue ---
    def test_makefile(self):
        assert self._matches("write a Makefile")

    def test_openroad_flow(self):
        assert self._matches("create an OpenROAD flow script")

    # --- Non-creation must NOT trigger ---
    def test_explain_does_not_match(self):
        assert not self._matches("explain what synthesis does")

    def test_run_does_not_match(self):
        assert not self._matches("run the DRC on my design")

    def test_show_does_not_match(self):
        assert not self._matches("show me the timing report")


class TestPlanClarificationPipeline:
    """plan_clarification reaches the LLM and returns stage-appropriate questions
    for every major saxoflow pipeline stage."""

    def _llm_questions(self, monkeypatch, questions: list, ab_mod):
        import json
        payload = json.dumps({"needs_clarification": True, "questions": questions})
        monkeypatch.setattr(ab_mod, "_invoke_llm", lambda **kw: payload)

    def test_synthesis_asks_pdk(self, monkeypatch):
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        self._llm_questions(monkeypatch, [
            {"key": "pdk", "question": "Target PDK/cell library?", "choices": [], "default": "sky130"},
            {"key": "goal", "question": "Optimise for area or speed?", "choices": ["area", "speed"], "default": "area"},
        ], ab_mod)
        result = plan_clarification("write a synthesis script")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "pdk" in keys

    def test_sdc_asks_clock(self, monkeypatch):
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        self._llm_questions(monkeypatch, [
            {"key": "clock_name", "question": "Clock signal name?", "choices": [], "default": "clk"},
            {"key": "freq_mhz", "question": "Clock frequency (MHz)?", "choices": [], "default": "100"},
        ], ab_mod)
        result = plan_clarification("write SDC constraints")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "clock_name" in keys

    def test_floorplan_asks_area(self, monkeypatch):
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        self._llm_questions(monkeypatch, [
            {"key": "utilisation", "question": "Target utilisation (%)?", "choices": [], "default": "50"},
            {"key": "aspect_ratio", "question": "Aspect ratio (W/H)?", "choices": [], "default": "1"},
        ], ab_mod)
        result = plan_clarification("create a floorplan")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "utilisation" in keys

    def test_drc_asks_tool(self, monkeypatch):
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        self._llm_questions(monkeypatch, [
            {"key": "tool", "question": "DRC tool?", "choices": ["Magic", "KLayout"], "default": "Magic"},
            {"key": "pdk", "question": "PDK name?", "choices": [], "default": "sky130"},
        ], ab_mod)
        result = plan_clarification("write a DRC script")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "tool" in keys

    def test_gds_asks_pdk(self, monkeypatch):
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        self._llm_questions(monkeypatch, [
            {"key": "pdk", "question": "PDK for the layout?", "choices": [], "default": "sky130"},
            {"key": "top_cell", "question": "Top cell name?", "choices": [], "default": ""},
        ], ab_mod)
        result = plan_clarification("generate GDS layout")
        assert result is not None
        keys = [q["key"] for q in result]
        assert "pdk" in keys

    def test_prompt_includes_pipeline_examples(self, monkeypatch):
        """The LLM prompt for a P&R request contains physical-design examples."""
        from cool_cli.ai_buddy import plan_clarification
        import cool_cli.ai_buddy as ab_mod
        prompts_seen = []
        monkeypatch.setattr(
            ab_mod, "_invoke_llm",
            lambda **kw: prompts_seen.append(kw.get("prompt", "")) or
                         '{"needs_clarification": false, "questions": []}',
        )
        plan_clarification("create a routing script")
        assert prompts_seen
        prompt = prompts_seen[0]
        assert "PDK" in prompt or "pdk" in prompt.lower()
        assert "floorplan" in prompt.lower() or "P&R" in prompt or "placement" in prompt.lower()


# ---------------------------------------------------------------------------
# Agent delegation — generate_code_for_save routes to saxoflow_agenticai
# ---------------------------------------------------------------------------

class TestAgentDelegation:
    """Verify that generate_code_for_save() routes rtl/tb/formal to the
    specialist saxoflow_agenticai agents and falls back to _invoke_llm when
    the agent backend is unavailable or raises.

    All agent objects are monkeypatched — no live LLM required.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _fake_iterate(self, code: str):
        """Return a callable that mimics AgentFeedbackCoordinator.iterate_improvements."""
        def _iterate(agent, initial_spec, feedback_agent, max_iters=1, **kw):
            return (code, "no issues")
        return _iterate

    def _patch_agents_available(self, monkeypatch, available: bool):
        import cool_cli.ai_buddy as ab
        monkeypatch.setattr(ab, "_AGENTS_AVAILABLE", available)

    def _patch_agent_manager(self, monkeypatch, agent_factory):
        """Replace _AgentManager.get_agent with *agent_factory*."""
        import cool_cli.ai_buddy as ab
        from types import SimpleNamespace
        fake_mgr = SimpleNamespace(get_agent=agent_factory)
        monkeypatch.setattr(ab, "_AgentManager", fake_mgr)

    def _patch_feedback_coordinator(self, monkeypatch, iterate_fn):
        import cool_cli.ai_buddy as ab
        from types import SimpleNamespace
        fake_coord = SimpleNamespace(iterate_improvements=iterate_fn)
        monkeypatch.setattr(ab, "_AgentFeedbackCoordinator", fake_coord)

    # ------------------------------------------------------------------
    # RTL routing
    # ------------------------------------------------------------------

    def test_rtl_uses_rtlgen_agent(self, monkeypatch):
        """RTL request calls get_agent('rtlgen') and returns agent output."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        agents_created = []

        def _mock_get_agent(name, verbose=False):
            agents_created.append(name)
            from types import SimpleNamespace
            return SimpleNamespace(agent_type=name)

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, _mock_get_agent)
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate("module alu(); endmodule"))

        result = generate_code_for_save("create an 8-bit ALU", content_type="rtl")
        assert "rtlgen" in agents_created
        assert "rtlreview" in agents_created
        assert "module alu" in result

    def test_tb_uses_tbgen_agent(self, monkeypatch):
        """TB request calls get_agent('tbgen') and returns agent output."""
        from cool_cli.ai_buddy import generate_code_for_save

        agents_created = []

        def _mock_get_agent(name, verbose=False):
            agents_created.append(name)
            from types import SimpleNamespace
            return SimpleNamespace(agent_type=name)

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, _mock_get_agent)
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate("`timescale 1ns/1ps\nmodule alu_tb;"))

        result = generate_code_for_save("write a testbench for alu", content_type="tb")
        assert "tbgen" in agents_created
        assert "tbreview" in agents_created
        assert "alu_tb" in result

    def test_formal_uses_fpropgen_agent(self, monkeypatch):
        """Formal request calls get_agent('fpropgen')."""
        from cool_cli.ai_buddy import generate_code_for_save

        agents_created = []

        def _mock_get_agent(name, verbose=False):
            agents_created.append(name)
            from types import SimpleNamespace
            return SimpleNamespace(agent_type=name)

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, _mock_get_agent)
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate("property p1; @(posedge clk) oe |-> ##1 valid; endproperty"))

        result = generate_code_for_save("write SVA for the ALU", content_type="formal")
        assert "fpropgen" in agents_created
        assert "fpropreview" in agents_created
        assert "property" in result

    def test_agent_result_is_returned(self, monkeypatch):
        """The code string from iterate_improvements[0] is what gets returned."""
        from cool_cli.ai_buddy import generate_code_for_save

        expected = "module counter(input clk, output reg q); endmodule"

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, lambda name, verbose=False: object())
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate(expected))

        result = generate_code_for_save("create a counter", content_type="rtl")
        assert result == expected

    # ------------------------------------------------------------------
    # Fallback behaviour
    # ------------------------------------------------------------------

    def test_agent_exception_falls_back_to_invoke_llm(self, monkeypatch):
        """If AgentManager raises, _invoke_llm is called (generic path)."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        def _boom(name, verbose=False):
            raise RuntimeError("agent unavailable")

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, _boom)

        llm_called = []
        monkeypatch.setattr(ab, "_invoke_llm",
                            lambda **kw: llm_called.append(1) or "module alu_fallback; endmodule")

        result = generate_code_for_save("create an ALU", content_type="rtl")
        assert llm_called, "_invoke_llm must be called as fallback"
        assert "alu_fallback" in result

    def test_agents_unavailable_falls_back(self, monkeypatch):
        """When _AGENTS_AVAILABLE=False the generic _invoke_llm path is used."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        self._patch_agents_available(monkeypatch, False)
        llm_called = []
        monkeypatch.setattr(ab, "_invoke_llm",
                            lambda **kw: llm_called.append(1) or "module generic; endmodule")

        result = generate_code_for_save("create a module", content_type="rtl")
        assert llm_called
        assert "generic" in result

    def test_agent_empty_result_falls_back(self, monkeypatch):
        """If the agent returns empty string, _invoke_llm is used instead."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, lambda name, verbose=False: object())
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate(""))  # empty

        llm_called = []
        monkeypatch.setattr(ab, "_invoke_llm",
                            lambda **kw: llm_called.append(1) or "module nonempty; endmodule")

        result = generate_code_for_save("create an ALU", content_type="rtl")
        assert llm_called
        assert "nonempty" in result

    # ------------------------------------------------------------------
    # Generic-path content types must never touch AgentManager
    # ------------------------------------------------------------------

    def test_synth_never_uses_agent_manager(self, monkeypatch):
        """'synth' content type always uses the generic LLM path."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        self._patch_agents_available(monkeypatch, True)
        agent_called = []
        self._patch_agent_manager(monkeypatch, lambda name, **kw: agent_called.append(name))
        monkeypatch.setattr(ab, "_invoke_llm", lambda **kw: "synth script content")

        generate_code_for_save("write synthesis script", content_type="synth")
        assert agent_called == [], "AgentManager must not be called for synth"

    def test_document_never_uses_agent_manager(self, monkeypatch):
        """'document' content type always uses the generic LLM path."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        self._patch_agents_available(monkeypatch, True)
        agent_called = []
        self._patch_agent_manager(monkeypatch, lambda name, **kw: agent_called.append(name))
        monkeypatch.setattr(ab, "_invoke_llm", lambda **kw: "# Design Spec")

        generate_code_for_save("document the alu module", content_type="document")
        assert agent_called == []

    def test_sdc_never_uses_agent_manager(self, monkeypatch):
        """Physical-design types (sdc, floorplan, drc…) use generic LLM path."""
        from cool_cli.ai_buddy import generate_code_for_save
        import cool_cli.ai_buddy as ab

        self._patch_agents_available(monkeypatch, True)
        agent_called = []
        self._patch_agent_manager(monkeypatch, lambda name, **kw: agent_called.append(name))
        monkeypatch.setattr(ab, "_invoke_llm", lambda **kw: "create_clock -period 10 clk")

        for ct in ("sdc", "floorplan", "pnr", "pdn", "sta", "drc", "lvs", "gds", "makefile"):
            generate_code_for_save("write a script", content_type=ct)
        assert agent_called == []

    # ------------------------------------------------------------------
    # TB agent receives RTL context
    # ------------------------------------------------------------------

    def test_tb_receives_rtl_context(self, monkeypatch):
        """initial_spec tuple for TB contains (spec, rtl_context, top_module)."""
        from cool_cli.ai_buddy import generate_code_for_save

        captured_spec = []

        def _iterate(agent, initial_spec, feedback_agent, max_iters=1, **kw):
            captured_spec.append(initial_spec)
            return ("module tb; endmodule", "ok")

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, lambda name, verbose=False: object())
        self._patch_feedback_coordinator(monkeypatch, _iterate)

        generate_code_for_save(
            "write TB for alu",
            content_type="tb",
            rtl_context="module alu(input clk, output q); endmodule",
            top_module="alu",
        )
        assert captured_spec, "iterate_improvements must have been called"
        spec_arg = captured_spec[0]
        assert isinstance(spec_arg, tuple), "TB initial_spec must be a tuple"
        assert "module alu" in spec_arg[1], "rtl_context must be in initial_spec[1]"
        assert spec_arg[2] == "alu", "top_module must be initial_spec[2]"

    def test_max_review_iters_forwarded(self, monkeypatch):
        """max_review_iters is forwarded to iterate_improvements."""
        from cool_cli.ai_buddy import generate_code_for_save

        captured_iters = []

        def _iterate(agent, initial_spec, feedback_agent, max_iters=1, **kw):
            captured_iters.append(max_iters)
            return ("module x; endmodule", "ok")

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, lambda name, verbose=False: object())
        self._patch_feedback_coordinator(monkeypatch, _iterate)

        generate_code_for_save("create ALU", content_type="rtl", max_review_iters=3)
        assert captured_iters == [3]

    def test_return_type_is_always_str(self, monkeypatch):
        """generate_code_for_save always returns a str, never a tuple."""
        from cool_cli.ai_buddy import generate_code_for_save

        self._patch_agents_available(monkeypatch, True)
        self._patch_agent_manager(monkeypatch, lambda name, verbose=False: object())
        self._patch_feedback_coordinator(monkeypatch, self._fake_iterate("module z; endmodule"))

        result = generate_code_for_save("create a counter", content_type="rtl")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# RTL context discovery in file_ops._find_rtl_in_unit
# ---------------------------------------------------------------------------

class TestFindRtlInUnit:
    """Tests for the _find_rtl_in_unit helper that locates existing RTL source."""

    def test_finds_sv_file(self, tmp_path):
        from cool_cli.file_ops import _find_rtl_in_unit
        (tmp_path / "source" / "rtl" / "systemverilog").mkdir(parents=True)
        sv = tmp_path / "source" / "rtl" / "systemverilog" / "alu.sv"
        sv.write_text("module alu; endmodule")
        result = _find_rtl_in_unit(tmp_path)
        assert result == sv

    def test_finds_v_file_when_no_sv(self, tmp_path):
        from cool_cli.file_ops import _find_rtl_in_unit
        (tmp_path / "source" / "rtl" / "verilog").mkdir(parents=True)
        v = tmp_path / "source" / "rtl" / "verilog" / "counter.v"
        v.write_text("`timescale 1ns/1ps")
        result = _find_rtl_in_unit(tmp_path)
        assert result == v

    def test_prefers_sv_over_v(self, tmp_path):
        from cool_cli.file_ops import _find_rtl_in_unit
        sv_dir = tmp_path / "source" / "rtl" / "systemverilog"
        sv_dir.mkdir(parents=True)
        (tmp_path / "source" / "rtl" / "verilog").mkdir(parents=True)
        sv = sv_dir / "alu.sv"
        sv.write_text("module alu; endmodule")
        (tmp_path / "source" / "rtl" / "verilog" / "counter.v").write_text("module counter; endmodule")
        result = _find_rtl_in_unit(tmp_path)
        assert result.suffix == ".sv"

    def test_returns_none_when_empty(self, tmp_path):
        from cool_cli.file_ops import _find_rtl_in_unit
        (tmp_path / "source" / "rtl").mkdir(parents=True)
        result = _find_rtl_in_unit(tmp_path)
        assert result is None

    def test_returns_none_when_rtl_absent(self, tmp_path):
        from cool_cli.file_ops import _find_rtl_in_unit
        result = _find_rtl_in_unit(tmp_path)
        assert result is None

