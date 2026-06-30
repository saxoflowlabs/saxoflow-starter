"""Source manifest resolver used by adapter request option parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Tuple

from saxoflow.source_manifests.base import ExplicitSourceManifest, ExplicitSourceManifestError
from saxoflow.source_manifests.bender import BenderManifest, BenderManifestError


class SourceManifestResolutionError(ValueError):
    """Raised when source manifest options cannot be resolved."""


def _optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_rtl_specs(
    workspace_root: Path,
    *,
    explicit_specs: Sequence[str],
    default_specs: Sequence[str],
    source_manifest_options: Optional[Mapping[str, Any]],
    target: str,
) -> Tuple[str, ...]:
    """Resolve RTL specs from explicit options or a source-manifest provider.

    Precedence:
    1) explicit `rtl` options passed to the adapter request
    2) source-manifest provider options
    3) adapter-specific SaxoFlow defaults
    """
    explicit = tuple(str(spec).strip() for spec in explicit_specs if str(spec).strip())
    if explicit:
        return explicit

    options = dict(source_manifest_options or {})
    provider = str(options.get("provider", "saxoflow")).strip().lower() or "saxoflow"

    if provider == "saxoflow":
        return tuple(default_specs)

    if provider == "bender":
        bender_target = _optional_string(options.get("target")) or target
        try:
            manifest = BenderManifest.from_path(workspace_root)
        except BenderManifestError as exc:
            raise SourceManifestResolutionError(str(exc)) from exc

        resolved = tuple(manifest.files_for_target(bender_target))
        if resolved:
            return resolved

        available = manifest.targets()
        if available:
            raise SourceManifestResolutionError(
                "Bender target "
                f"`{bender_target}` has no files. Available targets: {', '.join(available)}."
            )
        raise SourceManifestResolutionError("Bender manifest has no target-mapped source entries.")

    if provider in {"explicit", "filelist", "sources"}:
        manifest_path = _optional_string(options.get("path"))
        source_path = Path(manifest_path) if manifest_path is not None else workspace_root
        try:
            manifest = ExplicitSourceManifest.from_path(source_path)
        except ExplicitSourceManifestError as exc:
            raise SourceManifestResolutionError(str(exc)) from exc
        return tuple(manifest.files)

    raise SourceManifestResolutionError(
        "Unknown source_manifest provider "
        f"`{provider}`. Supported providers: saxoflow, bender, explicit."
    )
