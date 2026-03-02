# saxoflow/teach/pack.py
"""
Pack loader: reads ``pack.yaml`` and all referenced lesson YAML files,
validates them, and returns a fully populated :class:`PackDef`.

Design rules
------------
- Raises :class:`PackLoadError` (a subclass of ``ValueError``) with a
  human-readable message on any schema violation so CLI commands can
  surface helpful errors without a full traceback.
- Uses only ``PyYAML`` (already a project dependency) -- no additional
  packages required.
- All paths returned inside :class:`PackDef` are absolute
  ``pathlib.Path`` objects.

Python: 3.9+
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import yaml

from saxoflow.teach.session import (
    AgentInvocationDef,
    CheckDef,
    CommandDef,
    PackDef,
    StepDef,
)

__all__ = ["load_pack", "PackLoadError"]

logger = logging.getLogger("saxoflow.teach.pack")

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PackLoadError(ValueError):
    """Raised when a pack or lesson YAML fails validation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_pack(pack_path: Path) -> PackDef:
    """Load and validate a teaching pack from *pack_path*.

    Parameters
    ----------
    pack_path:
        Absolute path to the pack root directory (contains
        ``pack.yaml``).

    Returns
    -------
    PackDef
        Fully populated pack with all lessons loaded and validated.

    Raises
    ------
    PackLoadError
        When required keys are missing or types are incorrect.
    FileNotFoundError
        When ``pack_path`` or ``pack.yaml`` does not exist.
    """
    pack_path = pack_path.resolve()
    yaml_file = pack_path / "pack.yaml"
    if not yaml_file.exists():
        raise FileNotFoundError(f"pack.yaml not found at: {yaml_file}")

    raw = _load_yaml(yaml_file)
    _require_keys(raw, ["id", "name", "version", "authors", "description", "lessons"], yaml_file)

    docs_dir = pack_path / "docs"
    lessons_dir = pack_path / "lessons"

    steps: List[StepDef] = []
    lesson_files: List[str] = _as_list(raw.get("lessons", []), "lessons", yaml_file)
    for lesson_file in lesson_files:
        lesson_path = lessons_dir / lesson_file
        if not lesson_path.exists():
            raise PackLoadError(
                f"Lesson file declared in pack.yaml not found:\n"
                f"  Expected: {lesson_path}\n"
                f"  Check the 'lessons:' list in {yaml_file}"
            )
        step = _load_step(lesson_path)
        steps.append(step)

    if not steps:
        raise PackLoadError(f"Pack '{raw['id']}' declares no lessons in {yaml_file}")

    logger.debug("Loaded pack '%s' with %d steps from %s", raw["id"], len(steps), pack_path)
    return PackDef(
        id=str(raw["id"]),
        name=str(raw["name"]),
        version=str(raw.get("version", "1.0")),
        authors=_as_list(raw.get("authors", []), "authors", yaml_file),
        description=str(raw.get("description", "")),
        docs=_as_list(raw.get("docs", []), "docs", yaml_file),
        steps=steps,
        docs_dir=docs_dir,
        pack_path=pack_path,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_step(lesson_path: Path) -> StepDef:
    """Load and validate one lesson YAML into a :class:`StepDef`."""
    raw = _load_yaml(lesson_path)
    _require_keys(raw, ["id", "title", "goal"], lesson_path)

    commands = [_parse_command(c, lesson_path) for c in raw.get("commands", [])]
    agent_invocations = [_parse_agent_inv(a, lesson_path) for a in raw.get("agent_invocations", [])]
    success = [_parse_check(s, lesson_path) for s in raw.get("success", [])]
    read = _as_list(raw.get("read", []), "read", lesson_path)
    hints = _as_list(raw.get("hints", []), "hints", lesson_path)

    return StepDef(
        id=str(raw["id"]),
        title=str(raw["title"]),
        goal=str(raw["goal"]),
        read=read,
        commands=commands,
        agent_invocations=agent_invocations,
        success=success,
        hints=hints,
        notes=str(raw.get("notes", "")),
    )


def _parse_command(raw: Any, source: Path) -> CommandDef:
    """Parse one entry from a lesson's ``commands:`` list."""
    if isinstance(raw, str):
        # Allow bare string shorthand: "iverilog -g2012 ..."
        return CommandDef(native=raw)
    if not isinstance(raw, dict):
        raise PackLoadError(
            f"Each entry under 'commands:' must be a string or mapping.\n"
            f"Got: {type(raw).__name__!r} in {source}"
        )
    native = raw.get("native", "")
    if not native:
        raise PackLoadError(
            f"Command entry missing required 'native' key in {source}"
        )
    return CommandDef(
        native=str(native),
        preferred=str(raw["preferred"]) if raw.get("preferred") else None,
        use_preferred_if_available=bool(raw.get("use_preferred_if_available", True)),
    )


def _parse_agent_inv(raw: Any, source: Path) -> AgentInvocationDef:
    """Parse one entry from a lesson's ``agent_invocations:`` list."""
    if not isinstance(raw, dict):
        raise PackLoadError(
            f"Each entry under 'agent_invocations:' must be a mapping.\n"
            f"Got: {type(raw).__name__!r} in {source}"
        )
    agent_key = raw.get("agent_key", "")
    if not agent_key:
        raise PackLoadError(
            f"Agent invocation entry missing required 'agent_key' in {source}"
        )
    raw_args = raw.get("args", {})
    if not isinstance(raw_args, dict):
        raise PackLoadError(
            f"'args' under agent_invocations must be a mapping in {source}"
        )
    args: Dict[str, str] = {str(k): str(v) for k, v in raw_args.items()}
    return AgentInvocationDef(
        agent_key=str(agent_key),
        args=args,
        description=str(raw.get("description", "")),
    )


def _parse_check(raw: Any, source: Path) -> CheckDef:
    """Parse one entry from a lesson's ``success:`` list."""
    if not isinstance(raw, dict):
        raise PackLoadError(
            f"Each entry under 'success:' must be a mapping.\n"
            f"Got: {type(raw).__name__!r} in {source}"
        )
    kind = raw.get("kind", "")
    if not kind:
        raise PackLoadError(
            f"Success check entry missing required 'kind' key in {source}"
        )
    return CheckDef(
        kind=str(kind),
        pattern=str(raw.get("pattern", "")),
        file=str(raw.get("file", "")),
    )


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load YAML from *path*, raising :class:`PackLoadError` on parse failure."""
    try:
        content = path.read_text(encoding="utf-8")
        result = yaml.safe_load(content)
        if not isinstance(result, dict):
            raise PackLoadError(f"YAML file must define a mapping at top level: {path}")
        return result
    except yaml.YAMLError as exc:  # pragma: no cover - syntax errors in authored pack
        raise PackLoadError(f"YAML parse error in {path}:\n{exc}") from exc


def _require_keys(data: Dict[str, Any], keys: List[str], source: Path) -> None:
    """Raise :class:`PackLoadError` if any of *keys* is missing from *data*."""
    missing = [k for k in keys if k not in data]
    if missing:
        raise PackLoadError(
            f"Required key(s) missing in {source}: {', '.join(missing)}"
        )


def _as_list(value: Any, field_name: str, source: Path) -> List[Any]:
    """Coerce *value* to a list; raise :class:`PackLoadError` if not list-like."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    raise PackLoadError(
        f"Field '{field_name}' must be a list in {source}; got {type(value).__name__!r}"
    )
