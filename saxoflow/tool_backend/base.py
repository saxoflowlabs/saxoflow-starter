"""Tool backend contract abstractions for SaxoFlow."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional


@dataclass(frozen=True)
class ToolResolution:
    """Resolved tool location metadata."""

    tool: str
    path: Optional[str]
    in_path: bool
    variant: Optional[str]


class ToolBackend(ABC):
    """Abstract backend contract for tool operations."""

    name: str

    def __init__(self, workspace_root: Path | str = ".") -> None:
        self.workspace_root = Path(workspace_root).resolve()

    @abstractmethod
    def resolve_tool(
        self,
        tool: str,
        resolver: Callable[[str], tuple[Optional[str], bool, Optional[str]]],
    ) -> ToolResolution:
        """Resolve tool location using backend policy."""

    @abstractmethod
    def install_tool(self, tool: str, installer: Callable[[str], None]) -> None:
        """Install a tool under backend policy."""

    @abstractmethod
    def activate_tool(
        self,
        tool: str,
        *,
        bin_path: str,
        binary_name: str,
        persist_path_cb: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, str]:
        """Activate an installed tool for subsequent command resolution."""

    @abstractmethod
    def verify_tool(self, tool: str, verifier: Callable[[str], bool]) -> bool:
        """Verify whether a tool is accessible under backend policy."""

    @abstractmethod
    def export_lock(self, selected_tools: Iterable[str]) -> Dict[str, object]:
        """Export backend lock metadata for selected tools."""
