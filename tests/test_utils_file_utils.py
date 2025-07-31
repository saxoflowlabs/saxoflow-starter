from pathlib import Path
import os
from saxoflow_agenticai.utils import file_utils

def test_write_output_creates_file(tmp_path, capsys):
    out_dir = tmp_path / "out"
    file_utils.write_output("hello", output_file=None, default_folder=str(out_dir), default_name="foo", ext=".txt")
    target = out_dir / "foo.txt"
    assert target.exists()
    assert target.read_text() == "hello"

def test_write_output_with_output_file(tmp_path, capsys):
    out_file = tmp_path / "myout.v"
    file_utils.write_output("hi", output_file=str(out_file), default_folder="should_not_use", default_name="should_not_use", ext=".v")
    assert out_file.exists()
    assert out_file.read_text() == "hi"

def test_write_output_returns_path(tmp_path):
    out_file = tmp_path / "x.y.z"
    path = file_utils.write_output("abc", output_file=str(out_file))
    assert str(out_file) == path

def test_write_output_with_other_extension(tmp_path):
    out_dir = tmp_path / "out2"
    path = file_utils.write_output("data", output_file=None, default_folder=str(out_dir), default_name="stuff", ext=".dat")
    assert Path(path).exists()
    assert Path(path).read_text() == "data"
    assert path.endswith(".dat")

def test_base_name_from_path():
    assert file_utils.base_name_from_path("/path/to/file.ext") == "file"
    assert file_utils.base_name_from_path("file.v") == "file"
    assert file_utils.base_name_from_path("foo.bar.v") == "foo.bar"
    assert file_utils.base_name_from_path("/dir/.hidden.v") == ".hidden"
    assert file_utils.base_name_from_path("/weird.name.with.many.dots.ext") == "weird.name.with.many.dots"
    assert file_utils.base_name_from_path("justfilename") == "justfilename"
    assert file_utils.base_name_from_path("/noext/filename") == "filename"
    # Windows path style (if desired)
    assert file_utils.base_name_from_path(r"C:\folder\name.ext") == "name"
