# saxoflow/makeflow.py — v2.3 Pro Auto-detecting, Folder-Aware Task Wrappers
import os
import subprocess
import click
import shutil
from pathlib import Path


# --------------------------
# Shared Utils
# --------------------------

def require_makefile():
    if not Path("Makefile").exists():
        click.secho("❌ No Makefile found in this directory.", fg="red")
        click.secho(
            "💡 Run all SaxoFlow commands from the project root (where Makefile is).",
            fg="yellow"
        )
        raise click.Abort()


def run_make(target: str, extra_vars=None):
    click.secho(f"🛠️  make {target}", fg="blue")
    cmd = ["make", target]
    if extra_vars:
        for k, v in extra_vars.items():
            cmd.append(f"{k}={v}")

    process = subprocess.run(cmd, capture_output=True, text=True)

    return {
        "stdout": process.stdout,
        "stderr": process.stderr,
        "returncode": process.returncode
    }


# --------------------------
# Simulation Targets
# --------------------------

@click.command()
@click.option('--tb', help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.")
def sim(tb):
    """
    Run simulation using Icarus Verilog.
    If --tb is not given, auto-detects *_tb.v in simulation/icarus.
    """
    require_makefile()
    tb_files = (
        sorted(Path("source/tb/verilog").glob("*.v")) +
        sorted(Path("source/tb/systemverilog").glob("*.sv")) +
        sorted(Path("source/tb/vhdl").glob("*.vhd"))
    )
    if tb:
        # Try to find the specific testbench across all TB directories
        found_tb_file = None
        for tb_dir in ["source/tb/verilog", "source/tb/systemverilog", "source/tb/vhdl"]:
            for ext in [".v", ".sv", ".vhd"]:
                potential_path = Path(tb_dir) / f"{tb}{ext}"
                if potential_path.exists():
                    found_tb_file = potential_path
                    break
            if found_tb_file:
                break
        if not found_tb_file:
            click.secho(
                f"❌ Testbench '{tb}' (with .v, .sv, or .vhd extension) not found in any source/tb/ directory.",
                fg="red"
            )
            return
        tb_file = found_tb_file
    elif len(tb_files) == 1:
        tb_file = tb_files[0]
    elif len(tb_files) == 0:
        click.secho(
            "❌ No testbenches (*.v, *.sv, *.vhd) found in source/tb/ directories.",
            fg="red"
        )
        return
    else:
        click.secho("Multiple testbenches found:", fg="yellow")
        for idx, f in enumerate(tb_files):
            click.echo(f"  [{idx+1}] {f.name}")
        choice = click.prompt("Select file to simulate (number)", type=int, default=1)
        tb_file = tb_files[choice - 1]

    tb_mod = tb_file.stem
    click.secho(f"🧪 Running Icarus Verilog simulation with TB: {tb_mod}", fg="cyan")
    run_make("sim-icarus", extra_vars={"TOP_TB": tb_mod})

    sim_out = Path("simulation/icarus/out.vvp")
    vcd_files = list(Path("simulation/icarus").glob("*.vcd"))
    msg = []
    if sim_out.exists():
        msg.append(str(sim_out))
    if vcd_files:
        msg.extend(str(v) for v in vcd_files)
    if msg:
        click.secho(f"🗂️  Outputs: {', '.join(msg)}", fg="yellow")


@click.command()
@click.option('--tb', help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.")
def sim_verilator(tb):
    """
    Run Verilator C++ build step (not the run).
    If --tb is not given, auto-detects *_tb.v in simulation/verilator.
    """
    if not shutil.which("verilator"):
        click.secho("❌ Verilator not found in PATH. Please install it.", fg="red")
        raise click.Abort()
    require_makefile()
    tb_files = (
        sorted(Path("source/tb/verilog").glob("*.v")) +
        sorted(Path("source/tb/systemverilog").glob("*.sv")) +
        sorted(Path("source/tb/vhdl").glob("*.vhd"))
    )
    if tb:
        # Try to find the specific testbench across all TB directories
        found_tb_file = None
        for tb_dir in ["source/tb/verilog", "source/tb/systemverilog", "source/tb/vhdl"]:
            for ext in [".v", ".sv", ".vhd"]:
                potential_path = Path(tb_dir) / f"{tb}{ext}"
                if potential_path.exists():
                    found_tb_file = potential_path
                    break
            if found_tb_file:
                break
        if not found_tb_file:
            click.secho(
                f"❌ Testbench '{tb}' (with .v, .sv, or .vhd extension) not found in any source/tb/ directory.",
                fg="red"
            )
            return
        tb_file = found_tb_file
    elif len(tb_files) == 1:
        tb_file = tb_files[0]
    elif len(tb_files) == 0:
        click.secho(
            "❌ No testbenches (*.v, *.sv, *.vhd) found in source/tb/ directories.",
            fg="red"
        )
        return
    else:
        click.secho("Multiple testbenches found:", fg="yellow")
        for idx, f in enumerate(tb_files):
            click.echo(f"  [{idx+1}] {f.name}")
        choice = click.prompt("Select file to build (number)", type=int, default=1)
        tb_file = tb_files[choice - 1]

    tb_mod = tb_file.stem
    click.secho(f"⚡ Running Verilator build with TB: {tb_mod}", fg="cyan")
    run_make("sim-verilator", extra_vars={"TOP_TB": tb_mod})

    verilator_dir = Path("simulation/verilator/obj_dir")
    if verilator_dir.exists():
        outputs = [str(p) for p in verilator_dir.glob("*") if p.is_file()]
        if outputs:
            click.secho(
                f"🗂️  Outputs (simulation/verilator/obj_dir): {', '.join(outputs)}",
                fg="yellow"
            )


@click.command()
@click.option('--tb', help="Name of the testbench executable (without V prefix). Auto-detects most recent build.")
def sim_verilator_run(tb):
    """
    Run Verilator C++ executable to generate VCD (after sim-verilator).
    """
    bin_dir = Path("simulation/verilator/obj_dir")
    # Find the testbench binary
    if tb:
        exe_file = bin_dir / f"V{tb}"
    else:
        # Auto-detect: use newest V* file in obj_dir
        exe_files = sorted(bin_dir.glob("V*"), key=lambda f: f.stat().st_mtime, reverse=True)
        if not exe_files:
            click.secho("❌ No Verilator simulation executable found in obj_dir.", fg="red")
            return
        exe_file = exe_files[0]
    if not exe_file.exists():
        click.secho(
            f"❌ Executable {exe_file} not found. Did you build it with sim-verilator?",
            fg="red"
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
            fg="yellow"
        )


def check_x_display():
    if "DISPLAY" not in os.environ or not os.environ["DISPLAY"]:
        click.secho(
            "⚠️  DISPLAY variable is not set! GTKWave will not open a GUI window.\n"
            "   - If you are on WSL or remote, please run an X server (e.g., VcXsrv on Windows).\n"
            "   - Then: export DISPLAY=:0 (or use your IP)\n"
            "   - Or use a Windows GTKWave and open the .vcd manually.",
            fg="yellow"
        )
        return False
    return True


# --------------------------
# Waveform Viewers
# --------------------------

@click.command()
@click.argument("vcd_file", required=False)
def wave(vcd_file):
    """
    Launch GTKWave for Icarus (default: simulation/icarus/*.vcd).
    """
    vcd_dir = Path("simulation/icarus")
    if vcd_file:
        vcd_path = Path(vcd_file)
    else:
        vcd_files = sorted(vcd_dir.glob("*.vcd"))
        if not vcd_files:
            click.secho(f"⚠️  No VCD files found in {vcd_dir}/", fg="yellow")
            return
        elif len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx+1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]
    if not vcd_path.exists():
        click.secho(f"⚠️  {vcd_path} not found — you may need to simulate first.", fg="yellow")
        return
    click.secho(f"📈 Launching GTKWave on {vcd_path}...", fg="green")
    subprocess.run(["gtkwave", str(vcd_path)])


@click.command()
@click.argument("vcd_file", required=False)
def wave_verilator(vcd_file):
    """
    Launch GTKWave for Verilator-generated VCD (default: simulation/verilator/obj_dir/dump.vcd).
    """
    vcd_dir = Path("simulation/verilator/obj_dir")
    if vcd_file:
        vcd_path = Path(vcd_file)
    else:
        vcd_files = sorted(vcd_dir.glob("*.vcd"))
        if not vcd_files:
            click.secho(f"⚠️  No VCD files found in {vcd_dir}/", fg="yellow")
            return
        elif len(vcd_files) == 1:
            vcd_path = vcd_files[0]
        else:
            click.secho("Multiple VCD files found:", fg="yellow")
            for idx, vcd in enumerate(vcd_files):
                click.echo(f"  [{idx+1}] {vcd.name}")
            choice = click.prompt("Select VCD file to open (number)", type=int, default=1)
            vcd_path = vcd_files[choice - 1]
    if not vcd_path.exists():
        click.secho(f"⚠️  {vcd_path} not found — did you run the Verilator sim?", fg="yellow")
        return
    click.secho(f"📈 Launching GTKWave on {vcd_path}...", fg="green")
    subprocess.run(["gtkwave", str(vcd_path)])


# --------------------------
# New: Simulate "Easy" Commands
# --------------------------

@click.command()
@click.option('--tb', help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.")
def simulate(tb):
    """
    Easy mode: Run Icarus simulation + open GTKWave in one step.
    """
    ctx = click.get_current_context()
    ctx.invoke(sim, tb=tb)
    ctx.invoke(wave)


@click.command()
@click.option('--tb', help="Name of the testbench to simulate (without .v). Auto-detects *_tb.v if not set.")
def simulate_verilator(tb):
    """
    Easy mode: Run Verilator build, run simulation, then open GTKWave in one step.
    """
    ctx = click.get_current_context()
    ctx.invoke(sim_verilator, tb=tb)
    ctx.invoke(sim_verilator_run, tb=tb)
    ctx.invoke(wave_verilator)


# --------------------------
# Formal Verification
# --------------------------

@click.command()
def formal():
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
        msg = []
        if reports:
            msg.append(f"reports: {', '.join(str(p) for p in reports)}")
        if outputs:
            msg.append(f"out: {', '.join(str(p) for p in outputs)}")
        click.secho(f"🗂️  Formal outputs: {', '.join(msg)}", fg="yellow")


# --------------------------
# Synthesis Target
# --------------------------

@click.command()
def synth():
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
        msg = []
        if reports:
            msg.append(f"reports: {', '.join(str(p) for p in reports)}")
        if outputs:
            msg.append(f"out: {', '.join(str(p) for p in outputs)}")
        click.secho(f"🗂️  Synthesis outputs: {', '.join(msg)}", fg="yellow")


# --------------------------
# Clean Target
# --------------------------

@click.command()
def clean():
    """Clean all output and intermediate files."""
    if click.confirm("🧹 Clean all generated files and build artifacts?"):
        run_make("clean")
    else:
        click.echo("❎ Clean canceled.")


# --------------------------
# Tool Check
# --------------------------

@click.command()
def check_tools():
    """Check tool availability in PATH."""
    from saxoflow.tools import TOOL_DESCRIPTIONS

    click.echo("🔍 Checking installed tool availability:\n")
    for tool, desc in TOOL_DESCRIPTIONS.items():
        path = shutil.which(tool)
        status = click.style("✅ FOUND  ", fg="green") if path else click.style("❌ MISSING", fg="red")
        click.echo(f"{tool.ljust(18)} {status} — {desc}")
