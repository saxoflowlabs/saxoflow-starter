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
    assert "QEMU" in dt.tool_details("qemu-system-riscv64")
    assert "Debugger" in dt.tool_details("openocd")
    assert "Proxy Kernel" in dt.tool_details("riscv-pk")
    assert "waveform" in dt.tool_details("surfer").lower()
    assert "abstraction" in dt.tool_details("edalize").lower()
    assert "vhdl" in dt.tool_details("nvc").lower()
    assert "ip-xact" in dt.tool_details("kactus2").lower()
    assert "orchestration" in dt.tool_details("siliconcompiler").lower()
    assert "virtual platform" in dt.tool_details("renode").lower()
    assert "architecture" in dt.tool_details("gem5").lower()
    assert "virtual platform" in dt.tool_details("riscv-vp-plusplus").lower()
    assert "sram" in dt.tool_details("openram").lower()
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


def test_find_tool_binary_riscv_pk_triplet_path(tmp_path, monkeypatch):
    """riscv-pk should be found under ~/.local/riscv-pk/riscv64-unknown-elf/bin/pk."""
    def fake_which(name: str) -> str | None:
        return None

    monkeypatch.setattr(dt.shutil, "which", fake_which)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    pk = tmp_path / ".local" / "riscv-pk" / "riscv64-unknown-elf" / "bin" / "pk"
    pk.parent.mkdir(parents=True)
    pk.write_text("#!/bin/sh\n", encoding="utf-8")
    pk.chmod(pk.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary("riscv-pk")
    assert path == str(pk)
    assert in_path is False
    assert variant == "pk"


def test_find_tool_binary_edalize_local_el_docker(tmp_path, monkeypatch):
    """edalize should resolve to ~/.local/edalize/bin/el_docker when present."""
    monkeypatch.setattr(dt.shutil, "which", lambda _t: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    exe = tmp_path / ".local" / "edalize" / "bin" / "el_docker"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary("edalize")
    assert path == str(exe)
    assert in_path is False
    assert variant == "el_docker"


def test_find_tool_binary_edalize_el_docker_in_path(monkeypatch):
    """edalize should resolve via PATH when el_docker is available."""
    def fake_which(name: str) -> str | None:
        if name == "edalize":
            return None
        if name == "el_docker":
            return "/usr/bin/el_docker"
        return None

    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent/home"))
    monkeypatch.setattr(dt.shutil, "which", fake_which)
    path, in_path, variant = dt.find_tool_binary("edalize")
    assert path == "/usr/bin/el_docker"
    assert in_path is True
    assert variant == "el_docker"


def test_find_tool_binary_verible_requires_both_in_path(monkeypatch):
    """verible is considered installed only when lint+format binaries both exist in PATH."""
    def fake_which(name: str) -> str | None:
        if name == "verible":
            return None
        if name == "verible-verilog-lint":
            return "/usr/bin/verible-verilog-lint"
        if name == "verible-verilog-format":
            return "/usr/bin/verible-verilog-format"
        return None

    monkeypatch.setattr(dt.shutil, "which", fake_which, raising=True)

    path, in_path, variant = dt.find_tool_binary("verible")
    assert path == "/usr/bin/verible-verilog-lint"
    assert in_path is True
    assert variant == "verible-verilog-lint"


def test_find_tool_binary_verible_missing_formatter_returns_none(monkeypatch):
    """If only one Verible binary exists, find_tool_binary should report missing."""
    monkeypatch.setattr(Path, "home", lambda: Path("/nonexistent/home"), raising=True)

    def fake_which(name: str) -> str | None:
        if name == "verible":
            return None
        if name == "verible-verilog-lint":
            return "/usr/bin/verible-verilog-lint"
        if name == "verible-verilog-format":
            return None
        return None

    monkeypatch.setattr(dt.shutil, "which", fake_which, raising=True)

    path, in_path, variant = dt.find_tool_binary("verible")
    assert path is None
    assert in_path is False
    assert variant is None


def test_find_tool_binary_symbiyosys_found_as_sby_in_path(monkeypatch):
    """find_tool_binary resolves 'symbiyosys' to the 'sby' binary on PATH."""
    def fake_which(name: str) -> str | None:
        return "/usr/local/bin/sby" if name == "sby" else None

    monkeypatch.setattr(dt.shutil, "which", fake_which)
    path, in_path, variant = dt.find_tool_binary("symbiyosys")
    assert path == "/usr/local/bin/sby"
    assert in_path is True
    assert variant == "sby"


def test_find_tool_binary_symbiyosys_found_in_local_sby(tmp_path, monkeypatch):
    """find_tool_binary finds symbiyosys at ~/.local/sby/bin/sby when not in PATH."""
    monkeypatch.setattr(dt.shutil, "which", lambda _: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    sby = tmp_path / ".local" / "sby" / "bin" / "sby"
    sby.parent.mkdir(parents=True)
    sby.write_text("#!/bin/sh\nexit 0\n")
    sby.chmod(sby.stat().st_mode | stat.S_IXUSR)

    path, in_path, variant = dt.find_tool_binary("symbiyosys")
    assert path == str(sby)
    assert in_path is False
    assert variant == "sby"


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


def test_extract_version_riscv_pk_non_host_executable(tmp_path, monkeypatch):
    """riscv-pk/pk should not be executed on host for version probing."""
    fake = tmp_path / "pk"
    fake.write_text("", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("subprocess.run should not be called for pk")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    out = dt.extract_version("pk", str(fake))
    assert out == "cross-target ELF; host execution unsupported"
    assert calls["n"] == 0


def test_extract_version_surfer_reads_crates_toml(tmp_path, monkeypatch):
    """surfer version should be read from cargo prefix .crates.toml, not subprocess."""
    prefix = tmp_path / ".local" / "surfer"
    prefix.mkdir(parents=True)
    (prefix / ".crates.toml").write_text(
        '[v1]\n"surfer 0.3.2 (registry+https://github.com/rust-lang/crates.io-index)" = ["test_main"]\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(dt.Path, "home", staticmethod(lambda: tmp_path))

    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        raise AssertionError("subprocess.run should not be called for surfer")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    fake = tmp_path / "surfer"
    fake.write_text("", encoding="utf-8")
    out = dt.extract_version("surfer", str(fake))
    assert out == "0.3.2"
    assert calls["n"] == 0


def test_extract_version_surfer_fallback_no_crates_toml(tmp_path, monkeypatch):
    """surfer falls back gracefully when .crates.toml is absent."""
    monkeypatch.setattr(dt.Path, "home", staticmethod(lambda: tmp_path))
    fake = tmp_path / "surfer"
    fake.write_text("", encoding="utf-8")
    out = dt.extract_version("surfer", str(fake))
    assert out == "(unknown)"


def test_extract_version_edalize_reads_managed_python(tmp_path, monkeypatch):
    """edalize version should be read via managed venv python call."""
    monkeypatch.setattr(dt.Path, "home", staticmethod(lambda: tmp_path))

    class R:
        stdout = "0.6.5\n"
        stderr = ""

    calls = {"n": 0}

    def fake_run(*_args, **_kwargs):
        calls["n"] += 1
        return R()

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    fake = tmp_path / "el_docker"
    fake.write_text("", encoding="utf-8")
    out = dt.extract_version("edalize", str(fake))
    assert out == "0.6.5"
    assert calls["n"] == 1


def test_extract_version_edalize_fallback_unknown(tmp_path, monkeypatch):
    """edalize falls back gracefully when python probing fails."""
    monkeypatch.setattr(dt.Path, "home", staticmethod(lambda: tmp_path))

    def fake_run(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    fake = tmp_path / "el_docker"
    fake.write_text("", encoding="utf-8")
    out = dt.extract_version("edalize", str(fake))
    assert out == "(unknown)"


def test_extract_version_covered_and_spike(monkeypatch, tmp_path):
    """extract_version handles Covered's -v output and Spike's help banner."""
    fake = str(tmp_path / "bin")

    class R:
        def __init__(self, out, err=""):
            self.stdout = out
            self.stderr = err

    def fake_run(args, capture_output, text, timeout, check):
        if args[0] == fake and args[1] == "-v":
            return R("covered-20090802\n")
        if args[0] == fake and args[1] == "--help":
            return R("Spike RISC-V ISA Simulator 1.1.1-dev\nusage: spike ...\n")
        return R("nope")

    monkeypatch.setattr(dt.subprocess, "run", fake_run)
    assert dt.extract_version("covered", fake) == "covered-20090802"
    assert dt.extract_version("spike", fake) == "Spike RISC-V ISA Simulator 1.1.1-dev"


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
    """detect_wsl detects WSL via uname.release or /proc/version content."""
    # Case 1: uname.release shows WSL
    class U:
        release = "5.4.72-microsoft-standard-WSL2"
    monkeypatch.setattr(dt.platform, "uname", lambda: U, raising=True)
    assert dt.detect_wsl() is True

    # Case 2: uname not WSL, but /proc/version mentions Microsoft
    class U2:
        release = "linux"
    monkeypatch.setattr(dt.platform, "uname", lambda: U2, raising=True)
    monkeypatch.setattr(dt.os.path, "exists", lambda p: p == "/proc/version", raising=True)

    def fake_open(_path, *_args, **_kw):
        from io import StringIO
        return StringIO("Linux version 5.4.0-azure #1 SMP x86_64 Microsoft")

    # Patch the correct symbol (builtins.open), not dt.open
    monkeypatch.setattr("builtins.open", fake_open, raising=True)
    assert dt.detect_wsl() is True

    # Case 3: neither uname nor /proc/version indicate WSL
    def fake_open2(_path, *_args, **_kw):
        from io import StringIO
        return StringIO("Linux version 6.1.0 (generic)")

    monkeypatch.setattr("builtins.open", fake_open2, raising=True)
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


# ---------------------------
# _noop_match() (direct hit)
# ---------------------------

def test__noop_match_group0_empty():
    m = dt._noop_match()
    assert m is not None
    assert m.group(0) == ""


# ---------------------------------------------------------
# analyze_env: exercise path_tool_map.setdefault(...).append
# and duplicate PATH entry with no tools
# ---------------------------------------------------------

def test_analyze_env_populates_tool_map_and_duplicates_tools_list(tmp_path, monkeypatch):
    # Keep the tool universe tiny so we can create real files
    monkeypatch.setattr(dt, "ALL_TOOLS", ["foo"], raising=True)

    # Two path entries; first repeats to create a duplicate entry
    p1 = tmp_path / "bin1"
    p2 = tmp_path / "bin2"
    p1.mkdir()
    p2.mkdir()
    # Create an executable "foo" in p1 to populate path_tool_map
    exe = p1 / "foo"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("PATH", f"{p1}:{p2}:{p1}")
    env = dt.analyze_env()

    # Duplicate PATH entry exists
    dups = env["path_duplicates"]
    assert dups, "Expected duplicate PATH entries"

    # Because p1 appears twice, its second occurrence in duplicates
    # should show associated tools including 'foo'
    dup_paths = [p for p, _ in dups]
    assert str(p1) in dup_paths
    tools_for_p1 = [tools for p, tools in dups if p == str(p1)][0]
    assert "foo" in tools_for_p1


# ---------------------------------------------------------
# detect_wsl: except path (force uname() to raise)
# ---------------------------------------------------------

def test_detect_wsl_exception_returns_false(monkeypatch):
    def boom():
        raise RuntimeError("uname broke")
    monkeypatch.setattr(dt.platform, "uname", boom, raising=True)
    assert dt.detect_wsl() is False


# ---------------------------------------------------------
# pro_diagnostics: else branches for tips
#  - duplicate PATH entry with NO tools
#  - bins_missing_in_path entry with tool==None
# ---------------------------------------------------------

def test_pro_diagnostics_else_branches_for_tips(monkeypatch):
    env = {
        "path_duplicates": [("/dup", [])],            # triggers "Duplicate PATH entry: /dup." (no tools)
        "bins_missing_in_path": [("/tb", None)],      # triggers "Tool bin not in PATH: /tb. Add this ..."
        "wsl": False,
        "path": "",
        "project_root": "/p",
        "user": "u",
        "home": "/h",
        "python_version": "3.10",
        "platform": "Linux",
    }
    # Health at 100 → skip the "not all required tools" tip to isolate the two else branches
    health = ("minimal", 100, [], [])
    monkeypatch.setattr(dt, "analyze_env", lambda: env, raising=True)
    monkeypatch.setattr(dt, "compute_health", lambda: health, raising=True)

    report = dt.pro_diagnostics()
    tips = "\n".join(report["tips"])
    assert "Duplicate PATH entry: /dup." in tips
    assert "Tool bin not in PATH: /tb." in tips
    assert "best results" in tips  # part of the else-tip text


def test_pro_diagnostics_formal_solver_matrix_ready(monkeypatch):
    """Formal flow includes solver matrix and ready status when a solver exists."""
    env = {
        "path_duplicates": [],
        "bins_missing_in_path": [],
        "wsl": False,
        "path": "",
        "project_root": "/p",
        "user": "u",
        "home": "/h",
        "python_version": "3.10",
        "platform": "Linux",
    }
    monkeypatch.setattr(dt, "analyze_env", lambda: env, raising=True)
    monkeypatch.setattr(
        dt,
        "compute_health",
        lambda: (
            "formal",
            100,
            [
                ("yosys", True, "/usr/bin/yosys", "0.1", True),
                ("gtkwave", True, "/usr/bin/gtkwave", "0.1", True),
                ("symbiyosys", True, "/usr/bin/sby", "1.0", True),
            ],
            [],
        ),
        raising=True,
    )

    def fake_find(tool):
        if tool == "boolector":
            return "/usr/bin/boolector", True, "boolector"
        if tool == "symbiyosys":
            return "/usr/bin/sby", True, "sby"
        return None, False, None

    monkeypatch.setattr(dt, "find_tool_binary", fake_find, raising=True)
    monkeypatch.setattr(dt, "extract_version", lambda *_: "1.0", raising=True)

    report = dt.pro_diagnostics()
    formal = report["health"]["formal"]
    assert formal["formal_readiness"] == "ready"
    assert formal["recommended_solver"] == "boolector"
    assert any(row["solver"] == "boolector" and row["installed"] for row in formal["solver_matrix"])


def test_pro_diagnostics_formal_missing_solver_tip(monkeypatch):
    """Formal flow emits targeted tip when sby exists but no solver is installed."""
    env = {
        "path_duplicates": [],
        "bins_missing_in_path": [],
        "wsl": False,
        "path": "",
        "project_root": "/p",
        "user": "u",
        "home": "/h",
        "python_version": "3.10",
        "platform": "Linux",
    }
    monkeypatch.setattr(dt, "analyze_env", lambda: env, raising=True)
    monkeypatch.setattr(
        dt,
        "compute_health",
        lambda: (
            "formal",
            100,
            [
                ("yosys", True, "/usr/bin/yosys", "0.1", True),
                ("gtkwave", True, "/usr/bin/gtkwave", "0.1", True),
                ("symbiyosys", True, "/usr/bin/sby", "1.0", True),
            ],
            [],
        ),
        raising=True,
    )
    def _fake_find_no_solvers(tool):
        if tool == "symbiyosys":
            return "/usr/bin/sby", True, "sby"  # sby present but no solvers
        return None, False, None
    monkeypatch.setattr(dt, "find_tool_binary", _fake_find_no_solvers, raising=True)

    report = dt.pro_diagnostics()
    formal = report["health"]["formal"]
    assert formal["formal_readiness"] == "blocked"
    tips = "\n".join(report["tips"])
    assert "no supported formal solver is available" in tips


# ---------------------------------------------------------
# extract_version: branches you listed
#  - yosys with no numeric substring → (unknown)
#  - verilator with no numeric substring → (unknown)
#  - openfpgaloader: exceptions then no match → (unknown)
#  - nextpnr: exception on first flag, no match on others → (unknown)
#  - iverilog: neither regex matches → falls to _noop_match() (empty string)
# ---------------------------------------------------------

def _mk_fake(path: Path):
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)

class _R:
    def __init__(self, out: str, err: str = ""):
        self.stdout = out
        self.stderr = err


def test_extract_version_yosys_and_verilator_unknown(tmp_path, monkeypatch):
    fake = _mk_fake(tmp_path / "t")

    def run(args, capture_output, text, timeout, check):
        # Deliberately return NO digits so _RE_GENERIC won't match
        return _R("no version here", "")

    monkeypatch.setattr(dt.subprocess, "run", run, raising=True)
    assert dt.extract_version("yosys", fake) == "(unknown)"
    assert dt.extract_version("verilator", fake) == "(unknown)"


def test_extract_version_openfpgaloader_all_fail_to_unknown(tmp_path, monkeypatch):
    fake = _mk_fake(tmp_path / "openfpgaloader")

    calls = {"n": 0}
    def run(args, capture_output, text, timeout, check):
        calls["n"] += 1
        # First flag raises (exercise 'except: continue')
        if calls["n"] == 1:
            raise RuntimeError("boom")
        # Second flag returns no digits
        return _R("still no numbers")

    monkeypatch.setattr(dt.subprocess, "run", run, raising=True)
    assert dt.extract_version("openfpgaloader", fake) == "(unknown)"


def test_extract_version_nextpnr_continue_and_unknown(tmp_path, monkeypatch):
    fake = _mk_fake(tmp_path / "nextpnr-ice40")
    seq = iter([
        ("raise", None),          # --version → raise → continue
        ("nodigits", "nope"),     # -v → no match
        ("help", "help text"),    # --help → no match
    ])

    def run(args, capture_output, text, timeout, check):
        tag, payload = next(seq)
        if tag == "raise":
            raise OSError("fail")
        return _R(payload or "")

    monkeypatch.setattr(dt.subprocess, "run", run, raising=True)
    assert dt.extract_version("nextpnr-ice40", fake) == "(unknown)"


def test_extract_version_iverilog_falls_to_noop_match(tmp_path, monkeypatch):
    fake = _mk_fake(tmp_path / "iverilog")

    def run(args, capture_output, text, timeout, check):
        # Neither the Icarus pattern nor generic numeric pattern will match
        return _R("no matchable content at all")

    monkeypatch.setattr(dt.subprocess, "run", run, raising=True)
    # When both regexes miss, code returns _noop_match().group(0) → "" (empty string)
    assert dt.extract_version("iverilog", fake) == ""


def test_find_tool_binary_nextpnr_npdir_exists_but_not_executable_returns_none(tmp_path, monkeypatch):
    """
    Cover the branch where ~/.local/nextpnr/bin exists and contains files,
    but none are executable → fall through to final `return None, False, None`.
    """
    # No PATH hit for nextpnr or its variants
    monkeypatch.setattr(dt.shutil, "which", lambda _name: None, raising=True)
    # HOME → tmp_path so np_dir exists
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)

    np_dir = tmp_path / ".local" / "nextpnr" / "bin"
    np_dir.mkdir(parents=True)

    # Create a matching file that is NOT executable
    f = np_dir / "nextpnr-ice40"
    f.write_text("#!/bin/sh\necho 'not exec'\n", encoding="utf-8")
    # ensure executable bit NOT set
    f.chmod(stat.S_IRUSR | stat.S_IWUSR)

    path, in_path, variant = dt.find_tool_binary("nextpnr")
    assert path is None and in_path is False and variant is None


def test_find_tool_binary_openfpgaloader_scan_bases_but_no_exec_returns_none(tmp_path, monkeypatch):
    """
    Cover the nested scan over:
      ~/.local/bin, /usr/bin, /usr/local/bin
    when neither 'openfpgaloader' nor 'openFPGALoader' is executable anywhere.
    """
    # No PATH hit for either casing
    monkeypatch.setattr(dt.shutil, "which", lambda _name: None, raising=True)

    # Neutralize host environment: treat every candidate as non-executable
    monkeypatch.setattr(dt.os, "access", lambda _p, _mode: False, raising=True)

    # Put a NON-executable candidate in ~/.local/bin to exercise candidate.exists()
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    cand = local_bin / "openfpgaloader"
    cand.write_text("#!/bin/sh\necho nope\n", encoding="utf-8")
    # permissions don't matter now (os.access patched), but keep it clearly non-exec:
    cand.chmod(stat.S_IRUSR | stat.S_IWUSR)

    path, in_path, variant = dt.find_tool_binary("openfpgaloader")
    assert path is None and in_path is False and variant is None


def test_extract_version_openfpgaloader_returns_group_match(monkeypatch, tmp_path):
    """
    Hit the 'if m: return m.group(1).strip()' branch for openfpgaloader by
    returning an output string that matches _RE_GENERIC.
    """
    fake = tmp_path / "openfpgaloader"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    class _R:
        def __init__(self, out: str, err: str = ""):
            self.stdout = out
            self.stderr = err

    # First flag tried is "--version"; return something the generic regex will capture
    monkeypatch.setattr(
        dt.subprocess,
        "run",
        lambda args, capture_output, text, timeout, check: _R("openFPGALoader 1.2.3"),
        raising=True,
    )

    assert dt.extract_version("openfpgaloader", str(fake)) == "1.2.3"


def test_find_tool_binary_nextpnr_npdir_exists_but_not_executable_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(dt.shutil, "which", lambda _n: None, raising=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)

    np_dir = tmp_path / ".local" / "nextpnr" / "bin"
    np_dir.mkdir(parents=True)
    f = np_dir / "nextpnr-ice40"
    f.write_text("#!/bin/sh\necho nope\n", encoding="utf-8")
    # ensure NOT executable
    f.chmod(stat.S_IRUSR | stat.S_IWUSR)

    path, in_path, variant = dt.find_tool_binary("nextpnr")
    assert path is None and in_path is False and variant is None


def test_find_tool_binary_openfpgaloader_scan_bases_but_no_exec_returns_none(tmp_path, monkeypatch):
    # No PATH hit (for either casing)
    monkeypatch.setattr(dt.shutil, "which", lambda _n: None, raising=True)
    # Treat everything as non-executable (avoid host env interference)
    monkeypatch.setattr(dt.os, "access", lambda _p, _m: False, raising=True)

    # Put a non-exec candidate in ~/.local/bin to exercise candidate.exists()
    monkeypatch.setattr(Path, "home", lambda: tmp_path, raising=True)
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    (local_bin / "openfpgaloader").write_text("#!/bin/sh\necho nope\n", encoding="utf-8")

    path, in_path, variant = dt.find_tool_binary("openfpgaloader")
    assert path is None and in_path is False and variant is None


def test_extract_version_openfpgaloader_returns_group_match(tmp_path, monkeypatch):
    fake = tmp_path / "openfpgaloader"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)

    class R:
        def __init__(self, out, err=""):
            self.stdout = out
            self.stderr = err

    # First flag tried is "--version"; return a string the generic regex will capture
    monkeypatch.setattr(
        dt.subprocess,
        "run",
        lambda args, capture_output, text, timeout, check: R("openFPGALoader 1.2.3"),
        raising=True,
    )
    assert dt.extract_version("openfpgaloader", str(fake)) == "1.2.3"


def test_analyze_env_populates_tool_map_and_duplicates_tools_list(tmp_path, monkeypatch):
    monkeypatch.setattr(dt, "ALL_TOOLS", ["foo"], raising=True)

    p1 = tmp_path / "bin1"
    p2 = tmp_path / "bin2"
    p1.mkdir()
    p2.mkdir()
    exe = p1 / "foo"
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("PATH", f"{p1}:{p2}:{p1}")  # duplicate p1
    env = dt.analyze_env()

    dups = env["path_duplicates"]
    assert dups
    # The duplicate for p1 should list 'foo' in the tools column
    tools_for_p1 = [tools for p, tools in dups if p == str(p1)][0]
    assert "foo" in tools_for_p1


def test_detect_wsl_reads_proc_version_true_and_false(monkeypatch):
    # uname not WSL; /proc/version present and contains Microsoft → True
    class U:
        release = "linux"
    monkeypatch.setattr(dt.platform, "uname", lambda: U, raising=True)
    monkeypatch.setattr(dt.os.path, "exists", lambda p: p == "/proc/version", raising=True)

    def open_microsoft(_p, *_a, **_k):
        from io import StringIO
        return StringIO("Linux ... Microsoft WSL")
    monkeypatch.setattr("builtins.open", open_microsoft, raising=True)
    assert dt.detect_wsl() is True

    # Now /proc/version without Microsoft → False
    def open_plain(_p, *_a, **_k):
        from io import StringIO
        return StringIO("Linux ... vanilla")
    monkeypatch.setattr("builtins.open", open_plain, raising=True)
    assert dt.detect_wsl() is False


def test_detect_wsl_exception_returns_false(monkeypatch):
    # Force an exception path in detection → conservative False
    def boom():
        raise RuntimeError("uname broke")
    monkeypatch.setattr(dt.platform, "uname", boom, raising=True)
    assert dt.detect_wsl() is False


def test_pro_diagnostics_tips_variants(monkeypatch):
    # With tools in duplicate + bin with tool name + WSL → 3 distinct tips + not-all-tools-installed
    env = {
        "path_duplicates": [("/dup1", ["yosys"])],
        "bins_missing_in_path": [("/home/u/.local/yosys/bin", "yosys")],
        "wsl": True,
        "path": "/a:/b",
        "project_root": "/proj",
        "user": "u",
        "home": "/home/u",
        "python_version": "3.10.0",
        "platform": "Linux",
    }
    monkeypatch.setattr(dt, "analyze_env", lambda: env, raising=True)
    monkeypatch.setattr(dt, "compute_health", lambda: ("minimal", 50, [], []), raising=True)
    report = dt.pro_diagnostics()
    tips = "\n".join(report["tips"])
    assert "Duplicate PATH entry" in tips and "(used by: yosys)" in tips
    assert "Tool bin not in PATH: /home/u/.local/yosys/bin (needed for: yosys)" in tips
    assert "Detected WSL environment" in tips
    assert "diagnose repair" in tips  # score < 100

    # Now: duplicate with NO tools + bin with tool=None + wsl False → else-branches
    env2 = {
        "path_duplicates": [("/dup2", [])],
        "bins_missing_in_path": [("/tb", None)],
        "wsl": False,
        "path": "",
        "project_root": "/p",
        "user": "u",
        "home": "/h",
        "python_version": "3.11",
        "platform": "Linux",
    }
    monkeypatch.setattr(dt, "analyze_env", lambda: env2, raising=True)
    monkeypatch.setattr(dt, "compute_health", lambda: ("minimal", 100, [], []), raising=True)
    report2 = dt.pro_diagnostics()
    tips2 = "\n".join(report2["tips"])
    assert "Duplicate PATH entry: /dup2." in tips2


# ---------------------------------------------------------------------------
# OpenROAD version extraction
# ---------------------------------------------------------------------------

import stat as _stat


def _make_fake_exe(tmp_path, name: str) -> "Path":
    p = tmp_path / name
    p.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    p.chmod(p.stat().st_mode | _stat.S_IXUSR)
    return p


def _fake_run_factory(stdout: str = "", stderr: str = ""):
    """Return a subprocess.run stub that yields fixed stdout/stderr."""
    class _R:
        def __init__(self):
            self.stdout = stdout
            self.stderr = stderr
    return lambda *a, **k: _R()


def test_extract_version_openroad_typical_output(tmp_path, monkeypatch):
    """OpenROAD v2.0-7074-g0884de799-dirty → version captured by _RE_OPENROAD."""
    exe = _make_fake_exe(tmp_path, "openroad")
    monkeypatch.setattr(
        dt.subprocess, "run",
        _fake_run_factory(stdout="OpenROAD v2.0-7074-g0884de799-dirty\n"),
        raising=True,
    )
    result = dt.extract_version("openroad", str(exe))
    assert result == "2.0-7074-g0884de799-dirty"


def test_extract_version_openroad_stderr_only(tmp_path, monkeypatch):
    """Version on stderr only (some OpenROAD builds) is still captured."""
    exe = _make_fake_exe(tmp_path, "openroad")
    monkeypatch.setattr(
        dt.subprocess, "run",
        _fake_run_factory(stdout="", stderr="OpenROAD v2.1-0-gabcdef\n"),
        raising=True,
    )
    result = dt.extract_version("openroad", str(exe))
    assert result == "2.1-0-gabcdef"


def test_extract_version_openroad_generic_fallback(tmp_path, monkeypatch):
    """If OpenROAD line is absent, generic regex extracts the version number."""
    exe = _make_fake_exe(tmp_path, "openroad")
    monkeypatch.setattr(
        dt.subprocess, "run",
        _fake_run_factory(stdout="version 3.1.0\n"),
        raising=True,
    )
    result = dt.extract_version("openroad", str(exe))
    assert "3.1" in result


def test_extract_version_openroad_timeout(tmp_path, monkeypatch):
    """subprocess.TimeoutExpired → human-readable message, not a crash."""
    exe = _make_fake_exe(tmp_path, "openroad")

    def _boom(*a, **k):
        raise dt.subprocess.TimeoutExpired(cmd=["openroad", "-version"], timeout=15)

    monkeypatch.setattr(dt.subprocess, "run", _boom, raising=True)
    result = dt.extract_version("openroad", str(exe))
    assert "timeout" in result.lower()


def test_extract_version_openroad_bare_build_id(tmp_path, monkeypatch):
    """Real-world output '26Q1-1805-g362a91a058' (no prefix, no dot) is captured."""
    exe = _make_fake_exe(tmp_path, "openroad")
    monkeypatch.setattr(
        dt.subprocess, "run",
        _fake_run_factory(stdout="26Q1-1805-g362a91a058\n"),
        raising=True,
    )
    result = dt.extract_version("openroad", str(exe))
    assert result == "26Q1-1805-g362a91a058"


def test_get_version_info_openroad_recognizes_line(monkeypatch):
    """get_version_info('openroad', path) returns the 'OpenROAD v...' line."""
    import saxoflow.installer.runner as r

    class _P:
        returncode = 0
        stdout = "OpenROAD v2.0-1234-gabcdef\nsome other line\n"

    monkeypatch.setattr(
        r.subprocess, "run",
        lambda *a, **k: _P(),
        raising=True,
    )
    result = r.get_version_info("openroad", "/usr/local/bin/openroad")
    assert "OpenROAD" in result
    assert "2.0" in result


def test_get_version_info_openroad_bare_build_id(monkeypatch):
    """get_version_info returns bare build-id '26Q1-...' when no prefix line exists."""
    import saxoflow.installer.runner as r

    class _P:
        returncode = 0
        stdout = "26Q1-1805-g362a91a058\n"

    monkeypatch.setattr(
        r.subprocess, "run",
        lambda *a, **k: _P(),
        raising=True,
    )
    result = r.get_version_info("openroad", "/usr/local/bin/openroad")
    assert result == "26Q1-1805-g362a91a058"


# ---------------------------------------------------------------------------
# extract_version — klayout/magic/netgen dpkg branch
# ---------------------------------------------------------------------------

def test_extract_version_klayout_dpkg(monkeypatch):
    """extract_version for klayout uses dpkg-query when available."""
    from saxoflow import diagnose_tools as dt

    class _DpkgResult:
        returncode = 0
        stdout = "ii  klayout  0.28.5-1  amd64  GDS viewer"
        stderr = ""

    class _VersionResult:
        returncode = 0
        stdout = ""
        stderr = "KLayout 0.28.5"

    call_log = []

    def _fake_run(cmd, **kwargs):
        call_log.append(cmd)
        if cmd[0] == "dpkg":
            return _DpkgResult()
        return _VersionResult()

    monkeypatch.setattr(dt.subprocess, "run", _fake_run)
    result = dt.extract_version("klayout", "/usr/bin/klayout")
    # Should parse version from dpkg output
    assert "0.28" in result


def test_extract_version_magic_dpkg(monkeypatch):
    """extract_version for magic falls back to dpkg for version."""
    from saxoflow import diagnose_tools as dt

    class _DpkgResult:
        returncode = 0
        stdout = "ii  magic  8.3.276-1  amd64  VLSI layout"
        stderr = ""

    monkeypatch.setattr(dt.subprocess, "run", lambda *a, **k: _DpkgResult())
    result = dt.extract_version("magic", "/usr/bin/magic")
    assert "8.3" in result


def test_extract_version_klayout_dpkg_no_match_fallback(monkeypatch):
    """When dpkg output doesn't match, klayout falls back to -v flag."""
    from saxoflow import diagnose_tools as dt

    call_log = []

    class _DpkgEmpty:
        returncode = 0
        stdout = "No packages found."
        stderr = ""

    class _VFlag:
        returncode = 0
        stdout = "KLayout 0.29.0"
        stderr = ""

    def _fake_run(cmd, **kwargs):
        call_log.append(cmd[0])
        if cmd[0] == "dpkg":
            return _DpkgEmpty()
        return _VFlag()

    monkeypatch.setattr(dt.subprocess, "run", _fake_run)
    result = dt.extract_version("klayout", "/usr/bin/klayout")
    # Should try dpkg first, then -v flag
    assert "dpkg" in call_log
    # Some version-like string should appear
    assert result  # non-empty