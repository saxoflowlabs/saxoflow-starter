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

__all__ = ["handle_input", "start_session_panel", "session_end_panel"]

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
        return _handle_next(session)

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

    # Default: ask the TutorAgent
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


def _handle_next(session: TeachSession) -> Panel:
    """Advance to the next step."""
    if session.is_complete:
        return session_end_panel()
    advanced = session.advance()
    if not advanced:
        return session_end_panel()

    step = session.current_step
    if step is None:
        return session_end_panel()

    body = (
        f"[bold yellow]Step {session.current_step_index + 1} / {session.total_steps}:[/bold yellow] "
        f"{step.title}\n"
        f"[cyan]Goal:[/cyan] {step.goal}"
    )
    if step.hints:
        body += f"\n\n[dim]Hint: {step.hints[0]}[/dim]"
    return Panel(
        Text.from_markup(body),
        title="[bold green]Next Step[/bold green]",
        border_style="green",
        padding=(1, 2),
    )


def _handle_back(session: TeachSession) -> Panel:
    """Go back one step."""
    if not session.go_back():
        return _make_panel("Already at the first step.", style="yellow")

    step = session.current_step
    assert step is not None
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
    """Show current session progress."""
    step = session.current_step
    step_info = f"{step.title}" if step else "(complete)"
    passed = session.checks_passed
    body = (
        f"Pack: {session.pack.name}\n"
        f"Progress: {session.current_step_index + 1} / {session.total_steps}\n"
        f"Current step: {step_info}\n"
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
    """Ask the TutorAgent and return its reply as a panel."""
    try:
        from saxoflow_agenticai.agents.tutor_agent import TutorAgent  # noqa: PLC0415
    except ImportError as exc:
        return _make_panel(f"TutorAgent not available: {exc}", style="red")

    try:
        agent = TutorAgent(llm=llm, verbose=verbose)
        reply = agent.run(session=session, student_input=user_input)
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
