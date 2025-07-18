class AgentFeedbackCoordinator:
    @staticmethod
    def iterate_improvements(agent, initial_spec, feedback_agent, max_iters=1):
        """
        agent: generator agent (e.g., RTLGenAgent, TBGenAgent, FormalPropGenAgent)
        initial_spec: can be a tuple (spec, rtl_code) or just spec, as required by the agent
        feedback_agent: corresponding reviewer agent
        max_iters: maximum refinement cycles
        """
        if isinstance(initial_spec, tuple):
            spec_args = initial_spec
        else:
            spec_args = (initial_spec,)

        # Initial generation: agent.run(spec, [rtl_code])
        output = agent.run(*spec_args)
        prev_output = output

        for i in range(max_iters):
            # Reviewer: run(spec, [rtl_code], code)
            review_args = spec_args + (prev_output,)
            feedback = feedback_agent.run(*review_args)
            feedback = (feedback or "").strip()
            if not feedback:
                feedback = "No major issues found."
            lower_feedback = feedback.lower()
            if any(
                key in lower_feedback
                for key in [
                    "no major issue", "no issues found",
                    "no issues detected", "no issue", "no issues identified"
                ]
            ):
                break

            # Dynamic improvement for FormalPropGenAgent: pass prev formal props too
            if hasattr(agent, "agent_type") and agent.agent_type == "fpropgen":
                # fpropgen.improve(spec, rtl_code, prev_fprops, review)
                improve_args = spec_args + (prev_output, feedback)
            elif hasattr(agent, "agent_type") and agent.agent_type == "tbgen":
                # tbgen.improve(spec, prev_tb_code, feedback, rtl_code)
                improve_args = (spec_args[0], prev_output, feedback, spec_args[1])
            elif hasattr(agent, "agent_type") and agent.agent_type == "rtlgen":
                # rtlgen.improve(spec, prev_rtl_code, review)
                improve_args = (spec_args[0], prev_output, feedback)
            else:
                # fallback
                improve_args = spec_args + (prev_output, feedback)

            prev_output = agent.improve(*improve_args)

        return prev_output, feedback
