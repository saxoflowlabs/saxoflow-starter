"""System backend implementation.

This backend preserves existing SaxoFlow behavior where tool binaries are
exposed through PATH updates.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, Optional

from .base import ToolBackend, ToolResolution


class SystemToolBackend(ToolBackend):
    """System backend policy (default)."""

    name = "system"

    def resolve_tool(
        self,
        tool: str,
        resolver: Callable[[str], tuple[Optional[str], bool, Optional[str]]],
    ) -> ToolResolution:
        path, in_path, variant = resolver(tool)
        return ToolResolution(tool=tool, path=path, in_path=in_path, variant=variant)

    def install_tool(self, tool: str, installer: Callable[[str], None]) -> None:
        installer(tool)

    def activate_tool(
        self,
        tool: str,
        *,
        bin_path: str,
        binary_name: str,
        persist_path_cb: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, str]:
        if persist_path_cb:
            persist_path_cb(tool, bin_path)
        return {
            "backend": self.name,
            "activation": "path-persisted",
            "bin_path": bin_path,
            "binary_name": binary_name,
        }

    def verify_tool(self, tool: str, verifier: Callable[[str], bool]) -> bool:
        return verifier(tool)

    def export_lock(self, selected_tools: Iterable[str]) -> Dict[str, object]:
        return {
            "backend": self.name,
            "tools": sorted({str(tool) for tool in selected_tools}),
        }
