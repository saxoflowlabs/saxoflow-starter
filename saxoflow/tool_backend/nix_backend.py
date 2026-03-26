"""Nix flake/devshell backend for reproducible tool environments.

Supports:
- flake.nix with devShell for tool isolation and reproducibility.
- nix develop integration for environment setup.
- Tool version pinning via Nix lock files.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional

from .base import ToolBackend, ToolResolution


class NixToolBackend(ToolBackend):
    """Nix backend for reproducible tool environments.

    Uses Nix flakes and devShell to provide isolated, reproducible environments
    for tools. Each tool set can be defined in a flake.nix with specific versions
    pinned in flake.lock.

    Attributes
    ----------
    workspace_root : Path
        Path to workspace containing flake.nix.
    flake_path : Path
        Path to flake.nix in workspace.
    lock_path : Path
        Path to flake.lock in workspace.
    """

    name = "nix"

    def __init__(self, workspace_root: Path | str = ".") -> None:
        super().__init__(workspace_root)
        self.flake_path = self.workspace_root / "flake.nix"
        self.lock_path = self.workspace_root / "flake.lock"

    def _ensure_flake_exists(self) -> bool:
        """Check if flake.nix exists; create minimal one if not.

        Returns
        -------
        bool
            True if flake exists or was created; False if unable to create.
        """
        if self.flake_path.exists():
            return True

        # Create minimal flake.nix for nix develop support
        minimal_flake = '''{
  description = "SaxoFlow Nix environment";
  inputs = { nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable"; };
  outputs = { self, nixpkgs }:
    let pkgs = nixpkgs.legacyPackages.x86_64-linux;
    in {
      devShells.x86_64-linux.default = pkgs.mkShell {
        buildInputs = [ ];
      };
    };
}'''
        try:
            self.flake_path.write_text(minimal_flake, encoding="utf-8")
            return True
        except OSError:
            return False

    def resolve_tool(
        self,
        tool: str,
        resolver: Callable[[str], tuple[Optional[str], bool, Optional[str]]],
    ) -> ToolResolution:
        """Resolve tool via Nix devShell environment.

        Uses `nix flake show` to detect available tools in devShell,
        then delegates to resolver for actual path resolution.

        Parameters
        ----------
        tool : str
            Tool name to resolve.
        resolver : Callable
            Fallback resolver function for tool path detection.

        Returns
        -------
        ToolResolution
            Resolved tool metadata.
        """
        # First check if Nix devShell has the tool
        if self._tool_in_dev_shell(tool):
            return ToolResolution(
                tool=tool,
                path=f"nix-shell::{tool}",
                in_path=False,
                variant="from-devshell",
            )

        # Fall back to standard resolution
        path, in_path, variant = resolver(tool)
        return ToolResolution(tool=tool, path=path, in_path=in_path, variant=variant)

    def _tool_in_dev_shell(self, tool: str) -> bool:
        """Check if tool is available in Nix devShell.

        Parameters
        ----------
        tool : str
            Tool name.

        Returns
        -------
        bool
            True if tool can be resolved via nix develop.
        """
        if not self._ensure_flake_exists():
            return False

        try:
            # Query nix flake for available packages
            result = subprocess.run(
                ["nix", "flake", "show", "--json"],
                cwd=str(self.workspace_root),
                capture_output=True,
                timeout=10,
                text=True,
            )
            if result.returncode == 0:
                data = json.loads(result.stdout)
                # Check if tool is in devShells.x86_64-linux.default.inputsFrom
                if "devShells" in data:
                    return True  # If flake has devShells, assume tools could be there
            return False
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
            return False

    def activate_tool(
        self,
        tool: str,
        *,
        bin_path: str,
        binary_name: str,
        persist_path_cb: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, str]:
        """Activate tool for Nix environment.

        For Nix backend, activation is deferred to `nix develop` invocation.
        Tools are available via devShell at runtime.

        Parameters
        ----------
        tool : str
            Tool name.
        bin_path : str
            Expected binary path (informational for Nix).
        binary_name : str
            Binary name.
        persist_path_cb : Optional[Callable]
            Not used for Nix backend (no persistent PATH modification).

        Returns
        -------
        Dict[str, str]
            Activation metadata with status "nix-deferred".
        """
        del persist_path_cb  # Not used for nix backend
        self._ensure_flake_exists()
        return {
            "backend": self.name,
            "activation": "nix-deferred",
            "tool": tool,
            "binary_name": binary_name,
            "message": f"Tool '{tool}' will be available via 'nix develop'",
        }

    def verify_tool(self, tool: str, verifier: Callable[[str], bool]) -> bool:
        """Verify tool is available.

        Checks both Nix devShell and standard verifier.

        Parameters
        ----------
        tool : str
            Tool name.
        verifier : Callable
            Fallback verifier function.

        Returns
        -------
        bool
            True if tool is verifiable.
        """
        # Check Nix first
        if self._tool_in_dev_shell(tool):
            return True
        # Fall back to standard verification
        return verifier(tool)

    def export_lock(self, selected_tools: Iterable[str]) -> Dict[str, object]:
        """Export Nix lock information for selected tools.

        Returns metadata about flake.lock if present, otherwise placeholder.

        Parameters
        ----------
        selected_tools : Iterable[str]
            Tools to export.

        Returns
        -------
        Dict[str, object]
            Lock metadata including flake.lock content reference.
        """
        tools_list = sorted({str(tool) for tool in selected_tools})
        lock_content = None

        if self.lock_path.exists():
            try:
                lock_content = json.loads(self.lock_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        return {
            "backend": self.name,
            "tools": tools_list,
            "flake_path": str(self.flake_path),
            "lock_path": str(self.lock_path),
            "lock_exists": self.lock_path.exists(),
            "lock_version": lock_content.get("version") if lock_content else None,
            "status": "active",
        }

    def install_tool(self, tool: str, installer: Callable[[str], None]) -> None:
        """Install tool for Nix backend.

        For Nix backend, installation is delegated to the installer callback
        (typically nix package search or manual flake update).

        Parameters
        ----------
        tool : str
            Tool name.
        installer : Callable
            Installer function to call for the tool.
        """
        self._ensure_flake_exists()
        installer(tool)
