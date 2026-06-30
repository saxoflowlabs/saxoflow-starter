"""Deterministic prompt context builder for SaxoFlow Agentic AI.

P4.14 adds a small normalization layer for prompt-facing context metadata.
It keeps source ordering and budget accounting stable so later phases can feed
in richer context bundles without changing the prompt contract again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from saxoflow.schemas.context import ContextBundle, ContextRef


class PromptContextError(ValueError):
    """Raised when prompt context metadata is malformed or incomplete."""


def _as_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PromptContextError(f"Prompt context field `{field_name}` must be a non-empty string.")
    return value.strip()


def _as_optional_string(value: Any, field_name: str) -> Optional[str]:
    if value is None:
        return None
    return _as_string(value, field_name)


def _path_sort_key(value: str) -> Tuple[int, str]:
    normalized = value.strip()
    return (0 if normalized.startswith("/") else 1, normalized)


@dataclass(frozen=True)
class PromptContextSource:
    """One normalized source entry used when composing prompt context."""

    path: str
    kind: Optional[str] = None
    label: Optional[str] = None
    resolved_path: Optional[str] = None
    source: Optional[str] = None

    @classmethod
    def from_value(cls, value: Union[str, Mapping[str, Any], ContextRef]) -> "PromptContextSource":
        if isinstance(value, ContextRef):
            return cls(
                path=_as_string(value.path, "source.path"),
                kind=_as_optional_string(value.kind, "source.kind"),
                label=_as_optional_string(value.label, "source.label"),
                resolved_path=_as_optional_string(value.resolved_path, "source.resolved_path"),
                source=_as_optional_string(value.source, "source.source"),
            )
        if isinstance(value, str):
            return cls(path=_as_string(value, "source.path"))
        if not isinstance(value, Mapping):
            raise PromptContextError("Prompt context sources must be strings, mappings, or ContextRef objects.")
        data = dict(value)
        return cls(
            path=_as_string(data.get("path"), "source.path"),
            kind=_as_optional_string(data.get("kind"), "source.kind"),
            label=_as_optional_string(data.get("label"), "source.label"),
            resolved_path=_as_optional_string(data.get("resolved_path"), "source.resolved_path"),
            source=_as_optional_string(data.get("source"), "source.source"),
        )

    def sort_key(self) -> Tuple[int, str, str, str, str, str]:
        return (
            *_path_sort_key(self.path),
            self.kind or "",
            self.label or "",
            self.resolved_path or "",
            self.source or "",
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
class PromptContext:
    """Canonical prompt context payload."""

    context_budget: int
    workspace_root: Optional[str] = None
    sources: Tuple[PromptContextSource, ...] = field(default_factory=tuple)
    source_paths: Tuple[str, ...] = field(default_factory=tuple)
    source_count: int = 0
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "context_budget": self.context_budget,
            "source_count": self.source_count,
            "source_paths": list(self.source_paths),
            "sources": [source.to_dict() for source in self.sources],
        }
        if self.workspace_root is not None:
            data["workspace_root"] = self.workspace_root
        if self.notes is not None:
            data["notes"] = self.notes
        return data


class PromptContextBuilder:
    """Builds deterministic prompt context metadata for downstream prompts."""

    def __init__(self, *, default_budget: int = 2048) -> None:
        if default_budget <= 0:
            raise PromptContextError("Prompt context default budget must be positive.")
        self.default_budget = default_budget

    def build(
        self,
        sources: Iterable[Union[str, Mapping[str, Any], ContextRef]] = (),
        *,
        context_budget: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> PromptContext:
        normalized_sources = self._normalize_sources(sources)
        budget = self._normalize_budget(context_budget)

        return PromptContext(
            context_budget=budget,
            workspace_root=None,
            sources=normalized_sources,
            source_paths=tuple(source.path for source in normalized_sources),
            source_count=len(normalized_sources),
            notes=_as_optional_string(notes, "prompt_context.notes"),
        )

    def build_from_context_bundle(
        self,
        bundle: ContextBundle,
        *,
        context_budget: Optional[int] = None,
    ) -> PromptContext:
        """Build prompt context directly from a normalized context bundle."""
        if not isinstance(bundle, ContextBundle):
            raise PromptContextError("Prompt context bundle input must be a ContextBundle.")

        normalized_sources = self._normalize_sources(bundle.references)

        return PromptContext(
            context_budget=self._normalize_budget(context_budget),
            workspace_root=_as_optional_string(bundle.workspace_root, "context_bundle.workspace_root"),
            sources=normalized_sources,
            source_paths=tuple(source.path for source in normalized_sources),
            source_count=len(normalized_sources),
            notes=_as_optional_string(bundle.notes, "context_bundle.notes"),
        )

    def _normalize_sources(
        self,
        sources: Iterable[Union[str, Mapping[str, Any], ContextRef]],
    ) -> Tuple[PromptContextSource, ...]:
        normalized = {PromptContextSource.from_value(source) for source in sources}
        return tuple(sorted(normalized, key=lambda source: source.sort_key()))

    def _normalize_budget(self, context_budget: Optional[int]) -> int:
        budget = self.default_budget if context_budget is None else int(context_budget)
        if budget <= 0:
            raise PromptContextError("Prompt context budget must be positive.")
        return budget
