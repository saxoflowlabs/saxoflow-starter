"""Context reference schemas for SaxoFlow AI grounding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple


class ContextSchemaError(ValueError):
    """Raised when a context reference or bundle is missing required data."""


def _as_mapping(value: Any, field_name: str) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContextSchemaError(f"Context field `{field_name}` must be a mapping.")
    return dict(value)


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContextSchemaError(f"Context field `{field_name}` must be a non-empty string.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


@dataclass(frozen=True)
class ContextRef:
    """A workspace-local file, directory, or artifact reference used as context."""

    path: str
    kind: Optional[str] = None
    label: Optional[str] = None
    resolved_path: Optional[str] = None
    source: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ContextRef":
        data = _as_mapping(raw, "context")
        return cls(
            path=_as_string(data.get("path"), "context.path"),
            kind=_optional_string(data.get("kind"), "context.kind"),
            label=_optional_string(data.get("label"), "context.label"),
            resolved_path=_optional_string(data.get("resolved_path"), "context.resolved_path"),
            source=_optional_string(data.get("source"), "context.source"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"path": self.path}
        if self.kind is not None:
            data["kind"] = self.kind
        if self.label is not None:
            data["label"] = self.label
        if self.resolved_path is not None:
            data["resolved_path"] = self.resolved_path
        if self.source is not None:
            data["source"] = self.source
        return data


@dataclass(frozen=True)
class ContextBundle:
    """A normalized bundle of context references for a single AI request."""

    workspace_root: Optional[str] = None
    references: Tuple[ContextRef, ...] = field(default_factory=tuple)
    notes: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "ContextBundle":
        data = _as_mapping(raw, "context_bundle")
        references_raw = data.get("references", data.get("contexts")) or []
        if not isinstance(references_raw, list):
            raise ContextSchemaError("Context field `references` must be a list of mappings.")

        references = tuple(ContextRef.from_mapping(item) for item in references_raw)
        return cls(
            workspace_root=_optional_string(data.get("workspace_root"), "context_bundle.workspace_root"),
            references=references,
            notes=_optional_string(data.get("notes"), "context_bundle.notes"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "references": [ref.to_dict() for ref in self.references],
        }
        if self.workspace_root is not None:
            data["workspace_root"] = self.workspace_root
        if self.notes is not None:
            data["notes"] = self.notes
        return data