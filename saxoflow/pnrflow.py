"""Generic ORFS-backed physical-design workflow for SaxoFlow units."""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import click
import yaml
from click.testing import CliRunner

from saxoflow.pdk_registry import (
    PlatformManifest,
    RegistryError,
    file_sha256,
    get_manifest,
    is_installed,
    orfs_home,
    platform_root,
    resolve_artifact,
    resolve_artifact_matches,
    verify_installation,
)
from saxoflow.synthflow import DEFAULT_RTL_SPECS, collect_sources, project_path

PNR_DIRS = (
    "scripts",
    "generated",
    "logs",
    "objects",
    "reports",
    "results",
    "runs",
)
STAGES = ("floorplan", "place", "cts", "route", "finish")
ORFS_TARGETS = {
    "run": "all",
    "floorplan": "floorplan",
    "place": "place",
    "cts": "cts",
    "route": "route",
    "finish": "finish",
}
GUI_STAGE_DATABASES = {
    "floorplan": "2_floorplan.odb",
    "place": "3_place.odb",
    "cts": "4_cts.odb",
    "route": "5_route.odb",
    "finish": "6_final.odb",
}
IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
VARIANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
OVERRIDE_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
MODULE_RE = re.compile(
    r"\bmodule\s+([A-Za-z_][A-Za-z0-9_$]*)\b(.*?)\bendmodule\b",
    re.DOTALL,
)
INSTANTIATION_RE = re.compile(
    r"\b([A-Za-z_][A-Za-z0-9_$]*)\s+"
    r"(?:#\s*\([^;]*?\)\s*)?[A-Za-z_][A-Za-z0-9_$]*\s*\(",
    re.DOTALL,
)
MAKE_OVERRIDE_DENY = {"DESIGN_NAME", "PLATFORM", "VERILOG_FILES", "SDC_FILE"}


class PnrError(ValueError):
    """Raised for invalid project or flow configuration."""


@dataclass
class ResolvedFlow:
    root: Path
    manifest: PlatformManifest
    platform_root: Path
    library: Mapping[str, Any]
    corner: Mapping[str, Any]
    top: str
    netlists: List[Path]
    sdc: Path
    variant: str
    settings: Dict[str, Any]
    run_root: Path
    config_mk: Path


def ensure_pnr_layout(root: Path) -> Path:
    """Create the P&R workspace without touching design inputs."""
    pnr = root / "pnr"
    pnr.mkdir(parents=True, exist_ok=True)
    for name in PNR_DIRS:
        (pnr / name).mkdir(parents=True, exist_ok=True)
    return pnr


def config_path(root: Path) -> Path:
    return root / "pnr" / "config.yaml"


def lock_path(root: Path) -> Path:
    return root / "pnr" / "platform.lock.yaml"


def read_config(root: Path) -> Dict[str, Any]:
    path = config_path(root)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PnrError(f"Could not read {path}: {exc}") from exc
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise PnrError(f"{path} must contain a YAML mapping.")
    return dict(data)


def write_config(root: Path, config: Mapping[str, Any]) -> Path:
    ensure_pnr_layout(root)
    path = config_path(root)
    path.write_text(yaml.safe_dump(dict(config), sort_keys=False), encoding="utf-8")
    return path


def _resolve_path(root: Path, raw: str, label: str, *, file_ok: bool = True) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(raw)))
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if file_ok and not path.is_file():
        raise PnrError(f"{label} does not exist: {path}")
    return path


def _single_candidate(paths: Sequence[Path], label: str) -> Optional[Path]:
    files = sorted({path.resolve() for path in paths if path.is_file()})
    if len(files) > 1:
        listed = ", ".join(str(path) for path in files)
        raise PnrError(f"Multiple {label} candidates found: {listed}")
    return files[0] if files else None


def discover_sdc(root: Path) -> Optional[Path]:
    return _single_candidate(
        [
            *root.glob("constraints/*.sdc"),
            *root.glob("constraints/**/*.sdc"),
        ],
        "SDC",
    )


def _module_graph(paths: Sequence[Path]) -> Tuple[set[str], set[str]]:
    modules: set[str] = set()
    instantiated: set[str] = set()
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        text = re.sub(r"//.*?$|/\*.*?\*/", "", text, flags=re.MULTILINE | re.DOTALL)
        for module_match in MODULE_RE.finditer(text):
            modules.add(module_match.group(1))
            body = module_match.group(2)
            for instance_match in INSTANTIATION_RE.finditer(body):
                instantiated.add(instance_match.group(1))
    return modules, instantiated


def detect_top(paths: Sequence[Path]) -> str:
    """Return a unique module-graph root or require an explicit top."""
    modules, instantiated = _module_graph(paths)
    roots = sorted(modules - instantiated)
    if len(roots) == 1:
        return roots[0]
    if not roots:
        raise PnrError("No Verilog module declarations were found for top detection.")
    raise PnrError(
        "Multiple possible top modules were found: "
        + ", ".join(roots)
        + ". Pass --top MODULE."
    )


def _parse_area(value: Optional[str], label: str) -> Optional[str]:
    if value is None:
        return None
    parts = value.replace(",", " ").split()
    if len(parts) != 4:
        raise PnrError(f"{label} requires four coordinates: LX LY UX UY.")
    try:
        coords = [float(part) for part in parts]
    except ValueError as exc:
        raise PnrError(f"{label} coordinates must be numeric.") from exc
    if coords[2] <= coords[0] or coords[3] <= coords[1]:
        raise PnrError(f"{label} upper coordinates must exceed lower coordinates.")
    return " ".join(f"{coord:g}" for coord in coords)


def _parse_overrides(values: Sequence[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise PnrError(f"Invalid --set `{value}`; expected NAME=VALUE.")
        name, raw = value.split("=", 1)
        if not OVERRIDE_NAME_RE.fullmatch(name) or name in MAKE_OVERRIDE_DENY:
            raise PnrError(f"Unsafe or reserved ORFS override name `{name}`.")
        if not raw or any(token in raw for token in ("\n", "\r", "$", "`")):
            raise PnrError(f"Unsafe ORFS override value for `{name}`.")
        result[name] = raw
    return result


def _openroad_binary() -> Optional[str]:
    candidates = [
        shutil.which("openroad"),
        str(Path.home() / ".local/openroad/bin/openroad"),
        str(Path.home() / ".local/bin/openroad"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    return None


def _yosys_binary() -> Optional[str]:
    candidates = [
        os.environ.get("SAXOFLOW_YOSYS"),
        str(Path.home() / ".local/yosys/bin/yosys"),
        shutil.which("yosys"),
        str(Path.home() / ".local/bin/yosys"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    return None


def _tool_version(command: Sequence[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    output = (result.stdout or result.stderr).strip()
    return output.splitlines()[0] if output else "unknown"


def _orfs_revision(root: Path) -> str:
    revision_file = root / ".saxoflow-revision"
    if revision_file.is_file():
        return revision_file.read_text(encoding="utf-8").strip()
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _write_generated_sdc(
    root: Path,
    clock_port: Optional[str],
    clock_period: Optional[float],
) -> Path:
    if not clock_port or clock_period is None:
        raise PnrError(
            "No SDC file was found. Pass --sdc FILE or both --clock-port and "
            "--clock-period."
        )
    if not IDENTIFIER_RE.fullmatch(clock_port):
        raise PnrError(f"Invalid clock port `{clock_port}`.")
    path = root / "pnr/generated/saxoflow.sdc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Generated by SaxoFlow\n"
        f"create_clock -name {clock_port} -period {clock_period:g} "
        f"[get_ports {{{clock_port}}}]\n",
        encoding="utf-8",
    )
    return path


def _synthesis_manifest(root: Path) -> Dict[str, Any]:
    path = root / "synthesis/reports/saxoflow_synth_manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _augment_synthesis_manifest(
    root: Path,
    manifest: PlatformManifest,
    library: Mapping[str, Any],
    corner: Mapping[str, Any],
) -> None:
    path = root / "synthesis/reports/saxoflow_synth_manifest.json"
    data = _synthesis_manifest(root)
    data.update(
        {
            "platform": manifest.id,
            "pdk_version": manifest.version,
            "library": library.get("id"),
            "corner": corner.get("id"),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _run_platform_synthesis(
    root: Path,
    manifest: PlatformManifest,
    platform_dir: Path,
    library: Mapping[str, Any],
    corner: Mapping[str, Any],
    top: str,
    rtl_specs: Sequence[str],
    include_specs: Sequence[str],
    defines: Sequence[str],
    parameters: Sequence[str],
    clock_period: Optional[float],
) -> Path:
    if manifest.synthesis.get("mode") == "external-netlist-only":
        reason = manifest.synthesis.get(
            "reason",
            "the platform requires a synthesis configuration that cannot be "
            "represented by a single Liberty file",
        )
        raise PnrError(
            f"`--synthesize` is unavailable for `{manifest.id}`: {reason} "
            "Provide a platform-mapped netlist with --netlist."
        )
    liberty = resolve_artifact(
        platform_dir,
        str(corner["liberty"]),
        f"{manifest.id} Liberty",
    )
    from saxoflow.makeflow import synth as synth_command  # local import

    args: List[str] = [
        "--target",
        "asic",
        "--top",
        top,
        "--liberty",
        str(liberty),
        "--output-prefix",
        "synthesized",
        "--no-schematic",
        "--no-open-schematic",
        "--no-show-log",
    ]
    if clock_period is not None:
        args.extend(["--clock-period", str(clock_period)])
    for value in rtl_specs:
        args.extend(["--rtl", value])
    for value in include_specs:
        args.extend(["--include", value])
    for value in defines:
        args.extend(["--define", value])
    for value in parameters:
        args.extend(["--param", value])

    previous = Path.cwd()
    os.chdir(root)
    try:
        result = CliRunner().invoke(synth_command, args)
    finally:
        os.chdir(previous)
    if result.output:
        click.echo(result.output, nl=not result.output.endswith("\n"))
    if result.exit_code != 0:
        raise PnrError("Platform-aware ASIC synthesis failed.")
    netlist = root / "synthesis/out/synthesized.v"
    if not netlist.is_file():
        raise PnrError(f"Synthesis completed without the expected netlist: {netlist}")
    _verify_mapped_cells(netlist, liberty)
    _augment_synthesis_manifest(root, manifest, library, corner)
    return netlist.resolve()


def _read_text_maybe_gzip(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as stream:
            return stream.read()
    return path.read_text(encoding="utf-8", errors="ignore")


def _verify_mapped_cells(netlist: Path, liberty: Path) -> None:
    """Verify that external cell instances in a mapped netlist exist in Liberty."""
    liberty_text = _read_text_maybe_gzip(liberty)
    cells = set(
        re.findall(
            r"\bcell\s*\(\s*(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_$]*))\s*\)",
            liberty_text,
        )
    )
    cell_names = {quoted or plain for quoted, plain in cells}
    if not cell_names:
        raise PnrError(f"No cell declarations were found in Liberty file {liberty}.")

    defined, instantiated = _module_graph([netlist])
    external = {
        name
        for name in instantiated - defined
        if not name.startswith("$")
        and name not in {"and", "buf", "bufif0", "bufif1", "cmos", "nand",
                         "nmos", "nor", "not", "notif0", "notif1", "or", "pmos",
                         "pullup", "pulldown", "rcmos", "rnmos", "rpmos",
                         "rtran", "rtranif0", "rtranif1", "tran", "tranif0",
                         "tranif1", "xnor", "xor"}
    }
    unknown = sorted(external - cell_names)
    if unknown:
        preview = ", ".join(unknown[:10])
        suffix = " ..." if len(unknown) > 10 else ""
        raise PnrError(
            "Synthesized netlist contains cells outside the selected Liberty "
            f"library: {preview}{suffix}"
        )


def _resolve_netlists(
    root: Path,
    config: Mapping[str, Any],
    explicit: Sequence[str],
    manifest: PlatformManifest,
    library: Mapping[str, Any],
    corner: Mapping[str, Any],
    synthesize: bool,
    top: Optional[str],
    rtl_specs: Sequence[str],
    include_specs: Sequence[str],
    defines: Sequence[str],
    parameters: Sequence[str],
    clock_period: Optional[float],
    unsafe_netlist: bool,
) -> Tuple[List[Path], str]:
    if synthesize and explicit:
        raise PnrError("--synthesize cannot be combined with --netlist.")

    configured = config.get("netlists", [])
    if isinstance(configured, str):
        configured = [configured]
    specs = list(explicit) or list(configured or [])

    if synthesize:
        sources, unmatched, vhdl = collect_sources(
            root,
            rtl_specs or DEFAULT_RTL_SPECS,
            explicit=bool(rtl_specs),
        )
        if unmatched:
            raise PnrError("RTL inputs did not match files: " + ", ".join(unmatched))
        if vhdl:
            raise PnrError("VHDL is not supported by the ASIC synthesis handoff.")
        selected_top = top or detect_top(sources)
        netlist = _run_platform_synthesis(
            root,
            manifest,
            platform_root(manifest) or Path(),
            library,
            corner,
            selected_top,
            rtl_specs,
            include_specs,
            defines,
            parameters,
            clock_period,
        )
        return [netlist], selected_top

    if specs:
        paths = [_resolve_path(root, value, "Netlist") for value in specs]
        synth_data = _synthesis_manifest(root)
        known_outputs = set()
        for value in synth_data.get("outputs", []):
            if not isinstance(value, str):
                continue
            candidate = Path(os.path.expandvars(os.path.expanduser(value)))
            if not candidate.is_absolute():
                candidate = root / candidate
            if candidate.is_file():
                known_outputs.add(candidate.resolve())
        selected_outputs = set(paths) & known_outputs
        has_provenance = any(
            synth_data.get(key) is not None
            for key in ("platform", "library", "corner")
        )
        incompatible = (
            synth_data.get("platform") != manifest.id
            or synth_data.get("library") != library.get("id")
            or synth_data.get("corner") != corner.get("id")
        )
        if selected_outputs and has_provenance and incompatible and not unsafe_netlist:
            raise PnrError(
                "The selected netlist was synthesized for a different platform, "
                "library, or corner. Regenerate it for the locked platform or pass "
                "--unsafe-netlist to override this compatibility check."
            )
        selected_top = top or detect_top(paths)
        return paths, selected_top

    synth_data = _synthesis_manifest(root)
    outputs = synth_data.get("outputs", [])
    if isinstance(outputs, str):
        outputs = [outputs]
    compatible = (
        synth_data.get("target") == "asic"
        and synth_data.get("status") == "success"
        and synth_data.get("platform") == manifest.id
        and synth_data.get("library") == library.get("id")
        and synth_data.get("corner") == corner.get("id")
    )
    if compatible and outputs:
        netlist_outputs = [
            value
            for value in outputs
            if Path(str(value)).suffix.lower() in {".v", ".sv"}
        ]
        if not netlist_outputs:
            raise PnrError(
                "Compatible synthesis metadata does not contain a Verilog "
                "gate-level netlist. Rerun with --synthesize."
            )
        paths = [
            _resolve_path(root, value, "Synthesis output")
            for value in netlist_outputs
        ]
        selected_top = top or str(synth_data.get("top") or "") or detect_top(paths)
        return paths, selected_top

    raise PnrError(
        "No compatible mapped ASIC netlist is configured. Pass --netlist FILE "
        "or rerun with --synthesize."
    )


def _resolve_settings(
    manifest: PlatformManifest,
    config: Mapping[str, Any],
    options: Mapping[str, Any],
) -> Dict[str, Any]:
    settings = dict(manifest.defaults)
    for key in ("min_routing_layer", "max_routing_layer"):
        if key not in settings and manifest.physical.get(key):
            settings[key] = manifest.physical[key]
    for key, value in config.items():
        if value is not None:
            settings[key] = value
    for key, value in options.items():
        if value not in (None, (), []):
            settings[key] = value

    utilization = float(settings.get("utilization", 40))
    aspect_ratio = float(settings.get("aspect_ratio", 1.0))
    core_margin = float(settings.get("core_margin", 2))
    place_density = float(settings.get("place_density", 0.60))
    if not 1 <= utilization <= 95:
        raise PnrError("--utilization must be between 1 and 95.")
    if aspect_ratio <= 0:
        raise PnrError("--aspect-ratio must be greater than zero.")
    if core_margin < 0:
        raise PnrError("--core-margin cannot be negative.")
    if not 0 < place_density <= 1:
        raise PnrError("--place-density must be greater than 0 and at most 1.")
    settings.update(
        {
            "utilization": utilization,
            "aspect_ratio": aspect_ratio,
            "core_margin": core_margin,
            "place_density": place_density,
        }
    )
    settings["die_area"] = _parse_area(settings.get("die_area"), "--die-area")
    settings["core_area"] = _parse_area(settings.get("core_area"), "--core-area")
    if bool(settings["die_area"]) != bool(settings["core_area"]):
        raise PnrError("--die-area and --core-area must be provided together.")
    if settings["die_area"] and any(
        key in options and options.get(key) is not None
        for key in ("utilization", "aspect_ratio", "core_margin")
    ):
        raise PnrError(
            "Explicit die/core areas cannot be combined with automatic floorplan options."
        )

    for option in ("min_routing_layer", "max_routing_layer"):
        layer = settings.get(option)
        if layer and manifest.layers and layer not in manifest.layers:
            raise PnrError(
                f"Unknown {option.replace('_', ' ')} `{layer}`. Available: "
                + ", ".join(manifest.layers)
            )
    return settings


def _write_orfs_config(flow: ResolvedFlow, overrides: Mapping[str, str]) -> None:
    orfs_platform = str(flow.manifest.install.get("platform", flow.manifest.id))
    values: Dict[str, Any] = {
        "DESIGN_NAME": flow.top,
        "PLATFORM": orfs_platform,
        "SYNTH_NETLIST_FILES": " ".join(str(path) for path in flow.netlists),
        "SDC_FILE": str(flow.sdc),
        "PLACE_DENSITY": flow.settings["place_density"],
    }
    if flow.settings.get("die_area"):
        values.update(
            {
                "DIE_AREA": flow.settings["die_area"],
                "CORE_AREA": flow.settings["core_area"],
            }
        )
    else:
        values.update(
            {
                "CORE_UTILIZATION": flow.settings["utilization"],
                "CORE_ASPECT_RATIO": flow.settings["aspect_ratio"],
                "CORE_MARGIN": flow.settings["core_margin"],
            }
        )
    optional = {
        "MIN_ROUTING_LAYER": flow.settings.get("min_routing_layer"),
        "MAX_ROUTING_LAYER": flow.settings.get("max_routing_layer"),
        "NUM_CORES": flow.settings.get("threads"),
    }
    values.update({key: value for key, value in optional.items() if value is not None})
    values.update(flow.manifest.orfs_variables)
    values.update(flow.library.get("orfs_variables", {}))
    values.update(flow.corner.get("orfs_variables", {}))
    values.update(overrides)
    lines = [
        "# Generated by SaxoFlow. Edit pnr/config.yaml, not this file.",
        *(f"export {name} := {value}" for name, value in values.items()),
        "",
    ]
    flow.config_mk.parent.mkdir(parents=True, exist_ok=True)
    flow.config_mk.write_text("\n".join(lines), encoding="utf-8")


def _platform_lock_data(
    manifest: PlatformManifest,
    tech_root: Path,
    library: Mapping[str, Any],
    corner: Mapping[str, Any],
) -> Dict[str, Any]:
    orfs = orfs_home()
    openroad = _openroad_binary()
    lock: Dict[str, Any] = {
        "schema_version": 1,
        "platform": manifest.id,
        "pdk_version": manifest.version,
        "library": library.get("id"),
        "corner": corner.get("id"),
        "orfs_revision": _orfs_revision(orfs) if orfs else "unavailable",
        "openroad_version": (
            _tool_version([openroad, "-version"]) if openroad else "unavailable"
        ),
        "platform_root": str(tech_root),
        "artifacts": {},
    }
    artifact_specs: Dict[str, Any] = {
        "liberty": corner.get("liberty"),
        "platform_config": "config.mk",
    }
    for owner in (manifest.artifacts, library.get("artifacts", {}),
                  corner.get("artifacts", {})):
        for name in ("technology_lef", "cell_lefs", "rcx_rules", "rc_setup"):
            if owner.get(name):
                artifact_specs[name] = owner[name]
    for tool, artifacts in manifest.tooling.items():
        for name, raw_specs in artifacts.items():
            artifact_specs[f"tooling_{tool}_{name}"] = raw_specs
    for name, raw_specs in artifact_specs.items():
        records = [
            {"path": str(artifact), "sha256": file_sha256(artifact)}
            for artifact in resolve_artifact_matches(tech_root, raw_specs)
        ]
        if records:
            lock["artifacts"][name] = records[0] if len(records) == 1 else records
    if manifest.source_path and manifest.source_path.is_file():
        lock["manifest"] = {
            "path": str(manifest.source_path),
            "sha256": file_sha256(manifest.source_path),
        }
    return lock


def _write_lock(flow: ResolvedFlow) -> None:
    lock = _platform_lock_data(
        flow.manifest,
        flow.platform_root,
        flow.library,
        flow.corner,
    )
    lock_path(flow.root).write_text(
        yaml.safe_dump(lock, sort_keys=False),
        encoding="utf-8",
    )


def resolve_flow(root: Path, options: Mapping[str, Any]) -> ResolvedFlow:
    """Resolve project, platform, sources, constraints, and generated config."""
    if not (root / "Makefile").is_file():
        raise PnrError("Run `saxoflow pnr` from a SaxoFlow unit root.")
    ensure_pnr_layout(root)
    config = read_config(root)
    platform_id = options.get("platform") or config.get("platform")
    if not platform_id:
        raise PnrError(
            "No platform is configured. Run `saxoflow pnr init --platform PLATFORM`."
        )
    try:
        manifest = get_manifest(str(platform_id))
    except RegistryError as exc:
        raise PnrError(str(exc)) from exc
    if not is_installed(manifest):
        raise PnrError(
            f"Platform `{manifest.id}` is not activated. Run "
            f"`saxoflow pdk install {manifest.id} --accept-license`."
        )
    problems = verify_installation(manifest)
    if problems:
        raise PnrError("Platform verification failed: " + "; ".join(problems))
    missing_environment = [
        name for name in manifest.required_environment if name not in os.environ
    ]
    if missing_environment:
        raise PnrError(
            "Platform requires environment variable(s): "
            + ", ".join(missing_environment)
        )
    tech_root = platform_root(manifest)
    if tech_root is None:
        raise PnrError(f"Platform root for `{manifest.id}` is unavailable.")

    settings = _resolve_settings(manifest, config, options)
    try:
        library = manifest.library(settings.get("library"))
        corner = manifest.corner(library, settings.get("corner"))
    except RegistryError as exc:
        raise PnrError(str(exc)) from exc

    explicit_netlists = options.get("netlist_specs", ())
    netlists, top = _resolve_netlists(
        root,
        config,
        explicit_netlists,
        manifest,
        library,
        corner,
        bool(options.get("synthesize")),
        options.get("top") or config.get("top"),
        options.get("rtl_specs", ()),
        options.get("include_specs", ()),
        options.get("defines", ()),
        options.get("parameter_specs", ()),
        options.get("clock_period") or config.get("clock_period"),
        bool(options.get("unsafe_netlist")),
    )
    if not IDENTIFIER_RE.fullmatch(top):
        raise PnrError(f"Invalid top module `{top}`.")

    raw_sdc = options.get("sdc") or config.get("sdc")
    sdc = _resolve_path(root, raw_sdc, "SDC") if raw_sdc else discover_sdc(root)
    if sdc is None:
        sdc = _write_generated_sdc(
            root,
            options.get("clock_port") or config.get("clock_port"),
            options.get("clock_period") or config.get("clock_period"),
        )

    variant = str(options.get("variant") or config.get("variant") or "default")
    if not VARIANT_RE.fullmatch(variant):
        raise PnrError(f"Invalid variant name `{variant}`.")
    run_root = root / "pnr/runs" / variant
    run_root.mkdir(parents=True, exist_ok=True)
    flow = ResolvedFlow(
        root=root,
        manifest=manifest,
        platform_root=tech_root,
        library=library,
        corner=corner,
        top=top,
        netlists=netlists,
        sdc=sdc,
        variant=variant,
        settings=settings,
        run_root=run_root,
        config_mk=root / "pnr/generated" / f"{variant}.mk",
    )
    overrides = _parse_overrides(options.get("overrides", ()))
    _write_orfs_config(flow, overrides)
    _write_lock(flow)
    return flow


def orfs_command(flow: ResolvedFlow, stage: str) -> List[str]:
    root = orfs_home()
    if root is None:
        raise PnrError("ORFS is not installed. Run `saxoflow install orfs`.")
    flow_dir = root / "flow"
    if not (flow_dir / "Makefile").is_file():
        raise PnrError(f"ORFS flow Makefile was not found under {flow_dir}.")
    openroad = _openroad_binary()
    if openroad is None:
        raise PnrError(
            "OpenROAD is not available. Run `saxoflow install openroad`."
        )
    yosys = _yosys_binary()
    if yosys is None:
        raise PnrError("Yosys is not available. Run `saxoflow install yosys`.")
    target = ORFS_TARGETS[stage]
    return [
        "make",
        "-C",
        str(flow_dir),
        f"DESIGN_CONFIG={flow.config_mk}",
        f"WORK_HOME={flow.run_root}",
        f"FLOW_VARIANT={flow.variant}",
        f"OPENROAD_EXE={openroad}",
        f"YOSYS_EXE={yosys}",
        target,
    ]


def run_streaming(
    command: Sequence[str],
    *,
    cwd: Path,
    log_path: Path,
    show_output: bool = True,
) -> int:
    """Run a command with combined live output and an append-only log."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        process = subprocess.Popen(
            list(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            log.write(line)
            log.flush()
            if show_output:
                click.echo(line, nl=False)
        return process.wait()


def _tail(path: Path, count: int = 40) -> str:
    if not path.is_file():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-count:])


def _tcl_path(path: Path) -> str:
    return "{" + str(path).replace("}", r"\}") + "}"


def _failure_guidance(log_text: str) -> Optional[str]:
    if "PDN-0185" in log_text or "Insufficient width" in log_text:
        return (
            "The core is too small for the selected platform's power grid. "
            "Retry with larger explicit `--die-area` and `--core-area` values, "
            "then persist the working values in `pnr/config.yaml`."
        )
    return None


def _collect_artifacts(flow: ResolvedFlow) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for category in ("logs", "objects", "reports", "results"):
        paths = sorted(
            path
            for path in flow.run_root.rglob("*")
            if path.is_file() and category in path.parts
        )
        result[category] = [project_path(path, flow.root) for path in paths]
    return result


def _write_artifact_indexes(
    flow: ResolvedFlow,
    artifacts: Mapping[str, Sequence[str]],
) -> Dict[str, str]:
    indexes: Dict[str, str] = {}
    for category, paths in artifacts.items():
        index_dir = flow.root / "pnr" / category / flow.variant
        index_dir.mkdir(parents=True, exist_ok=True)
        index = index_dir / "artifacts.json"
        index.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "variant": flow.variant,
                    "category": category,
                    "artifacts": list(paths),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        indexes[category] = project_path(index, flow.root)
    return indexes


def _write_run_manifest(
    flow: ResolvedFlow,
    stage: str,
    status: str,
    command: Sequence[str],
    log_path: Path,
) -> Path:
    path = flow.run_root / "saxoflow-run.json"
    artifacts = _collect_artifacts(flow)
    data = {
        "schema_version": 1,
        "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "platform": flow.manifest.id,
        "library": flow.library.get("id"),
        "corner": flow.corner.get("id"),
        "top": flow.top,
        "variant": flow.variant,
        "stage": stage,
        "status": status,
        "netlists": [project_path(path, flow.root) for path in flow.netlists],
        "sdc": project_path(flow.sdc, flow.root),
        "generated_config": project_path(flow.config_mk, flow.root),
        "command": list(command),
        "log": project_path(log_path, flow.root),
        "artifacts": artifacts,
        "artifact_indexes": _write_artifact_indexes(flow, artifacts),
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def execute_stage(stage: str, options: Mapping[str, Any]) -> None:
    root = Path.cwd().resolve()
    flow = resolve_flow(root, options)
    command = orfs_command(flow, stage)
    click.secho(
        f"INFO: {stage} for {flow.top} on {flow.manifest.id} "
        f"({flow.library.get('id')}/{flow.corner.get('id')}, variant {flow.variant}).",
        fg="cyan",
    )
    click.echo(" ".join(command))
    if options.get("dry_run"):
        click.echo(f"Generated ORFS config: {project_path(flow.config_mk, root)}")
        return

    if options.get("fresh"):
        clean_target = f"clean_{ORFS_TARGETS[stage]}"
        clean_command = command[:-1] + [clean_target]
        clean_log = root / "pnr/logs" / flow.variant / f"{stage}-clean.log"
        clean_rc = run_streaming(clean_command, cwd=root, log_path=clean_log)
        if clean_rc != 0:
            raise click.ClickException(f"Failed to clean stage `{stage}`.")

    log_path = root / "pnr/logs" / flow.variant / f"{stage}.log"
    returncode = run_streaming(
        command,
        cwd=root,
        log_path=log_path,
        show_output=True,
    )
    status = "success" if returncode == 0 else "failed"
    run_manifest = _write_run_manifest(flow, stage, status, command, log_path)
    if returncode != 0:
        excerpt = _tail(log_path)
        if excerpt:
            click.secho(f"{stage} log excerpt:", fg="red")
            click.echo(excerpt)
        guidance = _failure_guidance(
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.is_file()
            else ""
        )
        if guidance:
            click.secho(f"Guidance: {guidance}", fg="yellow")
        raise click.ClickException(
            f"ORFS stage `{stage}` failed. Retry with `saxoflow pnr {stage} "
            f"--variant {flow.variant} --show-log`."
        )
    click.secho(f"SUCCESS: ORFS stage `{stage}` completed.", fg="green")
    click.echo(f"Run manifest: {project_path(run_manifest, root)}")
    if options.get("show_log"):
        click.echo(log_path.read_text(encoding="utf-8", errors="replace"))


def _common_stage_options(function):
    options = [
        click.option("--platform", metavar="PLATFORM"),
        click.option("--library", metavar="LIBRARY"),
        click.option("--corner", metavar="CORNER"),
        click.option("--top", metavar="MODULE"),
        click.option("--netlist", "netlist_specs", multiple=True, metavar="PATH"),
        click.option("--sdc", type=click.Path(dir_okay=False, path_type=str)),
        click.option("--synthesize", is_flag=True),
        click.option(
            "--unsafe-netlist",
            is_flag=True,
            help="Allow a netlist with conflicting synthesis provenance.",
        ),
        click.option("--rtl", "rtl_specs", multiple=True, metavar="PATH"),
        click.option("--include", "include_specs", multiple=True, metavar="DIR"),
        click.option("--define", "defines", multiple=True, metavar="NAME[=VALUE]"),
        click.option("--param", "parameter_specs", multiple=True, metavar="NAME=VALUE"),
        click.option("--clock-port", metavar="PORT"),
        click.option("--clock-period", type=click.FloatRange(min=0, min_open=True)),
        click.option("--utilization", type=click.FloatRange(min=1, max=95)),
        click.option("--aspect-ratio", type=click.FloatRange(min=0, min_open=True)),
        click.option("--core-margin", type=click.FloatRange(min=0)),
        click.option("--die-area", metavar='"LX LY UX UY"'),
        click.option("--core-area", metavar='"LX LY UX UY"'),
        click.option("--place-density", type=click.FloatRange(min=0, max=1, min_open=True)),
        click.option("--min-routing-layer", metavar="LAYER"),
        click.option("--max-routing-layer", metavar="LAYER"),
        click.option("--threads", type=click.IntRange(min=1)),
        click.option("--variant", default=None, metavar="NAME"),
        click.option("--set", "overrides", multiple=True, metavar="NAME=VALUE"),
        click.option("--fresh", is_flag=True),
        click.option("--dry-run", is_flag=True),
        click.option("--show-log", is_flag=True),
    ]
    for decorator in reversed(options):
        function = decorator(function)
    return function


@click.group("pnr")
def pnr() -> None:
    """Run staged physical design with ORFS and OpenROAD."""


@pnr.command("init")
@click.option("--platform", required=True, metavar="PLATFORM")
@click.option("--library", metavar="LIBRARY")
@click.option("--corner", metavar="CORNER")
@click.option("--top", metavar="MODULE")
@click.option("--netlist", "netlists", multiple=True, metavar="PATH")
@click.option("--sdc", type=click.Path(dir_okay=False, path_type=str))
@click.option("--clock-port", metavar="PORT")
@click.option("--clock-period", type=click.FloatRange(min=0, min_open=True))
@click.option("--force", is_flag=True)
def pnr_init(
    platform: str,
    library: Optional[str],
    corner: Optional[str],
    top: Optional[str],
    netlists: Tuple[str, ...],
    sdc: Optional[str],
    clock_port: Optional[str],
    clock_period: Optional[float],
    force: bool,
) -> None:
    """Initialize and lock a unit's physical-design configuration."""
    root = Path.cwd().resolve()
    if not (root / "Makefile").is_file():
        raise click.ClickException("Run `saxoflow pnr init` from a unit root.")
    try:
        manifest = get_manifest(platform)
        if not is_installed(manifest):
            raise PnrError(
                f"Platform `{manifest.id}` is not activated. Run "
                f"`saxoflow pdk install {manifest.id} --accept-license`."
            )
        selected_library = manifest.library(library)
        selected_corner = manifest.corner(selected_library, corner)
        tech_root = platform_root(manifest)
        if tech_root is None:
            raise PnrError(f"Platform root for `{manifest.id}` is unavailable.")
        problems = verify_installation(manifest)
        if problems:
            raise PnrError("Platform verification failed: " + "; ".join(problems))
    except (RegistryError, PnrError) as exc:
        raise click.ClickException(str(exc)) from exc

    path = config_path(root)
    if path.exists() and not force:
        raise click.ClickException(f"{path} already exists. Use --force to replace it.")
    config: Dict[str, Any] = {
        "schema_version": 1,
        "platform": manifest.id,
        "library": selected_library.get("id"),
        "corner": selected_corner.get("id"),
        "variant": "default",
    }
    optional = {
        "top": top,
        "netlists": list(netlists) or None,
        "sdc": sdc,
        "clock_port": clock_port,
        "clock_period": clock_period,
    }
    config.update({key: value for key, value in optional.items() if value is not None})
    write_config(root, config)
    lock_path(root).write_text(
        yaml.safe_dump(
            _platform_lock_data(
                manifest,
                tech_root,
                selected_library,
                selected_corner,
            ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    click.secho(f"SUCCESS: Initialized {project_path(path, root)}.", fg="green")
    if manifest.classification in {"experimental", "reference"}:
        click.secho(
            f"WARNING: `{manifest.id}` is a {manifest.classification} platform.",
            fg="yellow",
        )
    click.echo("Next: saxoflow pnr run --synthesize  # or configure a mapped netlist")


def _stage_command(name: str):
    @pnr.command(name)
    @_common_stage_options
    def command(**options: Any) -> None:
        try:
            execute_stage(name, options)
        except (PnrError, RegistryError) as exc:
            raise click.ClickException(str(exc)) from exc

    return command


pnr_run = _stage_command("run")
pnr_floorplan = _stage_command("floorplan")
pnr_place = _stage_command("place")
pnr_cts = _stage_command("cts")
pnr_route = _stage_command("route")
pnr_finish = _stage_command("finish")


@pnr.command("status")
@click.option("--variant", default="default", show_default=True)
def pnr_status(variant: str) -> None:
    """Show the latest recorded status for one experiment variant."""
    root = Path.cwd().resolve()
    path = root / "pnr/runs" / variant / "saxoflow-run.json"
    if not path.is_file():
        click.echo(f"No run manifest exists for variant `{variant}`.")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    click.echo(f"Variant: {variant}")
    click.echo(f"Platform: {data.get('platform', 'unknown')}")
    click.echo(f"Top: {data.get('top', 'unknown')}")
    click.echo(f"Last stage: {data.get('stage', 'unknown')}")
    click.echo(f"Status: {data.get('status', 'unknown')}")
    click.echo(f"Updated: {data.get('updated_at', 'unknown')}")
    for category, paths in sorted(data.get("artifacts", {}).items()):
        click.echo(f"{category.title()}: {len(paths)} artifact(s)")


def _flatten_metrics(data: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(data, dict):
        for key, value in data.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten_metrics(value, name)
    elif isinstance(data, (str, int, float, bool)):
        yield prefix, data


def _variant_metrics(root: Path, variant: str) -> Dict[str, Any]:
    run_root = root / "pnr/runs" / variant
    candidates = sorted(run_root.rglob("*metrics*.json"))
    metrics: Dict[str, Any] = {}
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key, value in _flatten_metrics(data):
            lower = key.lower()
            if any(
                token in lower
                for token in (
                    "wns",
                    "tns",
                    "area",
                    "util",
                    "power",
                    "wirelength",
                    "congestion",
                    "drc",
                    "runtime",
                    "memory",
                    "skew",
                    "instance",
                    "buffer",
                )
            ):
                metrics[key] = value
    return metrics


def _variant_artifact_indexes(root: Path, variant: str) -> Dict[str, str]:
    """Return stable top-level artifact index paths for one P&R variant."""
    run_manifest = root / "pnr/runs" / variant / "saxoflow-run.json"
    if not run_manifest.is_file():
        return {}
    try:
        data = json.loads(run_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    indexes = data.get("artifact_indexes", {})
    if not isinstance(indexes, dict):
        return {}
    return {
        str(category): str(path)
        for category, path in indexes.items()
        if isinstance(path, str) and path
    }


@pnr.command("report")
@click.option("--variant", default="default", show_default=True)
@click.option("--compare", "comparisons", multiple=True, metavar="VARIANT")
@click.option("--json-output", type=click.Path(dir_okay=False, path_type=Path))
def pnr_report(
    variant: str,
    comparisons: Tuple[str, ...],
    json_output: Optional[Path],
) -> None:
    """Summarize and compare available ORFS PPA metrics."""
    root = Path.cwd().resolve()
    variants = [variant, *comparisons]
    result = {name: _variant_metrics(root, name) for name in variants}
    if not any(result.values()):
        click.echo("No ORFS metrics JSON files were found for the selected variants.")
    for name, metrics in result.items():
        click.secho(f"Variant: {name}", fg="cyan")
        if not metrics:
            click.echo("  No metrics available.")
        for key, value in sorted(metrics.items()):
            click.echo(f"  {key}: {value}")
        indexes = _variant_artifact_indexes(root, name)
        for category, path in sorted(indexes.items()):
            click.echo(f"  {category} artifacts: {path}")
    if json_output:
        path = json_output.expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        click.echo(f"Report JSON: {path}")


def _select_gui_database(root: Path, variant: str, stage: Optional[str]) -> Path:
    run_root = root / "pnr/runs" / variant
    if stage:
        expected_name = GUI_STAGE_DATABASES[stage]
        matches = sorted(run_root.rglob(expected_name))
        if matches:
            return matches[-1]
        raise click.ClickException(
            f"No `{stage}` ODB checkpoint named `{expected_name}` was found "
            f"for variant `{variant}`."
        )
    candidates = sorted(run_root.rglob("*.odb"))
    if not candidates:
        raise click.ClickException(
            f"No ODB checkpoint found for variant `{variant}`."
        )
    return candidates[-1]


def _write_gui_bootstrap(
    root: Path,
    variant: str,
    database: Path,
) -> Tuple[Path, Optional[Path]]:
    config = read_config(root)
    platform_id = config.get("platform")
    if not platform_id:
        raise click.ClickException(
            "The project does not select a PDK platform. Run `saxoflow pnr init`."
        )
    try:
        manifest = get_manifest(str(platform_id))
        tech_root = platform_root(manifest)
        if tech_root is None:
            raise RegistryError(
                f"Platform `{manifest.id}` is not installed or activated."
            )
        library = manifest.library(config.get("library"))
        corner = manifest.corner(library, config.get("corner"))
        liberty = resolve_artifact(
            tech_root,
            str(corner["liberty"]),
            f"{manifest.id} {corner.get('id')} Liberty",
        )
    except (KeyError, RegistryError) as exc:
        raise click.ClickException(
            f"Could not prepare the OpenROAD GUI timing context: {exc}"
        ) from exc

    artifact_groups = (
        manifest.artifacts,
        library.get("artifacts", {}),
        corner.get("artifacts", {}),
    )
    rc_setup_spec = next(
        (
            str(group["rc_setup"])
            for group in artifact_groups
            if group.get("rc_setup")
        ),
        None,
    )
    rc_setup: Optional[Path] = None
    if rc_setup_spec:
        try:
            rc_setup = resolve_artifact(
                tech_root,
                rc_setup_spec,
                f"{manifest.id} OpenROAD RC setup",
            )
        except RegistryError as exc:
            raise click.ClickException(
                f"Could not prepare the OpenROAD GUI RC context: {exc}"
            ) from exc

    checkpoint_sdc = database.with_suffix(".sdc")
    sdc = checkpoint_sdc if checkpoint_sdc.is_file() else discover_sdc(root)
    lines = [
        "# Generated by SaxoFlow for timing-aware OpenROAD GUI inspection.",
        f"read_liberty {_tcl_path(liberty)}",
        f"read_db {_tcl_path(database)}",
    ]
    if sdc:
        lines.append(f"read_sdc {_tcl_path(sdc)}")
    if rc_setup:
        lines.append(f"source {_tcl_path(rc_setup)}")
    lines.append("")
    script = root / "pnr/generated" / f"gui-{variant}.tcl"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("\n".join(lines), encoding="utf-8")
    return script, sdc


def _gui_environment() -> Dict[str, str]:
    environment = dict(os.environ)
    if (
        "QT_QPA_PLATFORM" not in environment
        and (
            environment.get("WSL_DISTRO_NAME")
            or "microsoft" in platform.release().lower()
        )
    ):
        environment["QT_QPA_PLATFORM"] = "xcb"
    return environment


@pnr.command("gui")
@click.option("--variant", default="default", show_default=True)
@click.option("--stage", type=click.Choice(list(STAGES)))
@click.option("--db", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def pnr_gui(variant: str, stage: Optional[str], db: Optional[Path]) -> None:
    """Open an ODB checkpoint in the OpenROAD GUI."""
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise click.ClickException(
            "No graphical display is available. Configure WSLg/X11 and run "
            "`saxoflow diagnose pnr`."
        )
    root = Path.cwd().resolve()
    database = db.expanduser().resolve() if db else None
    if database is None:
        database = _select_gui_database(root, variant, stage)
    script, sdc = _write_gui_bootstrap(root, variant, database)
    binary = _openroad_binary()
    if not binary:
        raise click.ClickException("OpenROAD is not installed.")
    command = [binary, "-gui", str(script)]
    click.echo(f"Database: {project_path(database, root)}")
    if sdc:
        click.echo(f"Constraints: {project_path(sdc, root)}")
    else:
        click.secho(
            "WARNING: No matching SDC was found; timing views may be incomplete.",
            fg="yellow",
        )
    click.echo(f"GUI bootstrap: {project_path(script, root)}")
    click.echo(" ".join(command))
    subprocess.Popen(command, cwd=str(root), env=_gui_environment())


@pnr.command("clean")
@click.option("--variant", default="default", show_default=True)
@click.option("-y", "--yes", is_flag=True)
def pnr_clean(variant: str, yes: bool) -> None:
    """Remove one generated P&R variant without touching design inputs."""
    if not VARIANT_RE.fullmatch(variant):
        raise click.ClickException(f"Invalid variant `{variant}`.")
    root = Path.cwd().resolve()
    target = root / "pnr/runs" / variant
    if not target.exists():
        click.echo(f"No generated P&R run exists for variant `{variant}`.")
        return
    if not yes and not click.confirm(f"Remove generated variant `{variant}`?"):
        click.echo("Cancelled.")
        return
    shutil.rmtree(target)
    for category in ("logs", "objects", "reports", "results"):
        index_dir = root / "pnr" / category / variant
        if index_dir.exists():
            shutil.rmtree(index_dir)
    generated = root / "pnr/generated" / f"{variant}.mk"
    generated.unlink(missing_ok=True)
    click.secho(f"SUCCESS: Removed generated variant `{variant}`.", fg="green")


@pnr.command(
    "openroad",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.option("--script", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--db", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--gui", is_flag=True)
@click.option("--threads", type=click.IntRange(min=1))
@click.option("--log", "log_path", type=click.Path(dir_okay=False, path_type=Path))
@click.option("--metrics", type=click.Path(dir_okay=False, path_type=Path))
@click.pass_context
def pnr_openroad(
    ctx: click.Context,
    script: Optional[Path],
    db: Optional[Path],
    gui: bool,
    threads: Optional[int],
    log_path: Optional[Path],
    metrics: Optional[Path],
) -> None:
    """Run OpenROAD directly for custom Tcl or database exploration."""
    binary = _openroad_binary()
    if not binary:
        raise click.ClickException(
            "OpenROAD is not installed. Run `saxoflow install openroad`."
        )
    command = [binary]
    if gui:
        command.append("-gui")
    if db:
        command.extend(["-db", str(db.expanduser().resolve())])
    if threads:
        command.extend(["-threads", str(threads)])
    if log_path:
        command.extend(["-log", str(log_path.expanduser().resolve())])
    if metrics:
        command.extend(["-metrics", str(metrics.expanduser().resolve())])
    command.extend(ctx.args)
    if script:
        command.append(str(script.expanduser().resolve()))
    if not script and not db and not ctx.args:
        raise click.ClickException("Pass --script FILE, --db FILE, or OpenROAD arguments.")
    click.echo(" ".join(command))
    result = subprocess.run(command, cwd=str(Path.cwd()), check=False)
    if result.returncode != 0:
        raise click.ClickException(
            f"OpenROAD exited with status {result.returncode}."
        )


__all__ = [
    "pnr",
    "pnr_init",
    "pnr_run",
    "pnr_floorplan",
    "pnr_place",
    "pnr_cts",
    "pnr_route",
    "pnr_finish",
    "pnr_status",
    "pnr_report",
    "pnr_gui",
    "pnr_clean",
    "pnr_openroad",
    "resolve_flow",
    "detect_top",
    "run_streaming",
]
