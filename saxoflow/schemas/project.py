"""Repository topology schema and semantic role inference helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Mapping, Tuple


ROLE_KEYWORDS: Mapping[str, Tuple[str, ...]] = {
    "rtl": ("rtl", "design", "verilog", "systemverilog", "vhdl"),
    "sim": ("tb", "testbench", "uvm", "sim", "dv"),
    "formal": ("formal", "proof", "property", "sby"),
    "synth": ("synth", "synthesis", "yosys"),
    "pnr": ("pnr", "place", "route", "openroad", "apr", "backend"),
    "docs": ("docs", "doc", "spec", "specs", "readme"),
    "scripts": ("script", "scripts", "flow", "flows"),
    "reports": ("report", "reports", "log", "logs"),
    "generated": ("generated", "gen", "build", "out", "dist", "runs", "artifacts"),
}


@dataclass(frozen=True)
class RepositoryTopologyProfile:
    """Semantic role map inferred from a repository tree."""

    role_map: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {"role_map": {role: list(paths) for role, paths in self.role_map.items()}}


def _relative_text(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _tokens(path: Path) -> Tuple[str, ...]:
    return tuple(part.strip().lower() for part in path.parts if part.strip())


def _collapse_paths(paths: Iterable[str]) -> Tuple[str, ...]:
    ordered = sorted({path for path in paths if path}, key=lambda item: (len(Path(item).parts), item))
    kept: list[Path] = []
    for raw in ordered:
        candidate = Path(raw)
        if any(candidate != existing and candidate.is_relative_to(existing) for existing in kept):
            continue
        kept.append(candidate)
    return tuple(str(path) for path in kept)


def infer_repository_topology(root: Path, *, max_depth: int = 4) -> RepositoryTopologyProfile:
    """Infer semantic roles from nonstandard repository hierarchies."""
    workspace_root = Path(root).expanduser().resolve()
    role_hits: Dict[str, set[str]] = {role: set() for role in ROLE_KEYWORDS}

    for path in workspace_root.rglob("*"):
        if not path.exists():
            continue

        rel = _relative_text(path, workspace_root)
        depth = len(Path(rel).parts)
        if depth > max_depth:
            continue

        if path.is_dir():
            search_tokens = _tokens(Path(rel))
        elif path.is_file() and path.name.lower() in {"readme", "readme.md", "readme.rst"}:
            search_tokens = _tokens(Path(rel))
        else:
            continue

        for role, keywords in ROLE_KEYWORDS.items():
            if any(keyword in token for token in search_tokens for keyword in keywords):
                role_hits[role].add(rel)

    role_map: Dict[str, Tuple[str, ...]] = {}
    for role, hits in role_hits.items():
        collapsed = _collapse_paths(hits)
        if collapsed:
            role_map[role] = collapsed

    return RepositoryTopologyProfile(role_map=role_map)
