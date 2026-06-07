"""Manifest-driven PDK and OpenROAD platform registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import yaml

DATA_HOME_ENV = "SAXOFLOW_DATA_HOME"
ORFS_HOME_ENV = "SAXOFLOW_ORFS_HOME"
REGISTRY_SCHEMA_VERSION = 1
PLATFORM_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
ENVIRONMENT_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SUPPORT_CLASSES = {"validated", "experimental", "reference", "custom"}


class RegistryError(ValueError):
    """Raised when a platform manifest or installation is invalid."""


def data_home() -> Path:
    """Return SaxoFlow's managed data root."""
    override = os.environ.get(DATA_HOME_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".local" / "share" / "saxoflow"


def orfs_home() -> Optional[Path]:
    """Return the active ORFS checkout, if one is available."""
    override = os.environ.get(ORFS_HOME_ENV)
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.is_dir() else None

    root = data_home() / "orfs"
    current = root / "current"
    if current.exists():
        return current.resolve()

    marker = root / "CURRENT"
    if marker.is_file():
        candidate = root / marker.read_text(encoding="utf-8").strip()
        if candidate.is_dir():
            return candidate.resolve()
    return None


def registry_dir() -> Path:
    return data_home() / "registry"


def platforms_dir() -> Path:
    return data_home() / "platforms"


def pdks_dir() -> Path:
    return data_home() / "pdks"


def repository_revision(root: Path) -> Optional[str]:
    """Return a Git checkout revision without requiring GitPython."""
    revision_file = root / ".saxoflow-revision"
    if revision_file.is_file():
        value = revision_file.read_text(encoding="utf-8").strip()
        return value or None
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def _as_dict(value: Any, field: str) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise RegistryError(f"Manifest field `{field}` must be a mapping.")
    return dict(value)


def _as_string_list(value: Any, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RegistryError(f"Manifest field `{field}` must be a list of strings.")
    return list(value)


def _normalize_artifacts(value: Any, field: str) -> Dict[str, Any]:
    artifacts = _as_dict(value, field)
    for name, spec in artifacts.items():
        valid = isinstance(spec, str) or (
            isinstance(spec, list)
            and spec
            and all(isinstance(item, str) and item for item in spec)
        )
        if not valid:
            raise RegistryError(
                f"Manifest field `{field}.{name}` must be a path/glob or "
                "a non-empty list of paths/globs."
            )
    return artifacts


@dataclass(frozen=True)
class PlatformManifest:
    """Validated platform metadata consumed by PDK and P&R commands."""

    data: Mapping[str, Any]
    source_path: Optional[Path] = None

    @property
    def id(self) -> str:
        return str(self.data["id"])

    @property
    def aliases(self) -> List[str]:
        return list(self.data.get("aliases", []))

    @property
    def family(self) -> str:
        return str(self.data["family"])

    @property
    def provider(self) -> str:
        return str(self.data["provider"])

    @property
    def classification(self) -> str:
        return str(self.data["classification"])

    @property
    def support_status(self) -> str:
        return str(self.data.get("support_status", self.classification))

    @property
    def version(self) -> str:
        return str(self.data["version"])

    @property
    def description(self) -> str:
        return str(self.data.get("description", ""))

    @property
    def license(self) -> Mapping[str, Any]:
        return self.data.get("license", {})

    @property
    def install(self) -> Mapping[str, Any]:
        return self.data.get("install", {})

    @property
    def compatibility(self) -> Mapping[str, Any]:
        return self.data.get("compatibility", {})

    @property
    def synthesis(self) -> Mapping[str, Any]:
        return self.data.get("synthesis", {})

    @property
    def artifacts(self) -> Mapping[str, Any]:
        return self.data.get("artifacts", {})

    @property
    def libraries(self) -> Sequence[Mapping[str, Any]]:
        return self.data.get("libraries", [])

    @property
    def defaults(self) -> Mapping[str, Any]:
        return self.data.get("defaults", {})

    @property
    def layers(self) -> Sequence[str]:
        return self.data.get("layers", [])

    @property
    def physical(self) -> Mapping[str, Any]:
        return self.data.get("physical", {})

    @property
    def tooling(self) -> Mapping[str, Mapping[str, Any]]:
        return self.data.get("tooling", {})

    @property
    def required_environment(self) -> Sequence[str]:
        return self.data.get("required_environment", [])

    @property
    def verification(self) -> Mapping[str, Any]:
        return self.data.get("verification", {})

    @property
    def orfs_variables(self) -> Mapping[str, Any]:
        return self.data.get("orfs_variables", {})

    @property
    def validation(self) -> Mapping[str, Any]:
        return self.data.get("validation", {})

    def library(self, library_id: Optional[str] = None) -> Mapping[str, Any]:
        selected = library_id or str(self.defaults.get("library", ""))
        if not selected and len(self.libraries) == 1:
            selected = str(self.libraries[0].get("id", ""))
        for library in self.libraries:
            if library.get("id") == selected:
                return library
        choices = ", ".join(str(item.get("id")) for item in self.libraries)
        raise RegistryError(
            f"Unknown library `{selected}` for {self.id}. Available: {choices or 'none'}."
        )

    def corner(
        self,
        library: Mapping[str, Any],
        corner_id: Optional[str] = None,
    ) -> Mapping[str, Any]:
        corners = library.get("corners", [])
        selected = corner_id or str(
            library.get("default_corner", self.defaults.get("corner", ""))
        )
        if not selected and len(corners) == 1:
            selected = str(corners[0].get("id", ""))
        for corner in corners:
            if corner.get("id") == selected:
                return corner
        choices = ", ".join(str(item.get("id")) for item in corners)
        raise RegistryError(
            f"Unknown corner `{selected}` for {self.id}/{library.get('id')}. "
            f"Available: {choices or 'none'}."
        )


def validate_manifest(raw: Mapping[str, Any], source: Optional[Path] = None) -> PlatformManifest:
    """Validate and normalize a registry manifest."""
    data = dict(raw)
    if data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise RegistryError(
            f"Unsupported schema_version in {source or 'manifest'}; "
            f"expected {REGISTRY_SCHEMA_VERSION}."
        )

    for field in ("id", "family", "provider", "classification", "version"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise RegistryError(f"Manifest field `{field}` is required.")

    if not PLATFORM_ID_RE.fullmatch(data["id"]):
        raise RegistryError(f"Invalid platform id `{data['id']}`.")
    if data["classification"] not in SUPPORT_CLASSES:
        raise RegistryError(
            "Manifest classification must be one of: "
            + ", ".join(sorted(SUPPORT_CLASSES))
        )

    data["aliases"] = _as_string_list(data.get("aliases"), "aliases")
    for alias in data["aliases"]:
        if not PLATFORM_ID_RE.fullmatch(alias):
            raise RegistryError(f"Invalid platform alias `{alias}`.")

    install = _as_dict(data.get("install"), "install")
    if install.get("kind") not in {"orfs-platform", "external"}:
        raise RegistryError("Install kind must be `orfs-platform` or `external`.")
    if install["kind"] == "orfs-platform" and not install.get("platform"):
        raise RegistryError("ORFS platform manifests require `install.platform`.")
    for field in ("estimated_download_mb", "required_disk_mb"):
        value = install.get(field)
        if value is not None and (
            not isinstance(value, int) or isinstance(value, bool) or value <= 0
        ):
            raise RegistryError(f"Manifest install.{field} must be a positive integer.")
    data["install"] = install
    data["compatibility"] = _as_dict(data.get("compatibility"), "compatibility")
    data["synthesis"] = _as_dict(data.get("synthesis"), "synthesis")
    synthesis_mode = data["synthesis"].get("mode", "single-liberty")
    if synthesis_mode not in {"single-liberty", "external-netlist-only"}:
        raise RegistryError(
            "Manifest synthesis.mode must be `single-liberty` or "
            "`external-netlist-only`."
        )
    data["synthesis"]["mode"] = synthesis_mode
    data["artifacts"] = _normalize_artifacts(data.get("artifacts"), "artifacts")
    data["defaults"] = _as_dict(data.get("defaults"), "defaults")
    data["verification"] = _as_dict(data.get("verification"), "verification")
    data["orfs_variables"] = _as_dict(data.get("orfs_variables"), "orfs_variables")
    data["physical"] = _as_dict(data.get("physical"), "physical")
    for field in ("site", "min_routing_layer", "max_routing_layer"):
        value = data["physical"].get(field)
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            raise RegistryError(
                f"Manifest field `physical.{field}` must be a non-empty string."
            )
    tooling = _as_dict(data.get("tooling"), "tooling")
    data["tooling"] = {
        str(tool): _normalize_artifacts(
            artifacts,
            f"tooling.{tool}",
        )
        for tool, artifacts in tooling.items()
    }
    data["required_environment"] = _as_string_list(
        data.get("required_environment"),
        "required_environment",
    )
    for name in data["required_environment"]:
        if not ENVIRONMENT_NAME_RE.fullmatch(name):
            raise RegistryError(
                f"Invalid required environment variable name `{name}`."
            )
    data["validation"] = _as_dict(data.get("validation"), "validation")
    smoke_test = _as_dict(
        data["validation"].get("smoke_test"),
        "validation.smoke_test",
    )
    if smoke_test:
        command = smoke_test.get("command")
        if (
            not isinstance(command, list)
            or not command
            or not all(isinstance(item, str) and item for item in command)
        ):
            raise RegistryError(
                "Manifest validation.smoke_test.command must be a non-empty "
                "argument list."
            )
        smoke_test["command"] = list(command)
        smoke_test["timeout_seconds"] = int(
            smoke_test.get("timeout_seconds", 900)
        )
        if smoke_test["timeout_seconds"] <= 0:
            raise RegistryError(
                "validation.smoke_test.timeout_seconds must be positive."
            )
    data["validation"]["smoke_test"] = smoke_test
    data["layers"] = _as_string_list(data.get("layers"), "layers")

    libraries = data.get("libraries")
    if not isinstance(libraries, list) or not libraries:
        raise RegistryError("Manifest field `libraries` must contain at least one library.")
    normalized_libraries: List[Dict[str, Any]] = []
    for library in libraries:
        item = _as_dict(library, "libraries[]")
        if not item.get("id"):
            raise RegistryError("Every library requires an `id`.")
        item["artifacts"] = _normalize_artifacts(
            item.get("artifacts"),
            f"libraries[{item['id']}].artifacts",
        )
        item["physical"] = _as_dict(
            item.get("physical"),
            f"libraries[{item['id']}].physical",
        )
        corners = item.get("corners")
        if not isinstance(corners, list) or not corners:
            raise RegistryError(f"Library `{item['id']}` requires at least one corner.")
        for corner in corners:
            corner_data = _as_dict(corner, "corners[]")
            if not corner_data.get("id"):
                raise RegistryError(f"Library `{item['id']}` has a corner without an id.")
            if "liberty" not in corner_data:
                raise RegistryError(
                    f"Corner `{corner_data['id']}` requires a `liberty` path or glob."
                )
            corner_data["artifacts"] = _normalize_artifacts(
                corner_data.get("artifacts"),
                f"corners[{corner_data['id']}].artifacts",
            )
            corner.clear()
            corner.update(corner_data)
        normalized_libraries.append(item)
    data["libraries"] = normalized_libraries
    return PlatformManifest(data=data, source_path=source)


def load_manifest(path: Path) -> PlatformManifest:
    """Load one YAML platform manifest."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RegistryError(f"Could not read platform manifest {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise RegistryError(f"Platform manifest {path} must contain a mapping.")
    return validate_manifest(raw, path)


def _packaged_manifest_paths() -> Iterable[Path]:
    root = resources.files("saxoflow").joinpath("pdks")
    try:
        candidates = sorted(root.iterdir(), key=lambda item: item.name)
    except (FileNotFoundError, TypeError):
        return []
    paths: List[Path] = []
    for candidate in candidates:
        if candidate.name.endswith((".yaml", ".yml")):
            try:
                paths.append(Path(candidate))
            except TypeError:
                continue
    return paths


def all_manifests() -> List[PlatformManifest]:
    """Load packaged and user-registered manifests."""
    manifests: Dict[str, PlatformManifest] = {}
    for path in _packaged_manifest_paths():
        manifest = load_manifest(path)
        manifests[manifest.id] = manifest
    user_dir = registry_dir()
    if user_dir.is_dir():
        for path in sorted(user_dir.glob("*.y*ml")):
            manifest = load_manifest(path)
            manifests[manifest.id] = manifest
    return sorted(manifests.values(), key=lambda item: item.id)


def get_manifest(identifier: str) -> PlatformManifest:
    """Resolve a platform ID or alias."""
    key = identifier.strip().lower()
    exact_matches = [
        manifest
        for manifest in all_manifests()
        if key == manifest.id or key in manifest.aliases
    ]
    matches = exact_matches or [
        manifest for manifest in all_manifests() if key == manifest.family
    ]
    if not matches:
        raise RegistryError(f"Unknown PDK or platform `{identifier}`.")
    if len(matches) > 1:
        choices = ", ".join(item.id for item in matches)
        raise RegistryError(
            f"`{identifier}` matches multiple platforms: {choices}. "
            "Select a platform ID explicitly."
        )
    return matches[0]


def installation_dir(manifest: PlatformManifest) -> Path:
    return platforms_dir() / manifest.id / manifest.version


def installation_metadata_path(manifest: PlatformManifest) -> Path:
    return installation_dir(manifest) / "install.json"


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(dict(data), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def read_installation(manifest: PlatformManifest) -> Optional[Dict[str, Any]]:
    path = installation_metadata_path(manifest)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def platform_root(manifest: PlatformManifest) -> Optional[Path]:
    """Return the installed technology platform root."""
    metadata = read_installation(manifest)
    if metadata and metadata.get("platform_root"):
        path = Path(str(metadata["platform_root"])).expanduser()
        if path.is_dir():
            return path.resolve()

    if manifest.install.get("kind") == "orfs-platform":
        root = orfs_home()
        if root:
            path = root / "flow" / "platforms" / str(manifest.install["platform"])
            if path.is_dir():
                return path.resolve()
    return None


def is_installed(manifest: PlatformManifest) -> bool:
    return read_installation(manifest) is not None and platform_root(manifest) is not None


def _sparse_checkout_add(root: Path, patterns: Sequence[str]) -> None:
    """Materialize additional paths in a managed non-cone sparse checkout."""
    unique_patterns = sorted(set(patterns))
    if not unique_patterns:
        return
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "sparse-checkout",
                "add",
                *unique_patterns,
            ],
            capture_output=True,
            text=True,
            timeout=1800,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RegistryError(
            "Could not materialize ORFS sparse-checkout paths: "
            f"{', '.join(unique_patterns)}: {exc}"
        ) from exc
    if result.returncode != 0:
        details = (result.stdout + result.stderr).strip()
        raise RegistryError(
            "Could not materialize ORFS sparse-checkout paths "
            f"{', '.join(unique_patterns)}: "
            f"{details or 'git sparse-checkout failed'}"
        )


def _materialize_symlink_dependencies(
    root: Path,
    platform_name: str,
) -> List[str]:
    """Materialize ORFS platforms referenced by cross-platform symlinks."""
    platforms_root = (root / "flow" / "platforms").resolve()
    selected_root = platforms_root / platform_name
    selected_pattern = f"/flow/platforms/{platform_name}/"
    patterns = [selected_pattern]
    scan_roots = {selected_root}

    for _ in range(16):
        dependency_patterns: List[str] = []
        unresolved: List[Path] = []
        for scan_root in sorted(scan_roots):
            if not scan_root.is_dir():
                continue
            for link in scan_root.rglob("*"):
                if not link.is_symlink() or link.exists():
                    continue
                unresolved.append(link)
                raw_target = os.readlink(link)
                target = Path(
                    os.path.normpath(str(link.parent / raw_target))
                )
                try:
                    relative = target.relative_to(platforms_root)
                except ValueError as exc:
                    raise RegistryError(
                        f"ORFS platform symlink escapes the platform registry: "
                        f"{link} -> {raw_target}"
                    ) from exc
                if len(relative.parts) < 2:
                    raise RegistryError(
                        f"ORFS platform symlink has an invalid target: "
                        f"{link} -> {raw_target}"
                    )
                dependency = relative.parts[0]
                pattern = f"/flow/platforms/{dependency}/"
                if pattern not in patterns:
                    dependency_patterns.append(pattern)
                    scan_roots.add(platforms_root / dependency)

        if not unresolved:
            return patterns
        if not dependency_patterns:
            broken = ", ".join(str(path) for path in unresolved)
            raise RegistryError(
                "ORFS platform contains unresolved symlink dependencies after "
                f"sparse checkout: {broken}"
            )
        _sparse_checkout_add(root, dependency_patterns)
        patterns.extend(sorted(set(dependency_patterns)))

    raise RegistryError(
        f"ORFS platform `{platform_name}` has too many nested symlink dependencies."
    )


def activate_orfs_platform(manifest: PlatformManifest) -> Path:
    """Activate platform collateral already present in the managed ORFS tree."""
    root = orfs_home()
    if root is None:
        raise RegistryError(
            "ORFS is not installed. Run `saxoflow install orfs` first."
        )
    platform_name = str(manifest.install["platform"])
    platform = root / "flow" / "platforms" / platform_name
    if not platform.is_dir() and (root / ".git").exists():
        _sparse_checkout_add(root, [f"/flow/platforms/{platform_name}/"])
    if not platform.is_dir():
        raise RegistryError(
            f"ORFS platform `{manifest.install['platform']}` was not found under "
            f"{root / 'flow/platforms'}."
        )
    sparse_patterns = [f"/flow/platforms/{platform_name}/"]
    if (root / ".git").exists():
        sparse_patterns = _materialize_symlink_dependencies(root, platform_name)
    revision = repository_revision(root)
    expected_revision = manifest.compatibility.get("orfs_revision")
    if expected_revision and revision and revision != expected_revision:
        raise RegistryError(
            f"`{manifest.id}` requires ORFS revision {expected_revision}, "
            f"but {revision} is active. Run `saxoflow install orfs`."
        )
    target = installation_dir(manifest)
    target.mkdir(parents=True, exist_ok=True)
    pdk_link = pdks_dir() / manifest.family / manifest.version / manifest.id
    pdk_link.parent.mkdir(parents=True, exist_ok=True)
    if pdk_link.is_symlink():
        pdk_link.unlink()
    elif pdk_link.exists():
        raise RegistryError(
            f"Managed PDK path already exists and is not a symlink: {pdk_link}"
        )
    pdk_link.symlink_to(platform.resolve(), target_is_directory=True)
    metadata = {
        "schema_version": 1,
        "platform_id": manifest.id,
        "version": manifest.version,
        "install_kind": "orfs-platform",
        "platform_root": str(platform.resolve()),
        "orfs_root": str(root.resolve()),
        "source_revision": revision or "unknown",
        "managed_pdk_path": str(pdk_link),
        "sparse_patterns": sparse_patterns,
    }
    _write_json_atomic(installation_metadata_path(manifest), metadata)
    return platform.resolve()


def activate_external_platform(
    manifest: PlatformManifest,
    external_root: Path,
) -> Path:
    """Activate an existing external platform without copying PDK content."""
    root = external_root.expanduser().resolve()
    if not root.is_dir():
        raise RegistryError(f"External platform root does not exist: {root}")
    target = installation_dir(manifest)
    target.mkdir(parents=True, exist_ok=True)
    metadata = {
        "schema_version": 1,
        "platform_id": manifest.id,
        "version": manifest.version,
        "install_kind": "external",
        "platform_root": str(root),
    }
    _write_json_atomic(installation_metadata_path(manifest), metadata)
    return root


def remove_installation(manifest: PlatformManifest) -> None:
    """Remove SaxoFlow activation metadata without deleting external PDK data."""
    metadata = read_installation(manifest) or {}
    managed_link = metadata.get("managed_pdk_path")
    if managed_link:
        link = Path(str(managed_link))
        if link.is_symlink():
            link.unlink()
    if metadata.get("install_kind") == "orfs-platform":
        root_value = metadata.get("orfs_root")
        platform_name = str(manifest.install.get("platform", ""))
        if root_value and platform_name:
            root = Path(str(root_value))
            sparse_file = root / ".git/info/sparse-checkout"
            recorded_patterns = metadata.get(
                "sparse_patterns",
                [f"/flow/platforms/{platform_name}/"],
            )
            if not isinstance(recorded_patterns, list):
                recorded_patterns = [f"/flow/platforms/{platform_name}/"]
            retained_patterns = set()
            for install_file in platforms_dir().glob("*/*/install.json"):
                if install_file == installation_metadata_path(manifest):
                    continue
                try:
                    other = json.loads(install_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                other_patterns = other.get("sparse_patterns", [])
                if isinstance(other_patterns, list):
                    retained_patterns.update(
                        str(pattern) for pattern in other_patterns
                    )
            removable = {
                str(pattern)
                for pattern in recorded_patterns
                if str(pattern) not in retained_patterns
            }
            if sparse_file.is_file() and removable:
                lines = sparse_file.read_text(encoding="utf-8").splitlines()
                if any(pattern in lines for pattern in removable):
                    sparse_file.write_text(
                        "\n".join(
                            line for line in lines if line not in removable
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    result = subprocess.run(
                        ["git", "-C", str(root), "sparse-checkout", "reapply"],
                        capture_output=True,
                        text=True,
                        timeout=300,
                        check=False,
                    )
                    if result.returncode != 0:
                        raise RegistryError(
                            "Could not remove managed platform collateral: "
                            + (result.stdout + result.stderr).strip()
                        )
    target = installation_dir(manifest)
    if target.exists():
        shutil.rmtree(target)


def verify_installation(manifest: PlatformManifest) -> List[str]:
    """Return human-readable verification problems."""
    root = platform_root(manifest)
    if root is None:
        return ["Platform is not installed or its root is unavailable."]
    problems = verify_platform_root(manifest, root)
    metadata = read_installation(manifest) or {}
    checksum_groups = metadata.get("artifact_checksums", {})
    if isinstance(checksum_groups, dict):
        for group, raw_records in checksum_groups.items():
            records = raw_records if isinstance(raw_records, list) else [raw_records]
            for record in records:
                if not isinstance(record, dict):
                    problems.append(f"Invalid recorded checksum for {group}.")
                    continue
                path = Path(str(record.get("path", "")))
                expected = str(record.get("sha256", ""))
                if not path.is_file():
                    problems.append(f"Recorded {group} artifact is missing: {path}.")
                elif not expected or file_sha256(path) != expected:
                    problems.append(f"Checksum mismatch for {group} artifact: {path}.")
    return problems


def verify_platform_root(manifest: PlatformManifest, root: Path) -> List[str]:
    """Verify a concrete platform root without requiring activation metadata."""
    problems: List[str] = []
    required = manifest.verification.get("required_globs", [])
    if not isinstance(required, list):
        return ["Manifest verification.required_globs is invalid."]
    for pattern in required:
        if not any(root.glob(str(pattern))):
            problems.append(f"Missing required artifact matching `{pattern}`.")
    groups: List[tuple[str, Mapping[str, Any]]] = [
        ("platform", manifest.artifacts),
    ]
    groups.extend(
        (f"{tool} tooling", artifacts)
        for tool, artifacts in manifest.tooling.items()
    )
    for library in manifest.libraries:
        library_id = str(library.get("id"))
        groups.append((f"library {library_id}", library.get("artifacts", {})))
        for corner in library.get("corners", []):
            corner_id = str(corner.get("id"))
            groups.append(
                (
                    f"{library_id}/{corner_id}",
                    {
                        "liberty": corner.get("liberty"),
                        **corner.get("artifacts", {}),
                    },
                )
            )
    for owner, artifacts in groups:
        for name, raw_specs in artifacts.items():
            specs = raw_specs if isinstance(raw_specs, list) else [raw_specs]
            for pattern in specs:
                if not pattern:
                    continue
                expanded = Path(
                    os.path.expandvars(os.path.expanduser(str(pattern)))
                )
                matches = (
                    [expanded]
                    if expanded.is_absolute()
                    else list(root.glob(str(pattern)))
                )
                if not any(path.is_file() for path in matches):
                    problems.append(
                        f"Missing {owner} {name} artifact matching `{pattern}`."
                    )
    return problems


def resolve_artifact_matches(root: Path, raw_specs: Any) -> List[Path]:
    """Resolve one or more manifest artifact paths or glob patterns."""
    specs = raw_specs if isinstance(raw_specs, list) else [raw_specs]
    matches: List[Path] = []
    for raw_spec in specs:
        expanded = Path(
            os.path.expandvars(os.path.expanduser(str(raw_spec)))
        )
        candidates = (
            [expanded]
            if expanded.is_absolute()
            else sorted(root.glob(str(raw_spec)))
        )
        matches.extend(path.resolve() for path in candidates if path.is_file())
    return sorted(set(matches))


def validate_openroad_technology(
    manifest: PlatformManifest,
    root: Path,
    openroad_binary: str,
) -> None:
    """Run a read-only OpenROAD technology and cell LEF load smoke test."""
    library = manifest.library()
    artifacts = {**manifest.artifacts, **library.get("artifacts", {})}
    technology = resolve_artifact_matches(root, artifacts.get("technology_lef"))
    cells = resolve_artifact_matches(root, artifacts.get("cell_lefs"))
    if len(technology) != 1:
        raise RegistryError(
            "OpenROAD technology validation requires exactly one technology LEF."
        )
    if not cells:
        raise RegistryError(
            "OpenROAD technology validation requires at least one cell LEF."
        )

    def tcl_path(path: Path) -> str:
        return "{" + str(path).replace("}", r"\}") + "}"

    script_text = "\n".join(
        [
            f"read_lef -tech {tcl_path(technology[0])}",
            *(f"read_lef -library {tcl_path(path)}" for path in cells),
            "puts SAXOFLOW_TECHNOLOGY_LOAD_OK",
            "",
        ]
    )
    with tempfile.TemporaryDirectory(prefix="saxoflow-pdk-") as temp:
        script = Path(temp) / "technology_load.tcl"
        script.write_text(script_text, encoding="utf-8")
        try:
            result = subprocess.run(
                [openroad_binary, "-no_init", "-exit", str(script)],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RegistryError(f"OpenROAD technology-load test failed: {exc}") from exc
    if result.returncode != 0 or "SAXOFLOW_TECHNOLOGY_LOAD_OK" not in result.stdout:
        excerpt = (result.stdout + result.stderr).strip().splitlines()[-20:]
        raise RegistryError(
            "OpenROAD could not load the platform LEFs:\n"
            + "\n".join(excerpt)
        )


def run_platform_smoke_test(
    manifest: PlatformManifest,
    root: Path,
) -> str:
    """Run an explicitly requested platform-provided smoke-test adapter."""
    smoke_test = manifest.validation.get("smoke_test", {})
    command = smoke_test.get("command") if isinstance(smoke_test, dict) else None
    if not command:
        raise RegistryError(
            "The manifest does not define validation.smoke_test.command."
        )
    resolved = list(command)
    for index, argument in enumerate(resolved):
        candidate = Path(argument)
        if candidate.is_absolute() or "/" not in argument:
            continue
        path = (root / candidate).resolve()
        if root.resolve() not in path.parents and path != root.resolve():
            raise RegistryError("Smoke-test command path escapes the platform root.")
        if not path.exists():
            raise RegistryError(f"Smoke-test command path does not exist: {path}")
        resolved[index] = str(path)
    environment = os.environ.copy()
    environment["SAXOFLOW_PLATFORM_ROOT"] = str(root.resolve())
    try:
        with tempfile.TemporaryDirectory(prefix="saxoflow-pdk-smoke-") as temp:
            result = subprocess.run(
                resolved,
                cwd=temp,
                env=environment,
                capture_output=True,
                text=True,
                timeout=int(smoke_test.get("timeout_seconds", 900)),
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RegistryError(f"Platform smoke test failed: {exc}") from exc
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0:
        raise RegistryError(
            "Platform smoke test failed:\n"
            + "\n".join(output.splitlines()[-40:])
        )
    return output


def resolve_artifact(root: Path, pattern: str, label: str) -> Path:
    """Resolve one manifest artifact path or glob."""
    expanded = os.path.expandvars(os.path.expanduser(pattern))
    candidate = Path(expanded)
    if candidate.is_absolute():
        matches = [candidate] if candidate.is_file() else sorted(candidate.parent.glob(candidate.name))
    else:
        matches = sorted(root.glob(expanded))
    files = [path.resolve() for path in matches if path.is_file()]
    if not files:
        raise RegistryError(f"No {label} matched `{pattern}` under {root}.")
    if len(files) > 1:
        raise RegistryError(
            f"Multiple {label} files matched `{pattern}`; use a more specific manifest path."
        )
    return files[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_installation_checksums(manifest: PlatformManifest) -> Dict[str, Any]:
    """Record checksums for the active default technology and timing views."""
    root = platform_root(manifest)
    metadata = read_installation(manifest)
    if root is None or metadata is None:
        raise RegistryError(f"Platform `{manifest.id}` is not installed.")
    library = manifest.library()
    corner = manifest.corner(library)
    specs: Dict[str, Any] = {
        "liberty": corner.get("liberty"),
        "platform_config": "config.mk",
    }
    for owner in (manifest.artifacts, library.get("artifacts", {}),
                  corner.get("artifacts", {})):
        for name in ("technology_lef", "cell_lefs", "rcx_rules", "rc_setup"):
            if owner.get(name):
                specs[name] = owner[name]
    for tool, artifacts in manifest.tooling.items():
        for name, raw_specs in artifacts.items():
            specs[f"tooling_{tool}_{name}"] = raw_specs

    checksums: Dict[str, Any] = {}
    for name, raw_specs in specs.items():
        files = resolve_artifact_matches(root, raw_specs)
        if files:
            records = [
                {"path": str(path), "sha256": file_sha256(path)}
                for path in files
            ]
            checksums[name] = records[0] if len(records) == 1 else records
    metadata["artifact_checksums"] = checksums
    _write_json_atomic(installation_metadata_path(manifest), metadata)
    return checksums


def manifest_template() -> Dict[str, Any]:
    """Return a complete custom-platform manifest template."""
    return {
        "schema_version": 1,
        "id": "custom-platform",
        "aliases": [],
        "family": "custom-pdk",
        "provider": "user",
        "classification": "custom",
        "support_status": "custom",
        "version": "1",
        "description": "User-managed ORFS-compatible platform.",
        "license": {"name": "Define the PDK license", "url": ""},
        "install": {"kind": "external"},
        "compatibility": {"orfs_revision": "", "openroad_revision": ""},
        "synthesis": {"mode": "single-liberty"},
        "artifacts": {
            "technology_lef": "lef/technology.lef",
            "cell_lefs": ["lef/cells.lef"],
            "gds": ["gds/*.gds"],
            "rcx_rules": "openroad/rcx.rules",
        },
        "libraries": [
            {
                "id": "default",
                "default_corner": "typical",
                "corners": [
                    {
                        "id": "typical",
                        "liberty": "lib/*.lib",
                    }
                ],
            }
        ],
        "defaults": {
            "library": "default",
            "corner": "typical",
            "utilization": 40,
            "aspect_ratio": 1.0,
            "core_margin": 2,
            "place_density": 0.60,
        },
        "layers": ["M1", "M2", "M3", "M4", "M5", "M6"],
        "physical": {
            "site": "define-placement-site",
            "min_routing_layer": "M2",
            "max_routing_layer": "M6",
        },
        "tooling": {
            "klayout": {},
            "magic": {},
            "netgen": {},
        },
        "required_environment": [],
        "verification": {
            "required_globs": ["**/*.lef", "**/*.lib"],
        },
        "validation": {
            "smoke_test": {
                "command": ["bash", "validation/smoke_test.sh"],
                "timeout_seconds": 900,
            }
        },
        "orfs_variables": {},
    }
