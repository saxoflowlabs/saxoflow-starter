import click
from saxoflow import env_setup, project, flow_commands

@click.group()
def cli():
    """SaxoFlow CLI: FPGA/ASIC simulation, synthesis & verification."""
    pass

cli.add_command(env_setup.init_env)
cli.add_command(env_setup.target_device)
cli.add_command(project.init)
cli.add_command(flow_commands.sim)
cli.add_command(flow_commands.sim_verilator)
cli.add_command(flow_commands.wave)
cli.add_command(flow_commands.formal)
cli.add_command(flow_commands.clean)
cli.add_command(flow_commands.check_tools)
