"""
M3 Backend CLI commands module.

Provides user-facing commands for backend selection and configuration:
  - saxoflow config set-backend {system|managed|nix}
  - saxoflow config get-backend
  - saxoflow config show-backend-info
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from saxoflow.tool_backend import (
    create_backend,
    set_default_backend,
    get_default_backend,
)
from saxoflow.workspace.schema import (
    default_project_data,
    load_project_data,
    read_tool_backend,
    write_project_data,
    workspace_paths,
)


class BackendConfigCmd:
    """CLI commands for backend configuration."""

    @staticmethod
    def _normalize_workspace(workspace: Path) -> Path:
        """Resolve workspace path so relative inputs (Path('.')) behave consistently."""
        return workspace.resolve()

    @staticmethod
    def _sync_workspace_backend(workspace: Path, backend_name: str) -> None:
        """Persist backend into workspace contract to match runtime policy reads."""
        project_data = load_project_data(workspace)
        if project_data is None:
            project_name = workspace.name or workspace.resolve().name or "workspace"
            project_data = default_project_data(project_name=project_name, selected_tools=[])

        toolchain = project_data.get("toolchain")
        if not isinstance(toolchain, dict):
            toolchain = {}
            project_data["toolchain"] = toolchain

        toolchain["backend"] = backend_name
        write_project_data(workspace, project_data)

    @staticmethod
    def _effective_backend(workspace: Path) -> str:
        """Return backend from workspace contract when present, else legacy config."""
        workspace = BackendConfigCmd._normalize_workspace(workspace)
        paths = workspace_paths(workspace)
        if paths.project_file.exists():
            return read_tool_backend(workspace)
        return get_default_backend(workspace)

    @staticmethod
    def set_backend(workspace: Path, backend_name: str) -> int:
        """
        Set default backend for workspace.

        Args:
            workspace: Workspace root path
            backend_name: Backend name (system, managed, or nix)

        Returns:
            Exit code (0 on success)
        """
        try:
            workspace = BackendConfigCmd._normalize_workspace(workspace)
            normalized = backend_name.strip().lower()
            if normalized not in ("system", "managed", "nix"):
                raise ValueError(f"Unknown backend: {backend_name}")

            # Keep legacy config in sync for backward compatibility.
            set_default_backend(workspace, normalized)
            # Runtime policy reads backend from .saxoflow/project.yaml.
            BackendConfigCmd._sync_workspace_backend(workspace, normalized)

            print(f"✓ Backend set to '{normalized}' for workspace: {workspace}")
            return 0
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            return 1
        except (OSError, IOError) as e:
            print(f"✗ Failed to write config: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def get_backend(workspace: Path) -> int:
        """
        Get current backend for workspace.

        Args:
            workspace: Workspace root path

        Returns:
            Exit code (0 on success)
        """
        try:
            workspace = BackendConfigCmd._normalize_workspace(workspace)
            backend_name = BackendConfigCmd._effective_backend(workspace)
            print(f"{backend_name}")
            return 0
        except Exception as e:
            print(f"✗ Error reading backend config: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def show_backend_info(workspace: Path, backend_name: Optional[str] = None) -> int:
        """
        Show detailed backend information.

        Args:
            workspace: Workspace root path
            backend_name: Optional backend to inspect (default: current backend)

        Returns:
            Exit code (0 on success)
        """
        try:
            workspace = BackendConfigCmd._normalize_workspace(workspace)
            if backend_name is None:
                backend_name = BackendConfigCmd._effective_backend(workspace)

            backend = create_backend(backend_name, workspace_root=workspace)

            info = {
                "name": backend.name,
                "type": backend.__class__.__name__,
                "workspace_root": str(workspace),
            }

            # Backend-specific info
            if backend.name == "nix":
                flake_path = workspace / "flake.nix"
                lock_path = workspace / "flake.lock"
                info["flake_exists"] = flake_path.exists()
                info["lock_exists"] = lock_path.exists()
                info["flake_path"] = str(flake_path)
                info["lock_path"] = str(lock_path)
            elif backend.name == "managed":
                bin_dir = workspace / ".saxoflow" / "bin"
                info["bin_dir"] = str(bin_dir)
                info["bin_dir_exists"] = bin_dir.exists()
                if bin_dir.exists():
                    shims = list(bin_dir.iterdir())
                    info["shim_count"] = len(shims)
                    info["shims"] = [s.name for s in shims]
                else:
                    info["shim_count"] = 0
                    info["shims"] = []

            print(json.dumps(info, indent=2))
            return 0
        except Exception as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            return 1

    @staticmethod
    def list_backends() -> int:
        """
        List all available backends with descriptions.

        Returns:
            Exit code (0 on success)
        """
        backends = {
            "system": {
                "description": "Use system-installed tools directly from PATH",
                "characteristics": [
                    "Zero overhead",
                    "No workspace modifications",
                    "Tools must be pre-installed",
                    "No reproducibility guarantee"
                ],
            },
            "managed": {
                "description": "Manage tool installations in workspace .saxoflow/bin/",
                "characteristics": [
                    "Workspace-isolated",
                    "Explicit tool inventory",
                    "Portable across machines",
                    "Requires separate installation"
                ],
            },
            "nix": {
                "description": "Use Nix devShell for reproducible environments",
                "characteristics": [
                    "Reproducible with flake.lock",
                    "Cross-platform support",
                    "Declarative tool specification",
                    "Requires Nix installation",
                    "Deferred activation via 'nix develop'"
                ],
            },
        }

        print("\nAvailable Backends:\n")
        for name, details in backends.items():
            print(f"  {name:12} - {details['description']}")
            print(f"             Characteristics:")
            for char in details["characteristics"]:
                print(f"               • {char}")
            print()

        return 0
