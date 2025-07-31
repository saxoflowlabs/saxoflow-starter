"""
Tests for saxoflow_agenticai.utils.file_utils.

These helpers provide common file naming and writing functions.
The tests verify that files are correctly created in the right
directories and that the base name helper strips both extension and
directories.
"""

from pathlib import Path
import os

from saxoflow_agenticai.utils import file_utils


def test_write_output_creates_file(tmp_path, capsys):
    out_dir = tmp_path / "out"
    file_utils.write_output("hello", output_file=None, default_folder=str(out_dir), default_name="foo", ext=".txt")
    target = out_dir / "foo.txt"
    assert target.exists()
    assert target.read_text() == "hello"


def test_base_name_from_path():
    assert file_utils.base_name_from_path("/path/to/file.ext") == "file"
    assert file_utils.base_name_from_path("file.v") == "file"