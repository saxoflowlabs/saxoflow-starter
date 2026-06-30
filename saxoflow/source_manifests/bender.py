"""Bender manifest detection and schema helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml


BENDER_MANIFEST_FILENAMES: Tuple[str, ...] = (
    "Bender.yml",
    "Bender.yaml",
    "bender.yml",
    "bender.yaml",
)


class BenderManifestError(ValueError):
    """Raised when a Bender manifest is missing required data or is malformed."""


def _bender_manifest_candidates(root: Path) -> Tuple[Path, ...]:
    root = Path(root)
    return tuple(root / filename for filename in BENDER_MANIFEST_FILENAMES)


def discover_bender_manifest_path(root: Path) -> Optional[Path]:
    """Return the first Bender manifest found in a project root, if any."""
    for candidate in _bender_manifest_candidates(Path(root)):
        if candidate.is_file():
            return candidate
    return None


def _load_bender_mapping(path: Path) -> Dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise BenderManifestError(f"Could not read Bender manifest `{path}`.") from exc
    except yaml.YAMLError as exc:
        raise BenderManifestError(f"Could not parse Bender manifest `{path}` as YAML.") from exc

    if not isinstance(raw, Mapping):
        raise BenderManifestError(f"Bender manifest `{path}` must contain a mapping at the top level.")
    return dict(raw)


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BenderManifestError(f"Bender manifest field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BenderManifestError(f"Bender manifest field `{field_name}` must be a non-empty string.")
    return value.strip()


def _as_string_sequence(value: Any, field_name: str) -> Tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_as_string(value, field_name),)
    if isinstance(value, (list, tuple)):
        return tuple(_as_string(item, field_name) for item in value)
    raise BenderManifestError(f"Bender manifest field `{field_name}` must be a string or list of strings.")


@dataclass(frozen=True)
class BenderSourceGroup:
    """One Bender source entry with normalized target membership."""

    files: Tuple[str, ...] = field(default_factory=tuple)
    include_dirs: Tuple[str, ...] = field(default_factory=tuple)
    targets: Tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "BenderSourceGroup":
        data = _as_mapping(raw, "sources entry")
        files = _as_string_sequence(data.get("files"), "sources.files")
        include_dirs = _as_string_sequence(data.get("include_dirs"), "sources.include_dirs")
        targets = _as_string_sequence(data.get("target", data.get("targets")), "sources.target")
        return cls(files=files, include_dirs=include_dirs, targets=targets)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"files": list(self.files)}
        if self.include_dirs:
            data["include_dirs"] = list(self.include_dirs)
        if self.targets:
            data["target"] = list(self.targets)
        return data


@dataclass(frozen=True)
class BenderManifest:
    """Validated Bender manifest with target-aware source groups."""

    package: Mapping[str, Any] = field(default_factory=dict)
    dependencies: Mapping[str, Any] = field(default_factory=dict)
    sources: Tuple[BenderSourceGroup, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "BenderManifest":
        data = _as_mapping(raw, "Bender manifest")
        package = data.get("package") or {}
        if not isinstance(package, Mapping):
            raise BenderManifestError("Bender manifest field `package` must be a mapping.")

        dependencies = data.get("dependencies") or {}
        if not isinstance(dependencies, Mapping):
            raise BenderManifestError("Bender manifest field `dependencies` must be a mapping.")

        sources_raw = data.get("sources") or []
        if not isinstance(sources_raw, list):
            raise BenderManifestError("Bender manifest field `sources` must be a list of mappings.")

        sources = tuple(BenderSourceGroup.from_mapping(item) for item in sources_raw)
        return cls(package=dict(package), dependencies=dict(dependencies), sources=sources)

    @classmethod
    def from_path(cls, path: Path) -> "BenderManifest":
        manifest_path = discover_bender_manifest_path(path) if Path(path).is_dir() else Path(path)
        if manifest_path is None:
            raise BenderManifestError(f"No Bender manifest found under `{path}`.")
        return cls.from_mapping(_load_bender_mapping(manifest_path))

    def targets(self) -> Tuple[str, ...]:
        """Return all target names referenced by the manifest."""
        target_names = []
        for source in self.sources:
            for target in source.targets:
                if target not in target_names:
                    target_names.append(target)
        return tuple(target_names)

    def source_groups_for_target(self, target: str) -> Tuple[BenderSourceGroup, ...]:
        """Return source groups that participate in the named target."""
        normalized_target = _as_string(target, "target")
        return tuple(source for source in self.sources if normalized_target in source.targets)

    def files_for_target(self, target: str) -> Tuple[str, ...]:
        """Return file patterns attached to the named target."""
        patterns = []
        for source in self.source_groups_for_target(target):
            patterns.extend(source.files)
        return tuple(patterns)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "package": dict(self.package),
            "dependencies": dict(self.dependencies),
            "sources": [source.to_dict() for source in self.sources],
        }
        return data


def load_bender_manifest(path: Path) -> BenderManifest:
    """Load and validate a Bender manifest from a YAML file or project root directory."""
    path = Path(path)
    manifest_path = discover_bender_manifest_path(path) if path.is_dir() else path
    if manifest_path is None:
        raise BenderManifestError(f"No Bender manifest found under `{path}`.")
    return BenderManifest.from_mapping(_load_bender_mapping(manifest_path))
