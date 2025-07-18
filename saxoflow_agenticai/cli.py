from dotenv import load_dotenv
load_dotenv()

import click
import os
from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.orchestrator.agent_orchestrator import AgentOrchestrator
from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator
from saxoflow_agenticai.core.model_selector import ModelSelector

import logging

# Enable INFO-level logs for your whole app when verbose is set.
def setup_logging(verbose: bool):
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format='[%(levelname)s] %(asctime)s - %(name)s - %(message)s',
        datefmt='%H:%M:%S'
    )


def read_file_or_prompt(file, prompt_text):
    if file:
        with open(file, 'r') as f:
            return f.read()
    else:
        return click.prompt(prompt_text, type=str)

def write_output(output, output_file=None, default_folder=None, default_name=None, ext=".v"):
    if output_file:
        out_path = output_file
    else:
        os.makedirs(default_folder, exist_ok=True)
        out_path = os.path.join(default_folder, default_name + ext)
    with open(out_path, 'w') as f:
        f.write(output)
    click.secho(f"[✔] Output written to: {out_path}", fg="green")
    return out_path

def base_name_from_path(path):
    return os.path.splitext(os.path.basename(path))[0]

def print_phase_header(name, iter_num=None):
    border = "=" * 18
    if iter_num is not None:
        print(f"\n{border} [{name} - Iteration {iter_num}] {border}\n")
    else:
        print(f"\n{border} [{name}] {border}\n")

@click.group()
@click.option('--verbose', '-v', is_flag=True, default=False, help="Show LLM prompts/responses in terminal.")
@click.pass_context
def cli(ctx, verbose):
    setup_logging(verbose)
    ctx.ensure_object(dict)
    ctx.obj['VERBOSE'] = verbose

def run_with_review(gen_agent, review_agent, initial_input, max_iters=1, verbose=False):
    """Iterative improvement loop for generator + review agents, with phase logging."""
    output = gen_agent.run(initial_input)
    feedback = review_agent.run(output)
    if verbose:
        print_phase_header("REVIEW", 1)
        click.echo(feedback)
    for i in range(1, max_iters):
        if "no major issue" in feedback.lower() or "no issues found" in feedback.lower():
            break
        if verbose:
            print_phase_header("IMPROVEMENT", i+1)
        output = gen_agent.improve(initial_input, feedback)
        feedback = review_agent.run(output)
        if verbose:
            print_phase_header("REVIEW", i+1)
            click.echo(feedback)
    return output, feedback

# -------------------------
# 🔬 LLM/API Test Command
# -------------------------

@cli.command()
@click.pass_context
def testllms(ctx):
    """
    Test all LLM agent provider/model mappings and API keys with a dummy prompt.
    """
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
            click.secho(f"[{agent_key}] LLM test SUCCESS\nSnippet: {response[:150]}\n", fg="green")
        except Exception as e:
            click.secho(f"[{agent_key}] LLM test FAILED: {e}\n", fg="red")

# 🔧 Generation Commands (no changes below)

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Spec file (default: input/spec/...).')
@click.option('--output-file', '-o', type=click.Path(), help='Output RTL file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def rtlgen(ctx, input_file, output_file, iters):
    """Generate RTL from a design spec (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        click.secho("No --input-file specified. Looking in input/spec/ ...", fg="yellow")
        specs = sorted(os.listdir("input/spec/"))
        if not specs:
            raise click.ClickException("No specs in input/spec/. Please add one or use --input-file.")
        input_file = os.path.join("input/spec/", specs[0])
        click.secho(f"Using: {input_file}", fg="cyan")
    spec = read_file_or_prompt(input_file, 'Enter design spec')
    gen_agent = AgentManager.get_agent("rtlgen", verbose=verbose)
    review_agent = AgentManager.get_agent("rtlreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)
    rtl_code, review = run_with_review(gen_agent, review_agent, spec, max_iters=iters, verbose=verbose)
    click.secho(rtl_code, fg="cyan")
    base = base_name_from_path(input_file)
    write_output(rtl_code, output_file, default_folder="output/rtl", default_name=f"{base}_gen", ext=".v")

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: output/rtl/...).')
@click.option('--output-file', '-o', type=click.Path(), help='Output testbench file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def tbgen(ctx, input_file, output_file, iters):
    """Generate SystemVerilog testbench for RTL (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        click.secho("No --input-file specified. Looking in output/rtl/ ...", fg="yellow")
        rtls = sorted(os.listdir("output/rtl/"))
        if not rtls:
            raise click.ClickException("No RTL found in output/rtl/. Please generate RTL first.")
        input_file = os.path.join("output/rtl/", rtls[0])
        click.secho(f"Using: {input_file}", fg="cyan")
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')
    gen_agent = AgentManager.get_agent("tbgen", verbose=verbose)
    review_agent = AgentManager.get_agent("tbreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)
    tb_code, review = run_with_review(gen_agent, review_agent, rtl_code, max_iters=iters, verbose=verbose)
    click.secho(tb_code, fg="cyan")
    base = base_name_from_path(input_file)
    write_output(tb_code, output_file, default_folder="output/tb", default_name=f"{base}_tb_gen", ext=".sv")

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: output/rtl/...).')
@click.option('--output-file', '-o', type=click.Path(), help='Output formal property file.')
@click.option('--iters', default=1, show_default=True, help="Max review-improve iterations.")
@click.pass_context
def fpropgen(ctx, input_file, output_file, iters):
    """Generate SVA formal properties for RTL (reviewed, iterative)."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        click.secho("No --input-file specified. Looking in output/rtl/ ...", fg="yellow")
        rtls = sorted(os.listdir("output/rtl/"))
        if not rtls:
            raise click.ClickException("No RTL found in output/rtl/. Please generate RTL first.")
        input_file = os.path.join("output/rtl/", rtls[0])
        click.secho(f"Using: {input_file}", fg="cyan")
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')
    gen_agent = AgentManager.get_agent("fpropgen", verbose=verbose)
    review_agent = AgentManager.get_agent("fpropreview", verbose=verbose)
    if verbose:
        print_phase_header("GENERATION", 1)
    prop_code, review = run_with_review(gen_agent, review_agent, rtl_code, max_iters=iters, verbose=verbose)
    click.secho(prop_code, fg="cyan")
    base = base_name_from_path(input_file)
    write_output(prop_code, output_file, default_folder="output/formal", default_name=f"{base}_props_gen", ext=".sv")

# 📋 Review Commands

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='RTL file (default: output/rtl/...).')
@click.pass_context
def rtlreview(ctx, input_file):
    """Review RTL code for structure, style, and synthesizability."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        rtls = sorted(os.listdir("output/rtl/"))
        if not rtls:
            raise click.ClickException("No RTL found in output/rtl/. Please generate RTL first.")
        input_file = os.path.join("output/rtl/", rtls[0])
    rtl_code = read_file_or_prompt(input_file, 'Enter RTL code')
    result = AgentManager.get_agent("rtlreview", verbose=verbose).run(rtl_code)
    click.echo(result)

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Testbench file (default: output/tb/...).')
@click.pass_context
def tbreview(ctx, input_file):
    """Review SystemVerilog testbench for stimulus quality and coverage."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        tbs = sorted(os.listdir("output/tb/"))
        if not tbs:
            raise click.ClickException("No testbench found in output/tb/. Please generate testbench first.")
        input_file = os.path.join("output/tb/", tbs[0])
    testbench_code = read_file_or_prompt(input_file, 'Enter Testbench code')
    result = AgentManager.get_agent("tbreview", verbose=verbose).run(testbench_code)
    click.echo(result)

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='Formal property file (default: output/formal/...).')
@click.pass_context
def fpropreview(ctx, input_file):
    """Review formal properties for completeness and correctness."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        fps = sorted(os.listdir("output/formal/"))
        if not fps:
            raise click.ClickException("No formal property found in output/formal/. Please generate formal first.")
        input_file = os.path.join("output/formal/", fps[0])
    prop_code = read_file_or_prompt(input_file, 'Enter Formal Properties')
    result = AgentManager.get_agent("fpropreview", verbose=verbose).run(prop_code)
    click.echo(result)

# 🐞 Debugging Command

@cli.command()
@click.option('--input-file', '-i', type=click.Path(exists=True), help='File to debug (RTL, testbench, or log).')
@click.pass_context
def debug(ctx, input_file):
    """Debug RTL, testbench, or simulation log using AI agent."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not input_file:
        click.secho("No --input-file specified. Please provide a file to debug.", fg="yellow")
        return
    debug_input = read_file_or_prompt(input_file, 'Enter debug input (code or log)')
    result = AgentManager.get_agent("debug", verbose=verbose).run(debug_input)
    click.secho("\n[Debug Report]", fg="magenta", bold=True)
    click.echo(result)

# 📝 Report Generation Command

@cli.command()
@click.option('--spec-file', '-i', type=click.Path(exists=True), help='Spec file for end-to-end flow (default: input/spec/...).')
@click.option('--iters', default=1, show_default=True, help="Review-improve iterations per stage.")
@click.pass_context
def fullpipeline(ctx, spec_file, iters):
    """Run the full design and verification flow and generate a project report."""
    verbose = ctx.obj.get('VERBOSE', False)
    if not spec_file:
        specs = sorted(os.listdir("input/spec/"))
        if not specs:
            raise click.ClickException("No specs in input/spec/. Please add one or use --spec-file.")
        spec_file = os.path.join("input/spec/", specs[0])
        click.secho(f"Using: {spec_file}", fg="cyan")
    spec = read_file_or_prompt(spec_file, 'Enter full design spec')
    results = AgentOrchestrator.full_pipeline(spec, verbose=verbose, max_iters=iters)

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
    write_output(results['rtl_code'], None, "output/rtl", f"{base}_rtl_gen", ".v")
    write_output(results['testbench_code'], None, "output/tb", f"{base}_tb_gen", ".sv")
    write_output(results['formal_properties'], None, "output/formal", f"{base}_props_gen", ".sv")
    write_output(results['pipeline_report'], None, "output/report", f"{base}_pipeline_report", ".txt")

if __name__ == "__main__":
    cli(obj={})
