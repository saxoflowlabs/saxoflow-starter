"""Declarative custom agent loader for workspace or user-defined agent YAML files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

import yaml

from saxoflow.runtime_paths import user_config_dir
from saxoflow_agenticai.core.agent_tool_registry import AgentToolRegistry


PROJECT_CUSTOM_AGENT_DIR = Path(".saxoflow") / "agents"
USER_CUSTOM_AGENT_DIRNAME = "agents"


class CustomAgentLoadError(ValueError):
    """Raised when a declarative custom agent definition is malformed."""


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CustomAgentLoadError(f"Custom agent field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CustomAgentLoadError(f"Custom agent field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CustomAgentLoadError(f"Custom agent field `{field_name}` must be a list of strings.")
    return [_as_string(item, field_name) for item in value]


def _validate_capability_names(capabilities: list[str], field_name: str) -> tuple[str, ...]:
    registry = AgentToolRegistry.builtins()
    try:
        return registry.validate_capability_names(capabilities)
    except Exception as exc:
        raise CustomAgentLoadError(f"Custom agent field `{field_name}` is invalid: {exc}") from exc


@dataclass(frozen=True)
class CustomAgentDefinition:
    """Normalized declarative custom agent contract."""

    name: str
    description: Optional[str]
    model_profile: str
    graph_template: str
    prompt_system: str
    prompt_task: str
    input_schema: Optional[str]
    output_schema: Optional[str]
    tools_allow: tuple[str, ...]
    tools_deny: tuple[str, ...]
    approvals: Mapping[str, str]
    source_path: Optional[Path]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "model_profile": self.model_profile,
            "graph_template": self.graph_template,
            "prompt": {
                "system": self.prompt_system,
                "task": self.prompt_task,
            },
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "tools": {
                "allow": list(self.tools_allow),
                "deny": list(self.tools_deny),
            },
            "approvals": dict(self.approvals),
            "source_path": str(self.source_path) if self.source_path else None,
        }


def load_custom_agent_mapping(
    raw_mapping: Mapping[str, Any],
    *,
    source_path: Optional[Path] = None,
) -> CustomAgentDefinition:
    """Validate and normalize one custom agent mapping payload."""
    data = _as_mapping(raw_mapping, "custom_agent")

    prompt = _as_mapping(data.get("prompt"), "custom_agent.prompt")
    prompt_system = _as_string(prompt.get("system"), "custom_agent.prompt.system")
    prompt_task = _as_string(prompt.get("task"), "custom_agent.prompt.task")

    tools = _as_mapping(data.get("tools") or {}, "custom_agent.tools")
    tools_allow = _validate_capability_names(
        _string_list(tools.get("allow"), "custom_agent.tools.allow"),
        "custom_agent.tools.allow",
    )
    tools_deny = _validate_capability_names(
        _string_list(tools.get("deny"), "custom_agent.tools.deny"),
        "custom_agent.tools.deny",
    )

    approvals_raw = data.get("approvals") or {}
    approvals_map = _as_mapping(approvals_raw, "custom_agent.approvals")
    approvals: Dict[str, str] = {}
    for capability, status in approvals_map.items():
        capability_name = _as_string(capability, "custom_agent.approvals capability")
        approval_state = _as_string(status, f"custom_agent.approvals.{capability_name}").lower()
        if approval_state not in {"required", "optional"}:
            raise CustomAgentLoadError(
                f"Custom agent approval `{capability_name}` must be 'required' or 'optional'."
            )
        approvals[capability_name] = approval_state

    return CustomAgentDefinition(
        name=_as_string(data.get("name"), "custom_agent.name"),
        description=_optional_string(data.get("description"), "custom_agent.description"),
        model_profile=_as_string(data.get("model_profile"), "custom_agent.model_profile"),
        graph_template=_as_string(data.get("graph_template"), "custom_agent.graph_template"),
        prompt_system=prompt_system,
        prompt_task=prompt_task,
        input_schema=_optional_string(data.get("input_schema"), "custom_agent.input_schema"),
        output_schema=_optional_string(data.get("output_schema"), "custom_agent.output_schema"),
        tools_allow=tools_allow,
        tools_deny=tools_deny,
        approvals=approvals,
        source_path=source_path,
    )


def load_custom_agent_file(path: Path | str) -> CustomAgentDefinition:
    """Load one declarative custom agent YAML file and return its normalized contract."""
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise CustomAgentLoadError(f"Custom agent file not found: {file_path}")

    try:
        payload = yaml.safe_load(file_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CustomAgentLoadError(f"Could not parse custom agent YAML: {file_path}") from exc
    except OSError as exc:
        raise CustomAgentLoadError(f"Could not read custom agent file: {file_path}") from exc

    if not isinstance(payload, Mapping):
        raise CustomAgentLoadError(
            f"Custom agent file `{file_path}` must contain a top-level mapping."
        )

    return load_custom_agent_mapping(payload, source_path=file_path)


def _normalized_agent_name(agent_name: str) -> str:
    normalized = _as_string(agent_name, "custom_agent.name")
    if "/" in normalized or "\\" in normalized:
        raise CustomAgentLoadError("Custom agent name must not include path separators.")
    return normalized


def _resolve_project_agent_path(agent_name: str, project_root: Path | str | None) -> Path:
    root = Path(project_root).expanduser().resolve() if project_root is not None else Path.cwd().resolve()
    return root / PROJECT_CUSTOM_AGENT_DIR / f"{agent_name}.yaml"


def _resolve_user_agent_path(agent_name: str, user_dir: Path | str | None) -> Path:
    root = Path(user_dir).expanduser() if user_dir is not None else user_config_dir()
    return root / USER_CUSTOM_AGENT_DIRNAME / f"{agent_name}.yaml"


def resolve_custom_agent_definition(
    agent_name: str,
    *,
    project_root: Path | str | None = None,
    user_dir: Path | str | None = None,
) -> CustomAgentDefinition:
    """Resolve a custom agent by name with precedence: project workspace > user config."""
    normalized_name = _normalized_agent_name(agent_name)

    project_path = _resolve_project_agent_path(normalized_name, project_root)
    if project_path.is_file():
        return load_custom_agent_file(project_path)

    user_path = _resolve_user_agent_path(normalized_name, user_dir)
    if user_path.is_file():
        return load_custom_agent_file(user_path)

    raise CustomAgentLoadError(
        "Custom agent definition not found for "
        f"`{normalized_name}` in project path `{project_path}` or user path `{user_path}`."
    )
