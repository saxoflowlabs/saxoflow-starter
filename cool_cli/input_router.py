"""Input routing classifier for Cool CLI.

Phase P6.01 scope:
- Introduce a small, testable route classifier.
- Guarantee direct Unix commands are classified to shell routing.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

from .shell import is_unix_command
from saxoflow.services.ai_command_service import AICommandOptions


_EXPLICIT_AI_COMMANDS = frozenset({"ask", "plan", "run", "research"})


def _strip_wrapping_quotes(text: str) -> str:
    candidate = (text or "").strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in {"\"", "'"}:
        return candidate[1:-1].strip()
    return candidate


@dataclass(frozen=True)
class RouteDecision:
    """Normalized routing outcome for one user input."""

    route_type: str
    normalized_command: str
    reason: str
    ai_task: Optional[str] = None
    ai_prompt: Optional[str] = None
    ai_metadata: Optional[Mapping[str, Any]] = None


def _parse_explicit_ai_command(normalized: str, route_token: str) -> tuple[str, Mapping[str, Any]]:
    """Parse explicit AI command payload and compact options.

    Supports:
    - --agent <name> or --agent=<name>
    - --context <path> (repeatable) or --context=<path>
    - --tools <csv> or --tools=<csv>
    """
    try:
        parts = shlex.split(normalized)
    except ValueError:
        fallback_prompt = ""
        chunks = normalized.split(maxsplit=1)
        if len(chunks) > 1:
            fallback_prompt = _strip_wrapping_quotes(chunks[1])
        return fallback_prompt, {}

    # parts[0] is the route token itself
    prompt_tokens: list[str] = []
    context_paths: list[str] = []
    agent_name: Optional[str] = None
    tools_csv: Optional[str] = None
    help_requested = False

    index = 1
    while index < len(parts):
        token = parts[index]

        if token == "--context":
            if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                context_paths.append(parts[index + 1])
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--context="):
            context_paths.append(token.split("=", 1)[1])
            index += 1
            continue

        if token == "--agent":
            if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                agent_name = parts[index + 1]
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--agent="):
            agent_name = token.split("=", 1)[1]
            index += 1
            continue

        if token == "--tools":
            if index + 1 < len(parts) and not parts[index + 1].startswith("--"):
                tools_csv = parts[index + 1]
                index += 2
                continue
            index += 1
            continue
        if token.startswith("--tools="):
            tools_csv = token.split("=", 1)[1]
            index += 1
            continue

        if token in {"--help", "-h"}:
            help_requested = True
            index += 1
            continue

        prompt_tokens.append(token)
        index += 1

    prompt = _strip_wrapping_quotes(" ".join(prompt_tokens))
    options = AICommandOptions.from_compact_options(
        agent=agent_name,
        context=context_paths,
        tools=tools_csv,
    )
    metadata = dict(options.to_metadata())
    if help_requested:
        metadata["help_requested"] = True
    return prompt, metadata


def classify_input(
    raw_input: str,
    *,
    unix_command_detector: Callable[[str], bool] = is_unix_command,
) -> RouteDecision:
    """Classify one input line into a routing category.

    Current phase guarantees:
    - Explicit AI commands (ask, plan, run, research) route to AI service.
    - Direct Unix commands route to shell.
    - Non-shell inputs are returned as "unknown" for later phase handling.
    """
    normalized = (raw_input or "").strip()
    if not normalized:
        return RouteDecision(
            route_type="empty",
            normalized_command="",
            reason="input was empty after trimming",
        )

    first_token, *rest = normalized.split(maxsplit=1)
    route_token = first_token.lower()
    if route_token in _EXPLICIT_AI_COMMANDS:
        prompt, metadata = _parse_explicit_ai_command(normalized, route_token)
        return RouteDecision(
            route_type="ai_service",
            normalized_command=normalized,
            reason=f"explicit ai command: {route_token}",
            ai_task=route_token,
            ai_prompt=prompt,
            ai_metadata=metadata,
        )

    if unix_command_detector(normalized):
        return RouteDecision(
            route_type="shell",
            normalized_command=normalized,
            reason="direct unix command",
        )

    return RouteDecision(
        route_type="unknown",
        normalized_command=normalized,
        reason="no phase-6 shell route match",
    )
