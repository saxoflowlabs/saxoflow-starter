"""Tool backend factory and exports."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .base import ToolBackend, ToolResolution
from .managed_backend import ManagedToolBackend
from .nix_backend import NixToolBackend
from .system_backend import SystemToolBackend


def create_backend(name: str, workspace_root: Path | str = ".") -> ToolBackend:
    """Create a backend implementation from workspace policy name."""
    normalized = (name or "system").strip().lower()
    if normalized == "managed":
        return ManagedToolBackend(workspace_root=workspace_root)
    if normalized == "nix":
        return NixToolBackend(workspace_root=workspace_root)
    return SystemToolBackend(workspace_root=workspace_root)


def set_default_backend(workspace_root: Path | str, backend_name: str) -> None:
    """
    Set the default tool backend for a workspace.

    Args:
        workspace_root: Path to workspace root directory.
        backend_name: Name of backend ("system", "managed", or "nix").

    Raises:
        ValueError: If backend_name is not recognized.
    """
    normalized = backend_name.strip().lower()
    if normalized not in ("system", "managed", "nix"):
        raise ValueError(f"Unknown backend: {backend_name}")

    workspace = Path(workspace_root)
    config_dir = workspace / ".saxoflow"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config"
    config_data = {"backend": normalized}

    try:
        config_file.write_text(json.dumps(config_data, indent=2), encoding="utf-8")
    except (OSError, IOError) as e:
        # Log but don't raise - allow graceful degradation
        print(f"Warning: Could not write backend config: {e}")


def get_default_backend(workspace_root: Path | str) -> str:
    """
    Get the default tool backend for a workspace.

    Checks in order:
    1. SAXOFLOW_BACKEND environment variable
    2. Workspace .saxoflow/config file
    3. Default to "system"

    Args:
        workspace_root: Path to workspace root directory.

    Returns:
        Backend name ("system", "managed", or "nix").
    """
    # Check environment variable first
    if env_backend := os.environ.get("SAXOFLOW_BACKEND"):
        normalized = env_backend.strip().lower()
        if normalized in ("system", "managed", "nix"):
            return normalized

    # Check workspace config
    workspace = Path(workspace_root)
    config_file = workspace / ".saxoflow" / "config"

    if config_file.exists():
        try:
            config_data = json.loads(config_file.read_text(encoding="utf-8"))
            if isinstance(config_data, dict):
                backend = config_data.get("backend", "").strip().lower()
                if backend in ("system", "managed", "nix"):
                    return backend
        except (json.JSONDecodeError, OSError, IOError):
            # Config file exists but is invalid
            pass

    # Default fallback
    return "system"


__all__ = [
    "ToolBackend",
    "ToolResolution",
    "SystemToolBackend",
    "ManagedToolBackend",
    "NixToolBackend",
    "create_backend",
    "set_default_backend",
    "get_default_backend",
]
