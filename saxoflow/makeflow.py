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

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import click

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
        click.secho("❌ No Makefile found in this directory.", fg="red")
        click.secho(
            "💡 Run all SaxoFlow commands from the project root (where Makefile is).",
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
    click.secho(f"🛠️  make {target}", fg="blue")
    cmd = ["make", target]
    if extra_vars:
        for k, v in extra_vars.items():
            cmd.append(f"{k}={v}")

    process = subprocess.run(cmd, capture_output=True, text=True)
    return {"stdout": process.stdout, "stderr": process.stderr, "returncode": process.returncode}


def _collect_testbenches() -> List[Path]:
    """Collect available testbench files across supported languages.

    Returns
    -------
    list of pathlib.Path
        Ordered list of testbench file candidates found under:
        - source/tb/verilog/*.v
        - source/tb/systemverilog/*.sv
        - source/tb/vhdl/*.vhd
    """
    return (
        sorted(Path("source/tb/verilog").glob("*.v"))
        + sorted(Path("source/tb/systemverilog").glob("*.sv"))
        + sorted(Path("source/tb/vhdl").glob("*.vhd"))
    )


def _resolve_testbench(tb: Optional[str], prompt_action: str) -> Optional[Path]:
    """Resolve a testbench file from CLI `--tb` or interactively.

    Parameters
    ----------
    tb
        Base name of the testbench without extension (e.g., ``"my_tb"``). If
        provided, the file is searched across verilog/systemverilog/vhdl TB dirs.
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
            for ext in (".v", ".sv", ".vhd"):
                potential_path = Path(tb_dir) / f"{tb}{ext}"
                if potential_path.exists():
                    return potential_path

        click.secho(
            "❌ Testbench "
            f"'{tb}' (with .v, .sv, or .vhd extension) not found in any source/tb/ directory.",
            fg="red",
        )
        return None

    # Auto-detect mode (no --tb)
    if len(tb_files) == 1:
        return tb_files[0]
    if len(tb_files) == 0:
        click.secho(
            "❌ No testbenches (*.v, *.sv, *.vhd) found in source/tb/ directories.",
            fg="red",
        )
        return None

    # Multiple testbenches: prompt a selection
    click.secho("Multiple testbenches found:", fg="yellow")
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
    help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.",
)
def sim(tb: Optional[str]) -> None:
    """
    Run simulation using Icarus Verilog.

    If ``--tb`` is not given, auto-detects ``*_tb.v``/``*.sv``/``*.vhd`` in TB dirs.
    """
    require_makefile()
    tb_file = _resolve_testbench(tb, prompt_action="simulate")
    if not tb_file:
        return

    tb_mod = tb_file.stem
    click.secho(f"🧪 Running Icarus Verilog simulation with TB: {tb_mod}", fg="cyan")
    run_make("sim-icarus", extra_vars={"TOP_TB": tb_mod})

    sim_out = Path("simulation/icarus/out.vvp")
    vcd_files = list(Path("simulation/icarus").glob("*.vcd"))

    outputs: List[str] = []
    if sim_out.exists():
        outputs.append(str(sim_out))
    if vcd_files:
        outputs.extend(str(v) for v in vcd_files)

    if outputs:
        click.secho(f"🗂️  Outputs: {', '.join(outputs)}", fg="yellow")


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
        click.secho("❌ Verilator not found in PATH. Please install it.", fg="red")
        raise click.Abort()

    require_makefile()
    tb_file = _resolve_testbench(tb, prompt_action="build")
    if not tb_file:
        return

    tb_mod = tb_file.stem
    click.secho(f"⚡ Running Verilator build with TB: {tb_mod}", fg="cyan")
    run_make("sim-verilator", extra_vars={"TOP_TB": tb_mod})

    verilator_dir = Path("simulation/verilator/obj_dir")
    if verilator_dir.exists():
        outputs = [str(p) for p in verilator_dir.glob("*") if p.is_file()]
        if outputs:
            click.secho(
                f"🗂️  Outputs (simulation/verilator/obj_dir): {', '.join(outputs)}",
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
            click.secho("❌ No Verilator simulation executable found in obj_dir.", fg="red")
            return
        exe_file = exe_files[0]

    if not exe_file.exists():
        click.secho(
            f"❌ Executable {exe_file} not found. Did you build it with sim-verilator?",
            fg="red",
        )
        return

    click.secho(f"🏃 Running Verilator simulation: {exe_file.name}", fg="cyan")
    subprocess.run([str(exe_file)], check=True)

    # After run, look for dump.vcd
    vcd_path = bin_dir / "dump.vcd"
    if vcd_path.exists():
        click.secho(f"🗂️  VCD output: {vcd_path}", fg="yellow")
    else:
        click.secho(
            "⚠️  No VCD generated. Ensure your C++ testbench enables tracing.",
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
            "⚠️  DISPLAY variable is not set! GTKWave will not open a GUI window.\n"
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
            click.secho(f"⚠️  No VCD files found in {vcd_dir}/", fg="yellow")
            return
        if len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx + 1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]

    if not vcd_path.exists():
        click.secho(f"⚠️  {vcd_path} not found — you may need to simulate first.", fg="yellow")
        return

    click.secho(f"📈 Launching GTKWave on {vcd_path}...", fg="green")
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
            click.secho(f"⚠️  No VCD files found in {vcd_dir}/", fg="yellow")
            return
        if len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx + 1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]

    if not vcd_path.exists():
        click.secho(f"⚠️  {vcd_path} not found — did you run the Verilator sim?", fg="yellow")
        return

    click.secho(f"📈 Launching GTKWave on {vcd_path}...", fg="green")
    subprocess.run(["gtkwave", str(vcd_path)])


# ---------------------------------------------------------------------------
# Easy simulate commands
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--tb",
    help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.",
)
def simulate(tb: Optional[str]) -> None:
    """
    Easy mode: Run Icarus simulation + open GTKWave in one step.
    """
    ctx = click.get_current_context()
    ctx.invoke(sim, tb=tb)
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
def formal() -> None:
    """Run formal verification using SymbiYosys."""
    sby_files = list(Path("formal/scripts").glob("*.sby"))
    if not sby_files:
        click.secho("⚠️  No .sby spec found in formal/scripts/", fg="yellow")
        raise click.Abort()

    click.secho("📐 Running formal verification via SymbiYosys...", fg="cyan")
    run_make("formal")

    reports = list(Path("formal/reports").glob("*"))
    outputs = list(Path("formal/out").glob("*"))
    if reports or outputs:
        parts: List[str] = []
        if reports:
            parts.append(f"reports: {', '.join(str(p) for p in reports)}")
        if outputs:
            parts.append(f"out: {', '.join(str(p) for p in outputs)}")
        click.secho(f"🗂️  Formal outputs: {', '.join(parts)}", fg="yellow")


# ---------------------------------------------------------------------------
# Synthesis target
# ---------------------------------------------------------------------------


@click.command()
def synth() -> None:
    """Run synthesis using Yosys."""
    synth_script = Path("synthesis/scripts/synth.ys")
    if not synth_script.exists():
        click.secho("⚠️  synthesis/scripts/synth.ys not found.", fg="yellow")
        raise click.Abort()

    require_makefile()
    click.secho("🔧 Running Yosys synthesis...", fg="cyan")
    run_make("synth")

    reports = list(Path("synthesis/reports").glob("*"))
    outputs = list(Path("synthesis/out").glob("*"))
    if reports or outputs:
        parts: List[str] = []
        if reports:
            parts.append(f"reports: {', '.join(str(p) for p in reports)}")
        if outputs:
            parts.append(f"out: {', '.join(str(p) for p in outputs)}")
        click.secho(f"🗂️  Synthesis outputs: {', '.join(parts)}", fg="yellow")


# ---------------------------------------------------------------------------
# Clean target
# ---------------------------------------------------------------------------


@click.command()
def clean() -> None:
    """Clean all output and intermediate files."""
    if click.confirm("🧹 Clean all generated files and build artifacts?"):
        run_make("clean")
    else:
        click.echo("❎ Clean canceled.")


# ---------------------------------------------------------------------------
# Tool check
# ---------------------------------------------------------------------------


@click.command()
def check_tools() -> None:
    """Check tool availability in PATH."""
    # Import here to avoid circular import if __init__ changes; preserve original.
    from saxoflow.tools import TOOL_DESCRIPTIONS  # type: ignore  # TODO: unify import path

    click.echo("🔍 Checking installed tool availability:\n")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        path = shutil.which(tool)
        status = click.style("✅ FOUND  ", fg="green") if path else click.style("❌ MISSING", fg="red")
        click.echo(f"{tool.ljust(18)} {status} — {desc}")
