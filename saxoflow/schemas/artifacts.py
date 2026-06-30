"""Artifact reference schemas for SaxoFlow."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


class ArtifactSchemaError(ValueError):
    """Raised when an artifact reference is missing required data or is malformed."""


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactSchemaError(f"Artifact field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactSchemaError(f"Artifact field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to a concrete artifact produced by SaxoFlow or a tool flow."""

    artifact_id: str
    path: str
    sha256: str
    kind: Optional[str] = None
    label: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ArtifactRef":
        data = _as_mapping(raw, "artifact")
        return cls(
            artifact_id=_as_string(data.get("artifact_id", data.get("id")), "artifact.artifact_id"),
            path=_as_string(data.get("path"), "artifact.path"),
            sha256=_as_string(data.get("sha256"), "artifact.sha256"),
            kind=_optional_string(data.get("kind"), "artifact.kind"),
            label=_optional_string(data.get("label"), "artifact.label"),
        )

    @classmethod
    def from_path(cls, path: Path, artifact_id: Optional[str] = None, kind: Optional[str] = None, label: Optional[str] = None) -> "ArtifactRef":
        path = Path(path)
        if not path.is_file():
            raise ArtifactSchemaError(f"Artifact path `{path}` must point to a file.")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return cls(
            artifact_id=_as_string(artifact_id or path.stem, "artifact.artifact_id"),
            path=str(path),
            sha256=digest,
            kind=_optional_string(kind, "artifact.kind"),
            label=_optional_string(label, "artifact.label"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "artifact_id": self.artifact_id,
            "path": self.path,
            "sha256": self.sha256,
        }
        if self.kind is not None:
            data["kind"] = self.kind
        if self.label is not None:
            data["label"] = self.label
        return data
