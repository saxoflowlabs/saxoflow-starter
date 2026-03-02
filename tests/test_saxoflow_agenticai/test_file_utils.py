"""
Hermetic tests for saxoflow_agenticai.utils.file_utils.

We lock down the public API behaviors:
- write_output: explicit path vs default folder/name, parent dir creation rules,
  console printing when silent=False, error paths, and ext verbatim handling.
- base_name_from_path: pathlike inputs and multi-dot filenames.

All tests use tmp_path (no persistent FS) and patch click.secho for determinism.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def _read_text(p: Path) -> str:
    """Helper to read small test files."""
    return p.read_text(encoding="utf-8")


# -----------------------
# write_output
# -----------------------

def test_write_output_to_output_file_happy(tmp_path, monkeypatch):
    """
    Writing to an explicit output_file should succeed when the parent exists,
    return the path, write exact content, and emit no console output by default.
    """
    from saxoflow_agenticai.utils import file_utils as sut

    # Track click.secho to ensure silence by default
    calls: list = []
    monkeypatch.setattr(sut.click, "secho", lambda *a, **k: calls.append((a, k)), raising=True)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out_file = out_dir / "file.v"

    written = sut.write_output("hello", output_file=str(out_file))
    assert written == str(out_file)
    assert _read_text(out_file) == "hello"
    assert calls == [], "silent=True must not print a confirmation"


def test_write_output_output_file_missing_parent_raises(tmp_path):
    """
    When output_file's parent dir does not exist, the function should not create
    the parent and should raise an OSError (FileNotFoundError on POSIX).
    """
    from saxoflow_agenticai.utils import file_utils as sut

    out_file = tmp_path / "missing_parent" / "file.txt"
    # parent does not exist
    with pytest.raises(OSError):
        sut.write_output("x", output_file=str(out_file))
    assert not out_file.parent.exists(), "Parent directory must not be created for output_file path"


def test_write_output_default_folder_creates_and_prints_when_not_silent(tmp_path, monkeypatch):
    """
    When using default_folder/default_name, the function should create directories,
    write the file, and print a green confirmation when silent=False.
    """
    from saxoflow_agenticai.utils import file_utils as sut

    folder = tmp_path / "deep" / "nested"
    name = "mymod"
    ext = ".sv"

    calls: list = []

    def record(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(sut.click, "secho", record, raising=True)

    written = sut.write_output(
        "rtl!",
        default_folder=str(folder),
        default_name=name,
        ext=ext,
        silent=False,
    )

    expected = folder / f"{name}{ext}"
    assert written == str(expected)
    assert expected.exists()
    assert _read_text(expected) == "rtl!"
    # Confirm message and color
    assert len(calls) == 1
    args, kw = calls[0]
    (text,) = args
    assert isinstance(text, str)
    assert text.startswith("[✔] Output written to:")
    assert kw.get("fg") == "green"


@pytest.mark.parametrize(
    "default_folder, default_name",
    [
        (None, "foo"),   # missing folder
        ("some_folder", None),  # missing name
    ],
)
def test_write_output_missing_params_raises_valueerror(default_folder, default_name):
    """
    If output_file is not provided, both default_folder and default_name are required.
    Missing either should raise ValueError with a helpful message.
    """
    from saxoflow_agenticai.utils import file_utils as sut

    with pytest.raises(ValueError) as ei:
        sut.write_output("x", default_folder=default_folder, default_name=default_name)
    s = str(ei.value)
    assert "output_file" in s and "default_folder" in s and "default_name" in s


def test_write_output_ext_used_verbatim(tmp_path):
    """
    ext must be used verbatim (no auto-added dot).
    Passing 'v' should produce '<name>v', matching documented behavior.
    """
    from saxoflow_agenticai.utils import file_utils as sut

    folder = tmp_path / "rtl"
    written = sut.write_output(
        "body",
        default_folder=str(folder),
        default_name="foo",
        ext="v",  # no dot
    )
    out = folder / "foov"  # ext used exactly
    assert written == str(out)
    assert out.exists()
    assert _read_text(out) == "body"


# -----------------------
# base_name_from_path
# -----------------------

@pytest.mark.parametrize(
    "path, expected",
    [
        ("/a/b/c.txt", "c"),
        ("relative/dir/name", "name"),
        ("archive.tar.gz", "archive.tar"),
        (Path("dir") / "x.y.z", "x.y"),
        ("simple", "simple"),
    ],
)
def test_base_name_from_path_variants(path, expected):
    """
    base_name_from_path should return the stem (basename without extension)
    for strings and Path-like objects, including multi-dot names.
    """
    from saxoflow_agenticai.utils import file_utils as sut

    assert sut.base_name_from_path(path) == expected
