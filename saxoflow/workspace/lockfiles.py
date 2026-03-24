"""Lockfile generation helpers for SaxoFlow workspaces."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

import yaml

from saxoflow.tools.definitions import APT_TOOLS, SCRIPT_TOOLS

from .schema import SCHEMA_VERSION, normalize_selected_tools, workspace_paths


def _tool_source(tool: str) -> str:
    if tool in APT_TOOLS:
        return "apt"
    if tool in SCRIPT_TOOLS:
        return "recipe"
    return "unknown"


def build_toolchain_lock(selected_tools: Iterable[str], *, backend: str = "system") -> Dict[str, Any]:
    """Build deterministic toolchain lock data for the selected tools."""
    tools = normalize_selected_tools(list(selected_tools))
    return {
        "schema_version": SCHEMA_VERSION,
        "toolchain": {
            "backend": backend,
            "tools": [
                {
                    "name": tool,
                    "version": "unresolved",
                    "source": _tool_source(tool),
                }
                for tool in tools
            ],
        },
    }


def build_models_lock() -> Dict[str, Any]:
    """Build default models lock placeholder data."""
    return {
        "schema_version": SCHEMA_VERSION,
        "models": {
            "selection_policy": "inherit",
            "catalog": [],
        },
    }


def _write_yaml(path: Path, data: Dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def write_lockfiles(root: Path | str, project_data: Dict[str, Any]) -> Tuple[Path, Path]:
    """Write deterministic toolchain/models lockfiles for *root*."""
    paths = workspace_paths(root)
    toolchain = project_data.get("toolchain", {}) if isinstance(project_data, dict) else {}
    selected_tools = toolchain.get("selected_tools", []) if isinstance(toolchain, dict) else []
    backend = toolchain.get("backend", "system") if isinstance(toolchain, dict) else "system"

    toolchain_lock = build_toolchain_lock(selected_tools, backend=backend)
    models_lock = build_models_lock()
    return (
        _write_yaml(paths.toolchain_lock_file, toolchain_lock),
        _write_yaml(paths.models_lock_file, models_lock),
    )