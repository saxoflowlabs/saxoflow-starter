import click
from saxoflow import env_setup, makeflow, init_project

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """🔧 SaxoFlow CLI: RTL simulation, synthesis & formal verification for FPGA/ASIC."""
    pass

# 🛠️ Environment Setup
cli.add_command(env_setup.init_env)
cli.add_command(env_setup.target_device)

# 🚀 Project Initialization
cli.add_command(init_project.init)

# 🔁 Flow Commands
cli.add_command(makeflow.sim)
cli.add_command(makeflow.sim_verilator)
cli.add_command(makeflow.wave)
cli.add_command(makeflow.formal)
cli.add_command(makeflow.clean)
cli.add_command(makeflow.check_tools)

if __name__ == "__main__":
    cli()
