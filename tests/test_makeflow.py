"""
Tests for saxoflow.makeflow utilities and command functions.

Because the makeflow commands wrap calls to `make` and inspect the
project file tree, these tests avoid executing real Make targets by
monkeypatching subprocess.run.  Only the selection logic and error
handling around missing Makefiles and testbenches is exercised.
"""

import os
import pytest
from pathlib import Path
from click.testing import CliRunner
from unittest import mock

import saxoflow.makeflow as makeflow


def test_require_makefile_raises(tmp_path):
    """require_makefile should abort if Makefile is missing."""
    runner = CliRunner()
    # Change into empty directory
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        with pytest.raises(SystemExit):
            makeflow.require_makefile()
    finally:
        os.chdir(cwd)


def test_run_make_invokes_subprocess(monkeypatch):
    """run_make returns the subprocess output mapping."""
    # Mock subprocess.run to return a simple structure
    def fake_run(cmd, capture_output, text):
        class Result:
            stdout = "ok"
            stderr = ""
            returncode = 0
        # Save the passed command for verification
        nonlocal received_cmd
        received_cmd = cmd
        return Result()
    received_cmd = None
    monkeypatch.setattr(makeflow.subprocess, "run", fake_run)
    result = makeflow.run_make("sim-icarus", extra_vars={"TOP_TB": "tb"})
    assert received_cmd[:2] == ["make", "sim-icarus"]
    assert result == {"stdout": "ok", "stderr": "", "returncode": 0}