"""Managed backend implementation with project-local shims."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from .base import ToolBackend, ToolResolution


class ManagedToolBackend(ToolBackend):
    """Managed backend policy using `.saxoflow/bin` shims."""

    name = "managed"

    def resolve_tool(
        self,
        tool: str,
        resolver: Callable[[str], tuple[Optional[str], bool, Optional[str]]],
    ) -> ToolResolution:
        shim_path = self.workspace_root / ".saxoflow" / "bin" / tool
        if shim_path.exists() and os.access(str(shim_path), os.X_OK):
            return ToolResolution(
                tool=tool,
                path=str(shim_path),
                in_path=False,
                variant=tool,
            )
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
        del persist_path_cb  # Managed backend avoids global shell mutation.

        shim_dir = self.workspace_root / ".saxoflow" / "bin"
        shim_dir.mkdir(parents=True, exist_ok=True)

        resolved_bin = Path(os.path.expandvars(os.path.expanduser(bin_path))) / binary_name
        shim_path = shim_dir / tool

        shim_script = (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"target={str(resolved_bin)!r}\n"
            f"fallback={binary_name!r}\n"
            "if [[ -x \"$target\" ]]; then\n"
            "  exec \"$target\" \"$@\"\n"
            "fi\n"
            "if command -v \"$fallback\" >/dev/null 2>&1; then\n"
            "  exec \"$(command -v \"$fallback\")\" \"$@\"\n"
            "fi\n"
            f"echo \"ERROR: Unable to resolve '{tool}' for managed backend.\" >&2\n"
            "exit 127\n"
        )
        shim_path.write_text(shim_script, encoding="utf-8")
        shim_path.chmod(0o755)

        return {
            "backend": self.name,
            "activation": "workspace-shim",
            "shim": str(shim_path),
            "target": str(resolved_bin),
        }

    def verify_tool(self, tool: str, verifier: Callable[[str], bool]) -> bool:
        shim_path = self.workspace_root / ".saxoflow" / "bin" / tool
        if shim_path.exists() and os.access(str(shim_path), os.X_OK):
            return True
        return verifier(tool)

    def export_lock(self, selected_tools: Iterable[str]) -> Dict[str, object]:
        return {
            "backend": self.name,
            "shim_dir": ".saxoflow/bin",
            "tools": sorted({str(tool) for tool in selected_tools}),
        }
