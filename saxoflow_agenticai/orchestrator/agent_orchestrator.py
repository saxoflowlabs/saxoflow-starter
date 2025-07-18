from saxoflow_agenticai.core.agent_manager import AgentManager
from saxoflow_agenticai.core.log_manager import get_logger
from saxoflow_agenticai.orchestrator.feedback_coordinator import AgentFeedbackCoordinator

logger = get_logger()

class AgentOrchestrator:

    @staticmethod
    def full_pipeline(spec: str, verbose: bool = False, max_iters: int = 1):
        """
        Complete end-to-end generation pipeline, now with iterative review-improve:
        RTLGen <-> RTLReview (loop)
        TBGen <-> TBReview (loop)
        FormalPropGen <-> FormalPropReview (loop)
        Optionally includes debugging and final report phases.
        """
        logger.info("[Orchestrator] Starting full pipeline for given spec.")

        # === Iterative RTL Generation & Review ===
        logger.debug("[Orchestrator] Invoking RTLGenAgent with review loop...")
        rtlgen = AgentManager.get_agent("rtlgen", verbose=verbose)
        rtlreview = AgentManager.get_agent("rtlreview", verbose=verbose)
        rtl_code, rtl_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=rtlgen,
            initial_spec=spec,  # (spec,)
            feedback_agent=rtlreview,
            max_iters=max_iters
        )
        logger.info("[Orchestrator] RTL generation + review completed.")

        # === Iterative Testbench Generation & Review ===
        logger.debug("[Orchestrator] Invoking TBGenAgent with review loop...")
        tbgen = AgentManager.get_agent("tbgen", verbose=verbose)
        tbreview = AgentManager.get_agent("tbreview", verbose=verbose)
        tb_code, tb_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=tbgen,
            initial_spec=(spec, rtl_code),
            feedback_agent=tbreview,
            max_iters=max_iters
        )
        logger.info("[Orchestrator] Testbench generation + review completed.")

        # === Iterative Formal Property Generation & Review ===
        logger.debug("[Orchestrator] Invoking FormalPropGenAgent with review loop...")
        fpropgen = AgentManager.get_agent("fpropgen", verbose=verbose)
        fpropreview = AgentManager.get_agent("fpropreview", verbose=verbose)
        formal_properties, fprop_review_report = AgentFeedbackCoordinator.iterate_improvements(
            agent=fpropgen,
            initial_spec=(spec, rtl_code),
            feedback_agent=fpropreview,
            max_iters=max_iters
        )
        logger.info("[Orchestrator] Formal property generation + review completed.")

        # === (Optional) Debug Phase ===
        logger.debug("[Orchestrator] Invoking DebugAgent...")
        debug_agent = AgentManager.get_agent("debug", verbose=verbose)
        debug_report = debug_agent.run(
            f"RTL Code:\n{rtl_code}\n\nTestbench Code:\n{tb_code}\n\nFormal Properties:\n{formal_properties}"
        )
        logger.info("[Orchestrator] Debug phase completed.")

        # === Final Report Phase ===
        logger.debug("[Orchestrator] Invoking ReportAgent for pipeline summary...")
        report_agent = AgentManager.get_agent("report", verbose=verbose)
        phase_outputs = {
            "rtl_generation": rtl_code,
            "rtl_review": rtl_review_report,
            "testbench_generation": tb_code,
            "testbench_review": tb_review_report,
            "formal_property_generation": formal_properties,
            "formal_property_review": fprop_review_report,
            "debug": debug_report
        }
        pipeline_report = report_agent.run(phase_outputs)
        logger.info("[Orchestrator] Pipeline summary report generated.")

        results = {
            "rtl_code": rtl_code,
            "testbench_code": tb_code,
            "formal_properties": formal_properties,
            "rtl_review_report": rtl_review_report,
            "tb_review_report": tb_review_report,
            "fprop_review_report": fprop_review_report,
            "debug_report": debug_report,
            "pipeline_report": pipeline_report
        }

        logger.info("[Orchestrator] Full pipeline completed successfully.")
        return results
