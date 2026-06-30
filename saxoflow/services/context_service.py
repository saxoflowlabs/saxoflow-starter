"""Workspace-bounded context resolution for SaxoFlow AI commands."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

from saxoflow.schemas.context import ContextBundle, ContextRef


class ContextServiceError(ValueError):
    """Raised when a context reference cannot be resolved safely."""


DEFAULT_MAX_CONTEXT_FILES = 25
DEFAULT_MAX_DIRECTORY_DEPTH = 3
DEFAULT_MAX_CONTEXT_BYTES = 64 * 1024
IGNORED_DIRECTORY_NAMES = {".git", ".hg", ".svn", "__pycache__", ".tox", ".venv", "node_modules"}


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ResolvedContextRef:
    """A context reference normalized to an absolute workspace path."""

    path: str
    resolved_path: str
    kind: str | None = None
    label: str | None = None
    source: str | None = None

    def to_ref(self) -> ContextRef:
        return ContextRef(
            path=self.path,
            kind=self.kind,
            label=self.label,
            resolved_path=self.resolved_path,
            source=self.source,
        )


@dataclass
class ContextService:
    """Resolve and validate AI context references against a workspace root."""

    workspace_root: Path

    def __post_init__(self) -> None:
        self.workspace_root = Path(self.workspace_root).expanduser().resolve()

    @classmethod
    def from_workspace(cls, workspace_root: Path) -> "ContextService":
        return cls(workspace_root=workspace_root)

    def resolve_path(self, raw_path: str | Path) -> Path:
        """Resolve *raw_path* inside the workspace and reject escapes."""
        raw = Path(raw_path).expanduser()
        candidate = raw if raw.is_absolute() else self.workspace_root / raw
        resolved = candidate.resolve(strict=False)

        if not _is_within_root(resolved, self.workspace_root):
            raise ContextServiceError(
                f"Context path `{raw_path}` escapes the workspace root `{self.workspace_root}`."
            )
        if not resolved.exists():
            raise ContextServiceError(f"Context path `{raw_path}` does not exist inside the workspace.")
        return resolved

    def resolve_ref(self, ref: ContextRef) -> ResolvedContextRef:
        resolved_path = self.resolve_path(ref.path)
        return ResolvedContextRef(
            path=ref.path,
            resolved_path=str(resolved_path),
            kind=ref.kind,
            label=ref.label,
            source=ref.source,
        )

    def resolve_bundle(self, bundle: ContextBundle) -> ContextBundle:
        resolved_refs = tuple(self.resolve_ref(ref).to_ref() for ref in bundle.references)
        return ContextBundle(
            workspace_root=str(self.workspace_root),
            references=resolved_refs,
            notes=bundle.notes,
        )

    def resolve_many(self, refs: Iterable[ContextRef]) -> Tuple[ResolvedContextRef, ...]:
        return tuple(self.resolve_ref(ref) for ref in refs)

    def index_directory(
        self,
        directory: str | Path,
        *,
        max_files: int = DEFAULT_MAX_CONTEXT_FILES,
        max_depth: int = DEFAULT_MAX_DIRECTORY_DEPTH,
        max_bytes: int = DEFAULT_MAX_CONTEXT_BYTES,
    ) -> Tuple[ResolvedContextRef, ...]:
        """Return deterministic context refs for files inside *directory*.

        Hidden, binary, oversized, and deeply nested files are skipped.
        The returned refs are sorted by their workspace-relative path.
        """
        root = self.resolve_path(directory)
        if not root.is_dir():
            raise ContextServiceError(f"Context path `{directory}` must be a directory to index it.")

        indexed: list[ResolvedContextRef] = []

        for candidate in self._iter_indexable_files(root, max_depth=max_depth):
            if len(indexed) >= max_files:
                break
            if candidate.stat().st_size > max_bytes:
                continue
            if self._is_binary_file(candidate):
                continue
            rel_path = candidate.relative_to(self.workspace_root)
            indexed.append(
                ResolvedContextRef(
                    path=str(rel_path),
                    resolved_path=str(candidate),
                    kind="file",
                    source="directory-index",
                )
            )

        return tuple(indexed)

    def _iter_indexable_files(self, root: Path, *, max_depth: int) -> Iterable[Path]:
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack:
            current, depth = stack.pop()
            entries = sorted(current.iterdir(), key=lambda path: path.name)
            dirs: list[Path] = []
            files: list[Path] = []

            for entry in entries:
                if entry.name.startswith(".") and entry.name not in {"."}:
                    continue
                if entry.is_dir():
                    if entry.name in IGNORED_DIRECTORY_NAMES:
                        continue
                    dirs.append(entry)
                elif entry.is_file():
                    files.append(entry)

            for file_path in files:
                yield file_path

            if depth >= max_depth:
                continue

            for subdir in reversed(dirs):
                if not _is_within_root(subdir.resolve(strict=False), self.workspace_root):
                    continue
                stack.append((subdir, depth + 1))

    @staticmethod
    def _is_binary_file(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                chunk = handle.read(4096)
        except OSError as exc:
            raise ContextServiceError(f"Could not read context file `{path}`.") from exc
        return b"\0" in chunk
