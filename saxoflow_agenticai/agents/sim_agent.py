# saxoflow_agenticai/agents/sim_agent.py
"""
Simulation agent.

Runs the SaxoFlow CLI simulation (`saxoflow.makeflow.sim`) inside a target
project directory and returns a structured result dict. Stdout/stderr are
captured, the process exit code is checked, and the presence of a VCD file is
validated for success.

Public API (kept stable)
------------------------
- class SimAgent
    - run(project_path: str, top_module: str) -> dict

Notes
-----
- We intentionally keep Click's `CliRunner().invoke(...)` usage to preserve
  current behavior and compatibility with the rest of the pipeline.
- Output keys: "status", "stage", "stdout", "stderr", "error_message".

Python: 3.9+
"""

from __future__ import annotations

import os
# import subprocess  # Unused: kept for reference in case we switch to Popen-based runs.  # noqa: ERA001
import sys
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from typing import Dict, Iterator, Tuple

from saxoflow_agenticai.core.log_manager import get_logger

logger = get_logger()


@contextmanager
def _pushd(target: Path) -> Iterator[None]:
    """
    Temporarily change the current working directory.

    Parameters
    ----------
    target : Path
        Directory to enter for the duration of the context.

    Yields
    ------
    None
    """
    prev = Path.cwd()
    os.chdir(str(target))
    try:
        yield
    finally:
        os.chdir(str(prev))


@contextmanager
def _capture_stdio() -> Iterator[Tuple[StringIO, StringIO]]:
    """
    Temporarily redirect `sys.stdout` and `sys.stderr` to in-memory buffers.

    Returns
    -------
    tuple[StringIO, StringIO]
        (stdout_buffer, stderr_buffer)
    """
    old_out, old_err = sys.stdout, sys.stderr
    out_buf, err_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = out_buf, err_buf
    try:
        yield out_buf, err_buf
    finally:
        sys.stdout, sys.stderr = old_out, old_err


class SimAgent:
    """Thin wrapper around the SaxoFlow simulation CLI."""

    def __init__(self, verbose: bool = False) -> None:
        """
        Parameters
        ----------
        verbose : bool, default False
            Currently unused here (logging already informative), but kept for
            API parity with other agents.
        """
        self.name = "sim"
        self.verbose = bool(verbose)

    def run(self, project_path: str, top_module: str) -> Dict[str, object]:
        """
        Simulate the given design using SaxoFlow's CLI (Icarus flow).

        Parameters
        ----------
        project_path : str
            Path to the SaxoFlow project root (contains source/, simulation/, etc.).
        top_module : str
            Top-level module name (used to guess VCD filename and passed to CLI).

        Returns
        -------
        dict
            {
                "status": "success" | "failed",
                "stage": "simulation",
                "stdout": <captured stdout>,
                "stderr": <captured stderr>,
                "error_message": str | None,
            }

        Behavior
        --------
        - Invokes `saxoflow.makeflow.sim --tb <top_module>` in the given project dir.
        - Considers the run failed if the exit code is non-zero.
        - Considers the run failed if no non-empty VCD file is produced at
          `simulation/icarus/<top_module>.vcd` or `simulation/icarus/dump.vcd`.
        """
        logger.info("[%s] Running simulation for top module: %s", self.name, top_module)
        logger.info(
            "[%s] Running simulation for top module: %s in project: %s",
            self.name,
            top_module,
            project_path,
        )

        # Import locally to avoid any circular import issues.
        try:
            from saxoflow.makeflow import sim as saxoflow_sim  # type: ignore
        except Exception as exc:  # pragma: no cover - import resolution issue
            logger.error("[%s] Failed to import SaxoFlow sim entrypoint: %s", self.name, exc)
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": "",
                "stderr": "",
                "error_message": f"Failed to import SaxoFlow sim entrypoint: {exc}",
            }

        project_dir = Path(project_path)
        if not project_dir.exists():
            logger.error("[%s] Project path does not exist: %s", self.name, project_dir)
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": "",
                "stderr": "",
                "error_message": f"Project path does not exist: {project_dir}",
            }

        # Run the CLI inside the project directory while capturing stdout/stderr.
        with _pushd(project_dir), _capture_stdio() as (stdout_buf, stderr_buf):
            try:
                from click.testing import CliRunner

                runner = CliRunner()
                result = runner.invoke(saxoflow_sim, ["--tb", top_module])  # type: ignore[name-defined]

                sim_stdout = stdout_buf.getvalue()
                sim_stderr = stderr_buf.getvalue()
                return_code = int(result.exit_code)
            except Exception as exc:  # pragma: no cover - Click/CLI unexpected failure
                logger.error("[%s] Exception during simulation: %s", self.name, exc)
                return {
                    "status": "failed",
                    "stage": "simulation",
                    "stdout": stdout_buf.getvalue(),
                    "stderr": stderr_buf.getvalue(),
                    "error_message": f"An unexpected error occurred: {exc}",
                }

        # ------ Post-run checks (preserve existing behavior) ------
        # Heuristic: confirm a VCD file exists and is non-empty.
        vcd_name_guess = f"{top_module}.vcd"
        vcd_paths = [
            Path("simulation/icarus") / vcd_name_guess,
            Path("simulation/icarus") / "dump.vcd",
        ]
        found_vcd: Path | None = None
        for vcd_path in vcd_paths:
            try:
                if vcd_path.exists() and vcd_path.stat().st_size > 0:
                    found_vcd = vcd_path
                    break
            except OSError:  # pragma: no cover - rare FS error
                # Keep searching; we only need *one* valid VCD.
                continue

        if return_code != 0:
            logger.error(
                "[%s] SaxoFlow simulation failed with exit code %s.",
                self.name,
                return_code,
            )
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": sim_stdout,
                "stderr": sim_stderr,
                "error_message": f"SaxoFlow simulation failed with exit code {return_code}.",
            }

        if not found_vcd:
            logger.error(
                "[%s] Simulation did NOT complete: No VCD file found in simulation/icarus/ "
                "after simulation run.",
                self.name,
            )
            return {
                "status": "failed",
                "stage": "simulation",
                "stdout": sim_stdout,
                "stderr": sim_stderr,
                "error_message": (
                    "Simulation did not produce a VCD file. "
                    "Check your testbench and RTL for errors, or missing $dumpfile/$dumpvars."
                ),
            }

        logger.info("[%s] Simulation completed successfully. VCD: %s", self.name, found_vcd)
        return {
            "status": "success",
            "stage": "simulation",
            "stdout": sim_stdout,
            "stderr": sim_stderr,
            "error_message": None,
        }

        # ------------------------- Alternative approach (commented) -------------------------
        # If you later want to avoid Click's CliRunner capture and simulate via subprocess:
        #
        # try:
        #     completed = subprocess.run(
        #         ["saxoflow", "sim", "--tb", top_module],
        #         cwd=str(project_dir),
        #         text=True,
        #         capture_output=True,
        #         check=False,
        #     )
        #     sim_stdout = completed.stdout
        #     sim_stderr = completed.stderr
        #     return_code = completed.returncode
        # except Exception as exc:
        #     return {
        #         "status": "failed",
        #         "stage": "simulation",
        #         "stdout": "",
        #         "stderr": "",
        #         "error_message": f"Subprocess execution failed: {exc}",
        #     }
        # -----------------------------------------------------------------------------------
