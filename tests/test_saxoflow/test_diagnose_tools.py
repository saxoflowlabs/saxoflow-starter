"""
Integrated unit tests for saxoflow.diagnostics.diagnose_tools.

Goals
-----
- Hermetic: no real system modification, no network.
- Broad coverage: tool detection, version parsing, env analysis, WSL detection,
  health computation, and pro diagnostics tips.
- Preserve current behaviors (best-effort parsing + defensive fallbacks).

All OS/filesystem/subprocess touch points are monkeypatched or localized to
`tmp_path`. We always patch using the import path used by the SUT.
"""

from __future__ import annotations

import io
import os
import stat
from pathlib import Path
from typing import List

import pytest
import saxoflow.diagnose_tools as dt


# ---------------------------------------------------------------------------
# tool_details / load_user_selection / infer_flow
# ---------------------------------------------------------------------------


def test_tool_details_known_and_unknown():
    """tool_details returns a short description for known tools and '' for unknown."""
    assert "Synthesizer" in dt.tool_details("yosys")
    assert dt.tool_details("nonexistent_tool") == ""


def test_load_user_selection_missing_and_bad_json(tmp_path, monkeypatch):
    """load_user_selection handles missing file and corrupt JSON without crashing."""
    monkeypatch.chdir(tmp_path)
    # Missing file -> []
    assert dt.load_user_selection() == []

    # Corrupt JSON -> []
    (tmp_path / ".saxoflow_tools.json").write_text("{broken")
    assert dt.load_user_selection() == []


def test_load_user_selection_happy(tmp_path, monkeypatch):
    """load_user_selection reads valid list and normalizes entries to str."""
    monkeypatch.chdir(tmp_path)
    expected = ["iverilog", "yosys", "gtkwave"]
    (tmp_path / ".saxoflow_tools.json").write_text('["iverilog", "yosys", "gtkwave"]')
    assert dt.load_user_selection() == expected


@pytest.mark.parametrize(
    "selection,flow",
    [
        (["nextpnr"], "fpga"),
        (["openroad"], "asic"),
        (["magic"], "asic"),
        (["symbiyosys"], "formal"),
        (["iverilog"], "minimal"),
        ([], "minimal"),
    ],
)
def test_infer_flow(selection, flow):
    """infer_flow picks the correct profile based on sentinel tools."""
    assert dt.infer_flow(selection) == flow


# ---------------------------------------------------------------------------
# find_tool_binary
# ---------------------------------------------------------------------------


def test_find_tool_binary_none_when_absent(monkeypatch):
    """find_tool_binary returns (None, False, None) when nothing is found anywhere."""
    monkeypatch.setattr(dt.shutil, "which", lambda _t: None)
    # Also make sure ~/.local/<tool>/bin/<tool> doesn't exist
    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent/home"))
    path, in_path, variant = dt.find_tool_binary("nonexistent_tool")
    assert path is None and in_path is False and variant is None


def test_find_tool_binary_found_in_path(monkeypatch):
    """find_tool_binary returns (path, True, tool) when found via PATH."""
    monkeypatch.setattr(dt.shutil, "which", lambda t: f"/usr/bin/{t}")
    path, in_path, variant = dt.find_tool_binary("iverilog")
    assert path == "/usr/bin/iverilog" and in_path is True and variant == "iverilog"


def test_find_tool_binary_found_in_user_local(tmp_path, monkeypatch):
    """find_tool_binary returns (~/.local/<tool>/bin/<tool>, False, tool) when found in user bin."""
    monkeypatch.setattr(dt.shutil, "which", lambda _t: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    t = "iverilog"
    exe = tmp_path / ".local" / t / "bin" / t
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary(t)
    assert path == str(exe) and in_path is False and variant == t


def test_find_tool_binary_nextpnr_variant_in_path(monkeypatch):
    """find_tool_binary prefers nextpnr-* variant from PATH when base is absent."""
    def fake_which(name: str) -> str | None:
        if name == "nextpnr":
            return None
        if name == "nextpnr-ice40":
            return "/usr/bin/nextpnr-ice40"
        return None

    monkeypatch.setattr(dt.shutil, "which", fake_which)
    path, in_path, variant = dt.find_tool_binary("nextpnr")
    assert path == "/usr/bin/nextpnr-ice40" and in_path is True and variant == "nextpnr-ice40"


def test_find_tool_binary_nextpnr_found_in_common_dir(tmp_path, monkeypatch):
    """find_tool_binary returns a nextpnr-* file from ~/.local/nextpnr/bin if no PATH hit."""
    monkeypatch.setattr(dt.shutil, "which", lambda _t: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    exe = tmp_path / ".local" / "nextpnr" / "bin" / "nextpnr-custom"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary("nextpnr")
    assert path == str(exe) and in_path is False and variant == "nextpnr-custom"


def test_find_tool_binary_openfpgaloader_capitalization(tmp_path, monkeypatch):
    """find_tool_binary handles 'openFPGALoader' capitalization in user/local bins."""
    # No PATH hit
    monkeypatch.setattr(dt.shutil, "which", lambda _t: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    exe = tmp_path / ".local" / "bin" / "openFPGALoader"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary("openfpgaloader")
    assert path == str(exe) and in_path is False and variant == "openfpgaloader"


def test_find_tool_binary_openfpgaloader_in_path(monkeypatch):
    """find_tool_binary finds 'openFPGALoader' via PATH when base is missing."""
    def fake_which(name: str) -> str | None:
        if name == "openfpgaloader":
            return None
        if name == "openFPGALoader":
            return "/usr/bin/openFPGALoader"
        return None

    monkeypatch.setattr(dt.shutil, "which", fake_which)
    path, in_path, variant = dt.find_tool_binary("openfpgaloader")
    assert path == "/usr/bin/openFPGALoader" and in_path is True and variant == "openfpgaloader"


# ---------------------------------------------------------------------------
# extract_version
# ---------------------------------------------------------------------------


def test_extract_version_generic_success(tmp_path, monkeypatch):
    """extract_version parses a simple '--version' output via generic fallback."""
    fake = tmp_path / "tool"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    class R:
        def __init__(self, out, err=""):
            self.stdout = out
            self.stderr = err

    def fake_run(args, capture_output, text, timeout, check):
        # Whatever flag, return a plain version string
        return R("tool version 1.2.3\n", "")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    assert dt.extract_version("some_tool", str(fake)) == "1.2.3"


def test_extract_version_iverilog_and_gtkwave(monkeypatch, tmp_path):
    """extract_version recognizes iverilog and gtkwave custom formats."""
    fake = str(tmp_path / "bin")

    class R:
        def __init__(self, out, err=""):
            self.stdout = out
            self.stderr = err

    calls: List[List[str]] = []

    def fake_run(args, capture_output, text, timeout, check):
        calls.append(args)
        if args[0] == fake and args[1] == "-v":
            return R("Icarus Verilog version 12.0 (stable)")
        if args[0] == fake and args[1] == "--version":
            return R("GTKWave Analyzer v3.3.100")
        return R("nope")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    assert dt.extract_version("iverilog", fake) == "12.0 (stable)"
    assert dt.extract_version("gtkwave", fake) == "3.3.100"


def test_extract_version_nextpnr_flag_sequence(monkeypatch, tmp_path):
    """extract_version for nextpnr tries flags in order until it finds a parsable line."""
    fake = str(tmp_path / "nextpnr")

    class R:
        def __init__(self, out, err=""):
            self.stdout = out
            self.stderr = err

    def fake_run(args, capture_output, text, timeout, check):
        # args[-1] is the flag being tried
        flag = args[-1]
        if flag == "--version":
            # No recognizable version in this output
            return R("nextpnr (no version here)")
        if flag == "-v":
            # Provide the formatted line
            return R("nextpnr-ice40 (Version 0.5.1)")
        return R("help text")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    assert dt.extract_version("nextpnr-ice40", fake) == "0.5.1"


def test_extract_version_unknown_and_error(tmp_path, monkeypatch):
    """extract_version returns (unknown) for missing path or (parse error: ...) on exceptions."""
    assert dt.extract_version("anything", None) == "(unknown)"

    fake = str(tmp_path / "t")
    monkeypatch.setattr(
        dt.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    out = dt.extract_version("some_tool", fake)
    assert out.startswith("(parse error:")


# ---------------------------------------------------------------------------
# compute_health
# ---------------------------------------------------------------------------


def test_compute_health_all_required_present(monkeypatch):
    """compute_health returns 100 score when all required tools are present."""
    # Force minimal flow by selection
    monkeypatch.setattr(dt, "load_user_selection", lambda: ["iverilog"])
    # Required for minimal: ["iverilog", "yosys", "gtkwave"]
    # Mock find + version
    def fake_find(tool):
        return f"/usr/bin/{tool}", True, tool

    monkeypatch.setattr(dt, "find_tool_binary", fake_find)
    monkeypatch.setattr(dt, "extract_version", lambda t, p: "1.0")

    flow, score, req, opt = dt.compute_health()
    assert flow == "minimal"
    assert score == 100
    assert {t for (t, ok, *_rest) in req} == {"iverilog", "yosys", "gtkwave"}
    assert all(ok for (_t, ok, *_r) in req)


def test_compute_health_some_missing(monkeypatch):
    """compute_health returns <100 score when some required tools are missing."""
    monkeypatch.setattr(dt, "load_user_selection", lambda: ["nextpnr"])  # fpga profile

    def fake_find(tool):
        # Pretend only iverilog is present among required
        if tool == "iverilog":
            return "/usr/bin/iverilog", True, "iverilog"
        return None, False, None

    monkeypatch.setattr(dt, "find_tool_binary", fake_find)
    monkeypatch.setattr(dt, "extract_version", lambda t, p: "x.y")

    flow, score, req, _opt = dt.compute_health()
    assert flow == "fpga"
    # fpga required count is 5, only 1 present -> 20%
    assert score == 20
    present = [t for (t, ok, *_r) in req if ok]
    missing = [t for (t, ok, *_r) in req if not ok]
    assert present == ["iverilog"]
    assert "yosys" in missing and "gtkwave" in missing


# ---------------------------------------------------------------------------
# analyze_env / detect_wsl
# ---------------------------------------------------------------------------


def test_analyze_env_detects_duplicates_and_bins_missing(tmp_path, monkeypatch):
    """analyze_env reports duplicate PATH entries and tool bins missing from PATH."""
    # Constrain HOME and create some tool bin dirs that are not in PATH.
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for tool in dt.ALL_TOOLS[:2]:
        tdir = tmp_path / ".local" / tool / "bin"
        tdir.mkdir(parents=True, exist_ok=True)

    # PATH with duplicates
    monkeypatch.setenv("PATH", "/x:/y:/x")

    env = dt.analyze_env()
    assert env["path_duplicates"], "Expected duplicate PATH entries to be reported."
    assert env["bins_missing_in_path"], "Expected bins_missing_in_path to be non-empty."


def test_detect_wsl_variants(monkeypatch):
    """detect_wsl returns True when uname has WSL or /proc/version mentions Microsoft."""
    # Case 1: uname.release contains WSL
    class U1:
        release = "5.10.0-WSL2-microsoft-standard"

    monkeypatch.setattr(dt.platform, "uname", lambda: U1)
    monkeypatch.setattr(dt.os.path, "exists", lambda _p: False)
    assert dt.detect_wsl() is True

    # Case 2: uname without WSL, /proc/version mentions Microsoft
    class U2:
        release = "linux"

    monkeypatch.setattr(dt.platform, "uname", lambda: U2)
    monkeypatch.setattr(dt.os.path, "exists", lambda _p: True)

    def fake_open(*_a, **_k):
        return io.StringIO("Linux ... Microsoft WSL ...")

    monkeypatch.setattr(dt, "open", fake_open)
    assert dt.detect_wsl() is True

    # Case 3: neither path -> False
    monkeypatch.setattr(dt.os.path, "exists", lambda _p: True)

    def fake_open2(*_a, **_k):
        return io.StringIO("Linux vanilla kernel")

    monkeypatch.setattr(dt, "open", fake_open2)
    assert dt.detect_wsl() is False


# ---------------------------------------------------------------------------
# pro_diagnostics
# ---------------------------------------------------------------------------


def test_pro_diagnostics_compiles_tips(monkeypatch):
    """pro_diagnostics aggregates env + health and produces actionable tips."""
    # Env with duplicates, missing bins, and WSL
    env = {
        "path_duplicates": [("/dup", ["yosys"])],
        "bins_missing_in_path": [("/home/u/.local/yosys/bin", "yosys")],
        "wsl": True,
        "path": "/a:/b",
        "project_root": "/proj",
        "user": "u",
        "home": "/home/u",
        "python_version": "3.10.0",
        "platform": "Linux",
    }
    monkeypatch.setattr(dt, "analyze_env", lambda: env)

    # Health with <100 score
    health = ("minimal", 66, [("yosys", True, "/p", "0.1", True)], [])
    monkeypatch.setattr(dt, "compute_health", lambda: health)

    report = dt.pro_diagnostics()
    assert report["health"]["score"] == 66
    tips = "\n".join(report["tips"])
    # Should mention not all tools installed, duplicate path, bin not in PATH, and WSL
    assert "diagnose repair" in tips
    assert "Duplicate PATH entry" in tips
    assert "Tool bin not in PATH" in tips
    assert "WSL" in tips
