"""Prompt registry contract for package prompt bundles.

P4.13 introduces a lightweight registry that names prompt bundles and validates
that every referenced prompt asset exists under the package prompts directory.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml


class PromptRegistryError(ValueError):
    """Raised when prompt registry metadata is malformed or incomplete."""


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PromptRegistryError(f"Prompt registry field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromptRegistryError(f"Prompt registry field `{field_name}` must be a non-empty string.")
    return value.strip()


def _as_string_list(value: Any, field_name: str) -> Tuple[str, ...]:
    if not isinstance(value, list):
        raise PromptRegistryError(f"Prompt registry field `{field_name}` must be a list of strings.")
    return tuple(_as_string(item, field_name) for item in value)


@dataclass(frozen=True)
class PromptRegistryEntry:
    """One named prompt bundle in the prompt registry."""

    name: str
    role: str
    templates: Tuple[str, ...]
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "templates": list(self.templates),
        }
        if self.description is not None:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class PromptRegistry:
    """Validated prompt registry and its source path."""

    entries: Mapping[str, PromptRegistryEntry]
    source_path: Path
    prompt_dir: Path

    @classmethod
    def builtins(cls) -> "PromptRegistry":
        prompt_dir = Path(__file__).resolve().parents[1] / "prompts"
        return cls.load(prompt_dir / "registry.yaml", prompt_dir=prompt_dir)

    @classmethod
    def load(cls, registry_path: Path | str, *, prompt_dir: Path | str) -> "PromptRegistry":
        registry_file = Path(registry_path).expanduser().resolve()
        prompt_dir_path = Path(prompt_dir).expanduser().resolve()

        if not registry_file.is_file():
            raise PromptRegistryError(f"Prompt registry file not found: {registry_file}")
        if not prompt_dir_path.is_dir():
            raise PromptRegistryError(f"Prompt directory not found: {prompt_dir_path}")

        try:
            payload = yaml.safe_load(registry_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise PromptRegistryError(f"Could not parse prompt registry YAML: {registry_file}") from exc
        except OSError as exc:
            raise PromptRegistryError(f"Could not read prompt registry file: {registry_file}") from exc

        data = _as_mapping(payload, "prompt_registry")
        if int(data.get("version", 1)) != 1:
            raise PromptRegistryError("Prompt registry version must be 1.")

        prompts = _as_mapping(data.get("prompts"), "prompt_registry.prompts")
        entries: Dict[str, PromptRegistryEntry] = {}
        for name, entry_data in prompts.items():
            entry_name = _as_string(name, "prompt_registry.prompts name")
            entry_map = _as_mapping(entry_data, f"prompt_registry.prompts.{entry_name}")
            role = _as_string(entry_map.get("role"), f"prompt_registry.prompts.{entry_name}.role")
            templates = _as_string_list(
                entry_map.get("templates"), f"prompt_registry.prompts.{entry_name}.templates"
            )
            description = entry_map.get("description")
            if description is not None:
                description = _as_string(description, f"prompt_registry.prompts.{entry_name}.description")

            for template in templates:
                template_path = (prompt_dir_path / template).resolve()
                if not template_path.is_file():
                    raise PromptRegistryError(
                        f"Prompt registry entry `{entry_name}` references missing template `{template}`."
                    )

            entries[entry_name] = PromptRegistryEntry(
                name=entry_name,
                role=role,
                templates=templates,
                description=description,
            )

        return cls(entries=entries, source_path=registry_file, prompt_dir=prompt_dir_path)

    def get(self, name: str) -> PromptRegistryEntry:
        normalized = _as_string(name, "prompt_registry.name")
        try:
            return self.entries[normalized]
        except KeyError as exc:
            known = ", ".join(sorted(self.entries.keys()))
            raise PromptRegistryError(f"Unknown prompt bundle `{normalized}`. Known: {known}") from exc

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "prompt_dir": str(self.prompt_dir),
            "prompts": {name: entry.to_dict() for name, entry in self.entries.items()},
        }
