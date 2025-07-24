import re

class AgentFeedbackCoordinator:
    @staticmethod
    def is_no_action_feedback(feedback: str) -> bool:
        """
        Returns True if feedback means 'no action needed'.
        Detects semantically similar variants, headings, or all-'None' outputs.
        """
        text = (feedback or "").lower().strip()
        if not text or len(text) < 12:
            return True
        text = re.sub(r"[-*:_`']", " ", text)
        text = re.sub(r"\s+", " ", text)
        NO_ISSUE_PATTERNS = [
            r"\bno (major )?(issue|issues|problem|problems|concerns|errors|fixes|changes|action)(s)?\b",
            r"\bnothing to (fix|address|change|improve|add)\b",
            r"\bnone found\b", r"\ball good\b", r"\bok\b", r"\blooks good\b",
            r"\bno feedback\b", r"\bclean\b", r"\bapproved\b", r"\bpass(ed)?\b", r"\bcorrect\b"
        ]
        for pat in NO_ISSUE_PATTERNS:
            if re.search(pat, text):
                return True
        all_lines = [l.strip() for l in text.splitlines() if l.strip()]
        if all_lines and all(
            re.match(r"(none|no issues?|ok|looks good|pass|clean|approved|correct)[ .:;,-]*$", l)
            or re.match(r"^[A-Za-z0-9 _-]+:\s*(none|ok|pass|clean|approved|correct)[ .:;,-]*$", l)
            for l in all_lines
        ):
            return True
        return False

    @staticmethod
    def iterate_improvements(agent, initial_spec, feedback_agent, max_iters=1, logger=None):
        """
        agent: generator agent (e.g., RTLGenAgent, TBGenAgent, FormalPropGenAgent)
        initial_spec: tuple or single spec, as required by the agent
        feedback_agent: corresponding reviewer agent (can be review or debug agent!)
        max_iters: maximum refinement cycles
        logger: optional logger for debugging

        Handles all argument signatures robustly.
        """
        if logger is None:
            import logging
            logger = logging.getLogger("saxoflow_agenticai")

        # Standardize to tuple for easier handling
        if isinstance(initial_spec, tuple):
            spec_args = initial_spec
        else:
            spec_args = (initial_spec,)

        output = agent.run(*spec_args)
        prev_output = output

        for i in range(max_iters):
            # === Construct reviewer/debug agent input ===
            if hasattr(agent, "agent_type") and agent.agent_type == "tbgen":
                # TBGen's reviewer expects: (spec, rtl_code, top_module_name, testbench_code)
                review_args = (spec_args[0], spec_args[1], spec_args[2], prev_output)
            elif hasattr(agent, "agent_type") and agent.agent_type == "rtlgen":
                # RTLGen's reviewer expects: (spec, rtl_code)
                review_args = (spec_args[0], prev_output)
            elif hasattr(agent, "agent_type") and agent.agent_type == "fpropgen":
                # FormalPropGen's reviewer expects: (spec, rtl_code, formal_properties)
                review_args = (spec_args[0], spec_args[1], prev_output)
            else:
                # fallback: assume all gen inputs + generated code as last
                review_args = spec_args + (prev_output,)

            feedback = feedback_agent.run(*review_args)
            feedback = (feedback or "").strip()

            if not feedback:
                feedback = "No major issues found."
                logger.warning("[AgentFeedbackCoordinator] Review/debug agent returned blank feedback. Using fallback.")

            if AgentFeedbackCoordinator.is_no_action_feedback(feedback):
                logger.info(f"[AgentFeedbackCoordinator] Exiting improvement loop at iteration {i+1} as review/debug reports no major issues.")
                break

            logger.info(f"[AgentFeedbackCoordinator] Triggering improvement step at iteration {i+1}.")

            # === Construct improve() args for generation agent ===
            if hasattr(agent, "agent_type") and agent.agent_type == "fpropgen":
                # fpropgen.improve(spec, rtl_code, prev_formal_properties, feedback)
                improve_args = spec_args + (prev_output, feedback)
            elif hasattr(agent, "agent_type") and agent.agent_type == "tbgen":
                # tbgen.improve(spec, prev_tb_code, feedback, rtl_code, top_module_name)
                improve_args = (spec_args[0], prev_output, feedback, spec_args[1], spec_args[2])
            elif hasattr(agent, "agent_type") and agent.agent_type == "rtlgen":
                # rtlgen.improve(spec, prev_rtl_code, review)
                improve_args = (spec_args[0], prev_output, feedback)
            else:
                improve_args = spec_args + (prev_output, feedback)

            prev_output = agent.improve(*improve_args)

        else:
            logger.warning("[AgentFeedbackCoordinator] Max iterations reached without review agent reporting 'no major issues'.")

        logger.info(f"[AgentFeedbackCoordinator] Improvement loop finished at iteration {i+1 if 'i' in locals() else 0}. Returning output.")

        return prev_output, feedback
