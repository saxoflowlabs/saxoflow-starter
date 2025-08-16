"""
Pipeline orchestrator for SaxoFlow Agentic AI.

This module wires together generator/reviewer agents, an iterative simulation +
debug loop, and a final reporting pass. The goal is to keep this orchestration
clean, testable, and resilient, while preserving the project's current
input/output behavior.

Public API (kept stable)
------------------------
- class AgentOrchestrator
    - full_pipeline(spec_file: str, project_path: str,
                    verbose: bool = False, max_iters: int = 3) -> dict

Notes
-----
- The "Formal property generation & review" phase is currently commented
  out by design. We keep placeholders and clear comments.
- The simulation healing loop writes improved files in-place and re-runs.

Python: 3.9+
"""

from __future__ import annotations

import io
import logging
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.orchestrator.feedback_coordinator import (
    AgentFeedbackCoordinator,
)
from saxoflow_agenticai.utils.file_utils import base_name_from_path, write_output

logger = get_logger()


# -------------------
# Small data container
# -------------------

@dataclass(frozen=True)
class _ProjectPaths:
    """Strongly-typed container for per-project directories and key files."""

    base: str
    project_root: Path
    rtl_dir: Path
    tb_dir: Path
    formal_dir: Path
    report_dir: Path
    spec_dir: Path
    rtl_file: Path
    tb_file: Path


# ---------------
# Local utilities
# ---------------

def _read_file(filepath: Path) -> str:
    """
    Robustly read a text file as UTF-8.

    Returns an empty string on any error (keeps current behavior for extraction).
    """
    try:
        return filepath.read_text(encoding="utf-8")
    except Exception:  # pragma: no cover - defensive
        return ""


def _prepare_paths(project_path: str, spec_file: str) -> _ProjectPaths:
    """
    Create (if needed) and return all project directories and key file paths.

    Parameters
    ----------
    project_path : str
        Root path for the active project.
    spec_file : str
        Path to the specification; used to derive the base filename.

    Returns
    -------
    _ProjectPaths
        A dataclass with directories and output file paths.
    """
    project_root = Path(project_path).resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    base = base_name_from_path(spec_file)

    rtl_dir = project_root / "source" / "rtl" / "verilog"
    tb_dir = project_root / "source" / "tb" / "verilog"
    formal_dir = project_root / "formal"
    report_dir = project_root / "output" / "report"
    spec_dir = project_root / "source" / "specification"

    for d in (rtl_dir, tb_dir, formal_dir, report_dir, spec_dir):
        d.mkdir(parents=True, exist_ok=True)

    rtl_file = rtl_dir / f"{base}_rtl_gen.v"
    tb_file = tb_dir / f"{base}_tb_gen.v"

    return _ProjectPaths(
        base=base,
        project_root=project_root,
        rtl_dir=rtl_dir,
        tb_dir=tb_dir,
        formal_dir=formal_dir,
        report_dir=report_dir,
        spec_dir=spec_dir,
        rtl_file=rtl_file,
        tb_file=tb_file,
    )


def _detect_sim_failures(stdout: str, stderr: str) -> Tuple[bool, bool]:
    """
    Identify common failure signals in simulation output.

    Returns
    -------
    (vcd_missing, compile_fail) : Tuple[bool, bool]
        vcd_missing: True if VCD not found in stdout/stderr.
        compile_fail: True if stderr indicates compile/parse/fatal errors.
    """
    vcd_missing = ("No VCD files found" in stdout) or ("No VCD files found" in stderr)

    low = stderr.lower()
    compile_fail = ("error" in low) or ("parse" in low) or ("fatal" in low)
    return vcd_missing, compile_fail


@contextmanager
def _suppress_stdio(enabled: bool):
    """
    Temporarily suppress stdout/stderr when enabled.

    This is used to keep orchestrator-induced file writes quiet in non-verbose
    mode, without changing the public API or altering logging configuration.
    """
    if not enabled:
        yield
        return
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = io.StringIO(), io.StringIO()
        yield
    finally:
        sys.stdout, sys.stderr = old_out, old_err


# -------------
# Main Orchestrator
# -------------

class AgentOrchestrator:
    """
    Orchestrates the full end-to-end flow:
      1) Read spec
      2) Generate + review RTL
      3) Generate + review TB
      4) Write outputs
      5) Simulate + debug (iterative healing)
      6) Final report

    Notes
    -----
    - Keeps output keys and behavior identical to the original implementation.
    - Raises FileNotFoundError if `spec_file` cannot be read (explicit error).
    """

    @staticmethod
    def full_pipeline(
        spec_file: str,
        project_path: str,
        verbose: bool = False,
        max_iters: int = 3,
    ) -> Dict[str, str]:
        """
        End-to-end IC design/verification pipeline with feedback-driven healing.

        Parameters
        ----------
        spec_file : str
            Path to the input specification file (text).
        project_path : str
            Root directory where outputs (rtl/tb/formal/report) are written.
        verbose : bool, default False
            If True, agents will log prompt/response blocks (when supported).
        max_iters : int, default 3
            Max iterations for improvement/simulation healing.

        Returns
        -------
        Dict[str, str]
            Dictionary containing all generated artifacts and logs. Keys:
            - rtl_code, testbench_code, formal_properties
            - rtl_review_report, tb_review_report, fprop_review_report
            - debug_report
            - simulation_status, simulation_stdout, simulation_stderr, simulation_error_message
            - pipeline_report
        """
        logger.info("Starting full pipeline for given spec.")

        # ---- Load spec content (explicit error if missing) ----
        spec_path = Path(spec_file).resolve()
        if not spec_path.exists():
            raise FileNotFoundError(f"Spec file not found: {spec_path}")
        try:
            spec = spec_path.read_text(encoding="utf-8")
        except Exception as exc:
            raise FileNotFoundError(f"Failed to read spec file: {spec_path}") from exc

        # ---- Prepare directories & file paths ----
        paths = _prepare_paths(project_path=project_path, spec_file=spec_file)
        base = paths.base

        # =========================
        # RTL: Generate + Review
        # =========================
        logger.debug("Invoking RTLGenAgent with review loop...")
        rtlgen = AgentManager.get_agent("rtlgen", verbose=verbose)
        rtlreview = AgentManager.get_agent("rtlreview", verbose=verbose)
        rtl_code, rtl_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=rtlgen,
            initial_spec=spec,
            feedback_agent=rtlreview,
            max_iters=max_iters,
        )
        logger.info("RTL generation + review completed.")

        # =========================
        # TB: Generate + Review
        # =========================
        logger.debug("Invoking TBGenAgent with review loop...")
        tbgen = AgentManager.get_agent("tbgen", verbose=verbose)
        tbreview = AgentManager.get_agent("tbreview", verbose=verbose)
        tb_code, tb_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=tbgen,
            initial_spec=(spec, rtl_code, base),
            feedback_agent=tbreview,
            max_iters=max_iters,
        )
        logger.info("Testbench generation + review completed.")

        # ---- Persist initial improved artifacts (silent in non-verbose) ----
        with _suppress_stdio(enabled=not verbose):
            write_output(rtl_code, None, str(paths.rtl_dir), f"{base}_rtl_gen", ".v")
            write_output(tb_code, None, str(paths.tb_dir), f"{base}_tb_gen", ".v")

        # =========================
        # Simulation & Debug Loop
        # =========================
        logger.debug("Invoking SimAgent and DebugAgent...")
        sim_agent = AgentManager.get_agent("sim", verbose=verbose)
        debug_agent = AgentManager.get_agent("debug", verbose=verbose)

        sim_status = "failed"
        sim_stdout = ""
        sim_stderr = ""
        sim_error_message = ""
        final_debug_report = "No debug needed (simulation successful)"

        for i in range(max_iters):
            logger.info("Running simulation iteration %d/%d...", i + 1, max_iters)

            sim_result = sim_agent.run(str(paths.project_root), base)
            sim_status = sim_result.get("status", "failed")
            sim_stdout = sim_result.get("stdout", "")
            sim_stderr = sim_result.get("stderr", "")
            sim_error_message = sim_result.get("error_message", "")

            # Always re-read files from disk to catch any discrepancies.
            extracted_rtl_code = _read_file(paths.rtl_file)
            extracted_tb_code = _read_file(paths.tb_file)

            vcd_missing, compile_fail = _detect_sim_failures(sim_stdout, sim_stderr)

            if sim_status == "success" and not vcd_missing and not compile_fail:
                logger.info("Simulation successful.")
                break

            # Provide inputs separately to the debug agent to get actionable
            # suggestions and a list of agents to invoke for healing.
            debug_output, suggested_agents = debug_agent.run(
                rtl_code=extracted_rtl_code,
                tb_code=extracted_tb_code,
                sim_stdout=sim_stdout,
                sim_stderr=sim_stderr,
                sim_error_message=sim_error_message,
            )
            logger.info("Debug report generated based on simulation failure.")
            logger.info("Debug Report: %s", debug_output)
            final_debug_report = debug_output

            if i < max_iters - 1:
                # If only UserAction is suggested, we cannot auto-heal.
                if suggested_agents == ["UserAction"]:
                    logger.error(
                        "Debug agent suggests UserAction; cannot heal automatically."
                    )
                    break

                # Apply recommended healing agents (single quick pass each).
                for agent_name in suggested_agents:
                    if agent_name == "RTLGenAgent":
                        logger.info("Improving RTL per debug agent suggestion.")
                        rtl_code, _ = AgentFeedbackCoordinator.iterate_improvements(
                            agent=rtlgen,
                            initial_spec=spec,
                            feedback_agent=rtlreview,
                            feedback=debug_output,
                            max_iters=1,
                        )
                        with _suppress_stdio(enabled=not verbose):
                            write_output(
                                rtl_code,
                                None,
                                str(paths.rtl_dir),
                                f"{base}_rtl_gen",
                                ".v",
                            )
                    elif agent_name == "TBGenAgent":
                        logger.info("Improving Testbench per debug agent suggestion.")
                        tb_code, _ = AgentFeedbackCoordinator.iterate_improvements(
                            agent=tbgen,
                            initial_spec=(spec, rtl_code, base),
                            feedback_agent=tbreview,
                            feedback=debug_output,
                            max_iters=1,
                        )
                        with _suppress_stdio(enabled=not verbose):
                            write_output(
                                tb_code,
                                None,
                                str(paths.tb_dir),
                                f"{base}_tb_gen",
                                ".v",
                            )
                # Continue loop to re-simulate with improved code
            else:
                logger.error(
                    "Max simulation iterations reached. "
                    "Simulation still failing after healing attempts."
                )

        # =========================
        # Formal Property Phase
        # =========================
        # Currently commented out intentionally to keep runtime minimal.
        # Keep placeholders consistent with the original code path.
        formal_properties = "Formal property generation commented out."
        fprop_review_report = "Formal property review commented out."
        debug_report = final_debug_report
        logger.info("Debug phase completed.")

        # =========================
        # Final Reporting
        # =========================
        logger.debug("Invoking ReportAgent for pipeline summary...")
        report_agent = AgentManager.get_agent("report", verbose=verbose)

        # Named keys for every artifact (kept stable for downstream usage)
        phase_outputs: Dict[str, str] = {
            "specification": spec,
            "rtl_code": rtl_code,
            "rtl_review_report": rtl_review_report,
            "testbench_code": tb_code,
            "testbench_review_report": tb_review_report,
            "formal_properties": formal_properties,
            "formal_property_review_report": fprop_review_report,
            "simulation_status": sim_status,
            "simulation_stdout": sim_stdout,
            "simulation_stderr": sim_stderr,
            "simulation_error_message": sim_error_message,
            "debug_report": debug_report,
        }
        pipeline_report = report_agent.run(phase_outputs)
        logger.info("Pipeline summary report generated.")

        results: Dict[str, str] = {
            "rtl_code": rtl_code,
            "testbench_code": tb_code,
            "formal_properties": formal_properties,
            "rtl_review_report": rtl_review_report,
            "tb_review_report": tb_review_report,
            "fprop_review_report": fprop_review_report,
            "debug_report": debug_report,
            "simulation_status": sim_status,
            "simulation_stdout": sim_stdout,
            "simulation_stderr": sim_stderr,
            "simulation_error_message": sim_error_message,
            "pipeline_report": pipeline_report,
        }

        logger.info("Full pipeline completed successfully.")
        return results
