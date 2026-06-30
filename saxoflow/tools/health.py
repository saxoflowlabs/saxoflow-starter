"""Health checks for capability-scoped tool adapters."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple

from saxoflow.tools.registry import ToolRegistry


@dataclass(frozen=True)
class ToolHealthReport:
    """Health summary for one capability and its required external tools."""

    capability: str
    adapter_registered: bool
    required_tools: Tuple[str, ...]
    installed_tools: Tuple[str, ...]
    missing_tools: Tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return self.adapter_registered and not self.missing_tools

    def to_dict(self) -> Dict[str, object]:
        return {
            "capability": self.capability,
            "adapter_registered": self.adapter_registered,
            "required_tools": list(self.required_tools),
            "installed_tools": list(self.installed_tools),
            "missing_tools": list(self.missing_tools),
            "healthy": self.healthy,
        }


class ToolHealthService:
    """Resolve capability readiness from adapter registry and PATH checks."""

    def __init__(
        self,
        registry: ToolRegistry,
        tool_locator: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        self._registry = registry
        self._tool_locator = tool_locator or shutil.which

    @staticmethod
    def _normalize_tools(tools: Iterable[str]) -> Tuple[str, ...]:
        normalized = []
        for tool in tools:
            if isinstance(tool, str) and tool.strip():
                normalized.append(tool.strip())
        return tuple(dict.fromkeys(normalized))

    def check_capability(self, capability: str, required_tools: Sequence[str]) -> ToolHealthReport:
        required = self._normalize_tools(required_tools)
        installed = tuple(tool for tool in required if self._tool_locator(tool))
        installed_set = set(installed)
        missing = tuple(tool for tool in required if tool not in installed_set)
        return ToolHealthReport(
            capability=capability.strip(),
            adapter_registered=self._registry.has(capability),
            required_tools=required,
            installed_tools=installed,
            missing_tools=missing,
        )

    def check_many(self, required_tools_by_capability: Mapping[str, Sequence[str]]) -> Dict[str, ToolHealthReport]:
        reports: Dict[str, ToolHealthReport] = {}
        for capability, required_tools in required_tools_by_capability.items():
            reports[capability] = self.check_capability(capability, required_tools)
        return reports
