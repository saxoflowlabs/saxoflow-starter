"""Tests for the NetlistSVG schematic wrapper."""

from __future__ import annotations

import json
import os
from pathlib import Path

from click.testing import CliRunner

import saxoflow.schematicflow as schematicflow


def _chdir(path: Path):
    class _Context:
        def __enter__(self):
            self.previous = Path.cwd()
            os.chdir(path)
            return path

        def __exit__(self, exc_type, exc, tb):
            os.chdir(self.previous)

    return _Context()


def _write_netlist(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"modules": {"sample_core": {"ports": {}, "cells": {}}}}),
        encoding="utf-8",
    )
    return path


def test_schematic_renders_default_yosys_json(tmp_path, monkeypatch):
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    _write_netlist(tmp_path / schematicflow.DEFAULT_INPUT)
    monkeypatch.setattr(
        schematicflow,
        "find_netlistsvg",
        lambda: "/tools/netlistsvg",
    )
    opened = []
    monkeypatch.setattr(
        schematicflow,
        "open_schematic",
        lambda path, missing_ok=False: opened.append(path) or True,
    )
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout):
        captured["command"] = command
        captured["timeout"] = timeout
        output = Path(cwd) / command[command.index("-o") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("<svg></svg>\n", encoding="utf-8")
        return type(
            "Result",
            (),
            {"stdout": "", "stderr": "", "returncode": 0},
        )()

    monkeypatch.setattr(schematicflow.subprocess, "run", fake_run)
    with _chdir(tmp_path):
        result = CliRunner().invoke(schematicflow.schematic, [])

    assert result.exit_code == 0, result.output
    assert captured["command"] == [
        "/tools/netlistsvg",
        "synthesis/out/synthesized.json",
        "-o",
        "synthesis/reports/schematic.svg",
    ]
    assert captured["timeout"] == 120
    assert (tmp_path / schematicflow.DEFAULT_OUTPUT).is_file()
    assert "SUCCESS: Schematic written" in result.output
    assert opened == [tmp_path / schematicflow.DEFAULT_OUTPUT]


def test_schematic_supports_explicit_skin_and_output(tmp_path, monkeypatch):
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    _write_netlist(tmp_path / "custom/netlist.json")
    skin = tmp_path / "custom/skin.svg"
    skin.write_text("<svg></svg>\n", encoding="utf-8")
    monkeypatch.setattr(
        schematicflow,
        "find_netlistsvg",
        lambda: "/tools/netlistsvg",
    )
    monkeypatch.setattr(
        schematicflow,
        "open_schematic",
        lambda path, missing_ok=False: True,
    )
    captured = {}

    def fake_run(command, cwd, capture_output, text, timeout):
        captured["command"] = command
        output = Path(cwd) / command[command.index("-o") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("<svg></svg>\n", encoding="utf-8")
        return type(
            "Result",
            (),
            {"stdout": "", "stderr": "", "returncode": 0},
        )()

    monkeypatch.setattr(schematicflow.subprocess, "run", fake_run)
    with _chdir(tmp_path):
        result = CliRunner().invoke(
            schematicflow.schematic,
            [
                "--input",
                "custom/netlist.json",
                "--output",
                "custom/result.svg",
                "--skin",
                "custom/skin.svg",
            ],
        )

    assert result.exit_code == 0, result.output
    assert captured["command"][-2:] == ["--skin", "custom/skin.svg"]


def test_schematic_no_open_skips_viewer(tmp_path, monkeypatch):
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    _write_netlist(tmp_path / schematicflow.DEFAULT_INPUT)
    monkeypatch.setattr(
        schematicflow,
        "find_netlistsvg",
        lambda: "/tools/netlistsvg",
    )

    def fake_run(command, cwd, capture_output, text, timeout):
        output = Path(cwd) / command[command.index("-o") + 1]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("<svg></svg>\n", encoding="utf-8")
        return type(
            "Result",
            (),
            {"stdout": "", "stderr": "", "returncode": 0},
        )()

    monkeypatch.setattr(schematicflow.subprocess, "run", fake_run)
    monkeypatch.setattr(
        schematicflow,
        "open_schematic",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("viewer should not open")
        ),
    )
    with _chdir(tmp_path):
        result = CliRunner().invoke(
            schematicflow.schematic,
            ["--no-open"],
        )

    assert result.exit_code == 0, result.output


def test_viewer_commands_prefer_windows_interop_under_wsl(
    tmp_path, monkeypatch
):
    schematic = tmp_path / "schematic.svg"
    schematic.write_text("<svg></svg>\n", encoding="utf-8")
    monkeypatch.setattr(schematicflow, "_is_wsl", lambda: True)

    binaries = {
        "wslview": None,
        "wslpath": "/usr/bin/wslpath",
        "cmd.exe": "/mnt/c/Windows/System32/cmd.exe",
        "explorer.exe": "/mnt/c/Windows/explorer.exe",
        "xdg-open": "/usr/bin/xdg-open",
    }
    monkeypatch.setattr(
        schematicflow.shutil,
        "which",
        lambda name: binaries.get(name),
    )
    monkeypatch.setattr(
        schematicflow.subprocess,
        "run",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "stdout": (
                    r"\\wsl.localhost\Ubuntu\home\user\schematic.svg"
                    "\n"
                ),
                "stderr": "",
                "returncode": 0,
            },
        )(),
    )

    commands = schematicflow._viewer_commands(schematic)

    assert commands[0][:4] == [
        "/mnt/c/Windows/System32/cmd.exe",
        "/C",
        "start",
        "",
    ]
    assert commands[1][0] == "/mnt/c/Windows/explorer.exe"
    assert commands[2][0] == "/usr/bin/xdg-open"


def test_open_schematic_launches_first_available_viewer(tmp_path, monkeypatch):
    schematic = tmp_path / "schematic.svg"
    schematic.write_text("<svg></svg>\n", encoding="utf-8")
    monkeypatch.setattr(
        schematicflow,
        "_viewer_commands",
        lambda path: [["viewer", str(path)]],
    )
    captured = {}

    def fake_popen(command, stdout, stderr, start_new_session):
        captured["command"] = command
        captured["start_new_session"] = start_new_session
        return object()

    monkeypatch.setattr(schematicflow.subprocess, "Popen", fake_popen)

    assert schematicflow.open_schematic(schematic) is True
    assert captured["command"] == ["viewer", str(schematic)]
    assert captured["start_new_session"] is True


def test_schematic_reports_missing_tool(tmp_path, monkeypatch):
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    _write_netlist(tmp_path / schematicflow.DEFAULT_INPUT)
    monkeypatch.setattr(schematicflow, "find_netlistsvg", lambda: None)

    with _chdir(tmp_path):
        result = CliRunner().invoke(schematicflow.schematic, [])

    assert result.exit_code != 0
    assert "saxoflow install netlistsvg" in result.output


def test_schematic_rejects_invalid_json(tmp_path, monkeypatch):
    (tmp_path / "Makefile").write_text("all:\n\t@true\n", encoding="utf-8")
    netlist = tmp_path / schematicflow.DEFAULT_INPUT
    netlist.parent.mkdir(parents=True, exist_ok=True)
    netlist.write_text("not json\n", encoding="utf-8")
    monkeypatch.setattr(
        schematicflow,
        "find_netlistsvg",
        lambda: "/tools/netlistsvg",
    )

    with _chdir(tmp_path):
        result = CliRunner().invoke(schematicflow.schematic, [])

    assert result.exit_code != 0
    assert "Invalid Yosys JSON netlist" in result.output
