"""Parse and normalize compact AI command options.

Phase P4.09 introduces a parse-only contract for compact custom-agent options:
- --agent
- --context (repeatable)
- --tools (comma-separated capability subset)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Tuple


def _normalize_optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_context_paths(raw_paths: Optional[Iterable[Any]]) -> Tuple[str, ...]:
    if raw_paths is None:
        return tuple()

    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw_paths:
        path = _normalize_optional_text(item)
        if path is None or path in seen:
            continue
        normalized.append(path)
        seen.add(path)
    return tuple(normalized)


def _normalize_requested_tools(raw_tools: Optional[str]) -> Tuple[str, ...]:
    if raw_tools is None:
        return tuple()

    normalized: list[str] = []
    seen: set[str] = set()
    for part in str(raw_tools).split(","):
        tool = part.strip()
        if not tool or tool in seen:
            continue
        normalized.append(tool)
        seen.add(tool)
    return tuple(normalized)


@dataclass(frozen=True)
class AICommandOptions:
    """Normalized compact options for an AI command invocation."""

    agent_name: Optional[str] = None
    context_paths: Tuple[str, ...] = tuple()
    requested_tools: Tuple[str, ...] = tuple()

    @classmethod
    def from_compact_options(
        cls,
        *,
        agent: Optional[str] = None,
        context: Optional[Iterable[Any]] = None,
        tools: Optional[str] = None,
    ) -> "AICommandOptions":
        return cls(
            agent_name=_normalize_optional_text(agent),
            context_paths=_normalize_context_paths(context),
            requested_tools=_normalize_requested_tools(tools),
        )

    def to_metadata(self) -> Mapping[str, Any]:
        metadata: dict[str, Any] = {}
        if self.agent_name is not None:
            metadata["requested_agent"] = self.agent_name
        if self.context_paths:
            metadata["requested_context_paths"] = list(self.context_paths)
        if self.requested_tools:
            metadata["requested_capabilities"] = list(self.requested_tools)
        return metadata
