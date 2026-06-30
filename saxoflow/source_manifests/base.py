"""Explicit source manifest provider helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional, Tuple


EXPLICIT_SOURCE_MANIFEST_FILENAMES: Tuple[str, ...] = (
    "sources.txt",
    "sources.list",
    "sources.lst",
    "files.txt",
)


class ExplicitSourceManifestError(ValueError):
    """Raised when an explicit source manifest is missing or malformed."""


def _explicit_manifest_candidates(root: Path) -> Tuple[Path, ...]:
    root = Path(root)
    return tuple(root / filename for filename in EXPLICIT_SOURCE_MANIFEST_FILENAMES)


def discover_explicit_source_manifest_path(root: Path) -> Optional[Path]:
    """Return the first explicit file list found in a project root, if any."""
    for candidate in _explicit_manifest_candidates(Path(root)):
        if candidate.is_file():
            return candidate
    return None


def _load_explicit_lines(path: Path) -> Tuple[str, ...]:
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ExplicitSourceManifestError(f"Could not read explicit source manifest `{path}`.") from exc

    files = []
    for raw_line in raw_lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        files.append(line)
    return tuple(files)


@dataclass(frozen=True)
class ExplicitSourceManifest:
    """A source manifest backed by an explicit list of file paths or patterns."""

    files: Tuple[str, ...] = field(default_factory=tuple)
    source_path: Optional[str] = None

    @classmethod
    def from_path(cls, path: Path) -> "ExplicitSourceManifest":
        path = Path(path)
        manifest_path = discover_explicit_source_manifest_path(path) if path.is_dir() else path
        if manifest_path is None:
            raise ExplicitSourceManifestError(f"No explicit source manifest found under `{path}`.")
        return cls(files=_load_explicit_lines(manifest_path), source_path=str(manifest_path))

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {"files": list(self.files)}
        if self.source_path is not None:
            data["source_path"] = self.source_path
        return data
