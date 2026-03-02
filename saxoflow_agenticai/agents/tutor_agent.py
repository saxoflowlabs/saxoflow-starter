# saxoflow_agenticai/agents/tutor_agent.py
"""
TutorAgent: document-grounded interactive tutoring agent for SaxoFlow.

Architecture contracts (non-negotiable)
----------------------------------------
1. :class:`TeachSession` is always **injected** into :meth:`run`; it is never
   read from a global or module-level singleton.
2. The LLM decides **only** what to explain.  It never decides what command
   to execute.  Commands come from the step YAML ``CommandDef`` objects.
3. All context delivered to the LLM is composed in :meth:`_build_context_bundle`
   and nowhere else.
4. Retrieval is done exclusively via :func:`~saxoflow.teach.retrieval.retrieve_chunks`.
5. The result string returned by :meth:`run` is always formatted through
   ``tutor_agent_result.txt``.

Prompt template: ``saxoflow_agenticai/prompts/tutor_prompt.txt``
Result template: ``saxoflow_agenticai/prompts/tutor_agent_result.txt``

Python: 3.9+
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from saxoflow_agenticai.core.base_agent import BaseAgent

if TYPE_CHECKING:
    from saxoflow.teach.session import TeachSession

__all__ = ["TutorAgent"]

logger = logging.getLogger("saxoflow_agenticai.tutor")

# Maximum number of retrieved chunks to include in the context bundle.
_TOP_K_CHUNKS = 3

# Sentinel text when no document chunks are available.
_NO_CHUNKS_TEXT = (
    "[No document excerpts indexed yet. "
    "Run `saxoflow teach index <pack_id>` to build the index.]"
)


class TutorAgent(BaseAgent):
    """Interactive tutoring agent grounded in a teaching pack's documents.

    Parameters
    ----------
    **kwargs:
        Forwarded to :class:`~saxoflow_agenticai.core.base_agent.BaseAgent`.
        The ``template_name`` defaults to ``"tutor_prompt.txt"``; the
        ``name`` defaults to ``"TutorAgent"``.

    Usage
    -----
    .. code-block:: python

        agent = TutorAgent(llm=my_llm, verbose=False)
        reply = agent.run(session=session, student_input="What does -g2012 mean?")
    """

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("template_name", "tutor_prompt.txt")
        kwargs.setdefault("name", "TutorAgent")
        kwargs.setdefault("description", "Document-grounded interactive EDA design tutor")
        kwargs.setdefault("agent_type", "tutor")
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # BaseAgent abstract method implementation
    # ------------------------------------------------------------------

    def run(  # type: ignore[override]
        self,
        session: "TeachSession",
        student_input: str = "",
        **_: Any,
    ) -> str:
        """Generate a tutoring response grounded in the current step and docs.

        Parameters
        ----------
        session:
            The active :class:`~saxoflow.teach.session.TeachSession`.
            **Must be injected explicitly; never read from global state.**
        student_input:
            The student's raw question or command (e.g., ``"explain this"``).

        Returns
        -------
        str
            The tutor's response, formatted with the result template.

        Raises
        ------
        RuntimeError
            If no LLM is configured.
        """
        if self.llm is None:
            raise RuntimeError(
                "TutorAgent requires an LLM. "
                "Pass `llm=<model>` to the constructor or configure via ModelSelector."
            )

        step = session.current_step
        if step is None:
            return "Session complete — all steps finished!"

        context = self._build_context_bundle(session, student_input)
        prompt = self.render_prompt(context)
        raw_reply = self.query_model(prompt)

        # Record the turn in session history
        session.add_turn("student", student_input)
        session.add_turn("tutor", raw_reply)

        return self._format_result(raw_reply, session)

    def improve(self, session: "TeachSession", feedback: str = "", **_: Any) -> str:  # type: ignore[override]
        """Re-generate a tutor reply incorporating *feedback*.

        Typically called if the student says "simpler please" or "more detail".
        Injects feedback into the student_input and calls :meth:`run` again.
        """
        improved_input = f"[Feedback: {feedback}] Please provide a revised explanation."
        return self.run(session=session, student_input=improved_input)

    # ------------------------------------------------------------------
    # Context bundle: single source of truth for LLM input
    # ------------------------------------------------------------------

    def _build_context_bundle(
        self, session: "TeachSession", student_input: str
    ) -> Dict[str, str]:
        """Compose all context delivered to the LLM prompt.

        This is the **only** place where context for the LLM is assembled.
        No other method should add context to the prompt.

        Returns
        -------
        dict
            Variables matching the placeholders in ``tutor_prompt.txt``.
        """
        step = session.current_step
        assert step is not None, "_build_context_bundle called when step is None"

        # -- Retrieved document chunks -------------------------------------
        retrieved_text = self._retrieve_doc_context(session, student_input, step)

        # -- Step commands summary -----------------------------------------
        commands_text = self._format_commands(step)

        # -- Conversation history ------------------------------------------
        history_text = self._format_history(session)

        return {
            "step_index": str(session.current_step_index + 1),
            "total_steps": str(session.total_steps),
            "step_title": step.title,
            "step_goal": step.goal,
            "retrieved_chunks": retrieved_text,
            "step_commands": commands_text,
            "conversation_history": history_text,
            "student_input": student_input or "(no input)",
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _retrieve_doc_context(
        self, session: "TeachSession", student_input: str, step
    ) -> str:
        """Call :func:`~saxoflow.teach.retrieval.retrieve_chunks` and format output."""
        # Lazy import to keep saxoflow_agenticai free of circular deps
        from saxoflow.teach.retrieval import retrieve_chunks  # noqa: PLC0415

        query = f"{step.title} {step.goal} {student_input}".strip()
        chunks = retrieve_chunks(session, query, top_k=_TOP_K_CHUNKS)

        if not chunks:
            return _NO_CHUNKS_TEXT

        parts: List[str] = []
        for i, chunk in enumerate(chunks, start=1):
            header = f"[Excerpt {i}"
            if chunk.source_doc:
                header += f" — {chunk.source_doc}"
            if chunk.page_num > 0:
                header += f", p.{chunk.page_num}"
            if chunk.section_hint:
                header += f", §{chunk.section_hint}"
            header += "]"
            parts.append(f"{header}\n{chunk.text}")

        return "\n\n".join(parts)

    @staticmethod
    def _format_commands(step) -> str:
        """Render the step's command list as a numbered string."""
        if not step.commands:
            return "(No commands for this step — review only.)"
        lines: List[str] = []
        for i, cmd in enumerate(step.commands, start=1):
            if cmd.preferred:
                lines.append(
                    f"  {i}. {cmd.native}\n"
                    f"     (SaxoFlow alias: {cmd.preferred})"
                )
            else:
                lines.append(f"  {i}. {cmd.native}")
        return "\n".join(lines)

    @staticmethod
    def _format_history(session: "TeachSession") -> str:
        """Render the last N conversation turns as a readable string."""
        turns = session.conversation_turns
        if not turns:
            return "(no prior messages)"
        lines: List[str] = []
        for turn in turns:
            role = turn.get("role", "?").capitalize()
            content = turn.get("content", "")
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _format_result(self, raw_reply: str, session: "TeachSession") -> str:
        """Wrap *raw_reply* in the result template."""
        step = session.current_step
        if step is None:
            return raw_reply
        try:
            context: Dict[str, str] = {
                "tutor_explanation": raw_reply,
                "step_index": str(session.current_step_index + 1),
                "total_steps": str(session.total_steps),
                "step_title": step.title,
            }
            return self.render_prompt(context, template_name="tutor_agent_result.txt")
        except Exception:  # pragma: no cover - template missing, degrade gracefully
            return raw_reply
