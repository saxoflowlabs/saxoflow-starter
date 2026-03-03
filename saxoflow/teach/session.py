# saxoflow/teach/session.py
"""
TeachSession and related dataclasses for the SaxoFlow tutoring subsystem.

This module defines the **spine** of the entire tutoring system.
Every component in the teach subsystem either reads from or writes to
a ``TeachSession`` object.  It is stored as a module-level singleton in
``cool_cli/state.py`` and is injected as an explicit argument into every
``TutorAgent`` call -- never reconstructed mid-session, never inferred
from disk.

Design rules (non-negotiable)
------------------------------
1. ``TeachSession`` is the single source of truth for all tutoring state.
2. It is always injected explicitly.  No caller builds its own context.
3. ``add_turn()`` is the **only** way to append conversation history so
   the ``MAX_HISTORY_TURNS`` window is automatically enforced.
4. Dataclasses are frozen where mutation is not required (``CheckDef``,
   ``CommandDef``, ``AgentInvocationDef``) to prevent accidental mutation.

Python: 3.9+
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional


@dataclass(frozen=True)
class QuestionDef:
    """A reflection question shown to the student at a defined point in the lesson.

    Attributes
    ----------
    text:
        The question text displayed in the TUI panel.
    after_command:
        When to show this question:
        ``-1`` — after the student finishes reading all tutorial chunks (before
        the command phase begins).  ``N`` (0-based) — after command ``N`` has
        run (post-command reflection).  Currently only ``-1`` is acted on;
        post-command questions (N >= 0) are reserved for a future release.
    kind:
        ``"reflection"`` (default) — open-ended; no automated answer check.
        Future values: ``"numeric"``, ``"text_contains"``.
    """

    text: str
    after_command: int = -1
    kind: str = "reflection"


# ---------------------------------------------------------------------------
# Frozen leaf dataclasses (immutable once the pack is loaded)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckDef:
    """Describes a single success check for a lesson step.

    Attributes
    ----------
    kind:
        One of ``"file_exists"``, ``"log_regex"``, ``"exit_code"``.
    pattern:
        The regex pattern (for ``log_regex``), glob pattern (for
        ``file_exists``), or expected exit-code string (for ``exit_code``).
    file:
        Log file path used by ``log_regex`` checks.
    """

    kind: str
    pattern: str = ""
    file: str = ""


@dataclass(frozen=True)
class CommandDef:
    """A single command declared for a lesson step.

    Attributes
    ----------
    native:
        The command exactly as written in the source tutorial
        (e.g. ``"iverilog -g2012 -o sim.out tb.v dut.v"``).
    preferred:
        The SaxoFlow wrapper if the pack author has declared one
        (e.g. ``"saxoflow sim"``).  May be ``None``.
    use_preferred_if_available:
        When ``True`` and the command registry confirms the wrapper is
        ``available``, the step runner uses the preferred command.
    """

    native: str
    preferred: Optional[str] = None
    use_preferred_if_available: bool = True
    # When True the runner launches in background (non-blocking, fire-and-forget).
    # Use for GUI tools like GTKWave that block until the user closes the window.
    background: bool = False


@dataclass(frozen=True)
class AgentInvocationDef:
    """Declares an AI agent that should be invoked during a lesson step.

    Attributes
    ----------
    agent_key:
        Key registered in ``AgentManager.AGENT_MAP``
        (e.g. ``"rtlgen"``, ``"tbgen"``, ``"fullpipeline"``).
    args:
        Keyword arguments forwarded to the agent (e.g.
        ``{"spec_file": "source/specification/mod.md"}``).
    description:
        Human-readable summary shown to the student before invocation.
    """

    agent_key: str
    args: Dict[str, str] = field(default_factory=dict)
    description: str = ""

    # dataclass(frozen=True) requires hashable fields; use tuple for args.
    def __hash__(self) -> int:  # type: ignore[override]
        return hash((self.agent_key, tuple(sorted(self.args.items())), self.description))


# ---------------------------------------------------------------------------
# Mutable step and pack containers
# ---------------------------------------------------------------------------

@dataclass
class StepDef:
    """A single lesson step loaded from a lesson YAML file.

    Attributes
    ----------
    id:
        Unique identifier used as a dict key in ``TeachSession`` progress
        maps (e.g. ``"sim_run"``).
    title:
        Short human-readable step title.
    goal:
        One-paragraph explanation of what the student will achieve.
    read:
        List of ``{"doc": str, "pages": str, "section": str}`` dicts
        pointing to the source document sections for this step.
    commands:
        Ordered list of :class:`CommandDef` objects to execute.
    agent_invocations:
        List of :class:`AgentInvocationDef` for optional AI agent calls.
    success:
        List of :class:`CheckDef` that must all pass for the step to be
        considered complete.
    hints:
        List of common-failure hint strings shown on ``teach check`` fail.
    notes:
        Free-form instructor note (not shown in tutor prompts by default).
    """

    id: str
    title: str
    goal: str
    read: List[Dict[str, Any]] = field(default_factory=list)
    commands: List[CommandDef] = field(default_factory=list)
    agent_invocations: List[AgentInvocationDef] = field(default_factory=list)
    success: List[CheckDef] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    questions: List[QuestionDef] = field(default_factory=list)
    notes: str = ""
    mode: str = "sequential"  # "sequential" (tutorial) | "index" (lecture chooser)


@dataclass
class PackDef:
    """A fully loaded teaching pack.

    Attributes
    ----------
    id:
        Identifier matching the pack directory name (e.g.
        ``"ethz_ic_design"``).
    name:
        Human-readable pack name displayed to students.
    version:
        SemVer string (e.g. ``"1.0"``).
    authors:
        List of author / institution strings.
    description:
        Multi-line description shown by ``teach status``.
    docs:
        List of ``{"filename": str, "type": str}`` dicts describing
        documents to index.
    steps:
        Ordered list of :class:`StepDef` objects (the full curriculum).
    docs_dir:
        Absolute path to ``<pack_path>/docs/``.
    pack_path:
        Absolute path to the pack root directory.
    """

    id: str
    name: str
    version: str
    authors: List[str]
    description: str
    docs: List[Dict[str, str]]
    steps: List[StepDef]
    docs_dir: Path
    pack_path: Path


# ---------------------------------------------------------------------------
# TeachSession -- the spine of the tutoring system
# ---------------------------------------------------------------------------

@dataclass
class TeachSession:
    """Active tutoring session for a student working through a pack.

    Lives as a module-level singleton in ``cool_cli.state`` (``teach_session``).
    Injected *explicitly* into every ``TutorAgent.run()`` call.

    Attributes
    ----------
    pack:
        The fully loaded :class:`PackDef` for the active teaching pack.
    current_step_index:
        Zero-based index into ``pack.steps``; updated by :meth:`advance`.
    conversation_turns:
        Rolling conversation buffer.  Managed via :meth:`add_turn`;
        automatically capped at ``MAX_HISTORY_TURNS * 2`` entries.
    MAX_HISTORY_TURNS:
        Number of student/tutor *exchange* pairs kept in the LLM context.
    last_run_log:
        Combined stdout + stderr of the most recently executed step command.
    last_run_exit_code:
        Exit code of the most recently executed step command (``-1`` means
        no command has been executed yet).
    last_run_command:
        The exact command string that was last executed.
    workspace_snapshot:
        ``{relative_path: bool}`` mapping showing which expected artefacts
        exist in the project directory.
    checks_passed:
        ``{step_id: bool}`` mapping; updated by :meth:`mark_check_passed`.
    agent_results:
        ``{step_id: result_str}`` mapping; updated by
        :meth:`store_agent_result`.
    """

    pack: PackDef
    current_step_index: int = 0
    conversation_turns: List[Dict[str, str]] = field(default_factory=list)
    MAX_HISTORY_TURNS: int = 6
    last_run_log: str = ""
    last_run_exit_code: int = -1
    last_run_command: str = ""
    workspace_snapshot: Dict[str, bool] = field(default_factory=dict)
    checks_passed: Dict[str, bool] = field(default_factory=dict)
    agent_results: Dict[str, str] = field(default_factory=dict)
    # Chunk navigation state (populated by _tui_bridge when a step is entered)
    current_chunk_index: int = 0
    step_chunks: List[Any] = field(default_factory=list)
    in_content_phase: bool = True
    chunk_mode: str = "sequential"
    # Question state (populated from StepDef.questions by _tui_bridge)
    pending_questions: List[QuestionDef] = field(default_factory=list)
    question_phase: bool = False
    # The specific question currently shown to the student (cleared when phase ends).
    # Stored so the TutorAgent can evaluate/discuss it in context.
    current_question: Optional[QuestionDef] = None
    # Per-command execution cursor: which command the student is on next.
    # Incremented by _tui_bridge after each `run` press so only ONE command
    # executes per press.  Reset to 0 whenever the step changes.
    current_command_index: int = 0
    # Effective working directory relative to project_root.  Updated when the
    # student runs a command that contains 'cd'.  Empty string = project_root.
    cwd: str = ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_step(self) -> Optional[StepDef]:
        """Return the active :class:`StepDef`, or ``None`` when complete."""
        if self.current_step_index >= self.total_steps:
            return None
        return self.pack.steps[self.current_step_index]

    @property
    def total_steps(self) -> int:
        """Total number of steps in the pack."""
        return len(self.pack.steps)

    @property
    def is_complete(self) -> bool:
        """``True`` when the student has passed all steps."""
        return self.current_step_index >= self.total_steps

    # ------------------------------------------------------------------
    # Mutation helpers (the only correct way to modify session state)
    # ------------------------------------------------------------------

    def add_turn(self, role: str, content: str) -> None:
        """Append one conversation turn and enforce the history window.

        Parameters
        ----------
        role:
            ``"student"`` or ``"tutor"``.
        content:
            The message text.
        """
        if not content or not content.strip():
            return
        self.conversation_turns.append({"role": role, "content": content})
        max_entries = self.MAX_HISTORY_TURNS * 2
        if len(self.conversation_turns) > max_entries:
            self.conversation_turns = self.conversation_turns[-max_entries:]

    def advance(self) -> bool:
        """Advance to the next step.

        Returns
        -------
        bool
            ``True`` if successfully advanced; ``False`` if already on the
            last step (index is set to ``total_steps`` to mark completion).
        """
        if self.current_step_index < self.total_steps - 1:
            self.current_step_index += 1
            self.current_command_index = 0
            self.cwd = ""
            return True
        # Mark session as complete by pushing index past the last step
        self.current_step_index = self.total_steps
        return False

    def go_back(self) -> bool:
        """Move to the previous step.

        Returns
        -------
        bool
            ``True`` if successfully moved back; ``False`` if already on
            the first step.
        """
        if self.current_step_index > 0:
            self.current_step_index -= 1
            self.current_command_index = 0
            self.cwd = ""
            return True
        return False

    def reset_chunk_state(self) -> None:
        """Reset chunk navigation when entering a new or revisited step.

        Called by the TUI bridge whenever the step changes so the student
        starts reading from the first content chunk.
        """
        self.current_chunk_index = 0
        self.step_chunks = []
        self.in_content_phase = True
        self.pending_questions = []
        self.question_phase = False
        # NOTE: current_command_index is intentionally NOT reset here.
        # It is reset in advance() and go_back() when changing steps, and
        # restored from disk by load_progress() on session resume.
        step = self.current_step
        self.chunk_mode = step.mode if step is not None else "sequential"

    def mark_check_passed(self, step_id: str) -> None:
        """Record that all checks for *step_id* have passed."""
        self.checks_passed[step_id] = True

    def store_agent_result(self, step_id: str, result: str) -> None:
        """Persist the output of an agent invocation for a step."""
        self.agent_results[step_id] = result

    def update_workspace_snapshot(self, project_root: Path) -> None:
        """Refresh ``workspace_snapshot`` from the filesystem.

        Scans each success criterion that refers to a file path and records
        whether that path currently exists under *project_root*.
        """
        snapshot: Dict[str, bool] = {}
        for chk in self.current_step.success:
            if chk.kind == "file_exists" and (chk.file or chk.pattern):
                target = chk.file or chk.pattern
                snapshot[target] = bool(list(project_root.glob(target)) if "*" in target
                                        else (project_root / target).exists())
        self.workspace_snapshot = snapshot

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    # Default progress file — ClassVar so @dataclass ignores it;
    # can be overridden per-instance (e.g. in tests) via direct attribute set.
    _progress_file: ClassVar[Path] = Path(".saxoflow") / "teach" / "progress.json"

    def save_progress(self) -> None:
        """Persist step index and check results to disk."""
        self._progress_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pack_id": self.pack.id,
            "current_step_index": self.current_step_index,
            "current_command_index": self.current_command_index,
            "cwd": self.cwd,
            "checks_passed": self.checks_passed,
            "agent_results": {k: v[:500] for k, v in self.agent_results.items()},
        }
        self._progress_file.write_text(
            json.dumps(data, indent=2), encoding="utf-8"
        )

    def load_progress(self) -> bool:
        """Restore step index and check results from disk if available.

        Returns
        -------
        bool
            ``True`` if progress was loaded; ``False`` if no file found.
        """
        if not self._progress_file.exists():
            return False
        try:
            data = json.loads(self._progress_file.read_text(encoding="utf-8"))
            if data.get("pack_id") != self.pack.id:
                return False
            self.current_step_index = int(data.get("current_step_index", 0))
            self.current_command_index = int(data.get("current_command_index", 0))
            self.cwd = data.get("cwd", "")
            self.checks_passed = data.get("checks_passed", {})
            self.agent_results = data.get("agent_results", {})
            return True
        except (json.JSONDecodeError, KeyError, TypeError):
            return False
