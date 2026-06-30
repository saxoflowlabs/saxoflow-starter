"""Artifact registry service for SaxoFlow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

from saxoflow.schemas.artifacts import ArtifactRef, ArtifactSchemaError


class ArtifactRegistryError(ValueError):
    """Raised when an artifact registry operation cannot be completed."""


@dataclass
class ArtifactRegistry:
    """In-memory registry for artifact references with optional JSON persistence."""

    storage_path: Optional[Path] = None
    artifacts: Dict[str, ArtifactRef] = field(default_factory=dict)

    @classmethod
    def from_path(cls, path: Path) -> "ArtifactRegistry":
        path = Path(path)
        if not path.exists():
            return cls(storage_path=path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8") or "{}")
        except OSError as exc:
            raise ArtifactRegistryError(f"Could not read artifact registry `{path}`.") from exc
        except json.JSONDecodeError as exc:
            raise ArtifactRegistryError(f"Could not parse artifact registry `{path}` as JSON.") from exc

        if not isinstance(raw, dict):
            raise ArtifactRegistryError(f"Artifact registry `{path}` must contain a mapping.")

        registry = cls(storage_path=path)
        for artifact_id, value in raw.get("artifacts", {}).items():
            artifact = ArtifactRef.from_mapping(value if isinstance(value, dict) else {"artifact_id": artifact_id, **{}})
            registry.artifacts[artifact.artifact_id] = artifact
        return registry

    def add(self, artifact: ArtifactRef) -> ArtifactRef:
        if not isinstance(artifact, ArtifactRef):
            raise ArtifactRegistryError("ArtifactRegistry.add expects an ArtifactRef instance.")
        if artifact.artifact_id in self.artifacts:
            raise ArtifactRegistryError(f"Artifact `{artifact.artifact_id}` is already registered.")
        self.artifacts[artifact.artifact_id] = artifact
        return artifact

    def add_from_path(self, path: Path, artifact_id: Optional[str] = None, kind: Optional[str] = None, label: Optional[str] = None) -> ArtifactRef:
        try:
            artifact = ArtifactRef.from_path(path, artifact_id=artifact_id, kind=kind, label=label)
        except ArtifactSchemaError as exc:
            raise ArtifactRegistryError(str(exc)) from exc
        return self.add(artifact)

    def get(self, artifact_id: str) -> Optional[ArtifactRef]:
        return self.artifacts.get(artifact_id)

    def list(self, kind: Optional[str] = None) -> List[ArtifactRef]:
        if kind is None:
            return list(self.artifacts.values())
        return [artifact for artifact in self.artifacts.values() if artifact.kind == kind]

    def contains(self, artifact_id: str) -> bool:
        return artifact_id in self.artifacts

    def save(self, path: Optional[Path] = None) -> Path:
        target = Path(path or self.storage_path or "")
        if not target:
            raise ArtifactRegistryError("Artifact registry storage path is not configured.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"artifacts": {artifact_id: artifact.to_dict() for artifact_id, artifact in self.artifacts.items()}}, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.storage_path = target
        return target

    def extend(self, artifacts: Sequence[ArtifactRef]) -> None:
        for artifact in artifacts:
            self.add(artifact)

    def to_dict(self) -> Dict[str, object]:
        return {"artifacts": {artifact_id: artifact.to_dict() for artifact_id, artifact in self.artifacts.items()}}
