# saxoflow_agenticai/utils/file_utils.py
"""
File utilities for SaxoFlow Agentic AI.

Public API
----------
- write_output(output, output_file=None, default_folder=None, default_name=None,
               ext=".v", silent=True) -> str
- base_name_from_path(path) -> str

Notes
-----
- `write_output` behavior:
  * If `output_file` is provided, it writes there (does NOT create parent dirs).
  * Otherwise it ensures `default_folder` exists and writes to
    `default_folder/default_name + ext`.
  * By default it is **silent** and only returns the written path.
    Set `silent=False` to emit a green confirmation line.

Python: 3.9+
"""

from __future__ import annotations

import os
from typing import Optional, Union

import click

__all__ = ["write_output", "base_name_from_path"]


def write_output(
    output: str,
    output_file: Optional[Union[str, os.PathLike]] = None,
    default_folder: Optional[Union[str, os.PathLike]] = None,
    default_name: Optional[str] = None,
    ext: str = ".v",
    *,
    silent: bool = True,
) -> str:
    """
    Write a text `output` to disk and return the path written.

    Behavior
    --------
    - If `output_file` is provided, write directly to that path.
      (Parent directories are *not* created here, matching prior behavior.)
    - Otherwise, ensure `default_folder` exists and write to:
        `default_folder` / (`default_name` + `ext`)
    - By default, no console output is produced. Pass `silent=False` to
      print a green confirmation line.

    Parameters
    ----------
    output : str
        The text content to write.
    output_file : Optional[Union[str, os.PathLike]]
        Absolute or relative path to write to. If provided, other folder/name
        parameters are ignored.
    default_folder : Optional[Union[str, os.PathLike]]
        Folder to create/use when `output_file` is not provided.
    default_name : Optional[str]
        Base filename (without extension) when `output_file` is not provided.
    ext : str, default ".v"
        File extension to append to `default_name`. (Kept verbatim; we do NOT
        enforce a leading dot to preserve existing behavior.)
    silent : bool, default True
        If False, prints a confirmation line to stdout.

    Returns
    -------
    str
        The filesystem path that was written.

    Raises
    ------
    ValueError
        If `output_file` is not provided and either `default_folder` or
        `default_name` is missing.
    OSError
        If the OS-level write fails (permissions, missing parent for `output_file`, etc.).

    Examples
    --------
    >>> write_output("module ...", default_folder="out/rtl", default_name="foo", ext=".v")
    'out/rtl/foo.v'
    >>> write_output("...", output_file="foo/bar.v", silent=False)
    '[✔] Output written to: foo/bar.v'
    """
    if output_file:
        out_path = os.fspath(output_file)
        # NOTE: We intentionally do NOT create parent directories here to keep
        # backward-compatible behavior. Callers should ensure the directory exists.
        # TODO: Consider an opt-in flag to create parents for output_file paths.
    else:
        if default_folder is None or default_name is None:
            raise ValueError(
                "Either 'output_file' must be provided, or both "
                "'default_folder' and 'default_name' must be specified."
            )
        folder = os.fspath(default_folder)
        os.makedirs(folder, exist_ok=True)
        out_path = os.path.join(folder, f"{default_name}{ext}")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)

    if not silent:
        click.secho(f"[✔] Output written to: {out_path}", fg="green")

    return out_path


def base_name_from_path(path: Union[str, os.PathLike]) -> str:
    """
    Return the filename (without extension) from a filesystem path.

    Parameters
    ----------
    path : Union[str, os.PathLike]
        A filesystem path to a file.

    Returns
    -------
    str
        The stem (basename without extension). For example:
        '/a/b/c.txt' -> 'c'
    """
    return os.path.splitext(os.path.basename(os.fspath(path)))[0]
