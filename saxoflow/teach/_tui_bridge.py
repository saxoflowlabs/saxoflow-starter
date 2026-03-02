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

from rich.panel import Panel
from rich.text import Text

from saxoflow.teach.session import TeachSession

__all__ = ["handle_input", "start_session_panel", "session_end_panel", "prepare_step_for_display"]

logger = logging.getLogger("saxoflow.teach.tui_bridge")

# ---------------------------------------------------------------------------
# Teach-mode special commands (exact match after `.strip().lower()`)
# ---------------------------------------------------------------------------

_CMD_RUN = "run"
_CMD_NEXT = "next"
_CMD_BACK = "back"
_CMD_HINT = "hint"
_CMD_STATUS = "status"
_CMD_AGENTS = "agents"
_CMD_QUIT = "quit"

_TEACH_COMMANDS = {_CMD_RUN, _CMD_NEXT, _CMD_BACK, _CMD_HINT,
                   _CMD_STATUS, _CMD_AGENTS, _CMD_QUIT}


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

    if cmd == _CMD_RUN:
        return _handle_run(session, Path(project_root), verbose)

    if cmd == _CMD_NEXT:
        return _handle_next(session, llm, verbose)

    if cmd == _CMD_BACK:
        return _handle_back(session)

    if cmd == _CMD_HINT:
        return _handle_hint(session)

    if cmd == _CMD_STATUS:
        return _handle_status(session)

    if cmd == _CMD_AGENTS:
        return _handle_agents(session, verbose)

    if cmd == _CMD_QUIT:
        return _handle_quit()

    # In index mode a bare digit selects a content chunk by number
    if session.in_content_phase and session.chunk_mode == "index" and cmd.strip().isdigit():
        return _handle_index_select(session, int(cmd.strip()))

    # Default: ask the TutorAgent (with current chunk injected for context)
    return _handle_tutor_query(user_input, session, llm, verbose)


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
    """Execute the current step's declared commands."""
    from saxoflow.teach.runner import run_step_commands   # noqa: PLC0415
    from saxoflow.teach.checks import evaluate_step_success  # noqa: PLC0415

    results = run_step_commands(session, project_root)
    if not results:
        return _make_panel("No commands declared for this step.", style="yellow")

    lines = []
    for r in results:
        lines.append(f"$ {r.command_str}")
        lines.append(r.stdout if r.stdout else "(no output)")
        if r.exit_code != 0:
            lines.append(f"[red]Exit code: {r.exit_code}[/red]")
        lines.append("")

    # Check success
    passed = evaluate_step_success(session, project_root)
    if passed:
        step = session.current_step
        if step:
            session.mark_check_passed(step.id)
        lines.append("[green]✓ Step checks passed. Type: next  to continue.[/green]")
    else:
        lines.append("[yellow]Step checks not yet met. Review the output above.[/yellow]")

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
            # All chunks read — move to command phase
            session.in_content_phase = False
            return _render_command_phase_panel(session)

    # ---- Phase 2: command / Q&A phase — advance to next step ----
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
    if session.in_content_phase and session.step_chunks:
        chunk = session.step_chunks[session.current_chunk_index]
        enriched_input = (
            f"[Currently reading: {chunk.source_doc}, p.{chunk.page_num}]\n"
            f"{chunk.text[:400]}\n\n"
            f"Student question: {user_input}"
        )
    else:
        enriched_input = user_input

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


def prepare_step_for_display(session: TeachSession) -> Panel:
    """Load content chunks for the current step and return the first display panel.

    Called once when a step is entered (startup, advance, or go-back).
    Populates ``session.step_chunks`` from the indexed documents and returns
    either a content chunk panel, a topic index panel, or a command-phase
    panel if no docs were indexed for this step.
    """
    _load_step_chunks(session)
    if not session.step_chunks:
        session.in_content_phase = False
        return _render_command_phase_panel(session)
    if session.chunk_mode == "index":
        return _render_index_panel(session)
    return _render_chunk_panel(session)


def _load_step_chunks(session: TeachSession) -> None:
    """Populate ``session.step_chunks`` from the indexed pack documents.

    Filters the pre-built BM25 index to only the documents declared in the
    current step's ``read:`` list.  Falls back to a BM25 query over the full
    index if ``read:`` is empty (e.g. step has no explicit doc refs).
    """
    from saxoflow.teach.retrieval import get_index  # noqa: PLC0415

    session.reset_chunk_state()
    step = session.current_step
    if step is None:
        return

    idx = get_index(session)
    doc_names = [r.get("doc", "") for r in (step.read or []) if r.get("doc")]

    if doc_names:
        chunks = idx.get_chunks_for_docs(doc_names)
    else:
        # No explicit read refs — fall back to relevance retrieval
        query = f"{step.title} {step.goal}"
        chunks = idx.retrieve(query, top_k=20)

    session.step_chunks = chunks
    logger.debug(
        "Loaded %d chunks for step '%s' (docs: %s)",
        len(chunks), step.id, doc_names or "[bm25 fallback]",
    )


def _render_chunk_panel(session: TeachSession) -> Panel:
    """Render the currently active content chunk as a Rich panel."""
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
    citation = f"[dim]└ {chunk.source_doc}  {page_note}[/dim]"
    if chunk.section_hint:
        citation = f"[dim]└ {chunk.source_doc}  {page_note}  » {chunk.section_hint}[/dim]"

    # Navigation footer
    if idx < total - 1:
        nav = "\n[dim]\u25b8 next to continue reading  ·  or ask any question[/dim]"
    else:
        has_cmds = bool(step and step.commands)
        next_hint = "next to see commands" if has_cmds else "next for next lesson"
        nav = f"\n[dim]\u25b8 {next_hint}  ·  or ask any question[/dim]"

    body = f"{chunk.text}\n\n{citation}{nav}"
    return Panel(
        Text.from_markup(body),
        title=f"[bold green]Content {progress} — {step_label}[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


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


def _render_command_phase_panel(session: TeachSession) -> Panel:
    """Show all declared commands for the current step."""
    step = session.current_step
    if step is None:
        return _make_panel("No active step.", style="yellow")

    lines = []
    if step.commands:
        lines.append("[bold cyan]Commands for this step:[/bold cyan]\n")
        for i, cmd in enumerate(step.commands, 1):
            lines.append(f"  [bold]{i}.[/bold] [yellow]{cmd.native}[/yellow]")
        lines.append("")
        lines.append("[dim]Type 'run' to execute  ·  'next' to skip to next lesson  ·  or ask a question[/dim]")
    else:
        lines.append("[dim]No commands for this step.  Type 'next' to continue.[/dim]")

    return Panel(
        Text.from_markup("\n".join(lines)),
        title=f"[bold yellow]Commands — {step.title}[/bold yellow]",
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
