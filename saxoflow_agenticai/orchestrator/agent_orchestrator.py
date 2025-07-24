from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.core.log_manager import get_logger
from pathlib import Path

from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator
from saxoflow_agenticai.utils.file_utils import write_output, base_name_from_path

logger = get_logger()

def read_file(filepath):
    """Utility to robustly read a file as string. Returns '' if not found."""
    try:
        with open(filepath, 'r') as f:
            return f.read()
    except Exception:
        return ""

class AgentOrchestrator:

    @staticmethod
    def full_pipeline(spec_file: str, project_path: str, verbose: bool = False, max_iters: int = 3):
        """
        End-to-end IC design/verification pipeline with robust feedback-driven healing.
        Passes actual extracted code to debug agent for actionable debugging and
        invokes the recommended agents for automatic correction.
        """
        logger.info("Starting full pipeline for given spec.")

        # Read spec content
        with open(spec_file, 'r') as f:
            spec = f.read()

        base = base_name_from_path(spec_file)

        # Define project-specific output directories
        project_base_path = Path(project_path)
        rtl_output_dir = project_base_path / "source" / "rtl" / "verilog"
        tb_output_dir = project_base_path / "source" / "tb" / "verilog"
        formal_output_dir = project_base_path / "formal"
        report_output_dir = project_base_path / "output" / "report"
        spec_output_dir = project_base_path / "source" / "specification"

        rtl_output_dir.mkdir(parents=True, exist_ok=True)
        tb_output_dir.mkdir(parents=True, exist_ok=True)
        formal_output_dir.mkdir(parents=True, exist_ok=True)
        report_output_dir.mkdir(parents=True, exist_ok=True)
        spec_output_dir.mkdir(parents=True, exist_ok=True)

        # === Iterative RTL Generation & Review ===
        logger.debug("Invoking RTLGenAgent with review loop...")
        rtlgen = AgentManager.get_agent("rtlgen", verbose=verbose)
        rtlreview = AgentManager.get_agent("rtlreview", verbose=verbose)
        rtl_code, rtl_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=rtlgen,
            initial_spec=spec,
            feedback_agent=rtlreview,
            max_iters=max_iters
        )
        logger.info("RTL generation + review completed.")

        # === Iterative Testbench Generation & Review ===
        logger.debug("Invoking TBGenAgent with review loop...")
        tbgen = AgentManager.get_agent("tbgen", verbose=verbose)
        tbreview = AgentManager.get_agent("tbreview", verbose=verbose)
        tb_code, tb_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=tbgen,
            initial_spec=(spec, rtl_code, base),
            feedback_agent=tbreview,
            max_iters=max_iters
        )
        logger.info("Testbench generation + review completed.")

        # Write outputs (always after improvement)
        rtl_file = rtl_output_dir / f"{base}_rtl_gen.v"
        tb_file = tb_output_dir / f"{base}_tb_gen.v"
        write_output(rtl_code, None, str(rtl_output_dir), f"{base}_rtl_gen", ".v")
        write_output(tb_code, None, str(tb_output_dir), f"{base}_tb_gen", ".v")

        # === Simulation & Debug Loop ===
        logger.debug("Invoking SimAgent...")
        sim_agent = AgentManager.get_agent("sim", verbose=verbose)
        debug_agent = AgentManager.get_agent("debug", verbose=verbose)

        sim_status = "failed"
        sim_stdout = ""
        sim_stderr = ""
        sim_error_message = ""
        final_debug_report = "No debug needed (simulation successful)"

        for i in range(max_iters):
            logger.info(f"Running simulation iteration {i+1}/{max_iters}...")
            sim_result = sim_agent.run(project_path, base)
            sim_status = sim_result["status"]
            sim_stdout = sim_result["stdout"]
            sim_stderr = sim_result["stderr"]
            sim_error_message = sim_result["error_message"]

            # Always read the real, current files (to catch any file-extraction bugs)
            extracted_rtl_code = read_file(rtl_file)
            extracted_tb_code = read_file(tb_file)

            # Detect common code extraction/sim issues
            vcd_missing = "No VCD files found" in sim_stdout or "No VCD files found" in sim_stderr
            compile_fail = ("error" in sim_stderr.lower()) or ("parse" in sim_stderr.lower()) or ("fatal" in sim_stderr.lower())

            if sim_status == "success" and not vcd_missing and not compile_fail:
                logger.info("Simulation successful.")
                break

            # Provide all inputs separately to debug agent and receive actionable suggestions + agent list
            debug_output, suggested_agents = debug_agent.run(
                rtl_code=extracted_rtl_code,
                tb_code=extracted_tb_code,
                sim_stdout=sim_stdout,
                sim_stderr=sim_stderr,
                sim_error_message=sim_error_message
            )
            logger.info("Debug report generated based on simulation failure.")
            logger.info(f"Debug Report: {debug_output}")
            final_debug_report = debug_output

            if i < max_iters - 1:
                # If only UserAction suggested, cannot auto-heal
                if suggested_agents == ["UserAction"]:
                    logger.error("Debug agent suggests UserAction; cannot heal automatically.")
                    break
                # Else, invoke healing for each recommended agent
                for agent_name in suggested_agents:
                    if agent_name == "RTLGenAgent":
                        logger.info("Improving RTL based on debug agent suggestion.")
                        rtl_code, _ = AgentFeedbackCoordinator.iterate_improvements(
                            agent=rtlgen,
                            initial_spec=spec,
                            feedback_agent=rtlreview,
                            feedback=debug_output,
                            max_iters=1
                        )
                        write_output(rtl_code, None, str(rtl_output_dir), f"{base}_rtl_gen", ".v")
                    elif agent_name == "TBGenAgent":
                        logger.info("Improving Testbench based on debug agent suggestion.")
                        tb_code, _ = AgentFeedbackCoordinator.iterate_improvements(
                            agent=tbgen,
                            initial_spec=(spec, rtl_code, base),
                            feedback_agent=tbreview,
                            feedback=debug_output,
                            max_iters=1
                        )
                        write_output(tb_code, None, str(tb_output_dir), f"{base}_tb_gen", ".v")
                # Continue loop to simulate again with improved code
            else:
                logger.error("Max simulation iterations reached. Simulation still failing after healing attempts.")

        # === (Commented) Formal Property Gen & Review ===
        formal_properties = "Formal property generation commented out."
        fprop_review_report = "Formal property review commented out."
        debug_report = final_debug_report
        logger.info("Debug phase completed.")

        # === Final Report Phase ===
        logger.debug("Invoking ReportAgent for pipeline summary...")
        report_agent = AgentManager.get_agent("report", verbose=verbose)
        # --- Named keys for every artifact ---
        phase_outputs = {
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
            "debug_report": debug_report
        }
        pipeline_report = report_agent.run(phase_outputs)
        logger.info("Pipeline summary report generated.")

        results = {
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
            "pipeline_report": pipeline_report
        }

        logger.info("Full pipeline completed successfully.")
        return results
