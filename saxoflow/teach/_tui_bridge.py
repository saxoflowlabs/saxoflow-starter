# saxoflow/teach/_tui_bridge.py
"""
TUI bridge: thin adapter between the cool_cli TUI and the teach subsystem.

Architecture contract (strict)
-------------------------------
- This is the **ONLY** file in ``saxoflow/teach/`` that may import from
  ``cool_cli``.  All other teach modules are TUI-agnostic.
- Call direction: cool_cli/app.py → _tui_bridge.handle_input() → teach modules.
- No business logic lives here; it only formats Rich panels and routes calls.

What this module does
---------------------
1. Parses special teach-mode commands: ``run``, ``next``, ``back``,
   ``hint``, ``status``, ``agents``, ``quit``.
2. For all other input, calls :class:`~saxoflow_agenticai.agents.tutor_agent.TutorAgent`.
3. Returns a ``rich.panel.Panel`` so ``app.py`` can print it like any other
   assistant response.

Python: 3.9+
"""

from __future__ import annotations

import logging
from typing import Optional

from rich.console import Group as _RichGroup
from rich.panel import Panel
from rich.text import Text

from saxoflow.teach._image_render import render_image_from_bytes
from saxoflow.teach.session import TeachSession

__all__ = ["handle_input", "start_session_panel", "session_end_panel", "prepare_step_for_display", "record_manual_command"]

logger = logging.getLogger("saxoflow.teach.tui_bridge")

# ---------------------------------------------------------------------------
# Teach-mode special commands (exact match after `.strip().lower()`)
# ---------------------------------------------------------------------------

_CMD_RUN = "run"
_CMD_NEXT = "next"
_CMD_BACK = "back"
_CMD_SKIP = "skip"
_CMD_HINT = "hint"
_CMD_STATUS = "status"
_CMD_AGENTS = "agents"
_CMD_QUIT = "quit"
_CMD_CONFIRM = "confirm"

_TEACH_COMMANDS = {_CMD_RUN, _CMD_NEXT, _CMD_BACK, _CMD_SKIP, _CMD_HINT,
                   _CMD_STATUS, _CMD_AGENTS, _CMD_QUIT, _CMD_CONFIRM}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_input(
    user_input: str,
    session: TeachSession,
    project_root: str = ".",
    llm=None,
    verbose: bool = False,
) -> Panel:
    """Route *user_input* to the correct teach subsystem handler.

    Parameters
    ----------
    user_input:
        Raw input string from the CLI prompt.
    session:
        Active :class:`~saxoflow.teach.session.TeachSession`.
    project_root:
        Working directory for command execution (default current dir).
    llm:
        Optional pre-built LangChain LLM.  If ``None``, ``TutorAgent``
        will raise if invoked; the bridge catches this gracefully.
    verbose:
        Passed through to agent / runner calls.

    Returns
    -------
    rich.panel.Panel
        Formatted response panel ready for ``cool_cli.app`` to print.
    """
    from pathlib import Path  # noqa: PLC0415

    cmd = user_input.strip().lower()
    _was_question_phase = session.question_phase

    # Dispatch to the correct handler and capture the result.  The nav panel
    # is appended below as a separate box so students always know what to do.
    if session.question_phase:
        # In question phase the student can still type run/skip/back/hint/status;
        # only free-text (answers / follow-up questions) is forwarded to the tutor.
        if cmd == _CMD_NEXT:
            if session.pending_questions:
                q = session.pending_questions.pop(0)
                _inner = _render_question_panel(session, q)
            else:
                session.question_phase = False
                session.current_question = None
                _inner = _render_command_phase_panel(session)
        elif cmd == _CMD_RUN:
            _inner = _handle_run(session, Path(project_root), verbose)
        elif cmd == _CMD_SKIP:
            _inner = _handle_skip(session)
        elif cmd == _CMD_BACK:
            _inner = _handle_back(session)
        elif cmd == _CMD_HINT:
            _inner = _handle_hint(session)
        elif cmd == _CMD_STATUS:
            _inner = _handle_status(session)
        elif cmd == _CMD_AGENTS:
            _inner = _handle_agents(session, verbose)
        elif cmd == _CMD_QUIT:
            return _handle_quit()
        elif cmd == _CMD_CONFIRM:
            _inner = _handle_confirm(session)
        else:
            # Student is answering or asking a follow-up — tutor evaluates with
            # full question context so it can validate or expand the answer.
            _inner = _handle_tutor_query(user_input, session, llm, verbose)
    elif cmd == _CMD_RUN:
        _inner = _handle_run(session, Path(project_root), verbose)
    elif cmd == _CMD_NEXT:
        _inner = _handle_next(session, llm, verbose)
    elif cmd == _CMD_SKIP:
        _inner = _handle_skip(session)
    elif cmd == _CMD_BACK:
        _inner = _handle_back(session)
    elif cmd == _CMD_HINT:
        _inner = _handle_hint(session)
    elif cmd == _CMD_STATUS:
        _inner = _handle_status(session)
    elif cmd == _CMD_AGENTS:
        _inner = _handle_agents(session, verbose)
    elif cmd == _CMD_QUIT:
        return _handle_quit()  # no nav panel after quit
    elif cmd == _CMD_CONFIRM:
        _inner = _handle_confirm(session)
    elif session.in_content_phase and session.chunk_mode == "index" and cmd.strip().isdigit():
        _inner = _handle_index_select(session, int(cmd.strip()))
    else:
        # Default: ask the TutorAgent (with current chunk injected for context)
        _inner = _handle_tutor_query(user_input, session, llm, verbose)

    # Suppress nav after a question panel — let the student respond naturally;
    # the nav will reappear alongside the tutor's reply or next action.
    _just_showed_question = (
        session.question_phase
        and (not _was_question_phase or cmd == _CMD_NEXT)
    )
    if _just_showed_question or session.is_complete:
        return _inner
    return _RichGroup(_inner, _render_nav_panel(session))


def start_session_panel(session: TeachSession) -> Panel:
    """Return a welcome panel shown when a teach session begins."""
    step = session.current_step
    if step is None:
        return _make_panel("Pack is empty — no steps.", style="red")

    body = (
        f"[bold cyan]Pack:[/bold cyan] {session.pack.name}\n"
        f"[bold cyan]Total steps:[/bold cyan] {session.total_steps}\n\n"
        f"[bold yellow]Step 1:[/bold yellow] {step.title}\n"
        f"[cyan]Goal:[/cyan] {step.goal}\n\n"
        f"[dim]Commands: run | next | back | hint | status | agents | quit[/dim]"
    )
    return Panel(
        Text.from_markup(body),
        title="[bold green]SaxoFlow Tutor — Session Started[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


def session_end_panel() -> Panel:
    """Return the congratulations panel shown when all steps complete."""
    return _make_panel(
        "Congratulations — you have completed all steps in this pack!",
        style="green",
        title="[bold green]Tutorial Complete[/bold green]",
    )


# ---------------------------------------------------------------------------
# Internal handlers
# ---------------------------------------------------------------------------


def _handle_run(session: TeachSession, project_root, verbose: bool) -> Panel:
    """Execute ONE command per 'run' press (tracked by current_command_index).

    Automatically transitions out of the content reading phase so the student
    does not need to exhaust all content chunks before running commands.
    """
    from saxoflow.teach.runner import run_step_commands   # noqa: PLC0415
    from saxoflow.teach.checks import evaluate_step_success  # noqa: PLC0415

    step = session.current_step
    if step is None:
        return _make_panel("No active step.", style="yellow")

    # Auto-exit content reading phase — student need not page through every
    # chunk before running commands.
    if session.in_content_phase:
        session.in_content_phase = False

    commands = step.commands
    if not commands:
        return _make_panel(
            "No commands declared for this step.\nType [bold]next[/bold] to continue.",
            style="yellow",
        )

    cmd_idx = session.current_command_index
    total_cmds = len(commands)

    # All commands already executed — re-evaluate checks
    if cmd_idx >= total_cmds:
        passed = evaluate_step_success(session, project_root)
        if passed:
            session.mark_check_passed(step.id)
            return _make_panel(
                "[green]\u2713 All commands done \u2014 checks passed.[/green]\n"
                "Type [bold]next[/bold] to continue to the next step.",
                style="green",
            )
        confirm_checks = [c for c in step.success if c.kind == "user_confirms"]
        if confirm_checks and not session.user_confirms_acknowledged:
            tasks = "\n".join(
                f"  \u2022 {c.pattern or 'Manual verification task'}"
                for c in confirm_checks
            )
            return _make_panel(
                f"[yellow]All commands done.[/yellow] Complete the manual task(s) below, "
                f"then type [bold]confirm[/bold] to acknowledge.\n\n{tasks}",
                style="yellow",
            )
        return _make_panel(
            "[yellow]All commands have been run.[/yellow]\n"
            "Some checks not yet met. Ask the tutor for help or type [bold]next[/bold] to proceed.",
            style="yellow",
        )

    # Execute exactly the one command at the current cursor position
    results = run_step_commands(session, project_root, cmd_index=cmd_idx)
    if not results:
        return _make_panel("Command execution failed unexpectedly.", style="red")

    r = results[0]
    lines: list = []
    lines.append(f"[dim]Command {cmd_idx + 1} of {total_cmds}[/dim]")
    lines.append(f"$ {r.command_str}")
    _stdout_text = r.stdout if r.stdout else "(no output)"
    lines.append(_stdout_text)
    if r.exit_code != 0 or r.timed_out:
        lines.append(f"[red]Exit code: {r.exit_code}[/red]")
        # Helpful directory context hint when a path-related error occurs
        if "no such file or directory" in _stdout_text.lower() or "cannot access" in _stdout_text.lower():
            lines.append(
                "[dim yellow]\u26a0  Path not found — your current directory (pwd) may not match "
                "the command path.  Run [bold white]pwd[/bold white] to verify, then adjust the "
                "path in the command if needed.[/dim yellow]"
            )
    lines.append("")

    # Advance the cursor so next 'run' press fires the next command
    session.current_command_index += 1
    session.save_progress()
    remaining = total_cmds - session.current_command_index

    if remaining > 0:
        next_cmd = commands[session.current_command_index]
        lines.append(
            f"[bold cyan]Next ({session.current_command_index + 1}/{total_cmds}):[/bold cyan]  "
            f"[yellow]{next_cmd.native}[/yellow]"
        )
        lines.append("")
        lines.append("[dim]Type [bold white]run[/bold white] to execute  \u00b7  or ask the tutor a question[/dim]")
    else:
        # All commands done — evaluate success checks
        confirm_checks = [c for c in step.success if c.kind == "user_confirms"]
        if confirm_checks:
            lines.append("[bold yellow]Manual verification required:[/bold yellow]")
            for c in confirm_checks:
                lines.append(f"  [yellow]\u2022 {c.pattern or 'Complete the interactive step above'}[/yellow]")
            lines.append(
                "[dim]When done, type [bold white]confirm[/bold white] to acknowledge "
                "\u2014 then [bold white]next[/bold white] to continue.[/dim]"
            )
            lines.append("")

        passed = evaluate_step_success(session, project_root)
        if passed:
            session.mark_check_passed(step.id)
            if not confirm_checks:
                lines.append("[green]\u2713 All commands done \u2014 step checks passed![/green]")
                lines.append("Type [bold]next[/bold] to continue to the next step.")
        else:
            auto_checks = [c for c in step.success if c.kind != "user_confirms"]
            if auto_checks:
                lines.append("[yellow]All commands run \u2014 some checks not yet met.[/yellow]")
                lines.append("Ask the tutor for help or type [bold]next[/bold] to continue.")

    return Panel(
        Text.from_markup("\n".join(lines)),
        title="[bold white]Command Output[/bold white]",
        border_style="white",
        padding=(1, 2),
    )


def _handle_next(session: TeachSession, llm=None, verbose: bool = False) -> Panel:
    """Advance through content chunks, or transition to commands, or next step."""
    # ---- Phase 1: reading content chunks ----
    if session.in_content_phase:
        chunks = session.step_chunks
        if chunks and session.current_chunk_index < len(chunks) - 1:
            session.current_chunk_index += 1
            return _render_chunk_panel(session)
        else:
            # All chunks read — check for pre-command reflection questions
            session.in_content_phase = False
            step = session.current_step
            if step and step.questions:
                pre_cmd_qs = [q for q in step.questions if q.after_command == -1]
                if pre_cmd_qs:
                    session.pending_questions = list(pre_cmd_qs[1:])  # queue remainder
                    session.question_phase = True
                    return _render_question_panel(session, pre_cmd_qs[0])
            return _render_command_phase_panel(session)

    # ---- Phase 2: command / Q&A phase ----
    # Block advance when commands are unrun.  'next' only warns — the student
    # must type 'skip' to explicitly skip remaining commands.
    step = session.current_step
    if step and step.commands and session.current_command_index < len(step.commands):
        remaining = len(step.commands) - session.current_command_index
        cmd_panel = _render_command_phase_panel(session)
        return Panel(
            cmd_panel.renderable,
            title=(
                f"[bold yellow]⚠  {remaining} command(s) still to run — "
                f"type [bold white]run[/bold white] to execute them, "
                f"or [bold white]skip[/bold white] to skip this step's remaining commands[/bold yellow]"
            ),
            border_style="yellow",
            padding=(1, 2),
        )

    # Block advance when the step has unacknowledged user_confirms tasks.
    if step:
        uc_checks = [c for c in step.success if c.kind == "user_confirms"]
        if uc_checks and not session.user_confirms_acknowledged:
            task_list = "\n".join(
                f"  [yellow]\u2022[/yellow] {c.pattern or 'Complete the manual task above'}"
                for c in uc_checks
            )
            body = (
                "[bold yellow]Confirm manual tasks before continuing.[/bold yellow]\n\n"
                + task_list
                + "\n\n"
                "[dim]Once done, type [bold white]confirm[/bold white] to acknowledge, "
                "then [bold white]next[/bold white] to continue.[/dim]"
            )
            return Panel(
                Text.from_markup(body),
                title="[bold yellow]\u26a0  Manual Tasks Required[/bold yellow]",
                border_style="yellow",
                padding=(1, 2),
            )

    # All commands done (or step has none) — advance
    if session.is_complete:
        return session_end_panel()
    advanced = session.advance()
    if not advanced:
        return session_end_panel()

    step = session.current_step
    if step is None:
        return session_end_panel()

    # Load content for the new step and display first chunk / index
    _load_step_chunks(session)
    if session.step_chunks:
        if session.chunk_mode == "index":
            return _render_index_panel(session)
        return _render_chunk_panel(session)

    # No content chunks — fall straight to command phase
    session.in_content_phase = False
    return _render_command_phase_panel(session)


def _handle_skip(session: TeachSession) -> Panel:
    """Skip all remaining commands of the current step and advance to the next.

    Used when a student explicitly wants to move on without running every
    step command.  Marks all unrun commands as skipped (by advancing the
    cursor to the end) and then advances to the next step.
    """
    step = session.current_step
    if step and step.commands:
        skipped = len(step.commands) - session.current_command_index
        session.current_command_index = len(step.commands)  # mark all done
    else:
        skipped = 0

    if session.is_complete:
        return session_end_panel()
    advanced = session.advance()
    if not advanced:
        return session_end_panel()

    step = session.current_step
    if step is None:
        return session_end_panel()

    _load_step_chunks(session)
    skip_note = (
        f"[yellow]\u26a0  {skipped} command(s) were skipped.[/yellow]  "
        "You can return to them with [bold white]back[/bold white].\n\n"
        if skipped else ""
    )
    if session.step_chunks:
        if session.chunk_mode == "index":
            _inner = _render_index_panel(session)
        else:
            _inner = _render_chunk_panel(session)
        if skip_note:
            from rich.console import Group as _G  # noqa: PLC0415
            return _G(
                Panel(
                    Text.from_markup(skip_note.rstrip()),
                    border_style="yellow",
                    padding=(0, 2),
                ),
                _inner,
            )
        return _inner

    session.in_content_phase = False
    return _render_command_phase_panel(session)


def _handle_back(session: TeachSession) -> Panel:
    """Go back through content chunks or to the previous step."""
    # ---- Phase 1: in content phase — go back a chunk ----
    if session.in_content_phase and session.step_chunks:
        if session.current_chunk_index > 0:
            session.current_chunk_index -= 1
            return _render_chunk_panel(session)
        # At first chunk — fall through to go back one step

    # ---- Phase 2: in command phase — return to last content chunk ----
    if not session.in_content_phase and session.step_chunks:
        session.in_content_phase = True
        session.current_chunk_index = len(session.step_chunks) - 1
        return _render_chunk_panel(session)

    # ---- Go back to the previous step ----
    if not session.go_back():
        return _make_panel("Already at the first step.", style="yellow")

    step = session.current_step
    assert step is not None
    _load_step_chunks(session)
    if session.step_chunks:
        # Jump to last chunk of previous step (already seen)
        session.current_chunk_index = len(session.step_chunks) - 1
        return _render_chunk_panel(session)

    body = (
        f"[bold yellow]Step {session.current_step_index + 1} / {session.total_steps}:[/bold yellow] "
        f"{step.title}\n"
        f"[cyan]Goal:[/cyan] {step.goal}"
    )
    return Panel(
        Text.from_markup(body),
        title="[bold cyan]Previous Step[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )


def _handle_hint(session: TeachSession) -> Panel:
    """Show the next hint for the current step."""
    step = session.current_step
    if step is None:
        return _make_panel("No active step.", style="yellow")
    if not step.hints:
        return _make_panel("No hints available for this step.", style="yellow")

    lines = [f"Hint {i + 1}: {h}" for i, h in enumerate(step.hints)]
    return _make_panel("\n".join(lines), title="[bold yellow]Hints[/bold yellow]")


def _handle_status(session: TeachSession) -> Panel:
    """Show current session progress including content-reading position."""
    step = session.current_step
    step_info = step.title if step else "(complete)"
    passed = session.checks_passed

    # Chunk position line
    if session.step_chunks:
        phase = "reading" if session.in_content_phase else "commands"
        chunk_line = (
            f"Content: chunk {session.current_chunk_index + 1} / {len(session.step_chunks)}"
            f"  [{phase} phase]\n"
        )
    else:
        chunk_line = ""

    body = (
        f"Pack: {session.pack.name}\n"
        f"Progress: {session.current_step_index + 1} / {session.total_steps}\n"
        f"Current step: {step_info}\n"
        f"{chunk_line}"
        f"Steps with checks passed: {len(passed)}\n"
    )
    return _make_panel(body, title="[bold cyan]Session Status[/bold cyan]")


def _handle_agents(session: TeachSession, verbose: bool) -> Panel:
    """Execute agent_invocations for the current step."""
    from saxoflow.teach.agent_dispatcher import dispatch_step_agents  # noqa: PLC0415

    results = dispatch_step_agents(session, verbose=verbose)
    if not results:
        return _make_panel(
            "No agent invocations declared for this step.", style="yellow"
        )
    joined = "\n\n---\n\n".join(results)
    return Panel(
        Text(joined),
        title="[bold magenta]Agent Results[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    )


def _handle_quit() -> Panel:
    """Return a quit acknowledgement panel (app.py handles actual state teardown)."""
    return _make_panel(
        "Exiting tutor mode. Your progress has been saved.",
        title="[bold yellow]Tutor Quit[/bold yellow]",
        style="yellow",
    )


def _handle_confirm(session: TeachSession) -> Panel:
    """Acknowledge user_confirms tasks for the current step.

    Sets ``session.user_confirms_acknowledged = True``, which unblocks the
    ``next`` command when the step has manual verification requirements.
    """
    step = session.current_step
    if step is None:
        return _make_panel("No active step.", style="yellow")

    uc_checks = [c for c in step.success if c.kind == "user_confirms"]
    if not uc_checks:
        return _make_panel(
            "No manual verification tasks for this step.\n"
            "Type [bold]next[/bold] to continue.",
            style="yellow",
        )

    if session.user_confirms_acknowledged:
        return _make_panel(
            "[green]\u2713 Manual tasks already confirmed.[/green]\n"
            "Type [bold]next[/bold] to advance to the next step.",
            style="green",
        )

    session.user_confirms_acknowledged = True
    session.save_progress()

    task_lines = "\n".join(
        f"  [green]\u2713[/green] {c.pattern or 'Manual verification task'}"
        for c in uc_checks
    )
    body = (
        "[bold green]Manual tasks acknowledged![/bold green]\n\n"
        + task_lines
        + "\n\n"
        "[dim]Well done \u2014 type [bold white]next[/bold white] to advance to the next step.[/dim]"
    )
    return Panel(
        Text.from_markup(body),
        title="[bold green]\u2713 Tasks Confirmed[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


def _handle_tutor_query(
    user_input: str,
    session: TeachSession,
    llm,
    verbose: bool,
) -> Panel:
    """Ask the TutorAgent with the current chunk injected for tight-scope Q&A."""
    try:
        from saxoflow_agenticai.agents.tutor_agent import TutorAgent  # noqa: PLC0415
    except ImportError as exc:
        return _make_panel(f"TutorAgent not available: {exc}", style="red")

    # Inject the currently displayed chunk so questions about what is on screen
    # are answered from that content first; BM25 retrieval adds broader context.

    # Always prepend recent manual terminal activity so the tutor sees what
    # the student ran (cat file.sv, ll, etc.) without needing to be told.
    _terminal_ctx = ""
    if session.terminal_log:
        _entries = "\n\n".join(session.terminal_log[-3:])
        _terminal_ctx = f"[Recent terminal commands the student ran]:\n{_entries}\n\n"

    if session.question_phase and session.current_question is not None:
        # Student is in the reflection question phase — tell the tutor the
        # active question so it can evaluate or discuss the student's answer.
        q_text = session.current_question.text
        enriched_input = (
            f"[Active reflection question]: {q_text}\n\n"
            f"Student response / follow-up: {user_input}"
        )
    elif session.in_content_phase and session.step_chunks:
        chunk = session.step_chunks[session.current_chunk_index]
        enriched_input = (
            f"[Currently reading: {chunk.source_doc}, p.{chunk.page_num}]\n"
            f"{chunk.text[:400]}\n\n"
            f"Student question: {user_input}"
        )
    else:
        enriched_input = user_input

    # Prefix terminal context into every branch if available
    if _terminal_ctx:
        enriched_input = _terminal_ctx + enriched_input

    try:
        agent = TutorAgent(llm=llm, verbose=verbose)
        reply = agent.run(session=session, student_input=enriched_input)
    except RuntimeError as exc:
        return _make_panel(
            f"LLM not configured — set your API key.\nDetails: {exc}",
            style="red",
        )
    except Exception as exc:  # pragma: no cover
        logger.exception("TutorAgent error: %s", exc)
        return _make_panel(f"Tutor error: {exc}", style="red")

    return Panel(
        Text(reply),
        title="[bold blue]SaxoFlow Tutor[/bold blue]",
        border_style="blue",
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Content display helpers
# ---------------------------------------------------------------------------


def prepare_step_for_display(session: TeachSession):
    """Load content chunks for the current step and return the first display panel.

    Called once when a step is entered (startup, advance, or go-back).
    Populates ``session.step_chunks`` from the indexed documents and returns
    either a content chunk panel, a topic index panel, or a command-phase
    panel if no docs were indexed for this step.  Always includes the
    persistent navigation panel below the content.
    """
    _load_step_chunks(session)
    if not session.step_chunks:
        session.in_content_phase = False
        _inner = _render_command_phase_panel(session)
    elif session.chunk_mode == "index":
        _inner = _render_index_panel(session)
    else:
        _inner = _render_chunk_panel(session)
    return _RichGroup(_inner, _render_nav_panel(session))


def _load_step_chunks(session: TeachSession) -> None:
    """Populate ``session.step_chunks`` from the indexed pack documents.

    Only ``role: tutorial`` documents are shown chunk-by-chunk.
    ``role: reference`` documents stay in the BM25 index for Q&A only.

    For each ``read:`` entry the ``section:`` field is matched against the
    ``section_hint`` stored in each indexed chunk.  The hint comes directly
    from the nearest heading above the chunk in the source document, so it
    must equal one of the comma-separated section names in ``section:``.

    Matching is case-insensitive substring: a chunk is kept when its
    ``section_hint`` contains any token from ``section:`` that is longer than
    3 characters.  If the ``section:`` filter produces no matches (e.g. the
    heading names in the YAML differ from those in the PDF), ALL chunks from
    the document are returned so the step is never empty.

    Falls back to a BM25 query on the step title/goal if ``read:`` is empty.
    """
    from saxoflow.teach.retrieval import get_index  # noqa: PLC0415

    session.reset_chunk_state()
    step = session.current_step
    if step is None:
        return

    # Build set of tutorial-role filenames from pack metadata.
    tutorial_docs: set[str] = {
        d.get("filename", "")
        for d in (session.pack.docs or [])
        if d.get("role", "tutorial") == "tutorial"
    }

    idx = get_index(session)

    # Sentinel values that mean "show the whole document".
    _ALL_SECTIONS = {"all sections", "all", ""}

    chunks: list = []
    seen_keys: set = set()

    def _add(new_chunks):
        for c in new_chunks:
            key = (c.source_doc, c.chunk_index)
            if key not in seen_keys:
                seen_keys.add(key)
                chunks.append(c)

    read_entries = [
        r for r in (step.read or [])
        if r.get("doc") and r.get("doc") in tutorial_docs
    ]

    if read_entries:
        for entry in read_entries:
            doc_name = entry["doc"]
            section  = entry.get("section", "").strip()

            doc_chunks = idx.get_chunks_for_docs([doc_name])

            if section.lower() in _ALL_SECTIONS:
                _add(doc_chunks[:20])
            else:
                # Parse each comma-separated item as a distinct section name.
                # "File-Based Testbenches, Stimuli Application, Student Task 4"
                # → ["File-Based Testbenches", "Stimuli Application", "Student Task 4"]
                # A chunk is included when its section_hint is an exact
                # (case-insensitive) match for one of these names.  This
                # prevents "Student Task 4" from also matching Task 5, 7, 8…
                target_sections = [
                    s.strip().lower()
                    for s in section.split(",")
                    if s.strip()
                ]

                matched = [
                    c for c in doc_chunks
                    if c.section_hint.lower() in target_sections
                ]

                if matched:
                    _add(matched[:4])  # cap at 4 matched chunks per section
                else:
                    # Graceful fallback: section names in YAML don't match any
                    # heading in the PDF.  Show nothing — the step will skip
                    # the content reading phase and jump straight to the
                    # command phase, which displays the goal explicitly.
                    # Students can still ask the tutor questions to retrieve
                    # relevant context via BM25.
                    logger.warning(
                        "No section_hint matches for section=%r in '%s' — "
                        "skipping content phase for this section entry. "
                        "Update the 'section:' value to match a PDF heading "
                        "(check section_hint values via 'saxoflow teach index').",
                        section, doc_name,
                    )
    else:
        # No explicit tutorial read refs — BM25 fallback restricted to tutorial docs.
        # Cap at 5 chunks to avoid overwhelming the student; BM25 retrieval
        # remains available in full for Q&A via the TutorAgent.
        query = f"{step.title} {step.goal}"
        candidates = idx.retrieve(query, top_k=10)
        _add(c for c in candidates if c.source_doc in tutorial_docs)
        chunks = chunks[:5]

    session.step_chunks = _merge_chunks_by_section(chunks)
    logger.debug(
        "Loaded %d chunks for step '%s' (tutorial docs: %s)",
        len(chunks), step.id,
        [r.get("doc") for r in read_entries] or "[bm25 fallback — tutorial only]",
    )


def _render_chunk_panel(session: TeachSession):
    """Render the currently active content chunk as a Rich panel.

    If the source PDF page contains images, they are rendered below the text
    panel using ``chafa`` (Unicode art) when available, or a dim placeholder
    when it is not.  All image rendering errors are silenced gracefully.
    """
    chunks = session.step_chunks
    idx = session.current_chunk_index
    step = session.current_step
    step_label = step.title if step else ""

    if not chunks or idx >= len(chunks):
        return _make_panel("No content to display.", style="yellow")

    chunk = chunks[idx]
    total = len(chunks)
    progress = f"[{idx + 1}/{total}]"

    # Source citation
    page_note = f"p.{chunk.page_num}" if chunk.page_num > 0 else "markdown"
    if chunk.section_hint:
        citation = f"[dim]\u2514 {chunk.source_doc}  {page_note}  \u00bb {chunk.section_hint}[/dim]"
    else:
        citation = f"[dim]\u2514 {chunk.source_doc}  {page_note}[/dim]"

    # Paragraph-aware formatting — improves readability vs a single wrapped block
    formatted = _format_chunk_for_display(chunk.text, width=88)
    body = f"{formatted}\n\n{citation}"

    # Surface the section heading prominently in the panel title
    section_part = f" \u2014 {chunk.section_hint}" if chunk.section_hint else ""
    text_panel = Panel(
        Text.from_markup(body),
        title=f"[bold green]Content {progress}{section_part} \u2014 {step_label}[/bold green]",
        border_style="green",
        padding=(1, 2),
    )

    # ---- Inline image rendering ----------------------------------------
    # Fetch images for this page from the index (PDF only; markdown pages
    # have page_num == -1 so get_images_for_page returns [] cleanly).
    image_panels = []
    if chunk.page_num > 0:
        try:
            from saxoflow.teach.retrieval import get_index  # noqa: PLC0415
            doc_idx = get_index(session)
            page_images = doc_idx.get_images_for_page(chunk.source_doc, chunk.page_num)
            for fig_num, img_chunk in enumerate(page_images, start=1):
                try:
                    art = render_image_from_bytes(
                        img_chunk.image_bytes,
                        image_ext=img_chunk.image_ext,
                        fig_num=fig_num,
                    )
                    image_panels.append(
                        Panel(
                            Text.from_ansi(art),
                            title=f"[dim]Figure {fig_num} — {chunk.source_doc} p.{chunk.page_num}[/dim]",
                            border_style="dim",
                            padding=(0, 1),
                        )
                    )
                except Exception as ie:
                    logger.debug("Image render failed fig %d: %s", fig_num, ie)
        except Exception as exc:
            logger.debug("Could not fetch images for chunk: %s", exc)

    if image_panels:
        return _RichGroup(text_panel, *image_panels)
    return text_panel


def _render_index_panel(session: TeachSession) -> Panel:
    """Render a numbered topic index for the current step (lecture mode)."""
    chunks = session.step_chunks
    step = session.current_step
    step_label = step.title if step else ""

    if not chunks:
        return _make_panel("No content indexed for this step.", style="yellow")

    lines = []
    seen: set = set()
    display_idx = 1
    for chunk in chunks:
        heading = chunk.section_hint or chunk.text[:60].replace("\n", " ") + "…"
        key = heading[:80]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"  [bold]{display_idx}.[/bold] {heading}")
        display_idx += 1

    nav = "\n[dim]Type a number to read that section  ·  'next' to read sequentially[/dim]"
    body = "\n".join(lines) + nav
    return Panel(
        Text.from_markup(body),
        title=f"[bold green]Topics — {step_label}[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


def _render_question_panel(session: "TeachSession", q: "QuestionDef") -> Panel:
    """Render a reflection question panel between content and command phases."""
    from saxoflow.teach.session import QuestionDef  # noqa: PLC0415 (local to avoid circular)

    # Persist so _handle_tutor_query can inject it as context when the student
    # types a response or follow-up while in question phase.
    session.current_question = q

    remaining = len(session.pending_questions)
    more_note = f"  [dim]({remaining} more question{'s' if remaining != 1 else ''} after this)[/dim]" if remaining else ""
    body = (
        f"[bold yellow]Reflection Question[/bold yellow]\n\n"
        f"{q.text}\n\n"
        f"[dim]Think it through, then type [bold]next[/bold] to continue "
        f"— or ask the tutor anything.[/dim]{more_note}"
    )
    step = session.current_step
    step_label = step.title if step else ""
    return Panel(
        Text.from_markup(body),
        title=f"[bold yellow]\u2753 Question — {step_label}[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def _render_command_phase_panel(session: TeachSession) -> Panel:
    """Show the CURRENT command to run, with goal and progress context."""
    step = session.current_step
    if step is None:
        return _make_panel("No active step.", style="yellow")

    commands = step.commands

    if not commands:
        import textwrap as _tw  # noqa: PLC0415
        goal_str = ("\n         ").join(_tw.wrap(step.goal, width=86))
        lines = [
            f"[cyan]Goal:[/cyan]   {goal_str}\n",
            "[dim]No commands for this step.  Type [bold white]next[/bold white] to continue.[/dim]",
        ]
        return Panel(
            Text.from_markup("\n".join(lines)),
            title=f"[bold yellow]Step \u2014 {step.title}[/bold yellow]",
            border_style="yellow",
            padding=(1, 2),
        )

    cmd_idx = session.current_command_index
    total_cmds = len(commands)

    # All commands executed for this step
    if cmd_idx >= total_cmds:
        import textwrap as _tw  # noqa: PLC0415
        goal_str = ("\n         ").join(_tw.wrap(step.goal, width=86))
        uc_checks = [c for c in step.success if c.kind == "user_confirms"]
        if uc_checks and not session.user_confirms_acknowledged:
            task_items = "\n".join(
                f"  [yellow]\u2022 {c.pattern or 'Complete the manual task above'}[/yellow]"
                for c in uc_checks
            )
            lines = [
                f"[cyan]Goal:[/cyan]   {goal_str}\n",
                "[green]\u2713 All commands for this step have been executed.[/green]\n",
                "[bold yellow]Manual verification required:[/bold yellow]",
                task_items,
                "",
                "[dim]Type [bold white]confirm[/bold white] when done, "
                "then [bold white]next[/bold white] to continue.[/dim]",
            ]
        else:
            lines = [
                f"[cyan]Goal:[/cyan]   {goal_str}\n",
                "[green]\u2713 All commands for this step have been executed.[/green]",
                "[dim]Type [bold white]next[/bold white] to advance  \u00b7  or ask the tutor a question.[/dim]",
            ]
        return Panel(
            Text.from_markup("\n".join(lines)),
            title=f"[bold green]Done \u2014 {step.title}[/bold green]",
            border_style="green",
            padding=(1, 2),
        )

    current_cmd = commands[cmd_idx]

    import textwrap as _tw  # noqa: PLC0415
    goal_lines = _tw.wrap(step.goal, width=86)
    goal_str = ("\n         ").join(goal_lines)
    lines = [
        f"[cyan]Goal:[/cyan]   {goal_str}\n",
        f"[dim]Command {cmd_idx + 1} of {total_cmds}[/dim]",
        f"\n  [bold yellow]{current_cmd.native}[/bold yellow]\n",
    ]

    # Visual checklist of all commands so the student sees the full roadmap
    if total_cmds > 1:
        for i, cmd in enumerate(commands):
            if i < cmd_idx:
                lines.append(f"  [dim green]\u2713 {cmd.native}[/dim green]")
            elif i == cmd_idx:
                lines.append(f"  [bold white]\u25b6 {cmd.native}[/bold white]  [dim]\u2190 run this[/dim]")
            else:
                lines.append(f"  [dim]  {cmd.native}[/dim]")
        lines.append("")

    lines.append("[dim]Type [bold white]run[/bold white] to automate  \u00b7  or type the command yourself to practice  \u00b7  [bold white]skip[/bold white] to skip remaining commands[/dim]")
    lines.append("[dim]Note: command paths are relative to your current directory \u2014 run [bold white]pwd[/bold white] to check where you are[/dim]")

    return Panel(
        Text.from_markup("\n".join(lines)),
        title=f"[bold yellow]Command {cmd_idx + 1}/{total_cmds} \u2014 {step.title}[/bold yellow]",
        border_style="yellow",
        padding=(1, 2),
    )


def _handle_index_select(session: TeachSession, number: int) -> Panel:
    """Jump to a specific chunk number from the index panel."""
    chunks = session.step_chunks
    if not chunks:
        return _make_panel("No content loaded.", style="yellow")

    # Build the same unique heading list as _render_index_panel
    seen: list = []
    seen_keys: set = set()
    for chunk in chunks:
        heading = chunk.section_hint or chunk.text[:60]
        key = heading[:80]
        if key not in seen_keys:
            seen.append(chunk)
            seen_keys.add(key)

    if number < 1 or number > len(seen):
        return _make_panel(
            f"Please type a number between 1 and {len(seen)}.",
            style="yellow",
        )

    target_chunk = seen[number - 1]
    # Find this chunk's index in the full list
    try:
        session.current_chunk_index = chunks.index(target_chunk)
    except ValueError:
        session.current_chunk_index = 0
    session.in_content_phase = True
    session.chunk_mode = "sequential"  # switch to sequential after selection
    return _render_chunk_panel(session)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# New display helpers: section merging, paragraph formatting, nav panel
# ---------------------------------------------------------------------------

# Sentinel used as an initial "no section seen yet" marker in _merge_chunks_by_section
_MERGE_SENTINEL = object()


def _merge_chunks_by_section(chunks: list) -> list:
    """Merge consecutive BM25 chunks with the same section_hint into one display chunk.

    Students see one panel per document section (heading) rather than one per
    BM25 chunk.  This means pressing 'next' advances by section, giving a
    reading experience that mirrors the structure of the original PDF.
    """
    from saxoflow.teach.indexer import Chunk  # noqa: PLC0415

    if not chunks:
        return chunks

    grouped: list = []
    current_hint = _MERGE_SENTINEL
    buf_texts: list = []
    buf_base = None

    for chunk in chunks:
        hint = chunk.section_hint
        if hint != current_hint:
            if buf_base is not None:
                grouped.append(Chunk(
                    text="\n\n".join(buf_texts),
                    source_doc=buf_base.source_doc,
                    page_num=buf_base.page_num,
                    section_hint="" if current_hint is _MERGE_SENTINEL else current_hint,
                    chunk_index=buf_base.chunk_index,
                ))
            buf_texts = [chunk.text]
            buf_base = chunk
            current_hint = hint
        else:
            buf_texts.append(chunk.text)

    if buf_base is not None:
        grouped.append(Chunk(
            text="\n\n".join(buf_texts),
            source_doc=buf_base.source_doc,
            page_num=buf_base.page_num,
            section_hint="" if current_hint is _MERGE_SENTINEL else current_hint,
            chunk_index=buf_base.chunk_index,
        ))
    return grouped


def _format_chunk_for_display(text: str, width: int = 88) -> str:
    """Format PDF chunk text with paragraph-aware line wrapping.

    PDF extraction collapses paragraphs into long single-line strings.
    This heuristic re-introduces visual paragraph breaks every ~80 words
    at sentence boundaries so content is readable in the terminal.
    """
    import re as _re  # noqa: PLC0415
    import textwrap as _tw  # noqa: PLC0415

    raw_paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not raw_paras:
        raw_paras = [text.strip()]

    result_blocks: list = []
    for para in raw_paras:
        words = para.split()
        if len(words) <= 80:
            result_blocks.append(
                _tw.fill(para, width=width, break_long_words=False, break_on_hyphens=False)
            )
        else:
            # Long paragraph: split at sentence ends every ~80 words
            sentences = _re.split(r"(?<=[.!?:]) +", para)
            sub_words: list = []
            sub_paras: list = []
            for sent in sentences:
                sub_words.extend(sent.split())
                if len(sub_words) >= 80:
                    sub_paras.append(" ".join(sub_words))
                    sub_words = []
            if sub_words:
                sub_paras.append(" ".join(sub_words))
            for sp in sub_paras:
                result_blocks.append(
                    _tw.fill(sp, width=width, break_long_words=False, break_on_hyphens=False)
                )
    return "\n\n".join(result_blocks)


def _render_nav_panel(session: TeachSession) -> Panel:
    """Persistent 'Available Options' panel shown below every teach-mode response.

    Intelligently shows only the commands that make sense for the current phase:
    - In content-reading phase: next/back/hint; 'run' only on the last chunk
    - In command phase: run (when cmds remain), next, back, hint, status
    """
    step = session.current_step
    lines = ["[bold cyan]Available Options[/bold cyan]", ""]

    if session.in_content_phase:
        chunks = session.step_chunks
        idx = session.current_chunk_index
        total = len(chunks)
        is_last = idx >= total - 1

        if not is_last:
            lines.append("  [bold white]next[/bold white]   \u2192 Continue to the next section")
        elif step and step.commands:
            lines.append("  [bold white]next[/bold white]   \u2192 Finished reading \u2014 move on to the commands")
        else:
            lines.append("  [bold white]next[/bold white]   \u2192 Advance to the next step")

        if idx > 0:
            lines.append("  [bold white]back[/bold white]   \u2192 Go back to the previous section")
        else:
            lines.append("  [bold white]back[/bold white]   \u2192 Return to the previous step")

        # Only surface 'run' once the student has reached the last chunk
        if is_last and step and step.commands:
            lines.append("  [bold white]run[/bold white]    \u2192 Execute the next step command")

        lines.append("  [bold white]hint[/bold white]   \u2192 Show hints and tips for this step")
        lines.append("  [bold white]status[/bold white] \u2192 Show your current progress")
    else:
        # Command phase
        cmd_idx = session.current_command_index
        total_cmds = len(step.commands) if step and step.commands else 0
        has_remaining = cmd_idx < total_cmds
        if has_remaining:
            next_cmd = step.commands[cmd_idx].native if step and step.commands else ""
            lines.append(f"  [bold white]run[/bold white]    \u2192 Automate: execute [dim]{next_cmd}[/dim]")
            lines.append(f"  [dim]           (or type the command yourself to practice)[/dim]")
        lines.append("  [bold white]next[/bold white]   \u2192 Advance to the next step" + (" [dim](run commands first)[/dim]" if has_remaining else ""))
        if has_remaining:
            lines.append("  [bold white]skip[/bold white]   \u2192 Skip remaining commands and move to next step")
        lines.append("  [bold white]back[/bold white]   \u2192 Return to content review")
        lines.append("  [bold white]hint[/bold white]   \u2192 Show hints for this step")
        lines.append("  [bold white]status[/bold white] \u2192 Show your current progress")
        # Show 'confirm' when user_confirms tasks await acknowledgment
        if not has_remaining and step and step.success:
            uc = [c for c in step.success if c.kind == "user_confirms"]
            if uc and not session.user_confirms_acknowledged:
                lines.append("  [bold white]confirm[/bold white] \u2192 Acknowledge manual tasks to unlock [bold white]next[/bold white]")

    lines.append("")
    lines.append("  [dim]or type a question in plain English to ask the tutor[/dim]")
    return Panel(
        Text.from_markup("\n".join(lines)),
        title="[bold cyan]Available Options[/bold cyan]",
        border_style="cyan",
        padding=(1, 1),
    )


def record_manual_command(user_input: str, session: TeachSession) -> Optional[Panel]:
    """Check if *user_input* matches the current pending step command.

    Called by ``app.py`` after a unix command executes in teach mode so that
    manually typed step commands advance the command cursor exactly like ``run``.
    Returns the updated command panel (with nav panel) when the input matches
    the next pending command; returns ``None`` otherwise.
    """
    if session.in_content_phase:
        return None
    step = session.current_step
    if step is None or not step.commands:
        return None
    cmd_idx = session.current_command_index
    if cmd_idx >= len(step.commands):
        return None

    expected = " ".join(step.commands[cmd_idx].native.split()).lower()
    typed = " ".join(user_input.strip().split()).lower()
    if typed != expected:
        return None

    # Match — advance the cursor and persist
    session.current_command_index += 1
    session.save_progress()
    _inner = _render_command_phase_panel(session)
    return _RichGroup(_inner, _render_nav_panel(session))


def _make_panel(
    body: str,
    *,
    title: str = "[bold]SaxoFlow Tutor[/bold]",
    style: str = "blue",
) -> Panel:
    return Panel(
        Text.from_markup(body) if "[" in body else Text(body),
        title=title,
        border_style=style,
        padding=(1, 2),
    )
