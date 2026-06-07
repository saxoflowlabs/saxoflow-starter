# saxoflow/makeflow.py
"""
SaxoFlow Make-based build commands.

This module exposes Click commands that orchestrate common EDA flow tasks via
a project `Makefile`. It keeps behavior compatible with the original script
while improving readability, documentation, and safety.

Commands provided (imported by the top-level CLI):
- sim:                 Icarus Verilog simulation
- sim_verilator:       Verilator C++ build (no run)
- sim_verilator_run:   Run the compiled Verilator executable
- wave:                Open GTKWave for Icarus VCDs
- wave_verilator:      Open GTKWave for Verilator VCDs
- simulate:            Icarus sim + GTKWave (easy mode)
- simulate_verilator:  Verilator build + run + GTKWave (easy mode)
- formal:              SymbiYosys formal verification
- synth:               Yosys synthesis
- clean:               Clean generated files
- check_tools:         Check tool availability in PATH

Notes
-----
- The helper `check_x_display` is currently **unused**; it's retained for
  future use and documented below.
- Behavior of printed messages, prompts, and return codes is preserved for
  all used parts.
"""

from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import click
from saxoflow.synthflow import run_synthesis

__all__ = [
    "sim",
    "sim_verilator",
    "sim_verilator_run",
    "wave",
    "wave_verilator",
    "simulate",
    "simulate_verilator",
    "formal",
    "synth",
    "clean",
    "check_tools",
]

# Canonical solver names accepted by CLI.
FORMAL_SOLVER_CHOICES = ["auto", "z3", "boolector", "bitwuzla", "yices", "cvc5"]

# Auto-selection order: Tier-1 first, then Tier-2 fallbacks.
FORMAL_AUTO_SOLVER_PRIORITY = ["z3", "boolector", "bitwuzla", "yices", "cvc5"]

# Binary aliases used to detect solver availability in PATH.
FORMAL_SOLVER_BINARIES = {
    "z3": ["z3"],
    "boolector": ["boolector"],
    "bitwuzla": ["bitwuzla"],
    "yices": ["yices", "yices-smt2", "yices_smt2"],
    "cvc5": ["cvc5"],
}

DEFAULT_RTL_SPECS: Tuple[str, ...] = (
    "source/rtl/verilog",
    "source/rtl/systemverilog",
)
DEFAULT_TB_SPECS: Tuple[str, ...] = (
    "source/tb/verilog",
    "source/tb/systemverilog",
)
DEFAULT_INCLUDE_SPECS: Tuple[str, ...] = (
    "source/rtl/include",
)
DEFAULT_FORMAL_RTL_SPECS: Tuple[str, ...] = (
    "source/rtl/systemverilog",
    "source/rtl/verilog",
)
DEFAULT_FORMAL_SVA_SPECS: Tuple[str, ...] = (
    "formal/source",
    "formal/src",
)
FORMAL_SPEC = "spec.sby"
_MODULE_RE = re.compile(
    r"\bmodule\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b"
)

# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def require_makefile() -> None:
    """Ensure the current directory contains a `Makefile`.

    Raises
    ------
    click.Abort
        If no Makefile is found in the current directory.
    """
    if not Path("Makefile").exists():
        click.secho("ERROR: No Makefile found in this directory.", fg="red")
        click.secho(
            "Run all SaxoFlow commands from the project root (where Makefile is).",
            fg="yellow",
        )
        raise click.Abort()


def run_make(target: str, extra_vars: Optional[Dict[str, str]] = None) -> Dict[str, object]:
    """Run a `make` target with optional variable overrides.

    Parameters
    ----------
    target
        The Makefile target to invoke (e.g., ``"sim-icarus"``).
    extra_vars
        Optional mapping of variable names to values passed as `VAR=VALUE`
        arguments to `make`.

    Returns
    -------
    dict
        A dictionary with keys: ``stdout``, ``stderr``, ``returncode``.

    Notes
    -----
    - This function does **not** raise on non-zero exit codes (to preserve
      original behavior). Callers can inspect ``returncode`` if needed.
    """
    if (
        target == "synth"
        and extra_vars
        and "YOSYS_BIN" in extra_vars
        and "YOSYS_SCRIPT" in extra_vars
        and not _makefile_supports_synth_overrides(Path("Makefile"))
    ):
        return _run_legacy_synth_compat(extra_vars)

    click.secho(f"make {target}", fg="cyan")
    cmd = ["make", target]
    if extra_vars:
        for k, v in extra_vars.items():
            cmd.append(f"{k}={v}")

    process = subprocess.run(cmd, capture_output=True, text=True)
    return {"stdout": process.stdout, "stderr": process.stderr, "returncode": process.returncode}


def _makefile_supports_synth_overrides(makefile: Path) -> bool:
    """Return whether the project synth recipe uses SaxoFlow's overrides."""
    try:
        content = makefile.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False

    recipe_lines: List[str] = []
    in_synth_recipe = False
    for line in content.splitlines():
        if re.match(r"^synth\s*:", line):
            in_synth_recipe = True
            continue
        if in_synth_recipe and re.match(r"^[^\s#][^=]*:", line):
            break
        if in_synth_recipe:
            recipe_lines.append(line)

    recipe = "\n".join(recipe_lines)
    return "$(YOSYS_BIN)" in recipe and "$(YOSYS_SCRIPT)" in recipe


def _run_legacy_synth_compat(extra_vars: Dict[str, str]) -> Dict[str, object]:
    """Run the selected Yosys script directly for pre-wrapper unit Makefiles."""
    yosys_binary = extra_vars["YOSYS_BIN"]
    yosys_script = extra_vars["YOSYS_SCRIPT"]
    report_path = Path("synthesis/reports/yosys.log")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    Path("synthesis/out").mkdir(parents=True, exist_ok=True)

    click.secho(
        "INFO: Legacy unit Makefile detected; running the generated Yosys "
        "script directly.",
        fg="yellow",
    )
    click.secho(f"{yosys_binary} -s {yosys_script}", fg="cyan")
    try:
        process = subprocess.run(
            [yosys_binary, "-s", yosys_script],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        report_path.write_text(f"ERROR: {exc}\n", encoding="utf-8")
        return {"stdout": "", "stderr": "", "returncode": 127}
    report_path.write_text(
        f"{process.stdout}{process.stderr}",
        encoding="utf-8",
    )
    return {"stdout": "", "stderr": "", "returncode": process.returncode}


def _collect_testbenches() -> List[Path]:
    """Collect available testbench files across project language folders.

    Returns
    -------
    list of pathlib.Path
        Ordered list of testbench file candidates found under:
        - source/tb/verilog/*.v
        - source/tb/systemverilog/*.sv
        - source/tb/vhdl/*.vhd, *.vhdl (used by non-Icarus flows)
    """
    return _expand_path_specs(
        DEFAULT_TB_SPECS + ("source/tb/vhdl",),
        (".v", ".sv", ".vhd", ".vhdl"),
    )


def _expand_path_specs(specs: Iterable[str], suffixes: Sequence[str]) -> List[Path]:
    """Expand explicit paths, directories, and glob patterns into matching files."""
    allowed_suffixes = {suffix.lower() for suffix in suffixes}
    files: List[Path] = []
    seen = set()
    for raw in specs:
        spec = str(raw or "").strip()
        if not spec:
            continue

        matches: List[Path] = []
        if any(ch in spec for ch in "*?["):
            matches = [Path(p) for p in sorted(glob.glob(spec, recursive=True))]
        else:
            path = Path(spec)
            if path.is_dir():
                matches = sorted(path.rglob("*"))
            elif path.exists():
                matches = [path]

        for match in matches:
            if not match.is_file():
                continue
            if match.suffix.lower() not in allowed_suffixes:
                continue
            key = match.as_posix()
            if key not in seen:
                files.append(match)
                seen.add(key)
    return files


def _join_make_paths(paths: Sequence[Path]) -> str:
    """Return a shell-safe-ish space-separated path list for Make variables."""
    return " ".join(path.as_posix() for path in paths)


def _include_flags(include_specs: Iterable[str]) -> str:
    """Return Icarus include flags for existing include directories."""
    include_dirs: List[Path] = []
    seen = set()
    for raw in include_specs:
        spec = str(raw or "").strip()
        if not spec:
            continue
        candidates = [Path(p) for p in sorted(glob.glob(spec))] if any(
            ch in spec for ch in "*?["
        ) else [Path(spec)]
        for candidate in candidates:
            if not candidate.is_dir():
                continue
            key = candidate.as_posix()
            if key not in seen:
                include_dirs.append(candidate)
                seen.add(key)
    return " ".join(f"-I{path.as_posix()}" for path in include_dirs)


def _build_icarus_vars(
    tb_file: Path,
    rtl_specs: Sequence[str] = (),
    tb_specs: Sequence[str] = (),
    include_specs: Sequence[str] = (),
) -> Optional[Dict[str, str]]:
    """Build Make variable overrides for an Icarus simulation."""
    rtl_files = _expand_path_specs(rtl_specs or DEFAULT_RTL_SPECS, (".v", ".sv"))
    if not rtl_files:
        click.secho(
            "ERROR: No RTL files found. Checked source/rtl/verilog and "
            "source/rtl/systemverilog.",
            fg="red",
        )
        click.secho(
            "Use --rtl <file-or-dir-or-glob> to point SaxoFlow at your RTL.",
            fg="yellow",
        )
        return None

    tb_files = (
        _expand_path_specs(tb_specs, (".v", ".sv", ".vhd", ".vhdl"))
        if tb_specs
        else [tb_file]
    )
    if not tb_files:
        click.secho("ERROR: No testbench files selected for simulation.", fg="red")
        click.secho(
            "Use --tb-file <file-or-dir-or-glob> or --tb <module-name>.",
            fg="yellow",
        )
        return None

    make_vars = {
        "TOP_TB": tb_file.stem,
        "RTL_SRCS": _join_make_paths(rtl_files),
        "TB_SRCS": _join_make_paths(tb_files),
    }
    include_flags = _include_flags(include_specs or DEFAULT_INCLUDE_SPECS)
    if include_flags:
        make_vars["INCLUDE_DIRS"] = include_flags
    return make_vars


def _resolve_icarus_testbench(
    tb: Optional[str],
    tb_specs: Sequence[str],
) -> Optional[Path]:
    """Resolve the primary testbench from --tb-file or normal TB lookup."""
    if tb_specs:
        tb_files = _expand_path_specs(tb_specs, (".v", ".sv", ".vhd", ".vhdl"))
        if not tb_files:
            click.secho("ERROR: No files matched --tb-file.", fg="red")
            return None
        if tb:
            for candidate in tb_files:
                if candidate.stem == tb:
                    return candidate
            click.secho(
                f"ERROR: --tb '{tb}' was not found among --tb-file matches.",
                fg="red",
            )
            return None
        if len(tb_files) == 1:
            return tb_files[0]

        click.secho("WARNING: Multiple --tb-file matches found:", fg="yellow")
        for idx, fpath in enumerate(tb_files):
            click.echo(f"  [{idx + 1}] {fpath}")
        choice = click.prompt("Select file to simulate (number)", type=int, default=1)
        return tb_files[choice - 1]

    return _resolve_testbench(tb, prompt_action="simulate")


def _solver_available(solver: str) -> bool:
    """Return True when any known binary alias for *solver* exists in PATH."""
    for binary in FORMAL_SOLVER_BINARIES.get(solver, [solver]):
        if shutil.which(binary):
            return True
    return False


def _extract_module_name(path: Path) -> str:
    """Return the first Verilog/SystemVerilog module name in *path*."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = _MODULE_RE.search(text)
    return match.group(1) if match else ""


def _select_single_file(paths: Sequence[Path], label: str, explicit: bool) -> Optional[Path]:
    """Return one file from *paths*, prompting only for auto-detected multiples."""
    if not paths:
        source = "provided" if explicit else "detected"
        click.secho(f"ERROR: No {label} files {source}.", fg="red")
        return None
    if len(paths) == 1:
        return paths[0]
    if explicit:
        click.secho(f"ERROR: Multiple {label} files matched explicit paths:", fg="red")
        for path in paths:
            click.echo(f"  {path}")
        click.secho(f"Use a single --{label} file path for this formal run.", fg="yellow")
        return None

    click.secho(f"WARNING: Multiple {label} files found:", fg="yellow")
    for idx, path in enumerate(paths):
        click.echo(f"  [{idx + 1}] {path}")
    choice = click.prompt(f"Select {label} file (number)", type=int, default=1)
    return paths[choice - 1]


def _resolve_formal_sources(
    rtl_specs: Sequence[str],
    sva_specs: Sequence[str],
) -> Optional[Tuple[List[Path], Path]]:
    """Resolve RTL and formal property/harness files for `saxoflow formal`."""
    explicit_rtl = bool(rtl_specs)
    explicit_sva = bool(sva_specs)
    rtl_files = _expand_path_specs(
        rtl_specs or DEFAULT_FORMAL_RTL_SPECS,
        (".v", ".sv"),
    )
    sva_files = _expand_path_specs(
        sva_specs or DEFAULT_FORMAL_SVA_SPECS,
        (".sva", ".sv"),
    )

    if not explicit_rtl and not explicit_sva and (not rtl_files or not sva_files):
        return None

    if not rtl_files:
        source = "provided" if explicit_rtl else "detected"
        click.secho(f"ERROR: No rtl files {source}.", fg="red")
        return None
    sva_file = _select_single_file(sva_files, "sva", explicit_sva)
    if sva_file is None:
        return None
    return rtl_files, sva_file


def _formal_read_command(paths: Sequence[Path]) -> str:
    """Return a Yosys read command for formal Verilog/SystemVerilog files."""
    if any(path.suffix.lower() in {".sv", ".sva"} for path in paths):
        return "read -formal -sv " + " ".join(path.name for path in paths)
    return "read -formal " + " ".join(path.name for path in paths)


def _write_formal_spec_for_sources(rtl_paths: Sequence[Path], sva_path: Path) -> Path:
    """Update spec.sby for the selected RTL and SVA files."""
    scripts_dir = Path("formal/scripts")
    reports_dir = Path("formal/reports")
    scripts_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    rtl_relpaths = [
        os.path.relpath(path, reports_dir).replace(os.sep, "/")
        for path in rtl_paths
    ]
    sva_rel = os.path.relpath(sva_path, reports_dir).replace(os.sep, "/")
    rtl_top = _extract_module_name(rtl_paths[0]) if rtl_paths else ""
    top_module = _extract_module_name(sva_path) or rtl_top or sva_path.stem
    read_paths = [*rtl_paths, sva_path]
    read_command = _formal_read_command(read_paths)
    files_block = "\n".join([*rtl_relpaths, sva_rel])

    spec = f"""# SaxoFlow formal specification
#
# Updated by `saxoflow formal` from detected or provided RTL/SVA paths.

[tasks]
bmc_z3
prove_z3

[options]
bmc_z3: mode bmc
bmc_z3: depth 20
prove_z3: mode prove
prove_z3: depth 20

[engines]
bmc_z3: smtbmc z3
prove_z3: smtbmc z3

[script]
{read_command}
prep -top {top_module}

[files]
{files_block}
"""
    spec_path = scripts_dir / FORMAL_SPEC
    spec_path.write_text(spec, encoding="utf-8")
    return spec_path


def _resolve_testbench(tb: Optional[str], prompt_action: str) -> Optional[Path]:
    """Resolve a testbench file from CLI `--tb` or interactively.

    Parameters
    ----------
    tb
        Base name of the testbench without extension (e.g., ``"my_tb"``). If
        provided, the file is searched across project TB dirs.
    prompt_action
        The action word to show in the selection prompt. Example values:
        ``"simulate"`` (Icarus) or ``"build"`` (Verilator).

    Returns
    -------
    pathlib.Path or None
        Path to the chosen testbench file, or ``None`` if not found/aborted.

    Behavior (preserved)
    --------------------
    - If `tb` is given: find the first matching file among .v, .sv, .vhd.
      If not found, print the same error and return None.
    - If `tb` omitted:
        - 0 files  -> print the same "No testbenches" message and return None.
        - 1 file   -> auto-select it.
        - >1 files -> prompt for a numbered choice, default = 1.
    """
    tb_files = _collect_testbenches()

    if tb:
        # Try to find the specific testbench across all TB directories
        for tb_dir in ("source/tb/verilog", "source/tb/systemverilog", "source/tb/vhdl"):
            for ext in (".v", ".sv", ".vhd", ".vhdl"):
                potential_path = Path(tb_dir) / f"{tb}{ext}"
                if potential_path.exists():
                    return potential_path

        click.secho(
            "ERROR: Testbench "
            f"'{tb}' (with .v, .sv, or .vhd extension) not found in any source/tb/ directory.",
            fg="red",
        )
        return None

    # Auto-detect mode (no --tb)
    if len(tb_files) == 1:
        return tb_files[0]
    if len(tb_files) == 0:
        click.secho(
            "ERROR: No testbenches (*.v, *.sv, *.vhd) found in source/tb/ directories.",
            fg="red",
        )
        return None

    # Multiple testbenches: prompt a selection
    click.secho("WARNING: Multiple testbenches found:", fg="yellow")
    for idx, fpath in enumerate(tb_files):
        click.echo(f"  [{idx + 1}] {fpath.name}")

    choice = click.prompt(
        f"Select file to {prompt_action} (number)",
        type=int,
        default=1,
    )
    # NOTE: Original code did not validate the numeric range; we keep the same
    # behavior and rely on list indexing to raise if the user picks an invalid
    # number.  # TODO: consider safe clamping in a future release.
    return tb_files[choice - 1]


# ---------------------------------------------------------------------------
# Simulation targets
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench module/file stem. Auto-detects if not set.",
)
@click.option(
    "--rtl",
    "rtl_specs",
    multiple=True,
    help="RTL file, directory, or glob. Repeat for multiple paths.",
)
@click.option(
    "--tb-file",
    "tb_specs",
    multiple=True,
    help="Testbench file, directory, or glob. Overrides --tb file lookup.",
)
@click.option(
    "--include",
    "include_specs",
    multiple=True,
    help="Include directory for `include files. Repeat for multiple dirs.",
)
def sim(
    tb: Optional[str],
    rtl_specs: Tuple[str, ...],
    tb_specs: Tuple[str, ...],
    include_specs: Tuple[str, ...],
) -> None:
    """
    Run simulation using Icarus Verilog.

    If ``--tb`` is not given, auto-detects ``*_tb.v``/``*.sv`` in TB dirs.
    """
    require_makefile()
    tb_file = _resolve_icarus_testbench(tb, tb_specs)
    if not tb_file:
        raise click.Abort()
    if tb_file.suffix.lower() in {".vhd", ".vhdl"}:
        click.secho(
            "ERROR: Icarus simulation does not support VHDL testbenches directly.",
            fg="red",
        )
        click.secho(
            "Use a Verilog/SystemVerilog testbench or a VHDL-capable flow.",
            fg="yellow",
        )
        raise click.Abort()

    tb_mod = tb_file.stem
    make_vars = _build_icarus_vars(
        tb_file,
        rtl_specs=rtl_specs,
        tb_specs=tb_specs,
        include_specs=include_specs,
    )
    if make_vars is None:
        raise click.Abort()

    click.secho(f"Running Icarus Verilog simulation with TB: {tb_mod}", fg="cyan")
    make_result = run_make("sim-icarus", extra_vars=make_vars)
    if make_result.get("stdout"):
        click.echo(str(make_result["stdout"]))
    if make_result.get("stderr"):
        click.secho(str(make_result["stderr"]), fg="red")
    if int(make_result.get("returncode", 1)) != 0:
        raise click.Abort()

    sim_out = Path("simulation/icarus/out.vvp")
    vcd_files = list(Path("simulation/icarus").glob("*.vcd"))

    outputs: List[str] = []
    if sim_out.exists():
        outputs.append(str(sim_out))
    if vcd_files:
        for v in vcd_files:
            try:
                outputs.append(f"{v} ({v.stat().st_size} bytes)")
            except OSError:
                outputs.append(str(v))

    if outputs:
        click.secho(f"Outputs: {', '.join(outputs)}", fg="yellow")


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.",
)
def sim_verilator(tb: Optional[str]) -> None:
    """
    Run Verilator C++ build step (not the run).

    If ``--tb`` is not given, auto-detects TB in the source TB directories.
    """
    if not shutil.which("verilator"):
        click.secho("ERROR: Verilator not found in PATH. Please install it.", fg="red")
        raise click.Abort()

    require_makefile()
    tb_file = _resolve_testbench(tb, prompt_action="build")
    if not tb_file:
        raise click.Abort()

    tb_mod = tb_file.stem
    click.secho(f"Running Verilator build with TB: {tb_mod}", fg="cyan")
    make_result = run_make("sim-verilator", extra_vars={"TOP_TB": tb_mod})
    if make_result.get("stdout"):
        click.echo(str(make_result["stdout"]))
    if make_result.get("stderr"):
        click.secho(str(make_result["stderr"]), fg="red")
    if int(make_result.get("returncode", 1)) != 0:
        raise click.Abort()

    verilator_dir = Path("simulation/verilator/obj_dir")
    if verilator_dir.exists():
        outputs = [str(p) for p in verilator_dir.glob("*") if p.is_file()]
        if outputs:
            click.secho(
                f"Outputs (simulation/verilator/obj_dir): {', '.join(outputs)}",
                fg="yellow",
            )


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench executable (without V prefix). Auto-detects most recent build.",
)
def sim_verilator_run(tb: Optional[str]) -> None:
    """Run Verilator C++ executable to generate VCD (after ``sim-verilator``)."""
    bin_dir = Path("simulation/verilator/obj_dir")

    # Find the testbench binary
    if tb:
        exe_file = bin_dir / f"V{tb}"
    else:
        # Auto-detect: newest V* file in obj_dir
        exe_files = sorted(bin_dir.glob("V*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not exe_files:
            click.secho("ERROR: No Verilator simulation executable found in obj_dir.", fg="red")
            return
        exe_file = exe_files[0]

    if not exe_file.exists():
        click.secho(
            f"ERROR: Executable {exe_file} not found. Did you build it with sim-verilator?",
            fg="red",
        )
        return

    click.secho(f"Running Verilator simulation: {exe_file.name}", fg="cyan")
    subprocess.run([str(exe_file)], check=True)

    # After run, look for dump.vcd
    vcd_path = bin_dir / "dump.vcd"
    if vcd_path.exists():
        click.secho(f"VCD output: {vcd_path}", fg="yellow")
    else:
        click.secho(
            "WARNING: No VCD generated. Ensure your C++ testbench enables tracing.",
            fg="yellow",
        )


# ---------------------------------------------------------------------------
# Unused helper (retained): X display check for GUI tools
# ---------------------------------------------------------------------------

def check_x_display() -> bool:
    """Warn if the X11 DISPLAY variable is missing (affects GUI tools).

    Returns
    -------
    bool
        True if DISPLAY looks set; False otherwise.

    Notes
    -----
    Currently unused by ``wave`` commands to preserve original behavior.
    Kept for future use when automatic GUI checks are desired.
    """
    if "DISPLAY" not in os.environ or not os.environ["DISPLAY"]:
        click.secho(
            "WARNING: DISPLAY variable is not set! GTKWave will not open a GUI window.\n"
            "   - If you are on WSL or remote, please run an X server (e.g., VcXsrv on Windows).\n"
            "   - Then: export DISPLAY=:0 (or use your IP)\n"
            "   - Or use a Windows GTKWave and open the .vcd manually.",
            fg="yellow",
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Waveform viewers
# ---------------------------------------------------------------------------


@click.command()
@click.argument("vcd_file", required=False)
def wave(vcd_file: Optional[str]) -> None:
    """
    Launch GTKWave for Icarus (default: ``simulation/icarus/*.vcd``).
    """
    vcd_dir = Path("simulation/icarus")
    if vcd_file:
        vcd_path = Path(vcd_file)
    else:
        vcd_files = sorted(vcd_dir.glob("*.vcd"))
        if not vcd_files:
            click.secho(f"WARNING: No VCD files found in {vcd_dir}/", fg="yellow")
            return
        if len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("WARNING: Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx + 1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]

    if not vcd_path.exists():
        click.secho(f"WARNING: {vcd_path} not found - you may need to simulate first.", fg="yellow")
        return

    click.secho(f"Launching GTKWave on {vcd_path}...", fg="green")
    subprocess.run(["gtkwave", str(vcd_path)])


@click.command()
@click.argument("vcd_file", required=False)
def wave_verilator(vcd_file: Optional[str]) -> None:
    """
    Launch GTKWave for Verilator VCDs (default: ``simulation/verilator/obj_dir/dump.vcd``).
    """
    vcd_dir = Path("simulation/verilator/obj_dir")
    if vcd_file:
        vcd_path = Path(vcd_file)
    else:
        vcd_files = sorted(vcd_dir.glob("*.vcd"))
        if not vcd_files:
            click.secho(f"WARNING: No VCD files found in {vcd_dir}/", fg="yellow")
            return
        if len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("WARNING: Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx + 1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]

    if not vcd_path.exists():
        click.secho(f"WARNING: {vcd_path} not found - did you run the Verilator sim?", fg="yellow")
        return

    click.secho(f"Launching GTKWave on {vcd_path}...", fg="green")
    subprocess.run(["gtkwave", str(vcd_path)])


# ---------------------------------------------------------------------------
# Easy simulate commands
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench module/file stem. Auto-detects if not set.",
)
@click.option(
    "--rtl",
    "rtl_specs",
    multiple=True,
    help="RTL file, directory, or glob. Repeat for multiple paths.",
)
@click.option(
    "--tb-file",
    "tb_specs",
    multiple=True,
    help="Testbench file, directory, or glob. Overrides --tb file lookup.",
)
@click.option(
    "--include",
    "include_specs",
    multiple=True,
    help="Include directory for `include files. Repeat for multiple dirs.",
)
def simulate(
    tb: Optional[str],
    rtl_specs: Tuple[str, ...],
    tb_specs: Tuple[str, ...],
    include_specs: Tuple[str, ...],
) -> None:
    """
    Easy mode: Run Icarus simulation + open GTKWave in one step.
    """
    ctx = click.get_current_context()
    ctx.invoke(
        sim,
        tb=tb,
        rtl_specs=rtl_specs,
        tb_specs=tb_specs,
        include_specs=include_specs,
    )
    ctx.invoke(wave)


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.",
)
def simulate_verilator(tb: Optional[str]) -> None:
    """
    Easy mode: Run Verilator build, run simulation, then open GTKWave in one step.
    """
    ctx = click.get_current_context()
    ctx.invoke(sim_verilator, tb=tb)
    ctx.invoke(sim_verilator_run, tb=tb)
    ctx.invoke(wave_verilator)


# ---------------------------------------------------------------------------
# Formal verification
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--solver",
    type=click.Choice(FORMAL_SOLVER_CHOICES, case_sensitive=False),
    default="auto",
    show_default=True,
    help=(
        "Solver selection policy for formal runs. "
        "Tier-1: z3, boolector; Tier-2: bitwuzla, yices, cvc5."
    ),
)
@click.option("--sby-task", help="Optional SBY task name to execute.")
@click.option("--autotune", is_flag=True, help="Pass through --autotune to SymbiYosys.")
@click.option("--timeout", type=int, help="Timeout in seconds passed to SymbiYosys.")
@click.option("--dumptasks", is_flag=True, help="Pass through --dumptasks to SymbiYosys.")
@click.option("--dumpcfg", is_flag=True, help="Pass through --dumpcfg to SymbiYosys.")
@click.option(
    "--rtl",
    "rtl_specs",
    multiple=True,
    help="RTL file, directory, or glob for formal. Repeat for multiple paths.",
)
@click.option(
    "--sva",
    "sva_specs",
    multiple=True,
    help="SVA/formal harness file, directory, or glob. Repeat for multiple paths.",
)
def formal(
    solver: str,
    sby_task: Optional[str],
    autotune: bool,
    timeout: Optional[int],
    dumptasks: bool,
    dumpcfg: bool,
    rtl_specs: Tuple[str, ...],
    sva_specs: Tuple[str, ...],
) -> None:
    """Run formal verification using SymbiYosys."""
    resolved_formal_sources = _resolve_formal_sources(rtl_specs, sva_specs)
    generated_sby: Optional[Path] = None
    if resolved_formal_sources is not None:
        rtl_paths, sva_path = resolved_formal_sources
        generated_sby = _write_formal_spec_for_sources(rtl_paths, sva_path)
        click.secho(
            "INFO: Formal RTL: " + ", ".join(path.as_posix() for path in rtl_paths),
            fg="cyan",
        )
        click.secho(f"INFO: Formal SVA: {sva_path}", fg="cyan")
        click.secho(f"INFO: Updated formal spec: {generated_sby}", fg="cyan")
    elif rtl_specs or sva_specs:
        raise click.Abort()

    sby_files = (
        [generated_sby]
        if generated_sby is not None
        else sorted(Path("formal/scripts").glob("*.sby"))
    )
    if not sby_files:
        click.secho("WARNING: No .sby spec found in formal/scripts/", fg="yellow")
        click.secho(
            "TIP: Add RTL under source/rtl/<language>/ and SVA under formal/source/, "
            "or pass --rtl <file> --sva <file>.",
            fg="cyan",
        )
        raise click.Abort()

    selected_solver: Optional[str] = None
    if solver == "auto":
        for candidate in FORMAL_AUTO_SOLVER_PRIORITY:
            if _solver_available(candidate):
                selected_solver = candidate
                break
    else:
        if not _solver_available(solver):
            click.secho(
                f"ERROR: Requested solver '{solver}' is not available in PATH.",
                fg="red",
            )
            click.secho(
                (
                    "TIP: Install it with `saxoflow install <solver>` "
                    "or `saxoflow install formal-complete`."
                ),
                fg="cyan",
            )
            raise click.Abort()
        selected_solver = solver

    click.secho("INFO: Running formal verification via SymbiYosys...", fg="cyan")

    # Preserve existing behavior when no new option is used and no sources were auto-detected.
    has_advanced_flags = any([
        sby_task,
        autotune,
        timeout is not None,
        dumptasks,
        dumpcfg,
        generated_sby is not None,
    ])
    if solver == "auto" and not has_advanced_flags:
        result = run_make("formal")
    else:
        sby_file = sby_files[0].name
        extra_vars: Dict[str, str] = {
            "SBY_FILE": f"../scripts/{sby_file}",
            "SBY_TASK": sby_task or "",
            "SBY_TIMEOUT": str(timeout) if timeout is not None else "",
            "SBY_AUTOTUNE": "1" if autotune else "",
            "SBY_DUMPTASKS": "1" if dumptasks else "",
            "SBY_DUMPCFG": "1" if dumpcfg else "",
            "SBY_SOLVER": selected_solver or "",
        }
        if selected_solver:
            click.secho(f"INFO: Formal solver policy selected: {selected_solver}", fg="cyan")
        result = run_make("formal", extra_vars=extra_vars)

    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    returncode = int(result.get("returncode", 0))
    if stdout:
        click.echo(stdout, nl=False)
    if stderr:
        click.echo(stderr, err=True, nl=False)
    if returncode != 0:
        raise click.Abort()

    reports = list(Path("formal/reports").glob("*"))
    outputs = list(Path("formal/out").glob("*"))
    if reports or outputs:
        parts: List[str] = []
        if reports:
            parts.append(f"reports: {', '.join(str(p) for p in reports)}")
        if outputs:
            parts.append(f"out: {', '.join(str(p) for p in outputs)}")
        click.secho(f"Formal outputs: {', '.join(parts)}", fg="yellow")


# ---------------------------------------------------------------------------
# Synthesis target
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--rtl",
    "rtl_specs",
    multiple=True,
    metavar="PATH",
    help="RTL file, directory, or glob. Repeat for multiple inputs.",
)
@click.option(
    "--include",
    "include_specs",
    multiple=True,
    metavar="DIR",
    help="Include directory. Repeat for multiple directories.",
)
@click.option(
    "--define",
    "defines",
    multiple=True,
    metavar="NAME[=VALUE]",
    help="Preprocessor definition. Repeat for multiple definitions.",
)
@click.option("--top", metavar="MODULE", help="Top module for synthesis.")
@click.option(
    "--param",
    "parameter_specs",
    multiple=True,
    metavar="NAME=VALUE",
    help="Top-module parameter override. Repeat for multiple parameters.",
)
@click.option(
    "--frontend",
    type=click.Choice(["auto", "builtin", "slang"]),
    default="auto",
    show_default=True,
    help="SystemVerilog frontend policy.",
)
@click.option(
    "--target",
    type=click.Choice(["generic", "ice40", "ecp5", "xilinx", "asic"]),
    default="generic",
    show_default=True,
    help="Synthesis target profile.",
)
@click.option(
    "--device",
    type=click.Choice(["hx", "lp", "u"]),
    default="hx",
    show_default=True,
    help="iCE40 device family.",
)
@click.option(
    "--family",
    type=click.Choice(
        [
            "xcup", "xcu", "xc7", "xc6s", "xc6v", "xc5v", "xc4v",
            "xc3sda", "xc3sa", "xc3se", "xc3s", "xc2vp", "xc2v",
            "xcve", "xcv",
        ]
    ),
    default="xc7",
    show_default=True,
    help="Xilinx architecture family.",
)
@click.option(
    "--liberty",
    type=click.Path(dir_okay=False, path_type=str),
    help="Liberty cell library for ASIC mapping.",
)
@click.option(
    "--clock-period",
    type=click.FloatRange(min=0, min_open=True),
    metavar="NS",
    help="ASIC ABC delay target in nanoseconds.",
)
@click.option(
    "--lut",
    type=click.IntRange(min=1),
    metavar="INTEGER",
    help="Generic LUT mapping width.",
)
@click.option(
    "--flatten/--keep-hierarchy",
    default=True,
    show_default=True,
    help="Flatten or preserve design hierarchy.",
)
@click.option(
    "--format",
    "formats",
    multiple=True,
    type=click.Choice(["verilog", "json", "blif", "edif"]),
    help="Output netlist format. Repeat for multiple formats.",
)
@click.option(
    "--output-prefix",
    metavar="PATH",
    help="Output basename under synthesis/out, without an extension.",
)
@click.option(
    "--preflight-lint",
    is_flag=True,
    help="Run `saxoflow lint` before synthesis.",
)
@click.option(
    "--script",
    type=click.Path(dir_okay=False, path_type=str),
    help="Run an existing Yosys script unchanged.",
)
@click.option(
    "--show-log/--no-show-log",
    default=True,
    show_default=True,
    help="Print the captured Yosys log in the CLI.",
)
@click.option(
    "--schematic/--no-schematic",
    "create_schematic",
    default=True,
    show_default=True,
    help="Render the synthesized JSON netlist with NetlistSVG.",
)
@click.option(
    "--schematic-output",
    metavar="FILE",
    help="Schematic SVG destination.",
)
@click.option(
    "--schematic-input",
    metavar="FILE",
    help="Yosys JSON input, primarily for custom synthesis scripts.",
)
@click.option(
    "--schematic-skin",
    type=click.Path(dir_okay=False, path_type=str),
    metavar="FILE",
    help="Optional NetlistSVG skin file.",
)
@click.option(
    "--schematic-timeout",
    type=click.IntRange(min=1),
    default=120,
    show_default=True,
    metavar="SECONDS",
    help="Maximum NetlistSVG rendering time.",
)
@click.option(
    "--open-schematic/--no-open-schematic",
    default=True,
    show_default=True,
    help="Open the generated SVG after synthesis.",
)
def synth(
    rtl_specs: Tuple[str, ...],
    include_specs: Tuple[str, ...],
    defines: Tuple[str, ...],
    top: Optional[str],
    parameter_specs: Tuple[str, ...],
    frontend: str,
    target: str,
    device: str,
    family: str,
    liberty: Optional[str],
    clock_period: Optional[float],
    lut: Optional[int],
    flatten: bool,
    formats: Tuple[str, ...],
    output_prefix: Optional[str],
    preflight_lint: bool,
    script: Optional[str],
    show_log: bool,
    create_schematic: bool,
    schematic_output: Optional[str],
    schematic_input: Optional[str],
    schematic_skin: Optional[str],
    schematic_timeout: int,
    open_schematic: bool,
) -> None:
    """Synthesize discovered or explicitly selected RTL using Yosys."""
    run_synthesis(
        run_make=run_make,
        rtl_specs=rtl_specs,
        include_specs=include_specs,
        defines=defines,
        top=top,
        parameter_specs=parameter_specs,
        frontend=frontend,
        target=target,
        device=device,
        family=family,
        liberty=liberty,
        clock_period=clock_period,
        lut=lut,
        flatten=flatten,
        formats=formats,
        output_prefix=output_prefix,
        preflight_lint=preflight_lint,
        script=script,
        show_log=show_log,
        create_schematic=create_schematic,
        schematic_output=schematic_output,
        schematic_input=schematic_input,
        schematic_skin=schematic_skin,
        schematic_timeout=schematic_timeout,
        open_schematic=open_schematic,
    )


# ---------------------------------------------------------------------------
# Clean target
# ---------------------------------------------------------------------------


@click.command()
@click.option("-y", "--yes", is_flag=True, help="Skip confirmation prompt.")
def clean(yes: bool) -> None:
    """Clean all output and intermediate files."""
    if yes or click.confirm("Clean all generated files and build artifacts?"):
        run_make("clean")
    else:
        click.secho("INFO: Clean canceled.", fg="cyan")


# ---------------------------------------------------------------------------
# Tool check
# ---------------------------------------------------------------------------


@click.command()
def check_tools() -> None:
    """Check tool availability in PATH."""
    # Import directly from definitions to avoid relying on saxoflow.tools __init__
    from saxoflow.tools.definitions import TOOL_DESCRIPTIONS  # noqa: PLC0415
    from saxoflow.diagnose_tools import find_tool_binary, extract_version  # noqa: PLC0415

    click.secho("INFO: Checking installed tool availability:\n", fg="cyan")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        path, _, variant = find_tool_binary(tool)
        if path:
            version = extract_version(variant or tool, path)
            wrapped = (
                version
                if version.startswith("(") and version.endswith(")")
                else f"({version})"
            )
            version_str = click.style(f"  {wrapped}", fg="bright_black")
            status = click.style("FOUND   ", fg="green")
            click.echo(f"{tool.ljust(18)} {status} - {desc}{version_str}")
        else:
            status = click.style("MISSING ", fg="red")
            click.echo(f"{tool.ljust(18)} {status} - {desc}")
