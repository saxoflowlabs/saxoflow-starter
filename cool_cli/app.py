# cool_cli/app.py
"""
Interactive SaxoFlow CLI application entrypoint.

Responsibilities
----------------
- Render banner and welcome tips.
- Manage an interactive prompt session with fuzzy completion.
- Route user input to:
  1) Built-in commands (help/quit/exit/clear and init-env help variants).
  2) Agentic AI commands (rtlgen/tbgen/fpropgen/report/etc.) via subprocess.
  3) Shell/editor commands (prefixed with "!" or recognized UNIX commands).
  4) AI Buddy (conversational assistant & review/action orchestration).

Behavior-preserving notes
-------------------------
- Input/output text, panel styling, and routing precedence remain unchanged.
- Console history rendering is preserved.
- Subprocess invocation for agentic commands remains the same; now guarded
  with exceptions so the TUI does not crash.
- The `clear` command now also clears the in-memory conversation history and
  skips recording a history entry, so the banner/welcome view returns on the
  next loop.

Python 3.9+ compatible.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Mapping, Optional, Union

logger = logging.getLogger("cool_cli.app")

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import InMemoryHistory
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from .banner import print_banner
from .completers import HybridShellCompleter
from .constants import AGENTIC_COMMANDS, CUSTOM_PROMPT_HTML, SHELL_COMMANDS

# Bare saxoflow subcommand names that should be auto-expanded to "saxoflow <cmd>"
# when typed without the "saxoflow" prefix, so they route to the shell instead
# of falling through to the AI Buddy.
_SAXOFLOW_BARE_CMDS: frozenset = frozenset({
    "check-tools", "check_tools",
    "agenticai",
    "diagnose",
    "install",
    "synth",
    "schematic",
    "formal",
    "simulate", "simulate-verilator",
    "wave", "wave-verilator",
    "clean",
    "init-env",
    "unit",
})
from .editors import is_blocking_editor_command
from .panels import agent_panel, ai_panel, output_panel, saxoflow_panel, user_input_panel, welcome_panel
from .shell import is_unix_command, process_command, requires_raw_tty
from .input_router import classify_input
from .state import console, conversation_history
from . import state as _state  # for teach_session read at call time
from .bootstrap import ensure_first_run_setup
from .messages import error as msg_error, warning as msg_warning, info as msg_info
from .ai_buddy import (
    plan_clarification as _plan_clarification,
    detect_incomplete_request as _detect_incomplete_request,
    project_context as _project_context,
    ask_ai_buddy_chat_only as _ask_ai_buddy_chat_only,
)
from .preferences import load_prefs as _load_prefs, prefs_context as _prefs_context
from .agentic import _run_clarification_flow
from .agent_session_log import (
    handle_agentlog_command,
    init_session as init_agent_log_session,
    log_event as log_agent_event,
    record_user_turn,
)
from saxoflow.runtime_paths import resolve_workspace
from saxoflow.services.ai_request_service import AIRequestService, AIRequestServiceError
from saxoflow.services.policy_service import (
    PlanWorkflowPolicy,
    PlanWorkflowPolicyDecision,
    ResearchWorkflowPolicy,
    ResearchWorkflowPolicyDecision,
    RunWorkflowPolicy,
    RunWorkflowPolicyDecision,
    WebResearchRoutingPolicy,
)
from saxoflow.services.web_research_service import WebResearchError, WebResearchService


# =============================================================================
# Utilities
# =============================================================================

def ai_buddy_interactive(user_input, history, skip_clarification=False):
    from .agentic import ai_buddy_interactive as _abi
    return _abi(user_input, history, skip_clarification=skip_clarification)


def _clear_terminal() -> None:
    """Clear the terminal screen (Windows and POSIX)."""
    os.system("cls" if os.name == "nt" else "clear")  # noqa: S605


def _goodbye() -> Text:
    """Return the standard goodbye message as cyan Text."""
    return Text(
        "\nUntil next time, may your timing constraints always be met "
        "and your logic always latch-free.\n",
        style="cyan",
    )


def _build_ai_mode_help(task_type: str) -> Text:
    """Return mode-aware help text for explicit AI routes."""
    normalized_task = (task_type or "").strip().lower()
    ask_allowed_capabilities = (
        "file.read",
        "context.read",
        "artifact.read",
        "report.read",
    )
    plan_allowed_capabilities = PlanWorkflowPolicy(Path.cwd()).allowed_capabilities
    research_allowed_capabilities = ResearchWorkflowPolicy(Path.cwd()).allowed_capabilities
    run_allowed_capabilities = RunWorkflowPolicy(Path.cwd()).allowed_capabilities

    help_specs = {
        "ask": {
            "summary": "Grounded ask (read-only, citation-oriented).",
            "allowed_capabilities": ask_allowed_capabilities,
            "examples": (
                'ask "explain timing assumptions" --context docs/spec.md --tools file.read,report.read',
                'ask "summarize this module" --context source/rtl/top.sv',
            ),
        },
        "plan": {
            "summary": "Structured planning with optional docs-bounded artifact persistence.",
            "allowed_capabilities": plan_allowed_capabilities,
            "examples": (
                'plan "verification milestones" --context docs/spec.md --tools artifact.write',
                'plan "risk register" --context source/rtl --tools file.read,report.read',
            ),
        },
        "research": {
            "summary": "Evidence-synthesis research with optional policy-gated web retrieval.",
            "allowed_capabilities": research_allowed_capabilities,
            "examples": (
                'research "compare open-source PnR flows" --context docs/goals.md --tools web.search,web.fetch',
                'research "summarize constraints" --context docs/spec.md --tools file.read,artifact.write',
            ),
        },
        "run": {
            "summary": "Bounded run mode with approvals, adapter mediation, and resumable execution.",
            "allowed_capabilities": run_allowed_capabilities,
            "examples": (
                'run "prototype tests" --context docs/spec.md --tools file.read,eda.run',
                'run "optimize area" --agent my_ppa_agent --tools file.read,artifact.read,report.read,eda.run',
            ),
        },
    }

    spec = help_specs.get(normalized_task)
    if not spec:
        return msg_warning("Usage: ask|plan|research|run \"<prompt>\"")

    allowed_caps_csv = ", ".join(spec["allowed_capabilities"])
    lines = [
        f"{normalized_task} mode help",
        "",
        f"Summary: {spec['summary']}",
        "",
        "Supported options:",
        "- --context <path> (repeatable)",
        "- --agent <name>",
        "- --tools <cap1,cap2,...>",
        "- --help",
        "",
        f"Allowed capabilities: {allowed_caps_csv}",
        "",
        "Prompt structure examples:",
    ]
    lines.extend(f"- {example}" for example in spec["examples"])
    return Text("\n".join(lines), style="white")


def _is_saxoflow_install(cmd: str) -> bool:
    """Return True when *cmd* is a 'saxoflow install <tool>' invocation."""
    try:
        parts = shlex.split(cmd) if cmd else []
    except ValueError:
        return False
    return len(parts) >= 3 and parts[0] == "saxoflow" and parts[1] == "install"


def _is_saxoflow_output_command(cmd: str) -> bool:
    """Return True when output should use the full-width SaxoFlow panel."""
    if not cmd:
        return False

    normalized = cmd.strip().lower()
    if normalized in {"help", "init-env --help", "init-env help"}:
        return True

    try:
        parts = shlex.split(cmd)
    except ValueError:
        parts = normalized.split()

    if not parts:
        return False

    first = parts[0].lower()
    return first == "saxoflow" or first in _SAXOFLOW_BARE_CMDS


def _show_opening_look(panel_width: int) -> None:
    """Print initial banner and welcome tips."""
    welcome_text = (
        "Welcome to SaxoFlow CLI! Take your first step toward mastering "
        "digital design and verification."
    )
    tips = Text(
        "Tips for getting started:\n"
        "1. Ask questions, generate RTL/testbenches, or run simple commands.\n"
        "2. Try shell commands like 'ls' or design commands like 'rtlgen'.\n"
        "3. Type 'help' to see available commands.\n"
        "4. Type 'quit' or 'exit' to leave the CLI.\n",
        style="yellow",
    )
    print_banner(console)
    console.print(welcome_panel(welcome_text, panel_width=panel_width))
    console.print(tips)
    console.print("")


def _build_completer() -> HybridShellCompleter:
    """Create the fuzzy command/path completer."""
    commands: List[str] = [
        # Built-ins
        "help", "quit", "exit", "simulate", "synth", "schematic", "ai", "clear",
        # Agentic
        "rtlgen", "tbgen", "fpropgen", "report", "rtlreview", "tbreview",
        "fpropreview", "debug", "sim", "fullpipeline",
        # Utilities
        "attach", "save", "load", "export", "stats", "system", "models", "set",
        "agentlog", "agentlog path", "agentlog list", "agentlog show",
        "agentlog mode", "agentlog dir",
        # Teach / tutoring
        "teach", "teach start", "teach list", "teach index", "teach status",
        "teach next", "teach prev", "teach back", "teach run", "teach check",
        "teach ask", "teach invoke-agent", "teach quit",
        # Shell
        "cd", *SHELL_COMMANDS.keys(), "nano", "vim", "vi", "micro", "code", "subl", "gedit",
    ]
    return HybridShellCompleter(commands=commands)


def _render_history(panel_width: int) -> None:
    """Reprint the conversation history as panels."""
    for entry in conversation_history:
        user_text = entry.get("user", "")
        # Skip the user bubble for auto-shown entries (e.g. first content chunk
        # displayed immediately after 'teach start' with no user input).
        if user_text:
            upanel = user_input_panel(user_text, width=panel_width)
            console.print(upanel)

        assistant_msg = entry.get("assistant")
        panel_type = entry.get("panel", "ai")

        if not assistant_msg:
            console.print("")
            continue

        # If we stored a direct renderable (Panel, Group, or anything else
        # that is not a plain string/Text/Markdown), print it without wrapping.
        if not isinstance(assistant_msg, (str, Text, Markdown)):
            console.print(assistant_msg)
            console.print("")
            continue

        assistant_renderable = (
            Text(assistant_msg) if isinstance(assistant_msg, str) else assistant_msg
        )

        if panel_type == "output":
            op = output_panel(assistant_renderable, border_style="white", width=panel_width)
        elif panel_type == "agent":
            op = agent_panel(assistant_renderable, width=panel_width)
        else:
            op = ai_panel(assistant_renderable, width=panel_width)
        console.print(op)
        console.print("")


def _erase_prompt_line() -> None:
    """Erase the prompt line the user just submitted.

    Called right before the first console output for a command so the
    raw '✦ saxoflow ⮞ <input>' line is replaced by the styled user panel.
    """
    sys.stdout.write("\033[1A\033[2K\r")
    sys.stdout.flush()


def _erase_lines(num_lines: int) -> None:
    """Erase N lines above the cursor.
    
    Useful for cleaning up interactive command output (prompts, answers, etc.)
    before displaying styled output panels.
    """
    for _ in range(num_lines):
        sys.stdout.write("\033[1A\033[2K\r")
    sys.stdout.flush()


def _print_and_record(
    user_input: str,
    renderable: Union[str, Text, Markdown, Panel],
    panel_kind: str,
    panel_width: int,
) -> None:
    """Print the user input panel + renderable panel, and append to history.

    Args:
        user_input: The original command the user entered.
        renderable: The assistant output (string, Text/Markdown, or Panel).
        panel_kind: One of {'ai', 'agent', 'output', 'panel'} to control styling.
        panel_width: Target panel width for layout consistency.
    """
    # Direct renderables (Panel, Group, etc.) are printed without extra wrapping.
    if not isinstance(renderable, (str, Text, Markdown)):
        _erase_prompt_line()
        console.print(user_input_panel(user_input, width=panel_width))
        console.print(renderable)
        console.print("")
        conversation_history.append(
            {"user": user_input, "assistant": renderable, "panel": panel_kind}
        )
        record_user_turn(user_input, panel_kind, renderable)
        return

    _erase_prompt_line()
    console.print(user_input_panel(user_input, width=panel_width))

    if panel_kind == "output":
        if _is_saxoflow_output_command(user_input):
            panel = saxoflow_panel(renderable, width=console.width)
        else:
            panel = output_panel(renderable, border_style="white", width=panel_width)
    elif panel_kind == "agent":
        panel = agent_panel(renderable, width=panel_width)
    else:
        panel = ai_panel(renderable, width=panel_width)

    console.print(panel)
    console.print("")
    conversation_history.append(
        {"user": user_input, "assistant": renderable, "panel": panel_kind}
    )
    record_user_turn(user_input, panel_kind, renderable)


def _run_agentic_subprocess(command_line: str) -> Union[Text, Markdown]:
    """Execute an agentic CLI command via subprocess and return its output.

    Args:
        command_line: Full user input string (e.g., 'rtlgen --arg val').

    Returns:
        Text|Markdown: Output wrapped as a Rich renderable (Text for now).

    Notes:
        - Matches original behavior: uses `python3 -m saxoflow_agenticai.cli`.
        - Combines stdout + stderr.
        - Non-zero return codes produce a red error Text.
    """
    parts = shlex.split(command_line)
    log_agent_event(
        "agentic_command_start",
        title="Agentic Command Started",
        summary=f"Running agentic command `{command_line}`.",
        data={"command": command_line, "args": parts},
    )
    try:
        stdout_pipe = getattr(subprocess, "PIPE", None)
        stderr_pipe = getattr(subprocess, "PIPE", None)

        popen_kwargs = {"text": True}
        if stdout_pipe is not None:
            popen_kwargs["stdout"] = stdout_pipe
        if stderr_pipe is not None:
            popen_kwargs["stderr"] = stderr_pipe

        proc = subprocess.Popen(  # noqa: S603
            ["python3", "-m", "saxoflow_agenticai.cli"] + parts,
            **popen_kwargs,
        )
        stdout, stderr = proc.communicate()
    except FileNotFoundError as exc:
        # was: Text(f"[❌] Failed to run agentic command: {exc}", style="bold red")
        log_agent_event(
            "agentic_command_error",
            title="Agentic Command Error",
            summary=f"Failed to run `{command_line}`.",
            data={"command": command_line, "error": str(exc)},
        )
        return msg_error(f"Failed to run agentic command: {exc}")
    except Exception as exc:  # noqa: BLE001
        # was: Text(f"[❌] Unexpected error running agentic command: {exc}", style="bold red")
        log_agent_event(
            "agentic_command_error",
            title="Agentic Command Error",
            summary=f"Unexpected error while running `{command_line}`.",
            data={"command": command_line, "error": str(exc)},
        )
        return msg_error(f"Unexpected error running agentic command: {exc}")

    output = (stdout or "") + (stderr or "")
    log_agent_event(
        "agentic_command_end",
        title="Agentic Command Completed",
        summary=f"Agentic command `{command_line}` exited with status {proc.returncode}.",
        data={
            "command": command_line,
            "returncode": proc.returncode,
            "output_excerpt": output[-4000:],
        },
        full_data={"output": output},
    )
    if proc.returncode != 0:
        # was: Text(f"[❌] Error in `{command_line}`\n\n{output}", style="bold red")
        return msg_error(f"Error in `{command_line}`\n\n{output}")

    # was: Text(output or f"[⚠] No output from `{command_line}` command.", style="white")
    if output:
        return Text(output, style="white")
    return msg_warning(f"No output from `{command_line}` command.")


_CONTEXT_TEXT_SUFFIXES = {
    ".sv", ".svh", ".v", ".vh", ".vhd", ".vhdl", ".sva",
    ".md", ".txt", ".json", ".yaml", ".yml",
}


def _collect_web_research_sources(
    query: str,
    requested_capabilities: List[str],
) -> Mapping[str, Any]:
    """Execute real web retrieval for research mode when approved."""
    fetch_pages = "web.fetch" in set(requested_capabilities)
    service = WebResearchService()
    sources = service.search(
        query,
        max_results=3,
        fetch_pages=fetch_pages,
        max_fetched_pages=2,
    )
    source_dicts = [item.to_dict() for item in sources]
    return {
        "executed": True,
        "provider": service.provider_name,
        "query": query,
        "result_count": len(source_dicts),
        "fetched_page_count": sum(1 for item in source_dicts if item.get("fetched_excerpt")),
        "sources": source_dicts,
    }


def _render_web_research_summary(web_execution: Optional[Mapping[str, Any]]) -> List[str]:
    if not isinstance(web_execution, Mapping) or not web_execution.get("executed"):
        return []

    lines = ["Web retrieval:"]
    provider = str(web_execution.get("provider") or "").strip() or "unknown"
    query = str(web_execution.get("query") or "").strip() or "(none)"
    result_count = int(web_execution.get("result_count", 0) or 0)
    fetched_count = int(web_execution.get("fetched_page_count", 0) or 0)
    lines.append(f"- Provider: {provider}")
    lines.append(f"- Query: {query}")
    lines.append(f"- Search results retrieved: {result_count}")
    lines.append(f"- Target pages fetched: {fetched_count}")

    for item in web_execution.get("sources") or []:
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("source_id") or "").strip()
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not source_id or not title or not url:
            continue
        lines.append(f"- [web:{source_id}] {title} — {url}")
    return lines


def _build_research_note_document(
    *,
    prompt: str,
    checkpoints: List[str],
    web_execution: Optional[Mapping[str, Any]],
    response_markdown: str,
) -> str:
    lines = ["# Research notes", "", f"Query: {prompt}", "", "## Approval checkpoints"]
    lines.extend(f"- {line}" for line in checkpoints)
    web_lines = _render_web_research_summary(web_execution)
    if web_lines:
        lines.extend(["", "## Web retrieval"])
        lines.extend(web_lines[1:] if web_lines and web_lines[0] == "Web retrieval:" else web_lines)
    lines.extend(["", response_markdown.strip(), ""])
    return "\n".join(lines)


def _build_research_rendered_output(
    *,
    checkpoints: List[str],
    saved_path_text: str,
    web_execution: Optional[Mapping[str, Any]],
    response_markdown: str,
) -> str:
    lines = ["Research synthesis (read-only)", "", "Approval checkpoints:"]
    lines.extend(f"- {line}" for line in checkpoints)
    web_lines = _render_web_research_summary(web_execution)
    if web_lines:
        lines.extend([""] + web_lines)
    if saved_path_text:
        lines.extend(["", f"Saved research notes: {saved_path_text}"])
    lines.extend(["", response_markdown.strip()])
    return "\n".join(lines)


def _build_run_note_document(
    *,
    prompt: str,
    checkpoints: List[str],
    tool_events: List[str],
    resume_token: str,
    web_execution: Optional[Mapping[str, Any]],
    response_markdown: str,
) -> str:
    lines = ["# Run execution notes", "", f"Prompt: {prompt}", "", "## Approval checkpoints"]
    lines.extend(f"- {line}" for line in checkpoints)
    lines.extend(["", "## Tool events"])
    lines.extend(f"- {line}" for line in tool_events)
    web_lines = _render_web_research_summary(web_execution)
    if web_lines:
        lines.extend(["", "## Web retrieval"])
        lines.extend(web_lines[1:] if web_lines and web_lines[0] == "Web retrieval:" else web_lines)
    lines.extend(["", "## Resumable state", f"- Resume token: {resume_token}"])
    lines.extend(["", response_markdown.strip(), ""])
    return "\n".join(lines)


def _build_run_rendered_output(
    *,
    checkpoints: List[str],
    tool_events: List[str],
    resume_token: str,
    saved_path_text: str,
    web_execution: Optional[Mapping[str, Any]],
    response_markdown: str,
) -> str:
    lines = ["Bounded run (agent-mode)", "", "Approval checkpoints:"]
    lines.extend(f"- {line}" for line in checkpoints)
    lines.extend(["", "Tool events:"])
    lines.extend(f"- {line}" for line in tool_events)
    web_lines = _render_web_research_summary(web_execution)
    if web_lines:
        lines.extend([""] + web_lines)
    lines.extend(["", "Resumable state:", f"- resume_token={resume_token}"])
    if saved_path_text:
        lines.extend(["", f"Saved run artifact: {saved_path_text}"])
    lines.extend(["", response_markdown.strip()])
    return "\n".join(lines)


def _collect_grounded_context_documents(
    context_refs: List[str],
    *,
    max_files: int = 6,
    max_chars: int = 24000,
) -> List[Mapping[str, Any]]:
    """Collect bounded text evidence from grounded context refs for ask prompts."""
    workspace = Path.cwd().resolve()
    documents: List[Mapping[str, Any]] = []
    remaining_chars = max_chars

    def _iter_candidate_files(path: Path):
        if path.is_file():
            yield path
            return
        if path.is_dir():
            for candidate in sorted(path.rglob("*")):
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in _CONTEXT_TEXT_SUFFIXES:
                    continue
                yield candidate

    for raw_ref in context_refs:
        if len(documents) >= max_files or remaining_chars <= 0:
            break

        ref_path = str(raw_ref or "").strip()
        if not ref_path:
            continue

        resolved = (workspace / ref_path).resolve()
        try:
            resolved.relative_to(workspace)
        except ValueError:
            continue
        if not resolved.exists():
            continue

        for candidate in _iter_candidate_files(resolved):
            if len(documents) >= max_files or remaining_chars <= 0:
                break
            try:
                raw = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "\x00" in raw:
                continue

            clip_budget = min(remaining_chars, 6000)
            clipped = raw[:clip_budget]
            remaining_chars -= len(clipped)
            try:
                rel_path = str(candidate.relative_to(workspace))
            except ValueError:
                rel_path = str(candidate)
            documents.append(
                {
                    "path": rel_path,
                    "content": clipped,
                    "truncated": len(clipped) < len(raw),
                }
            )

    return documents


def _run_ai_service_command(
    task_type: str,
    prompt: str,
    history,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Union[Text, Markdown]:
    """Temporary AI-service adapter for explicit TUI ask/plan/run/research routes."""
    normalized_task = (task_type or "").strip().lower()
    help_requested = bool((metadata or {}).get("help_requested"))
    if help_requested:
        return _build_ai_mode_help(normalized_task)

    normalized_prompt = (prompt or "").strip()
    if not normalized_prompt:
        return msg_warning(f"Usage: {normalized_task} \"<prompt>\"")

    _ctx = _project_context()
    _prefs = _load_prefs()
    _pref_ctx = _prefs_context(_prefs)
    if _pref_ctx:
        _ctx = ((_ctx + "\n" + _pref_ctx) if _ctx else _pref_ctx)

    # P6.04 contract: parsed --context/--agent/--tools metadata is carried
    # through the explicit AI-service request boundary for downstream workflow
    # integration.
    _request_metadata = dict(metadata or {})

    plan_policy: Optional[PlanWorkflowPolicy] = None
    plan_policy_decision: Optional[PlanWorkflowPolicyDecision] = None
    research_policy: Optional[ResearchWorkflowPolicy] = None
    research_policy_decision: Optional[ResearchWorkflowPolicyDecision] = None
    run_policy: Optional[RunWorkflowPolicy] = None
    run_policy_decision: Optional[RunWorkflowPolicyDecision] = None
    if normalized_task == "plan":
        plan_policy = PlanWorkflowPolicy(Path.cwd())
        plan_policy_decision = plan_policy.evaluate(_request_metadata.get("requested_capabilities") or [])
        _request_metadata["plan_workflow_policy"] = plan_policy_decision.to_dict()
        if not plan_policy_decision.feasible:
            allowed_caps = ", ".join(plan_policy.allowed_capabilities)
            return msg_error(
                f"{plan_policy_decision.reason}. "
                f"Allowed capabilities for `plan`: {allowed_caps}."
            )
    elif normalized_task == "research":
        research_policy = ResearchWorkflowPolicy(Path.cwd())
        research_policy_decision = research_policy.evaluate(_request_metadata.get("requested_capabilities") or [])
        _request_metadata["research_workflow_policy"] = research_policy_decision.to_dict()
        _request_metadata["web_research_policy"] = WebResearchRoutingPolicy(
            allow_web_research=True,
        ).evaluate(_request_metadata.get("requested_capabilities") or []).to_dict()
        if not research_policy_decision.feasible:
            allowed_caps = ", ".join(research_policy.allowed_capabilities)
            return msg_error(
                f"{research_policy_decision.reason}. "
                f"Allowed capabilities for `research`: {allowed_caps}."
            )
        web_policy = _request_metadata.get("web_research_policy") or {}
        if isinstance(web_policy, Mapping) and web_policy.get("requested") and web_policy.get("allowed"):
            try:
                web_execution = _collect_web_research_sources(
                    normalized_prompt,
                    list(_request_metadata.get("requested_capabilities") or []),
                )
            except WebResearchError as exc:
                return msg_error(f"Web research failed: {exc}")
            _request_metadata["web_research_execution"] = {
                key: value for key, value in web_execution.items() if key != "sources"
            }
            _request_metadata["web_research_execution"]["executed"] = True
            _request_metadata["web_research_sources"] = list(web_execution.get("sources") or [])
    elif normalized_task == "run":
        run_policy = RunWorkflowPolicy(Path.cwd())
        run_policy_decision = run_policy.evaluate(_request_metadata.get("requested_capabilities") or [])
        _request_metadata["run_workflow_policy"] = run_policy_decision.to_dict()
        _request_metadata["web_research_policy"] = WebResearchRoutingPolicy(
            allow_web_research=True,
        ).evaluate(_request_metadata.get("requested_capabilities") or []).to_dict()
        if not run_policy_decision.feasible:
            allowed_caps = ", ".join(run_policy.allowed_capabilities)
            return msg_error(
                f"{run_policy_decision.reason}. "
                f"Allowed capabilities for `run`: {allowed_caps}."
            )
        web_policy = _request_metadata.get("web_research_policy") or {}
        if isinstance(web_policy, Mapping) and web_policy.get("requested") and web_policy.get("allowed"):
            try:
                web_execution = _collect_web_research_sources(
                    normalized_prompt,
                    list(_request_metadata.get("requested_capabilities") or []),
                )
            except WebResearchError as exc:
                return msg_error(f"Web research failed: {exc}")
            _request_metadata["web_research_execution"] = {
                key: value for key, value in web_execution.items() if key != "sources"
            }
            _request_metadata["web_research_execution"]["executed"] = True
            _request_metadata["web_research_sources"] = list(web_execution.get("sources") or [])

    # P6.04a grounding: explicit AI routes must resolve into workflow request
    # state with context/agent/prompt provenance before advisory rendering.
    try:
        grounded_state = AIRequestService(Path.cwd()).start_grounded_task(
            normalized_task,
            normalized_prompt,
            metadata=_request_metadata,
        )
    except AIRequestServiceError as exc:
        return msg_error(str(exc))

    grounded_context_refs: List[str] = []
    try:
        top_bundle = getattr(grounded_state, "context_bundle", None)
        if top_bundle is not None:
            for ref in getattr(top_bundle, "references", ()):
                path = str(getattr(ref, "path", "") or "").strip()
                if path:
                    grounded_context_refs.append(path)
        for task in getattr(grounded_state, "tasks", ()) or ():
            task_bundle = getattr(task, "context_bundle", None)
            if task_bundle is None:
                continue
            for ref in getattr(task_bundle, "references", ()):
                path = str(getattr(ref, "path", "") or "").strip()
                if path:
                    grounded_context_refs.append(path)
    except Exception:
        grounded_context_refs = []

    if grounded_context_refs:
        _request_metadata["grounded_context_refs"] = list(dict.fromkeys(grounded_context_refs))
        if normalized_task in {"ask", "research"}:
            _request_metadata["grounded_context_documents"] = _collect_grounded_context_documents(
                _request_metadata["grounded_context_refs"]
            )

    if normalized_task == "run":
        run_adapter_routing: Mapping[str, Any] = {}
        try:
            tasks = list(getattr(grounded_state, "tasks", ()) or ())
            if tasks:
                task_metadata = getattr(tasks[0], "metadata", None)
                if isinstance(task_metadata, Mapping):
                    candidate = task_metadata.get("run_adapter_routing")
                    if isinstance(candidate, Mapping):
                        run_adapter_routing = candidate
        except Exception:
            run_adapter_routing = {}
        if run_adapter_routing:
            _request_metadata["run_adapter_routing"] = dict(run_adapter_routing)

        requested_caps = list(_request_metadata.get("requested_capabilities") or [])
        if "eda.run" in requested_caps:
            routing_state = dict(_request_metadata.get("run_adapter_routing") or {})
            if routing_state.get("classification_status") == "rejected":
                reason = str(routing_state.get("reason") or "run adapter scenario was not classified")
                return msg_error(f"Run workflow could not classify `eda.run` scenario: {reason}")

    # Phase P6.02 route isolation: explicit AI commands should stay advisory
    # and avoid triggering AI Buddy file-write/review/action flows.
    result = _ask_ai_buddy_chat_only(
        normalized_prompt,
        history,
        context=_ctx or None,
        task_hint=normalized_task,
        metadata=_request_metadata,
    )
    if result.get("type") == "error":
        return msg_error(result.get("message", "AI service failed."))

    message = result.get("message", "")
    if normalized_task == "ask":
        citation_refs = [
            str(path).strip()
            for path in (_request_metadata.get("grounded_context_refs") or [])
            if str(path).strip()
        ]
        if citation_refs:
            citation_lines = "\n".join(f"- [context:{path}]" for path in citation_refs)
        else:
            citation_lines = "- [context:none]"
        message = (
            "Grounded ask (read-only)\n"
            "Cited context used:\n"
            f"{citation_lines}\n\n"
            f"{message}"
        )
    elif normalized_task == "plan":
        checkpoints: List[str] = []
        if plan_policy_decision and plan_policy_decision.approval_checkpoints:
            checkpoints.extend(
                f"Approve capability `{capability}` usage in planning mode."
                for capability in plan_policy_decision.approval_checkpoints
            )
        else:
            checkpoints.append("No additional approvals required for requested plan capabilities.")

        saved_path_text = ""
        if plan_policy and plan_policy_decision and plan_policy_decision.persist_plan_artifact:
            docs_root = Path(plan_policy_decision.allowed_docs_root)
            docs_root.mkdir(parents=True, exist_ok=True)
            filename = f"plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            artifact_path = plan_policy.ensure_docs_path(filename)
            plan_doc = (
                "# Structured plan\n\n"
                "## Milestones\n"
                "- Fill in milestone sequencing from the plan output below.\n\n"
                "## Prerequisites\n"
                "- Fill in required setup, dependencies, and assumptions.\n\n"
                "## Risks\n"
                "- Fill in key risks and mitigations.\n\n"
                "## Approval Checkpoints\n"
                + "\n".join(f"- {line}" for line in checkpoints)
                + "\n\n## Plan details\n"
                + message
                + "\n"
            )
            try:
                artifact_path.write_text(plan_doc, encoding="utf-8")
                try:
                    saved_path_text = str(artifact_path.relative_to(Path.cwd()))
                except ValueError:
                    saved_path_text = str(artifact_path)
            except OSError as exc:
                return msg_error(f"Could not save plan artifact under docs/: {exc}")

        plan_header = [
            "Structured plan (read-only)",
            "",
            "Milestones:",
            "- Extract and sequence milestones from the plan details section.",
            "",
            "Prerequisites:",
            "- Extract dependencies, assumptions, and setup requirements from plan details.",
            "",
            "Risks:",
            "- Extract top risks and mitigations from plan details.",
            "",
            "Approval checkpoints:",
        ]
        plan_header.extend(f"- {line}" for line in checkpoints)
        if saved_path_text:
            plan_header.extend(
                [
                    "",
                    f"Saved plan artifact: {saved_path_text}",
                ]
            )
        plan_header.extend([
            "",
            "Plan details:",
            message,
        ])
        message = "\n".join(plan_header)
    elif normalized_task == "research":
        checkpoints: List[str] = []
        if research_policy_decision and research_policy_decision.approval_checkpoints:
            checkpoints.extend(
                f"Approve capability `{capability}` usage in research mode."
                for capability in research_policy_decision.approval_checkpoints
            )
        else:
            checkpoints.append("No additional approvals required for requested research capabilities.")

        saved_path_text = ""
        web_execution = dict(_request_metadata.get("web_research_execution") or {})
        if _request_metadata.get("web_research_sources"):
            web_execution["sources"] = list(_request_metadata.get("web_research_sources") or [])
        if research_policy and research_policy_decision and research_policy_decision.persist_research_artifact:
            docs_root = Path(research_policy_decision.allowed_docs_root)
            docs_root.mkdir(parents=True, exist_ok=True)
            filename = f"research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            artifact_path = research_policy.ensure_docs_path(filename)
            research_doc = _build_research_note_document(
                prompt=normalized_prompt,
                checkpoints=checkpoints,
                web_execution=web_execution,
                response_markdown=message,
            )
            try:
                artifact_path.write_text(research_doc, encoding="utf-8")
                try:
                    saved_path_text = str(artifact_path.relative_to(Path.cwd()))
                except ValueError:
                    saved_path_text = str(artifact_path)
            except OSError as exc:
                return msg_error(f"Could not save research notes under docs/: {exc}")

        message = _build_research_rendered_output(
            checkpoints=checkpoints,
            saved_path_text=saved_path_text,
            web_execution=web_execution,
            response_markdown=message,
        )
    elif normalized_task == "run":
        checkpoints: List[str] = []
        if run_policy_decision and run_policy_decision.approval_checkpoints:
            checkpoints.extend(
                f"Approve capability `{capability}` usage in run mode."
                for capability in run_policy_decision.approval_checkpoints
            )
        else:
            checkpoints.append("No additional approvals required for requested run capabilities.")

        requested_caps = list(_request_metadata.get("requested_capabilities") or [])
        tool_events: List[str] = ["workflow.start: bounded run request accepted"]
        run_adapter_routing = dict(_request_metadata.get("run_adapter_routing") or {})
        if "eda.run" in requested_caps:
            scenario = str(run_adapter_routing.get("scenario") or "unknown")
            adapter_module = str(run_adapter_routing.get("adapter_module") or "unknown")
            tool_events.append(
                f"tool.adapter: staged `eda.run` invocation queued (scenario: {scenario})"
            )
            tool_events.append(
                f"tool.event: `eda.run` execution contract registered via `{adapter_module}`"
            )
        if "artifact.write" in requested_caps:
            tool_events.append("artifact.event: docs-scoped write requested")
        if "web.search" in requested_caps:
            tool_events.append("tool.adapter: staged `web.search` retrieval queued")
        if "web.fetch" in requested_caps:
            tool_events.append("tool.adapter: staged `web.fetch` page retrieval queued")

        web_execution = dict(_request_metadata.get("web_research_execution") or {})
        if _request_metadata.get("web_research_sources"):
            web_execution["sources"] = list(_request_metadata.get("web_research_sources") or [])

        resume_token = f"run-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        saved_path_text = ""
        if run_policy and run_policy_decision and run_policy_decision.persist_run_artifact:
            docs_root = Path(run_policy_decision.allowed_docs_root)
            docs_root.mkdir(parents=True, exist_ok=True)
            filename = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            artifact_path = run_policy.ensure_docs_path(filename)
            run_doc = _build_run_note_document(
                prompt=normalized_prompt,
                checkpoints=checkpoints,
                tool_events=tool_events,
                resume_token=resume_token,
                web_execution=web_execution,
                response_markdown=message,
            )
            try:
                artifact_path.write_text(run_doc, encoding="utf-8")
                try:
                    saved_path_text = str(artifact_path.relative_to(Path.cwd()))
                except ValueError:
                    saved_path_text = str(artifact_path)
            except OSError as exc:
                return msg_error(f"Could not save run artifact under docs/: {exc}")

        message = _build_run_rendered_output(
            checkpoints=checkpoints,
            tool_events=tool_events,
            resume_token=resume_token,
            saved_path_text=saved_path_text,
            web_execution=web_execution,
            response_markdown=message,
        )
    return Text(message, style="white")


# =============================================================================
# Teach-mode handler
# =============================================================================

def _handle_teach_input(
    user_input: str,
    first_token: str,
    session,
    panel_width: int,
) -> str:
    """Route one turn of input when a teach session is active.

    Returns ``"quit"`` when the user typed ``quit`` inside teach mode so
    the caller knows to tear down the session; returns ``""`` otherwise.
    """
    try:
        from saxoflow.teach._tui_bridge import handle_input as _teach_handle  # noqa: PLC0415
    except ImportError as exc:
        console.print(Text(f"[teach] Bridge module not available: {exc}", style="red"))
        return ""

    llm = getattr(_state, "_teach_llm", None)
    panel = _teach_handle(user_input, session, llm=llm)
    _print_and_record(user_input, panel, "output", panel_width)

    if first_token == "quit":
        return "quit"
    return ""


# =============================================================================
# In-process teach-start (must run inside TUI so _state.teach_session is set
# in the correct process — not in a captured subprocess)
# =============================================================================

def _start_teach_session_inproc(parts: List[str], panel_width: int) -> None:
    """Start a teach session in the running TUI process.

    Called by the main loop whenever the user types
    ``saxoflow teach start <pack_id>``.
    Runs the pack-loading and LLM-initialisation logic directly here (no
    subprocess) so that ``_state.teach_session`` is bound to the parent TUI
    process and the teach-mode routing guard activates immediately.
    """
    from saxoflow.teach.pack import load_pack, PackLoadError  # noqa: PLC0415
    from saxoflow.teach.session import TeachSession  # noqa: PLC0415
    from saxoflow.teach.indexer import DocIndex  # noqa: PLC0415
    from saxoflow.runtime_paths import resolve_packs_dir  # noqa: PLC0415
    from .panels import tutor_panel  # noqa: PLC0415

    # parts: ["saxoflow", "teach", "start", pack_id, ...optional flags...]
    if len(parts) < 4:
        console.print(user_input_panel(" ".join(parts), width=panel_width))
        console.print(tutor_panel(
            Text("Usage: saxoflow teach start <pack_id>", style="yellow"),
            width=panel_width,
        ))
        console.print("")
        return

    pack_id = parts[3]
    # Simple flag extraction (--provider / --model)
    provider = None
    model = None
    packs_dir = None
    for i, tok in enumerate(parts[4:], start=4):
        if tok == "--provider" and i + 1 < len(parts):
            provider = parts[i + 1]
        elif tok == "--model" and i + 1 < len(parts):
            model = parts[i + 1]
        elif tok == "--packs-dir" and i + 1 < len(parts):
            packs_dir = parts[i + 1]
        elif tok.startswith("--packs-dir="):
            packs_dir = tok.split("=", 1)[1]

    packs_path = resolve_packs_dir(packs_dir)
    pack_path = packs_path / pack_id
    lines: List[str] = []

    # --- Load pack -----------------------------------------------------------
    try:
        pack = load_pack(pack_path)
    except (FileNotFoundError, PackLoadError) as exc:
        console.print(user_input_panel(" ".join(parts), width=panel_width))
        console.print(tutor_panel(
            Text(f"Error loading pack '{pack_id}': {exc}", style="red"),
            width=panel_width,
        ))
        console.print("")
        return

    # --- Index ---------------------------------------------------------------
    idx = DocIndex(pack)
    try:
        idx.load_or_build()
        if idx.chunk_count == 0:
            lines.append(
                f"No document chunks found. "
                f"Add a PDF to {pack_path / 'docs'} and run "
                f"'saxoflow teach index {pack_id}' to enable "
                "document-grounded tutoring.  Continuing without context."
            )
        else:
            lines.append(f"Index ready: {idx.chunk_count} chunks.")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"Warning: could not load index ({exc}). Running without context.")

    # --- LLM -----------------------------------------------------------------
    llm = None
    try:
        from saxoflow_agenticai.core.model_selector import ModelSelector  # noqa: PLC0415
        llm = ModelSelector.get_model(
            agent_type="tutor", provider=provider, model_name=model
        )
        lines.append(f"LLM ready: {type(llm).__name__}")
    except Exception as exc:  # noqa: BLE001
        lines.append(
            f"LLM unavailable ({exc}). "
            "Set an API key (e.g. OPENAI_API_KEY) to enable AI explanations."
        )

    # --- Session -------------------------------------------------------------
    session = TeachSession(pack=pack)
    if not session.load_progress():
        lines.append("No saved progress — starting from step 1.")

    # Bind into TUI state (this is why we must run in-process!)
    _state.teach_session = session
    _state._teach_llm = llm  # type: ignore[attr-defined]

    step = session.current_step
    step_title = step.title if step else "(all steps complete)"
    lines.append(f"")
    lines.append(f"Pack:  {pack.name}")
    lines.append(f"Step:  {session.current_step_index + 1} / {session.total_steps} — {step_title}")
    lines.append("")
    lines.append("Commands: run · next · back · hint · status · agents · quit  |  or type any question")

    content = Text("\n".join(lines), style="white")
    user_cmd = " ".join(parts)
    console.print(user_input_panel(user_cmd, width=panel_width))
    console.print(tutor_panel(content, width=panel_width))
    console.print("")
    conversation_history.append(
        {"user": user_cmd, "assistant": "\n".join(lines), "panel": "output"}
    )

    # Load and display the first content chunk for the opening step
    try:
        from saxoflow.teach._tui_bridge import prepare_step_for_display  # noqa: PLC0415
        first_panel = prepare_step_for_display(session)
        console.print(first_panel)
        console.print("")
        conversation_history.append(
            {"user": "", "assistant": first_panel, "panel": "output"}
        )
    except Exception as _exc:  # noqa: BLE001
        logger.debug("Could not load first content chunk: %s", _exc)


def _main_in_workspace(workspace: Optional[str] = None) -> None:
    """Run the interactive SaxoFlow CLI session inside its workspace."""
    active_workspace = resolve_workspace(workspace, create=True)
    os.chdir(active_workspace)
    init_agent_log_session(active_workspace)

    # Run first-run provider key setup before anything else.
    ensure_first_run_setup(console)

    cli_history = InMemoryHistory()
    session = PromptSession(completer=_build_completer(), history=cli_history)

    # Panel width: keep existing ratio to preserve layout/UX.
    panel_width = int(console.width * 0.8)
    custom_prompt = HTML(CUSTOM_PROMPT_HTML)

    while True:
        if not conversation_history:
            _clear_terminal()
            _show_opening_look(panel_width)
        # else: history is already visible on screen — don't clear or redraw it

        try:
            user_input = session.prompt(custom_prompt)
        except EOFError:
            console.print(_goodbye())
            break
        except KeyboardInterrupt:
            # Prompt-level Ctrl+C should cancel current input and keep the REPL alive.
            console.print(Text("Cancelled.", style="yellow"))
            continue

        # Erase the prompt line the user just submitted so the screen only
        # shows the styled user-bubble panel (printed below), not both.
        # NOTE: actual erasure is deferred to _erase_prompt_line() which is
        # called right before the first console.print, so the prompt stays
        # visible during any loading/thinking delay.

        user_input = (user_input or "").strip()
        if not user_input:
            continue

        first_token = user_input.split(maxsplit=1)[0].lower()
        display_input = user_input  # preserve original typed text for user-bubble display

        # ---------------------------------------------------------------------
        # 1) Built-ins (split to preserve spec: quit/exit never recorded)
        # ---------------------------------------------------------------------
        if first_token in {"quit", "exit"}:
            try:
                process_command(user_input)  # optional cleanup
            except Exception:
                pass
            console.print(_goodbye())
            break

        if first_token == "clear":
            try:
                process_command(user_input)  # optional side-effects
            except Exception:
                pass
            conversation_history.clear()
            console.clear()
            continue  # next loop will show banner

        if first_token == "help" or user_input in {"init-env --help", "init-env help"}:
            result = process_command(user_input)
            if isinstance(result, Panel):
                _print_and_record(user_input, result, "panel", panel_width)
            else:
                _print_and_record(user_input, result, "output", panel_width)
            continue

        if first_token == "agentlog":
            result = handle_agentlog_command(user_input)
            _print_and_record(user_input, result, "output", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 1b) Teach-mode routing guard
        #     When a teach session is active, all non-built-in input is
        #     handled by _tui_bridge.  Shell/agentic/AI-buddy routing below
        #     is skipped.  The guard is placed AFTER built-ins so that
        #     quit/exit/clear/help continue to function normally.
        # ---------------------------------------------------------------------
        if _state.teach_session is not None:
            # Allow standard Unix/shell commands to execute directly even in
            # teach mode so students can explore the workspace freely alongside
            # the tutorial (ls, cat, pwd, etc. just work).
            if is_unix_command(user_input) or user_input.startswith("!"):
                if _is_saxoflow_install(user_input):
                    # Print user panel BEFORE the subprocess runs so it appears first.
                    console.print(user_input_panel(user_input, width=panel_width))
                    console.print("")
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    if not (isinstance(renderable, Text) and not renderable.plain.strip()):
                        console.print(renderable)
                        console.print("")
                    conversation_history.append({"user": user_input, "assistant": renderable or Text(""), "panel": "output"})
                elif requires_raw_tty(user_input):
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(user_input, renderable, "output", panel_width)
                else:
                    with console.status("[cyan]Running...", spinner="aesthetic"):
                        renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(user_input, renderable, "output", panel_width)
                # Capture plain text output into the session terminal_log so the
                # TutorAgent can see recent shell activity (cat, ll, cat file, etc.)
                try:
                    from rich.text import Text as _RT  # noqa: PLC0415
                    from rich.panel import Panel as _RP  # noqa: PLC0415
                    _r = renderable
                    if isinstance(_r, _RT):
                        _plain = _r.plain
                    elif isinstance(_r, _RP) and isinstance(_r.renderable, _RT):
                        _plain = _r.renderable.plain
                    else:
                        _plain = str(_r)
                    if _plain and _plain.strip():
                        _state.teach_session.add_terminal_entry(user_input, _plain.strip())
                except Exception:  # noqa: BLE001
                    pass
                # If the typed command matches the current pending step command,
                # advance the command cursor so the student doesn't have to use 'run'.
                try:
                    from saxoflow.teach._tui_bridge import record_manual_command as _rmc  # noqa: PLC0415
                    _auto = _rmc(user_input, _state.teach_session)
                    if _auto is not None:
                        console.print(_auto)
                        console.print("")
                        conversation_history.append({"user": "", "assistant": _auto, "panel": "output"})
                except Exception:  # noqa: BLE001
                    pass
                continue

            teach_result = _handle_teach_input(
                user_input, first_token, _state.teach_session, panel_width
            )
            if teach_result == "quit":
                _state.teach_session = None
                console.print(Text("Exited tutor mode.", style="cyan"))
            continue

        # ---------------------------------------------------------------------
        # 1c) In-process saxoflow-teach-start interceptor
        #     Must run here (not as a subprocess) so _state.teach_session is
        #     bound in this process and the teach guard above activates.
        # ---------------------------------------------------------------------
        _cmd_parts = shlex.split(user_input) if user_input else []
        if (
            len(_cmd_parts) >= 3
            and _cmd_parts[0] == "saxoflow"
            and _cmd_parts[1] == "teach"
            and _cmd_parts[2] == "start"
        ):
            _start_teach_session_inproc(_cmd_parts, panel_width)
            continue

        # ---------------------------------------------------------------------
        # 1d) Auto-expand bare saxoflow subcommand names typed without the
        #     "saxoflow " prefix (e.g. "check-tools" → "saxoflow check-tools",
        #     "agenticai" → "saxoflow agenticai").
        #     This prevents these commands from falling through to the AI Buddy.
        # ---------------------------------------------------------------------
        if first_token in _SAXOFLOW_BARE_CMDS and not user_input.startswith("saxoflow "):
            user_input = "saxoflow " + user_input
            first_token = "saxoflow"

        route_decision = classify_input(user_input)

        if route_decision.route_type == "ai_service":
            with console.status("[cyan]AI service running...", spinner="dots"):
                renderable = _run_ai_service_command(
                    route_decision.ai_task or "",
                    route_decision.ai_prompt or "",
                    conversation_history,
                    route_decision.ai_metadata,
                )
            _print_and_record(display_input, renderable, "ai", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 2) Shell/editor commands → Output panel
        # ---------------------------------------------------------------------
        is_cli_command = user_input.startswith("!") or is_unix_command(user_input)

        if is_cli_command:
            # Blocking editors should always return to the CLI after closing.
            if is_blocking_editor_command(user_input):
                renderable = process_command(user_input)
                _print_and_record(display_input, renderable, "output", panel_width)
            else:
                if _is_saxoflow_install(user_input):
                    # Print user panel BEFORE the subprocess so it appears first in terminal.
                    _erase_prompt_line()
                    console.print(user_input_panel(display_input, width=panel_width))
                    console.print("")
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    if not (isinstance(renderable, Text) and not renderable.plain.strip()):
                        console.print(renderable)
                        console.print("")
                    conversation_history.append({"user": display_input, "assistant": renderable or Text(""), "panel": "output"})
                # saxoflow clean: ask confirmation here (not via subprocess) so we
                # control exactly which lines appear and can erase precisely.
                elif user_input.startswith("saxoflow clean"):
                    # Show spinner briefly, then exit
                    with console.status("[cyan]Loading...", spinner="aesthetic"):
                        pass
                    
                    # Ask confirmation directly on the terminal (1 line printed)
                    sys.stdout.write("Clean all generated files and build artifacts? [y/N]: ")
                    sys.stdout.flush()
                    try:
                        answer = sys.stdin.readline().strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        answer = ""
                    
                    # Erase exactly 2 lines:
                    # 1. The confirmation prompt + answer line
                    # 2. The "✦ saxoflow ⮞ clean" REPL line
                    _erase_lines(2)
                    
                    if answer in ("y", "yes"):
                        # Run with --yes (captured, no interactive prompt bleeds through)
                        renderable = process_command("saxoflow clean --yes")
                    else:
                        renderable = saxoflow_panel(Text("Clean cancelled.", style="white"), width=console.width)
                    
                    # Print user panel, then result panel (no blank line between, matching _print_and_record)
                    console.print(user_input_panel(display_input, width=panel_width))
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    if not (isinstance(renderable, Text) and not renderable.plain.strip()):
                        console.print(renderable)
                        console.print("")
                    conversation_history.append({"user": display_input, "assistant": renderable or Text(""), "panel": "output"})
                # 🔧 FIX: Skip spinner for interactive/raw-TTY commands (e.g., saxoflow init-env)
                elif requires_raw_tty(user_input):
                    renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(display_input, renderable, "output", panel_width)
                else:
                    with console.status("[cyan]Loading...", spinner="aesthetic"):
                        renderable = process_command(user_input)
                    if renderable is None:
                        console.print(_goodbye())
                        break
                    _print_and_record(display_input, renderable, "output", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 3) Agentic AI commands → Agent panel
        # ---------------------------------------------------------------------
        if first_token in AGENTIC_COMMANDS:
            with console.status("[magenta]Agentic AI running...", spinner="clock"):
                renderable = _run_agentic_subprocess(user_input)
            _print_and_record(display_input, renderable, "agent", panel_width)
            continue

        # ---------------------------------------------------------------------
        # 4) AI Buddy → AI panel
        # ---------------------------------------------------------------------
        # Clarification Q&A must happen OUTSIDE the spinner: Rich's status
        # context (Live rendering) intercepts the terminal and its spinner
        # frames appear interleaved with input() prompts, making interaction
        # impossible.  The spinner starts immediately while question planning
        # runs, then exits before the first clarification prompt is printed.
        with console.status("[cyan]Thinking...", spinner="dots"):
            _buddy_ctx = _project_context()
            _buddy_prefs = _load_prefs()
            _buddy_pref_ctx = _prefs_context(_buddy_prefs)
            if _buddy_pref_ctx:
                _buddy_ctx = (
                    (_buddy_ctx + "\n" + _buddy_pref_ctx)
                    if _buddy_ctx
                    else _buddy_pref_ctx
                )

            _cq = _plan_clarification(user_input, context=_buddy_ctx, prefs=_buddy_prefs)
            if _cq is None:
                _cq = _detect_incomplete_request(user_input, _buddy_prefs)

            if not _cq:
                assistant_response = ai_buddy_interactive(
                    user_input, conversation_history, skip_clarification=True
                )

        if _cq:
            _enriched = _run_clarification_flow(user_input, _cq, context=_buddy_ctx)
            if _enriched is None:
                _print_and_record(
                    display_input, Text("Cancelled.", style="yellow"), "ai", panel_width
                )
                continue
            user_input = _enriched
            assistant_response = ai_buddy_interactive(
                user_input, conversation_history, skip_clarification=True
            )
        _print_and_record(display_input, assistant_response, "ai", panel_width)


def main(workspace: Optional[str] = None) -> None:
    """Run the TUI and restore the caller's working directory on exit."""
    caller_cwd = Path.cwd()
    try:
        _main_in_workspace(workspace)
    finally:
        try:
            os.chdir(caller_cwd)
        except OSError:
            pass


if __name__ == "__main__":  # pragma: no cover
    main()
