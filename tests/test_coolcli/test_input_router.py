"""Inventory tests for current TUI bare-command routing support."""

from __future__ import annotations

from cool_cli.input_router import classify_input


def test_bare_command_allowlist_documents_current_tui_auto_expansion():
    """Phase-0 inventory lock: only the current bare SaxoFlow commands are auto-expanded."""
    from cool_cli.app import _SAXOFLOW_BARE_CMDS

    expected = {
        "check-tools",
        "check_tools",
        "agenticai",
        "diagnose",
        "install",
        "synth",
        "schematic",
        "formal",
        "simulate",
        "simulate-verilator",
        "wave",
        "wave-verilator",
        "clean",
        "init-env",
        "unit",
    }

    assert _SAXOFLOW_BARE_CMDS == expected


def test_bare_command_allowlist_does_not_include_unsupported_cli_groups():
    """Phase-0 inventory lock: missing bare-command coverage stays visible."""
    from cool_cli.app import _SAXOFLOW_BARE_CMDS

    for missing in {"lint", "pdk", "pnr", "teach", "sim"}:
        assert missing not in _SAXOFLOW_BARE_CMDS


def test_input_router_routes_direct_unix_command_to_shell():
    decision = classify_input("which yosys", unix_command_detector=lambda cmd: cmd.startswith("which "))

    assert decision.route_type == "shell"
    assert decision.normalized_command == "which yosys"
    assert decision.reason == "direct unix command"


def test_input_router_routes_explicit_ask_to_ai_service():
    decision = classify_input('ask "explain this project"', unix_command_detector=lambda _cmd: False)

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "ask"
    assert decision.ai_prompt == "explain this project"
    assert decision.reason == "explicit ai command: ask"


def test_input_router_routes_explicit_plan_run_research_to_ai_service():
    for task in ("plan", "run", "research"):
        decision = classify_input(f"{task} optimize area", unix_command_detector=lambda _cmd: False)

        assert decision.route_type == "ai_service"
        assert decision.ai_task == task
        assert decision.ai_prompt == "optimize area"
        assert decision.reason == f"explicit ai command: {task}"


def test_input_router_parses_compact_ai_options_into_metadata():
    decision = classify_input(
        'run "improve pnr" --context docs/spec.md --context source/rtl --agent ppa_research --tools file.read,eda.run,file.read',
        unix_command_detector=lambda _cmd: False,
    )

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "run"
    assert decision.ai_prompt == "improve pnr"
    assert decision.ai_metadata == {
        "requested_agent": "ppa_research",
        "requested_context_paths": ["docs/spec.md", "source/rtl"],
        "requested_capabilities": ["file.read", "eda.run"],
    }


def test_input_router_parses_equals_style_ai_options_and_prompt_order():
    decision = classify_input(
        'ask --agent=mentor --context=docs/notes.md --tools=artifact.read,report.read "summarize status"',
        unix_command_detector=lambda _cmd: False,
    )

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "ask"
    assert decision.ai_prompt == "summarize status"
    assert decision.ai_metadata == {
        "requested_agent": "mentor",
        "requested_context_paths": ["docs/notes.md"],
        "requested_capabilities": ["artifact.read", "report.read"],
    }


def test_input_router_handles_missing_explicit_ai_prompt_as_empty():
    decision = classify_input("ask", unix_command_detector=lambda _cmd: False)

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "ask"
    assert decision.ai_prompt == ""


def test_input_router_parses_mode_help_flag_without_prompt_tokens():
    decision = classify_input("run --help", unix_command_detector=lambda _cmd: False)

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "run"
    assert decision.ai_prompt == ""
    assert decision.ai_metadata == {"help_requested": True}


def test_input_router_marks_non_shell_input_unknown():
    decision = classify_input("explain this project", unix_command_detector=lambda _cmd: False)

    assert decision.route_type == "unknown"
    assert decision.normalized_command == "explain this project"
    assert decision.reason == "no phase-6 shell route match"


def test_input_router_marks_whitespace_input_empty():
    decision = classify_input("   ", unix_command_detector=lambda _cmd: True)

    assert decision.route_type == "empty"
    assert decision.normalized_command == ""
    assert decision.reason == "input was empty after trimming"


def test_input_router_handles_malformed_quotes_with_fallback_prompt_parse():
    decision = classify_input('ask "unterminated', unix_command_detector=lambda _cmd: False)

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "ask"
    assert decision.ai_prompt == '"unterminated'
    assert decision.ai_metadata == {}


def test_input_router_ignores_missing_option_values_without_crashing():
    decision = classify_input(
        "plan --context --agent --tools",
        unix_command_detector=lambda _cmd: False,
    )

    assert decision.route_type == "ai_service"
    assert decision.ai_task == "plan"
    assert decision.ai_prompt == ""
    assert decision.ai_metadata == {}
