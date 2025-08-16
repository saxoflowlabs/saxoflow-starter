import os
import sys
import io
import click
from pathlib import Path
import logging
from dotenv import load_dotenv
from contextlib import contextmanager

from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.orchestrator.agent_orchestrator import AgentOrchestrator
from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator  # noqa: F401 (kept for CLI parity)
from saxoflow_agenticai.core.model_selector import ModelSelector
import saxoflow_agenticai.core.model_selector as _ms  # access PROVIDERS registry
from saxoflow_agenticai.utils.file_utils import write_output, base_name_from_path

load_dotenv()

# Reset root handlers (avoid duplicate logs on repeated invocations)
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)


# ---------------------------------------------------------------------------
# Logging / utilities
# ---------------------------------------------------------------------------

def setup_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='[%(levelname)s] %(asctime)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def read_file_or_prompt(file, prompt_text):
    if file:
        with open(file, 'r', encoding='utf-8') as f:
            return f.read()
    return click.prompt(prompt_text, type=str)


def print_phase_header(name, iter_num=None):
    border = "=" * 18
    if iter_num is not None:
        print(f"\n{border} [{name} - Iteration {iter_num}] {border}\n")
    else:
        print(f"\n{border} [{name}] {border}\n")


@contextmanager
def _suppress_output(enabled: bool):
    """
    Suppress stdout/stderr and disable logging (<= CRITICAL) when enabled.
    Used to hide review chatter from nested agents by default.
    """
    if not enabled:
        # Nothing to do
        yield
        return

    old_stdout, old_stderr = sys.stdout, sys.stderr
    old_disable = logging.root.manager.disable
    try:
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        # Disable all logging while suppressed.
        logging.disable(logging.CRITICAL)
        yield
    finally:
        logging.disable(old_disable)
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _unit_project_error(
    project_root: Path,
    command: str,
    required_rel_path: str,
    extra_hint: str = ""
) -> click.ClickException:
    where = project_root
    full_needed = project_root / required_rel_path
    msg = (
        f"Not a SaxoFlow unit project at: {where}\n\n"
        f"The `{command}` command expects the unit layout. Please create a unit "
        f"project and add the required file(s) here:\n"
        f"  {full_needed}\n\n"
        f"Alternatively, pass an explicit file path using the appropriate option "
        f"(e.g., --input-file).\n"
    )
    if extra_hint:
        msg += f"\nHint: {extra_hint}\n"
    return click.ClickException(msg)


# ---------------------------------------------------------------------------
# Interactive first-run LLM key setup
# ---------------------------------------------------------------------------

def _env_path() -> Path:
    return Path.cwd() / ".env"


def _ensure_env_file(env_path: Path) -> None:
    """Create a .env if missing so we can write into it safely."""
    if not env_path.exists():
        env_path.write_text("# SaxoFlow Agentic AI settings\n", encoding="utf-8")


def _supported_provider_envs() -> dict:
    """
    Return {provider_name: ENV_VAR} from the ModelSelector provider registry,
    but only for providers that actually declare an env var (skip pseudo entries).
    """
    out = {}
    for name, spec in _ms.PROVIDERS.items():
        env = getattr(spec, "env", None)
        if env:
            out[name] = env
    return out


def _any_llm_key_present() -> bool:
    """True if any supported provider API key is already present in env."""
    for env_var in _supported_provider_envs().values():
        if os.getenv(env_var):
            return True
    return False


def _write_env_kv(env_path: Path, key: str, value: str) -> None:
    """
    Idempotently set KEY=VALUE in .env, preserving other lines/comments.
    """
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()

    updated = False
    out = []
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            out.append(line)
            continue
        k = line.split("=", 1)[0].strip()
        if k == key:
            out.append(f"{key}={value}")
            updated = True
        else:
            out.append(line)
    if not updated:
        out.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out).rstrip() + "\n")


def _interactive_setup_keys(*, force: bool = False) -> None:
    """
    Prompt the user to choose a provider and paste an API key if none is set
    (or always, when force=True). Writes to .env and reloads env vars.
    Raises ClickException in non-interactive (non-TTY) shells so callers can handle it.
    """
    env_path = _env_path()
    _ensure_env_file(env_path)

    if not force and _any_llm_key_present():
        return

    # Non-interactive shell (e.g., invoked via Click's CliRunner inside Cool CLI)
    # -> surface an actionable error instead of silently skipping.
    if not sys.stdin.isatty():
        raise click.ClickException(
            "No LLM API key detected and input is non-interactive.\n\n"
            "Run this once in a real terminal:\n"
            "  python -m saxoflow_agenticai.cli setupkeys\n\n"
            "Or set one of these environment variables before running:\n  "
            + ", ".join(sorted(_supported_provider_envs().values()))
        )

    click.secho("\nNo LLM API key detected. Let's set one up.\n", fg="yellow", bold=True)

    prov_envs = _supported_provider_envs()
    providers = sorted(prov_envs.keys())

    click.echo("Supported providers:")
    for i, name in enumerate(providers, start=1):
        click.echo(f"  {i}) {name}  (env: {prov_envs[name]})")

    choice = click.prompt(
        "\nChoose a provider",
        type=click.Choice(providers, case_sensitive=False)
    ).strip().lower()

    env_var = prov_envs[choice]
    key = click.prompt(
        f"Enter your API key for '{choice}' ({env_var})",
        hide_input=True,
        confirmation_prompt=True
    ).strip()

    _write_env_kv(env_path, env_var, key)
    load_dotenv(override=True)

    click.secho(
        f"\nSaved {env_var} to {env_path}. Using provider '{choice}'.\n"
        "Tip: To use Claude/Gemini via OpenRouter, choose 'openrouter'.",
        fg="green",
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option('--verbose', '-v', is_flag=True, default=False, help="Show LLM prompts/responses in terminal.")
@click.pass_context
def cli(ctx, verbose):
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose
    # Prompt for an API key if none is configured yet (or raise on non-TTY).
    _interactive_setup_keys(force=False)


@cli.command()
def setupkeys():
    """
    Manually (re)configure an API key for a chosen provider and save to .env.
    """
    _interactive_setup_keys(force=True)


# ---------------------------------------------------------------------------
# Shared generation/review loop
# ---------------------------------------------------------------------------

def run_with_review(gen_agent, review_agent, initial_input, max_iters=1, verbose=False):
    """
    Supports:
    - 1-arg (for e.g., rtlgen: spec)
    - 3-arg (for tbgen: spec, rtl_code, top_module_name)

    Default behavior: suppress inner prints/logs unless verbose=True.
    """
    # Hide any prints from nested agents/review unless verbose.
    with _suppress_output(enabled=not verbose):
        if isinstance(initial_input, tuple):
            output = gen_agent.run(*initial_input)
            feedback = review_agent.run(*initial_input, output)
        else:
            output = gen_agent.run(initial_input)
            feedback = review_agent.run(initial_input, output)

        for i in range(1, max_iters):
            if "no major issue" in feedback.lower() or "no issues found" in feedback.lower():
                break
            if isinstance(initial_input, tuple):
                output = gen_agent.improve(*initial_input, feedback)
                feedback = review_agent.run(*initial_input, output)
            else:
                output = gen_agent.improve(initial_input, feedback)
                feedback = review_agent.run(initial_input, output)

    # Optional visibility of review when verbose=True (outside suppression).
    if verbose:
        print_phase_header("REVIEW", 1)
        click.echo(feedback)

    return output, feedback


# ---------------------------------------------------------------------------
# Utility command to sanity-check provider/model mapping
# ---------------------------------------------------------------------------

@cli.command()
@click.pass_context
def testllms(ctx):
    agent_keys = [
        "rtlgen", "tbgen", "fpropgen", "rtlreview", "tbreview", "fpropreview", "debug", "report"
    ]
    dummy_inputs = {
        "rtlgen": "module test; endmodule",
        "tbgen": "module test; endmodule",
        "fpropgen": "module test; endmodule",
        "rtlreview": "module test; endmodule",
        "tbreview": "module test; endmodule",
        "fpropreview": "property p_test; endproperty",
        "debug": "Error: X is undefined in module test; at time 10ns",
        "report": {
            "rtl_generation": "module test; endmodule",
            "rtl_review": "No issues found.",
            "testbench_generation": "module tb; endmodule",
            "testbench_review": "Stimulus covers all branches.",
            "formal_property_generation": "property p_test; endproperty",
            "formal_property_review": "Properties are complete.",
            "debug": "No critical errors."
        }
    }
    click.secho("Testing all agent LLM provider/model mappings...\n", fg="yellow", bold=True)
    for agent_key in agent_keys:
        try:
            agent = AgentManager.get_agent(agent_key, verbose=False)
            provider, model = ModelSelector.get_provider_and_model(agent_type=agent_key)
            click.secho(f"[{agent_key}] Using provider: {provider}, model: {model}", fg="cyan")
            input_data = dummy_inputs[agent_key]
            response = agent.run(input_data)
            # response might be large / non-string; keep it safe
            snippet = str(response)[:150]
            click.secho(f"[{agent_key}] LLM test SUCCESS\nSnippet: {snippet}\n", fg="green")
        except Exception as e:
            click.secho(f"[{agent_key}] LLM test FAILED: {e}\n", fg="red")


# ---------------------------------------------------------------------------
# RTL / TB / FPROP generation and review commands
# ---------------------------------------------------------------------------

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Spec file (default: source/specification/).')
@click.option('--output-file', '-o', type=click.Path(), help='Output RTL file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def rtlgen(ctx, input_file, output_file, iters):
    """Generate RTL from a design spec (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        spec_dir = project_root / "source" / "specification"
        if not spec_dir.exists():
            raise _unit_project_error(
                project_root,
                "rtlgen",
                "source/specification/",
                extra_hint="Create a unit project and add a spec Markdown file "
                           "(e.g., source/specification/design.md), or pass --input-file."
            )
        specs = sorted(list(spec_dir.glob("*.md")))
        if not specs:
            raise click.ClickException(
                f"No spec files (*.md) found in {spec_dir}.\n\n"
                f"Add a spec Markdown file (e.g., {spec_dir/'design.md'}) or pass --input-file."
            )
        input_file = str(specs[0])
    spec = read_file_or_prompt(input_file, 'Enter design spec')
    gen_agent = AgentManager.get_agent("rtlgen", verbose=verbose)
    review_agent = AgentManager.get_agent("rtlreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)

    rtl_code, _review = run_with_review(gen_agent, review_agent, spec, max_iters=iters, verbose=verbose)

    # Show ONLY the final artifact
    click.secho(rtl_code, fg="cyan")

    # Suppress any file-utils chatter unless verbose
    with _suppress_output(enabled=not verbose):
        base = base_name_from_path(input_file)
        write_output(
            rtl_code,
            output_file,
            default_folder=str(project_root / "source" / "rtl" / "verilog"),
            default_name=f"{base}_rtl_gen",
            ext=".v"
        )


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: source/rtl/verilog/).')
@click.option('--output-file', '-o', type=click.Path(), help='Output testbench file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def tbgen(ctx, input_file, output_file, iters):
    """Generate Verilog testbench for RTL (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())

    # ----- Step 1: Find RTL -----
    if not input_file:
        rtl_dir = project_root / "source" / "rtl" / "verilog"
        if not rtl_dir.exists():
            raise _unit_project_error(
                project_root,
                "tbgen",
                "source/rtl/verilog/",
                extra_hint="Generate RTL first (e.g., `rtlgen`) which writes to source/rtl/verilog/, "
                           "or pass --input-file to an RTL .v file."
            )
        rtls = sorted(list(rtl_dir.glob("*.v")))
        if not rtls:
            raise click.ClickException(
                f"No RTL found in {rtl_dir}.\n\n"
                f"Generate RTL first (e.g., `rtlgen`) or pass --input-file to an RTL .v file."
            )
        input_file = str(rtls[0])
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')

    # ----- Step 2: Find SPEC -----
    spec_dir = project_root / "source" / "specification"
    if not spec_dir.exists():
        raise _unit_project_error(
            project_root,
            "tbgen",
            "source/specification/",
            extra_hint="Add a spec Markdown file (e.g., source/specification/design.md)."
        )
    specs = sorted(list(spec_dir.glob("*.md")))
    if not specs:
        raise click.ClickException(
            f"No spec files (*.md) found in {spec_dir}.\n\n"
            f"Add a spec Markdown file (e.g., {spec_dir/'design.md'})."
        )
    spec = read_file_or_prompt(str(specs[0]), 'Enter design spec')

    # ----- Step 3: Infer TOP MODULE NAME -----
    import re
    m = re.search(r'\bmodule\s+(\w+)', rtl_code)
    if not m:
        raise click.ClickException("Unable to infer top module name from RTL code.")
    top_module_name = m.group(1)

    gen_agent = AgentManager.get_agent("tbgen", verbose=verbose)
    review_agent = AgentManager.get_agent("tbreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)

    tb_code, _review = run_with_review(
        gen_agent,
        review_agent,
        (spec, rtl_code, top_module_name),
        max_iters=iters,
        verbose=verbose
    )

    # Show ONLY the final artifact
    click.secho(tb_code, fg="cyan")

    # Suppress any file-utils chatter unless verbose
    with _suppress_output(enabled=not verbose):
        base = base_name_from_path(input_file)
        write_output(
            tb_code,
            output_file,
            default_folder=str(project_root / "source" / "tb" / "verilog"),
            default_name=f"{base}_tb_gen",
            ext=".v"
        )


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: source/rtl/verilog/).')
@click.option('--output-file', '-o', type=click.Path(), help='Output formal property file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def fpropgen(ctx, input_file, output_file, iters):
    """Generate SVA formal properties for RTL (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        rtl_dir = project_root / "source" / "rtl" / "verilog"
        if not rtl_dir.exists():
            raise _unit_project_error(
                project_root,
                "fpropgen",
                "source/rtl/verilog/",
                extra_hint="Generate RTL first (e.g., `rtlgen`) which writes to source/rtl/verilog/, "
                           "or pass --input-file to an RTL .v file."
            )
        rtls = sorted(list(rtl_dir.glob("*.v")))
        if not rtls:
            raise click.ClickException(
                f"No RTL found in {rtl_dir}.\n\n"
                f"Generate RTL first (e.g., `rtlgen`) or pass --input-file to an RTL .v file."
            )
        input_file = str(rtls[0])
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')
    gen_agent = AgentManager.get_agent("fpropgen", verbose=verbose)
    review_agent = AgentManager.get_agent("fpropreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)

    prop_code, _review = run_with_review(gen_agent, review_agent, rtl_code, max_iters=iters, verbose=verbose)

    # Show ONLY the final artifact
    click.secho(prop_code, fg="cyan")

    # Suppress any file-utils chatter unless verbose
    with _suppress_output(enabled=not verbose):
        base = base_name_from_path(input_file)
        write_output(
            prop_code,
            output_file,
            default_folder=str(project_root / "formal"),
            default_name=f"{base}_props_gen",
            ext=".sv"
        )


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: source/rtl/verilog/).')
@click.pass_context
def rtlreview(ctx, input_file):
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        rtl_dir = project_root / "source" / "rtl" / "verilog"
        if not rtl_dir.exists():
            raise _unit_project_error(
                project_root,
                "rtlreview",
                "source/rtl/verilog/",
                extra_hint="Generate RTL first (e.g., `rtlgen`) or pass --input-file to an RTL .v file."
            )
        rtls = sorted(list(rtl_dir.glob("*.v")))
        if not rtls:
            raise click.ClickException(
                f"No RTL found in {rtl_dir}.\n\n"
                f"Generate RTL first (e.g., `rtlgen`) or pass --input-file to an RTL .v file."
            )
        input_file = str(rtls[0])
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')
    result = AgentManager.get_agent("rtlreview", verbose=verbose).run(rtl_code)
    click.echo(result)


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Testbench file (default: source/tb/verilog/).')
@click.pass_context
def tbreview(ctx, input_file):
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        tb_dir = project_root / "source" / "tb" / "verilog"
        if not tb_dir.exists():
            raise _unit_project_error(
                project_root,
                "tbreview",
                "source/tb/verilog/",
                extra_hint="Generate a testbench first (e.g., `tbgen`) which writes to source/tb/verilog/, "
                           "or pass --input-file to a TB .v file."
            )
        tbs = sorted(list(tb_dir.glob("*.v")))
        if not tbs:
            raise click.ClickException(
                f"No testbench found in {tb_dir}.\n\n"
                f"Generate a testbench first (e.g., `tbgen`) or pass --input-file to a TB .v file."
            )
        input_file = str(tbs[0])
    testbench_code = read_file_or_prompt(input_file, 'Enter Testbench code')
    result = AgentManager.get_agent("tbreview", verbose=verbose).run(testbench_code)
    click.echo(result)


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Formal property file (default: formal/).')
@click.pass_context
def fpropreview(ctx, input_file):
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        fp_dir = project_root / "formal"
        if not fp_dir.exists():
            raise _unit_project_error(
                project_root,
                "fpropreview",
                "formal/",
                extra_hint="Generate properties first (e.g., `fpropgen`) which writes to formal/, "
                           "or pass --input-file to a .sv property file."
            )
        fps = sorted(list(fp_dir.glob("*.sv")))
        if not fps:
            raise click.ClickException(
                f"No formal property found in {fp_dir}.\n\n"
                f"Generate properties first (e.g., `fpropgen`) or pass --input-file to a .sv file."
            )
        input_file = str(fps[0])
    prop_code = read_file_or_prompt(input_file, 'Enter Formal Properties')
    result = AgentManager.get_agent("fpropreview", verbose=verbose).run(prop_code)
    click.echo(result)


@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='File to debug (RTL, testbench, or log).')
@click.pass_context
def debug(ctx, input_file):
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    if not input_file:
        click.secho("No --input-file specified. Please provide a file to debug.", fg="yellow")
        return
    input_path = Path(input_file)
    if not input_path.is_absolute():
        input_file = str(project_root / input_path)
    debug_input = read_file_or_prompt(input_file, 'Enter debug input (code or log)')
    result = AgentManager.get_agent("debug", verbose=verbose).run(debug_input)
    click.secho("\n[Debug Report]", fg="magenta", bold=True)
    click.echo(result)


@cli.command()
@click.option('--rtl-file', '-r', type=click.Path(exists=True), required=True, help='Path to the RTL file relative to project root.')
@click.option('--tb-file', '-t', type=click.Path(exists=True), required=True, help='Path to the testbench file relative to project root.')
@click.option('--top-module', '-m', type=str, required=True, help='Name of the top module.')
@click.pass_context
def sim(ctx, rtl_file, tb_file, top_module):
    verbose = ctx.obj.get('VERBOSE', False)
    project_root = Path(os.getcwd())
    full_rtl_path = project_root / rtl_file
    full_tb_path = project_root / tb_file
    sim_agent = AgentManager.get_agent("sim", verbose=verbose)
    with open(full_rtl_path, 'r', encoding='utf-8') as f:
        rtl_code = f.read()
    with open(full_tb_path, 'r', encoding='utf-8') as f:
        tb_code = f.read()
    click.secho(f"\n[Simulation] Running simulation for {top_module}...", fg="magenta", bold=True)
    sim_result = sim_agent.run(str(project_root), top_module)
    click.secho(f"\n[Simulation Status]: {sim_result['status']}", fg="yellow", bold=True)
    if sim_result['error_message']:
        click.secho(f"[Simulation Error]: {sim_result['error_message']}", fg="red")
    if sim_result['stdout']:
        click.secho("\n[Simulation STDOUT]:", fg="cyan")
        click.echo(sim_result['stdout'])
    if sim_result['stderr']:
        click.secho("\n[Simulation STDERR]:", fg="red")
        click.echo(sim_result['stderr'])


@cli.command()
@click.option('--iters', default=1, show_default=True, help="Review-improve iterations per stage.")
@click.pass_context
def fullpipeline(ctx, iters):
    verbose = ctx.obj.get('VERBOSE', False)
    project_path = os.getcwd()
    if not os.path.exists(project_path):
        raise click.ClickException(
            f"Project path does not exist: {project_path}. "
            f"Please run this command from within the project directory."
        )
    spec_dir = Path(project_path) / "source" / "specification"
    if not spec_dir.exists():
        raise click.ClickException(
            f"Project structure invalid: {spec_dir} not found. "
            f"Please ensure you are in a SaxoFlow unit project."
        )
    specs = sorted(list(spec_dir.glob("*.md")))
    if not specs:
        raise click.ClickException(
            f"No spec files (*.md) found in {spec_dir}. Please add one."
        )
    if len(specs) > 1:
        raise click.ClickException(
            f"Multiple spec files found in {spec_dir}. Please specify which one to use "
            f"or ensure only one exists."
        )
    spec_file = str(specs[0])
    click.secho(f"Using spec file: {spec_file}", fg="cyan")
    results = AgentOrchestrator.full_pipeline(spec_file, project_path, verbose=verbose, max_iters=iters)
    click.secho("\n[RTL Code]", fg="cyan", bold=True)
    click.echo(results['rtl_code'])
    click.secho("\n[Testbench Code]", fg="cyan", bold=True)
    click.echo(results['testbench_code'])
    click.secho("\n[Formal Properties]", fg="cyan", bold=True)
    click.echo(results['formal_properties'])
    click.secho("\n[RTL Review Report]", fg="green")
    click.echo(results['rtl_review_report'])
    click.secho("\n[Testbench Review Report]", fg="green")
    click.echo(results['tb_review_report'])
    click.secho("\n[Formal Property Review Report]", fg="green")
    click.echo(results['fprop_review_report'])
    click.secho("\n[Debug Report]", fg="magenta", bold=True)
    click.echo(results['debug_report'])
    click.secho("\n[Pipeline Summary Report]", fg="blue", bold=True)
    click.echo(results['pipeline_report'])
    base = base_name_from_path(spec_file)

    # Keep file writes silent in non-verbose mode as well
    with _suppress_output(enabled=not verbose):
        write_output(
            results['rtl_code'],
            None,
            os.path.join(project_path, "source", "rtl", "verilog"),
            f"{base}_rtl_gen",
            ".v"
        )
        write_output(
            results['testbench_code'],
            None,
            os.path.join(project_path, "source", "tb", "verilog"),
            f"{base}_tb_gen",
            ".v"
        )
        write_output(
            results['formal_properties'],
            None,
            os.path.join(project_path, "formal"),
            f"{base}_props_gen",
            ".sv"
        )
        write_output(
            results['pipeline_report'],
            None,
            os.path.join(project_path, "output", "report"),
            f"{base}_pipeline_report",
            ".txt"
        )


if __name__ == "__main__":
    cli(obj={})
