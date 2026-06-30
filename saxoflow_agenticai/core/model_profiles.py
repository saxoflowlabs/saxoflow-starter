"""Model profile loader with project, user, and packaged-default precedence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

import yaml

from saxoflow.runtime_paths import user_config_dir

DEFAULT_MODEL_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "model_config.yaml"
PROJECT_PROFILE_CANDIDATES = (
    Path(".saxoflow") / "saxoflow_models.yaml",
    Path("saxoflow_models.yaml"),
)
USER_PROFILE_CANDIDATES = (
    "saxoflow_models.yaml",
    "model_config.yaml",
)


class ModelProfileLoadError(ValueError):
    """Raised when a model profile YAML cannot be loaded or validated."""


@dataclass(frozen=True)
class ModelProfileSources:
    """Resolved source paths used to build the merged model profile mapping."""

    default_path: Path
    user_path: Optional[Path]
    project_path: Optional[Path]


@dataclass(frozen=True)
class ModelProfiles:
    """Merged model profile mapping plus provenance of loaded sources."""

    data: Mapping[str, Any]
    sources: ModelProfileSources

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.data)


def _load_yaml_mapping(path: Path, field_name: str) -> Dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ModelProfileLoadError(f"Could not read model profile file `{path}`.") from exc
    except yaml.YAMLError as exc:
        raise ModelProfileLoadError(f"Could not parse model profile file `{path}` as YAML.") from exc

    if not isinstance(raw, Mapping):
        raise ModelProfileLoadError(
            f"Model profile field `{field_name}` must be a mapping at top-level in `{path}`."
        )
    return dict(raw)


def _merge_dicts(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_dicts(dict(merged[key]), dict(value))
        else:
            merged[key] = value
    return merged


def _resolve_project_profile_path(project_root: Optional[Union[str, Path]]) -> Optional[Path]:
    if project_root is None:
        return None
    root = Path(project_root).expanduser().resolve()
    for relative in PROJECT_PROFILE_CANDIDATES:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def _resolve_user_profile_path(user_dir: Optional[Union[str, Path]] = None) -> Optional[Path]:
    root = Path(user_dir).expanduser() if user_dir is not None else user_config_dir()
    for filename in USER_PROFILE_CANDIDATES:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None


def load_model_profiles(
    *,
    project_root: Optional[Union[str, Path]] = None,
    user_dir: Optional[Union[str, Path]] = None,
    default_path: Optional[Union[str, Path]] = None,
) -> ModelProfiles:
    """Load model profiles with precedence: project > user > packaged defaults."""
    resolved_default = Path(default_path).expanduser().resolve() if default_path else DEFAULT_MODEL_CONFIG_PATH
    if not resolved_default.is_file():
        raise ModelProfileLoadError(f"Default model profile file not found: `{resolved_default}`.")

    default_data = _load_yaml_mapping(resolved_default, "model_profiles.defaults")

    user_path = _resolve_user_profile_path(user_dir)
    user_data: Dict[str, Any] = {}
    if user_path is not None:
        user_data = _load_yaml_mapping(user_path, "model_profiles.user")

    project_path = _resolve_project_profile_path(project_root)
    project_data: Dict[str, Any] = {}
    if project_path is not None:
        project_data = _load_yaml_mapping(project_path, "model_profiles.project")

    merged = _merge_dicts(default_data, user_data)
    merged = _merge_dicts(merged, project_data)

    return ModelProfiles(
        data=merged,
        sources=ModelProfileSources(
            default_path=resolved_default,
            user_path=user_path,
            project_path=project_path,
        ),
    )
