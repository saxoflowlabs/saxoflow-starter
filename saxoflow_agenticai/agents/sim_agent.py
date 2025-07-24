import os
import subprocess
from pathlib import Path
from io import StringIO
import sys

from saxoflow_agenticai.core.log_manager import get_logger

logger = get_logger()

class SimAgent:
    def __init__(self, verbose: bool = False):
        self.name = "sim"
        self.verbose = verbose

    def run(self, project_path: str, top_module: str) -> dict:
        """
        Simulates the given RTL and testbench code using Icarus Verilog.
        Returns a dictionary with simulation status, stdout, and stderr.
        """
        logger.info(f"[{self.name}] Running simulation for top module: {top_module}")
        logger.info(f"[{self.name}] Running simulation for top module: {top_module} in project: {project_path}")

        # Import saxoflow_sim locally to avoid circular imports
        from saxoflow.makeflow import sim as saxoflow_sim

        # Change to the project directory to run saxoflow commands
        original_cwd = os.getcwd()
        os.chdir(project_path)

        # Capture stdout and stderr
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        redirected_stdout = StringIO()
        redirected_stderr = StringIO()
        sys.stdout = redirected_stdout
        sys.stderr = redirected_stderr

        try:
            # Create a dummy Click context for saxoflow_sim
            from click.testing import CliRunner
            runner = CliRunner()
            result = runner.invoke(saxoflow_sim, ['--tb', top_module])

            sim_stdout = redirected_stdout.getvalue()
            sim_stderr = redirected_stderr.getvalue()
            return_code = result.exit_code

            # ------ CHANGES BEGIN HERE ------
            # After simulation, check for VCD file
            vcd_name_guess = f"{top_module}.vcd"
            vcd_paths = [
                Path("simulation/icarus") / vcd_name_guess,
                Path("simulation/icarus") / "dump.vcd",
            ]
            found_vcd = None
            for vcd_path in vcd_paths:
                if vcd_path.exists() and vcd_path.stat().st_size > 0:
                    found_vcd = vcd_path
                    break

            if return_code != 0:
                logger.error(f"[{self.name}] SaxoFlow simulation failed with exit code {return_code}.")
                return {
                    "status": "failed",
                    "stage": "simulation",
                    "stdout": sim_stdout,
                    "stderr": sim_stderr,
                    "error_message": f"SaxoFlow simulation failed with exit code {return_code}."
                }

            if not found_vcd:
                logger.error(
                    f"[{self.name}] Simulation did NOT complete: No VCD file found in simulation/icarus/ after simulation run."
                )
                return {
                    "status": "failed",
                    "stage": "simulation",
                    "stdout": sim_stdout,
                    "stderr": sim_stderr,
                    "error_message": (
                        "Simulation did not produce a VCD file. "
                        "Check your testbench and RTL for errors, or missing $dumpfile/$dumpvars."
                    )
                }
            # ------ CHANGES END HERE ------

            logger.info(f"[{self.name}] Simulation completed successfully. VCD: {found_vcd}")
            return {
                "status": "success",
                "stage": "simulation",
                "stdout": sim_stdout,
                "stderr": sim_stderr,
                "error_message": None
            }

        except Exception as e:
            logger.error(f"[{self.name}] An unexpected error occurred during simulation: {e}")
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": redirected_stdout.getvalue(),
                "stderr": redirected_stderr.getvalue(),
                "error_message": f"An unexpected error occurred: {e}"
            }
        finally:
            # Restore stdout and stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            # Change back to the original directory
            os.chdir(original_cwd)
