"""Runtime path helpers for installed SaxoFlow applications.

This module keeps user-owned workspace state separate from the installed
application source and bundled read-only resources.
"""

from __future__ import annotations

import json
import os
from importlib import resources
from pathlib import Path
from typing import Optional, Union

WORKSPACE_ENV_VAR = "SAXOFLOW_WORKSPACE"
CONFIG_HOME_ENV_VAR = "SAXOFLOW_CONFIG_HOME"
AGENT_LOG_DIR_ENV_VAR = "SAXOFLOW_AGENT_LOG_DIR"
DEFAULT_WORKSPACE_NAME = "SaxoFlow"
CONFIG_FILENAME = "config.json"


def repository_root() -> Path:
    """Return the source checkout root when running from an editable clone."""
    return Path(__file__).resolve().parent.parent


def default_workspace() -> Path:
    """Return the default user-visible SaxoFlow workspace path."""
    return Path.home() / DEFAULT_WORKSPACE_NAME


def user_config_dir() -> Path:
    """Return the per-user SaxoFlow config directory."""
    override = os.environ.get(CONFIG_HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()

    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config).expanduser() / "saxoflow"

    return Path.home() / ".config" / "saxoflow"


def config_path() -> Path:
    """Return the path used for persistent SaxoFlow runtime config."""
    return user_config_dir() / CONFIG_FILENAME


def read_runtime_config(path: Optional[Path] = None) -> dict:
    """Return persisted SaxoFlow runtime config as a dictionary."""
    cfg_path = path or config_path()
    if not cfg_path.exists():
        return {}

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_runtime_config(data: dict, path: Optional[Path] = None) -> None:
    """Persist SaxoFlow runtime config."""
    cfg_path = path or config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_runtime_config(updates: dict, path: Optional[Path] = None) -> dict:
    """Merge *updates* into persisted runtime config and return the result."""
    data = read_runtime_config(path)
    data.update(updates)
    write_runtime_config(data, path)
    return data


def read_saved_workspace(path: Optional[Path] = None) -> Optional[Path]:
    """Return a workspace path saved in config, if one exists."""
    data = read_runtime_config(path)

    workspace = data.get("workspace") if isinstance(data, dict) else None
    if not workspace:
        return None
    return Path(str(workspace)).expanduser()


def save_workspace_path(workspace: Path, path: Optional[Path] = None) -> None:
    """Persist the preferred workspace path for later SaxoFlow launches."""
    update_runtime_config({"workspace": str(Path(workspace).expanduser())}, path)


def default_agent_log_dir(workspace: Optional[Union[str, Path]] = None) -> Path:
    """Return the default directory for user-facing agent session logs."""
    root = Path(workspace).expanduser().resolve() if workspace else resolve_workspace(create=False)
    return root / ".saxoflow" / "agent_sessions"


def resolve_agent_log_dir(
    workspace: Optional[Union[str, Path]] = None,
    *,
    create: bool = False,
) -> Path:
    """Resolve the active agent session log directory."""
    selected = os.environ.get(AGENT_LOG_DIR_ENV_VAR)
    if selected is None:
        selected = read_runtime_config().get("agent_log_dir")

    resolved = (
        Path(str(selected)).expanduser().resolve()
        if selected
        else default_agent_log_dir(workspace)
    )
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_workspace(
    workspace: Optional[Union[str, Path]] = None,
    *,
    create: bool = False,
) -> Path:
    """Resolve the active workspace using CLI, env, config, then default."""
    selected: Optional[Union[str, Path]] = workspace

    if selected is None:
        selected = os.environ.get(WORKSPACE_ENV_VAR)
    if selected is None:
        selected = read_saved_workspace()
    if selected is None:
        selected = default_workspace()

    resolved = Path(selected).expanduser().resolve()
    if create:
        ensure_workspace(resolved)
    return resolved


def ensure_workspace(workspace: Path) -> Path:
    """Create the standard user workspace layout if it does not exist."""
    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "projects").mkdir(exist_ok=True)
    (root / "examples").mkdir(exist_ok=True)
    (root / ".saxoflow").mkdir(exist_ok=True)

    readme = root / "README.md"
    if not readme.exists():
        readme.write_text(_workspace_readme(), encoding="utf-8")

    copy_bundled_examples(root / "examples")
    return root


def _workspace_readme() -> str:
    """Return the starter README created in a new workspace."""
    return (
        "# SaxoFlow Workspace\n\n"
        "This directory is for your SaxoFlow projects and learning files.\n\n"
        "## Layout\n\n"
        "- `projects/`: create or keep your own unit projects here.\n"
        "- `examples/`: starter examples copied from the installed SaxoFlow package.\n"
        "- `.saxoflow/`: local SaxoFlow state, teach progress, and indexes.\n\n"
        "Run `saxoflow unit projects/my_counter` to create a new project.\n"
    )


def copy_bundled_examples(destination: Path) -> None:
    """Copy packaged starter examples into *destination* without overwriting."""
    destination.mkdir(parents=True, exist_ok=True)
    examples_root = _resource_root("saxoflow", "examples")
    if examples_root is None or not examples_root.is_dir():
        return

    _copy_resource_children(examples_root, destination)


def _copy_resource_children(source, destination: Path) -> None:
    """Copy importlib resource children into a normal filesystem directory."""
    for child in source.iterdir():
        if child.name.startswith("__"):
            continue
        target = destination / child.name
        if child.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _copy_resource_children(child, target)
        elif child.is_file() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(child.read_bytes())


def bundled_packs_dir() -> Path:
    """Return the directory containing bundled teaching packs."""
    dev_packs = repository_root() / "packs"
    if (dev_packs / "ethz_ic_design" / "pack.yaml").exists():
        return dev_packs

    package_root = _resource_root("packs")
    if package_root is not None:
        try:
            return Path(package_root)
        except TypeError:
            pass

    return dev_packs


def resolve_packs_dir(packs_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolve an explicit or bundled teach packs directory."""
    if packs_dir:
        return Path(packs_dir).expanduser().resolve()
    return bundled_packs_dir()


def find_template_path(name: str, *, legacy_path: Optional[Path] = None) -> Optional[Path]:
    """Find a bundled template as a filesystem path when available."""
    candidates = []
    if legacy_path is not None:
        candidates.append(Path(legacy_path))
    candidates.append(repository_root() / "templates" / name)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    resource = _resource_root("templates", name)
    if resource is not None and resource.is_file():
        try:
            return Path(resource)
        except TypeError:
            return None

    return None


def _resource_root(package: str, *parts: str):
    """Return an importlib resource root, or None when unavailable."""
    try:
        root = resources.files(package)
    except (ModuleNotFoundError, AttributeError):
        return None

    for part in parts:
        root = root.joinpath(part)
    return root
