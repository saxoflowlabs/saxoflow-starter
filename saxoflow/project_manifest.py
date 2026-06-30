"""Validated SaxoFlow project manifest schema and discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

import yaml

from saxoflow.schemas.project import infer_repository_topology


MANIFEST_SCHEMA_VERSION = 1
MANIFEST_FILENAMES = (
    "saxoflow_project.yaml",
    "saxoflow_project.yml",
    "project.yaml",
    "project.yml",
)


class ManifestError(ValueError):
    """Raised when a project manifest is missing required data or is malformed."""


def _load_manifest_mapping(path: Path) -> Dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ManifestError(f"Could not read manifest file `{path}`.") from exc
    except yaml.YAMLError as exc:
        raise ManifestError(f"Could not parse manifest file `{path}` as YAML.") from exc

    if not isinstance(raw, Mapping):
        raise ManifestError(f"Manifest file `{path}` must contain a mapping at the top level.")
    return dict(raw)


def _manifest_candidates(root: Path) -> Tuple[Path, ...]:
    return tuple(root / filename for filename in MANIFEST_FILENAMES)


def discover_manifest_path(root: Path) -> Optional[Path]:
    """Return the first manifest file found in a project root, if any."""
    root = Path(root)
    for candidate in _manifest_candidates(root):
        if candidate.is_file():
            return candidate
    return None


def load_project_manifest(path: Path) -> "ProjectManifest":
    """Load and validate a project manifest from a YAML file."""
    return ProjectManifest.from_mapping(_load_manifest_mapping(Path(path)))


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ManifestError(f"Manifest field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Manifest field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"Manifest field `{field_name}` must be a string when set.")
    return value.strip()


@dataclass(frozen=True)
class ProjectIdentity:
    """Top-level project identity metadata."""

    name: str
    top_module: Optional[str] = None
    language: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProjectIdentity":
        data = _as_mapping(raw, "project")
        return cls(
            name=_as_string(data.get("name"), "project.name"),
            top_module=_optional_string(data.get("top_module"), "project.top_module"),
            language=_optional_string(data.get("language"), "project.language"),
        )

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"name": self.name}
        if self.top_module is not None:
            result["top_module"] = self.top_module
        if self.language is not None:
            result["language"] = self.language
        return result


@dataclass(frozen=True)
class SourceManifest:
    """Source manifest metadata and provider selection."""

    provider: str = "saxoflow"
    path: Optional[str] = None
    targets: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Optional[Mapping[str, Any]]) -> "SourceManifest":
        if raw is None:
            return cls()
        data = _as_mapping(raw, "source_manifest")
        targets = data.get("targets") or {}
        if not isinstance(targets, Mapping):
            raise ManifestError("Manifest field `source_manifest.targets` must be a mapping.")
        normalized_targets: Dict[str, str] = {}
        for key, value in targets.items():
            normalized_targets[_as_string(key, "source_manifest.targets key")] = _as_string(
                value,
                f"source_manifest.targets.{key}",
            )
        return cls(
            provider=_as_string(data.get("provider", "saxoflow"), "source_manifest.provider"),
            path=_optional_string(data.get("path"), "source_manifest.path"),
            targets=normalized_targets,
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"provider": self.provider, "targets": dict(self.targets)}
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(frozen=True)
class ProjectLogicalProfile:
    """Normalized repository profile inferred from manifest and workspace contents."""

    project_name: str
    top_modules: Tuple[str, ...]
    entrypoints: Tuple[str, ...]
    missing_files: Tuple[str, ...]
    role_map: Mapping[str, Tuple[str, ...]]
    flow_readiness: Mapping[str, str]
    manifest_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "project_name": self.project_name,
            "top_modules": list(self.top_modules),
            "entrypoints": list(self.entrypoints),
            "missing_files": list(self.missing_files),
            "role_map": {role: list(paths) for role, paths in self.role_map.items()},
            "flow_readiness": dict(self.flow_readiness),
        }
        if self.manifest_path is not None:
            data["manifest_path"] = self.manifest_path
        return data


@dataclass(frozen=True)
class ProjectManifest:
    """Validated SaxoFlow project manifest."""

    schema_version: int
    project: ProjectIdentity
    source_manifest: SourceManifest = field(default_factory=SourceManifest)
    artifacts: Mapping[str, Any] = field(default_factory=dict)
    constraints: Tuple[str, ...] = field(default_factory=tuple)
    tool_profiles: Mapping[str, Any] = field(default_factory=dict)
    target_profile: Optional[str] = None
    generated_artifact_policy: Mapping[str, Any] = field(default_factory=dict)
    approval_policy: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ProjectManifest":
        data = _as_mapping(raw, "manifest")
        schema_version = data.get("schema_version")
        if schema_version != MANIFEST_SCHEMA_VERSION:
            raise ManifestError(
                f"Unsupported schema_version `{schema_version}`; expected {MANIFEST_SCHEMA_VERSION}."
            )

        project = ProjectIdentity.from_mapping(data.get("project", {}))
        source_manifest = SourceManifest.from_mapping(data.get("source_manifest"))

        artifacts = data.get("artifacts") or {}
        if not isinstance(artifacts, Mapping):
            raise ManifestError("Manifest field `artifacts` must be a mapping.")

        constraints_value = data.get("constraints") or []
        if not isinstance(constraints_value, list) or not all(
            isinstance(item, str) and item.strip() for item in constraints_value
        ):
            raise ManifestError("Manifest field `constraints` must be a list of strings.")

        tool_profiles = data.get("tool_profiles") or {}
        if not isinstance(tool_profiles, Mapping):
            raise ManifestError("Manifest field `tool_profiles` must be a mapping.")

        generated_artifact_policy = data.get("generated_artifact_policy") or {}
        if not isinstance(generated_artifact_policy, Mapping):
            raise ManifestError(
                "Manifest field `generated_artifact_policy` must be a mapping."
            )

        approval_policy = data.get("approval_policy") or {}
        if not isinstance(approval_policy, Mapping):
            raise ManifestError("Manifest field `approval_policy` must be a mapping.")

        target_profile = data.get("target_profile")
        if target_profile is not None and (not isinstance(target_profile, str) or not target_profile.strip()):
            raise ManifestError("Manifest field `target_profile` must be a string when set.")

        return cls(
            schema_version=MANIFEST_SCHEMA_VERSION,
            project=project,
            source_manifest=source_manifest,
            artifacts=dict(artifacts),
            constraints=tuple(constraints_value),
            tool_profiles=dict(tool_profiles),
            target_profile=target_profile.strip() if isinstance(target_profile, str) else None,
            generated_artifact_policy=dict(generated_artifact_policy),
            approval_policy=dict(approval_policy),
        )

    @classmethod
    def from_path(cls, path: Path) -> "ProjectManifest":
        """Load a manifest from a YAML file or project root directory."""
        path = Path(path)
        manifest_path = discover_manifest_path(path) if path.is_dir() else path
        if manifest_path is None:
            raise ManifestError(f"No manifest file found under `{path}`.")
        return cls.from_mapping(_load_manifest_mapping(manifest_path))

    def infer_logical_profile(self, root: Path) -> ProjectLogicalProfile:
        """Infer a normalized repository profile from this manifest and workspace contents."""
        return infer_logical_project_profile(root, self)

    @classmethod
    def discover_from_root(cls, root: Path) -> Optional["ProjectManifest"]:
        """Load the first manifest discovered under a project root, if present."""
        manifest_path = discover_manifest_path(Path(root))
        if manifest_path is None:
            return None
        return cls.from_mapping(_load_manifest_mapping(manifest_path))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project": self.project.to_dict(),
            "source_manifest": self.source_manifest.to_dict(),
            "artifacts": dict(self.artifacts),
            "constraints": list(self.constraints),
            "tool_profiles": dict(self.tool_profiles),
            "target_profile": self.target_profile,
            "generated_artifact_policy": dict(self.generated_artifact_policy),
            "approval_policy": dict(self.approval_policy),
        }


_ROLE_PATH_CANDIDATES = {
    "rtl": ("source/rtl", "rtl", "src/rtl"),
    "sim": ("source/tb", "tb", "sim", "testbench"),
    "formal": ("formal", "proof", "proofs"),
    "synth": ("synth", "synthesis"),
    "pnr": ("pnr", "place_route", "openroad"),
    "docs": ("README.md", "docs"),
}


def _as_sorted_unique(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted({value.strip() for value in values if value and value.strip()}))


def _relative_text(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _candidate_top_modules(root: Path) -> Tuple[str, ...]:
    candidates: list[str] = []
    for search_root in (root / "source" / "rtl", root / "rtl", root / "src", root):
        if not search_root.exists():
            continue
        for path in sorted(search_root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".sv", ".v", ".svh"}:
                continue
            candidates.append(path.stem)
        if candidates:
            break
    return _as_sorted_unique(candidates)


def _role_map_from_workspace(root: Path, manifest: ProjectManifest) -> Dict[str, Tuple[str, ...]]:
    role_map: Dict[str, Tuple[str, ...]] = {}
    topology_profile = infer_repository_topology(root)

    manifest_paths: list[str] = []
    discovered_manifest = discover_manifest_path(root)
    if discovered_manifest is not None:
        manifest_paths.append(_relative_text(discovered_manifest, root))
    if manifest.source_manifest.path:
        source_manifest_path = (root / manifest.source_manifest.path).resolve(strict=False)
        manifest_paths.append(_relative_text(source_manifest_path, root))
    if manifest_paths:
        role_map["manifest"] = _as_sorted_unique(manifest_paths)

    for role, candidates in _ROLE_PATH_CANDIDATES.items():
        matches: list[str] = []
        for candidate in candidates:
            path = (root / candidate).resolve(strict=False)
            if path.exists():
                matches.append(_relative_text(path, root))
        if matches:
            role_map[role] = _as_sorted_unique(matches)

    for role, paths in topology_profile.role_map.items():
        existing = set(role_map.get(role, ()))
        role_map[role] = _as_sorted_unique(tuple(existing) + tuple(paths))

    return role_map


def infer_logical_project_profile(root: Path, manifest: Optional[ProjectManifest] = None) -> ProjectLogicalProfile:
    """Infer a logical project profile from a workspace root and optional manifest."""
    workspace_root = Path(root).expanduser().resolve()
    resolved_manifest = manifest or ProjectManifest.discover_from_root(workspace_root)
    topology_profile = infer_repository_topology(workspace_root)

    if resolved_manifest is None:
        project_name = workspace_root.name or "workspace"
        top_modules = _candidate_top_modules(workspace_root)
        role_map: Dict[str, Tuple[str, ...]] = dict(topology_profile.role_map)
        entrypoints: list[str] = []
        missing_files: list[str] = []
        flow_readiness = {
            "rtl": "ready" if top_modules else "blocked",
            "sim": "ready" if role_map.get("sim") else "blocked",
            "formal": "ready" if role_map.get("formal") else "blocked",
            "synth": "ready" if role_map.get("synth") else "blocked",
            "pnr": "ready" if role_map.get("pnr") else "blocked",
            "overall": "ready" if top_modules else "blocked",
        }
        return ProjectLogicalProfile(
            project_name=project_name,
            top_modules=top_modules,
            entrypoints=tuple(entrypoints),
            missing_files=tuple(missing_files),
            role_map=role_map,
            flow_readiness=flow_readiness,
            manifest_path=None,
        )

    role_map = _role_map_from_workspace(workspace_root, resolved_manifest)
    entrypoints: list[str] = []
    missing_files: list[str] = []

    if resolved_manifest.source_manifest.path:
        manifest_path = (workspace_root / resolved_manifest.source_manifest.path).resolve(strict=False)
        entrypoints.append(_relative_text(manifest_path, workspace_root))
        if not manifest_path.exists():
            missing_files.append(_relative_text(manifest_path, workspace_root))

    for default_entry in ("README.md", "Makefile"):
        path = (workspace_root / default_entry).resolve(strict=False)
        if path.exists():
            entrypoints.append(_relative_text(path, workspace_root))

    top_modules = _as_sorted_unique(
        [resolved_manifest.project.top_module] if resolved_manifest.project.top_module else []
        + list(_candidate_top_modules(workspace_root))
    )

    flow_readiness = {
        "rtl": "ready" if role_map.get("rtl") and top_modules else "blocked",
        "sim": "ready" if role_map.get("sim") else "blocked",
        "formal": "ready" if role_map.get("formal") else "blocked",
        "synth": "ready" if role_map.get("synth") else "blocked",
        "pnr": "ready" if role_map.get("pnr") else "blocked",
    }
    flow_readiness["overall"] = (
        "ready" if any(state == "ready" for key, state in flow_readiness.items() if key != "overall") and top_modules else "blocked"
    )

    return ProjectLogicalProfile(
        project_name=resolved_manifest.project.name,
        top_modules=top_modules,
        entrypoints=_as_sorted_unique(entrypoints),
        missing_files=_as_sorted_unique(missing_files),
        role_map=role_map,
        flow_readiness=flow_readiness,
        manifest_path=str(discovered_manifest.relative_to(workspace_root)) if (discovered_manifest := discover_manifest_path(workspace_root)) is not None else None,
    )
