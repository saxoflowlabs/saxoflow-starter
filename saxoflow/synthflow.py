"""Design-agnostic Yosys synthesis support for SaxoFlow unit projects."""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import click
from saxoflow.schematicflow import render_schematic

DEFAULT_RTL_SPECS: Tuple[str, ...] = (
    "source/rtl/systemverilog",
    "source/rtl/verilog",
    "source/rtl/vhdl",
    "synthesis/src",
)
DEFAULT_INCLUDE_SPECS: Tuple[str, ...] = ("source/rtl/include",)
HDL_SUFFIXES = {".v", ".sv"}
VHDL_SUFFIXES = {".vhd", ".vhdl"}
OUTPUT_SUFFIXES = {
    "verilog": ".v",
    "json": ".json",
    "blif": ".blif",
    "edif": ".edif",
}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")
_DEFINE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:=.*)?$")
_PACKAGE_RE = re.compile(r"(?m)^\s*package\s+(?!body\b)[A-Za-z_][A-Za-z0-9_$]*\b")

RunMake = Callable[[str, Optional[Dict[str, str]]], Dict[str, object]]


def _has_glob_magic(value: str) -> bool:
    return any(char in value for char in "*?[")


def _expand_spec(root: Path, raw_spec: str) -> List[Path]:
    """Expand a file, directory, or recursive glob relative to *root*."""
    expanded = os.path.expandvars(os.path.expanduser(raw_spec.strip()))
    candidate = Path(expanded)
    pattern = str(candidate if candidate.is_absolute() else root / candidate)

    if _has_glob_magic(expanded):
        matches = [Path(item) for item in sorted(glob.glob(pattern, recursive=True))]
    else:
        path = Path(pattern)
        if path.is_dir():
            matches = sorted(path.rglob("*"))
        elif path.exists():
            matches = [path]
        else:
            matches = []
    return [path for path in matches if path.is_file()]


def collect_sources(
    root: Path,
    specs: Sequence[str],
    explicit: bool,
) -> Tuple[List[Path], List[str], List[Path]]:
    """Collect synthesis sources and return sources, unmatched specs, and VHDL."""
    sources: List[Path] = []
    unmatched: List[str] = []
    vhdl_files: List[Path] = []
    seen = set()

    for spec in specs:
        matches = _expand_spec(root, spec)
        if not matches:
            if explicit:
                unmatched.append(spec)
            continue

        matched = False
        for path in matches:
            suffix = path.suffix.lower()
            if suffix in VHDL_SUFFIXES:
                vhdl_files.append(path)
                matched = True
                continue
            if suffix not in HDL_SUFFIXES:
                continue
            matched = True
            key = path.resolve()
            if key not in seen:
                sources.append(path)
                seen.add(key)
        if explicit and not matched:
            unmatched.append(spec)

    return source_order(sources), unmatched, sorted(vhdl_files)


def collect_include_dirs(
    root: Path,
    explicit_specs: Sequence[str],
) -> Tuple[List[Path], List[str]]:
    """Collect default and user-provided include directories."""
    include_dirs: List[Path] = []
    invalid: List[str] = []
    seen = set()

    for spec in [*DEFAULT_INCLUDE_SPECS, *explicit_specs]:
        expanded = os.path.expandvars(os.path.expanduser(spec.strip()))
        candidate = Path(expanded)
        pattern = str(candidate if candidate.is_absolute() else root / candidate)
        matches = (
            [Path(item) for item in sorted(glob.glob(pattern))]
            if _has_glob_magic(expanded)
            else [Path(pattern)]
        )
        valid = False
        for path in matches:
            if not path.is_dir():
                continue
            valid = True
            key = path.resolve()
            if key not in seen:
                include_dirs.append(path)
                seen.add(key)
        if spec in explicit_specs and not valid:
            invalid.append(spec)
    return include_dirs, invalid


def _is_package_file(path: Path) -> bool:
    if path.suffix.lower() != ".sv":
        return False
    try:
        return bool(_PACKAGE_RE.search(path.read_text(encoding="utf-8", errors="ignore")))
    except OSError:
        return False


def source_order(sources: Sequence[Path]) -> List[Path]:
    """Return deterministic source order with packages first."""
    return sorted(
        sources,
        key=lambda path: (
            0 if _is_package_file(path) else 1,
            path.as_posix(),
        ),
    )


def project_path(path: Path, root: Path) -> str:
    """Return a project-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _yosys_candidates() -> List[str]:
    candidates: List[Path] = [
        Path.home() / ".local/yosys/bin/yosys",
        Path.home() / ".local/bin/yosys",
    ]
    found = shutil.which("yosys")
    if found:
        candidates.append(Path(found))

    result: List[str] = []
    seen = set()
    for candidate in candidates:
        if not candidate.is_file() or not os.access(str(candidate), os.X_OK):
            continue
        key = candidate.resolve()
        if key not in seen:
            result.append(str(candidate))
            seen.add(key)
    return result


def slang_available(yosys_binary: str) -> bool:
    """Return whether *yosys_binary* can load the Slang frontend."""
    try:
        result = subprocess.run(
            [yosys_binary, "-Q", "-m", "slang", "-p", "help read_slang"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = f"{result.stdout}\n{result.stderr}"
    return result.returncode == 0 and "Slang-based SystemVerilog frontend" in output


def select_yosys(
    frontend: str,
    has_systemverilog: bool,
) -> Tuple[str, str, Optional[str]]:
    """Select a Yosys binary and effective frontend."""
    candidates = _yosys_candidates()
    if not candidates:
        raise click.UsageError(
            "Yosys is not installed. Run `saxoflow install yosys`."
        )

    wants_slang = frontend == "slang" or (
        frontend == "auto" and has_systemverilog
    )
    if wants_slang:
        for candidate in candidates:
            if slang_available(candidate):
                return candidate, "slang", None
        if frontend == "slang":
            raise click.UsageError(
                "The Slang frontend was requested, but no installed Yosys "
                "binary could load it. Run `saxoflow install yosys`."
            )
        return (
            candidates[0],
            "builtin",
            "Slang is unavailable; falling back to Yosys's limited built-in "
            "SystemVerilog frontend.",
        )
    return candidates[0], "builtin", None


def _resolve_file(root: Path, raw_path: str, option: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    path = expanded if expanded.is_absolute() else root / expanded
    if not path.is_file():
        raise click.UsageError(f"{option} file not found: {raw_path}")
    return path.resolve()


def _validate_identifier(value: str, option: str) -> None:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise click.UsageError(f"Invalid {option} identifier: {value}")


def parse_parameters(parameters: Sequence[str]) -> List[Tuple[str, str]]:
    result: List[Tuple[str, str]] = []
    for parameter in parameters:
        if "=" not in parameter:
            raise click.UsageError(
                f"Invalid --param value '{parameter}'. Use NAME=VALUE."
            )
        name, value = parameter.split("=", 1)
        _validate_identifier(name, "--param")
        if not value.strip():
            raise click.UsageError(
                f"Invalid --param value '{parameter}'. VALUE cannot be empty."
            )
        result.append((name, value))
    return result


def validate_defines(defines: Sequence[str]) -> None:
    for define in defines:
        if not _DEFINE_RE.fullmatch(define):
            raise click.UsageError(
                f"Invalid --define value '{define}'. Use NAME or NAME=VALUE."
            )


def _ys_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _slang_path(value: str) -> str:
    """Return a path accepted by read_slang's command parser."""
    if any(char.isspace() for char in value) or '"' in value or "'" in value:
        raise click.UsageError(
            "The Yosys Slang frontend cannot read paths containing whitespace "
            f"or quotes: {value}"
        )
    return value


def _frontend_lines(
    root: Path,
    sources: Sequence[Path],
    include_dirs: Sequence[Path],
    defines: Sequence[str],
    top: Optional[str],
    parameters: Sequence[Tuple[str, str]],
    frontend: str,
) -> List[str]:
    includes = [project_path(path, root) for path in include_dirs]

    if frontend == "slang":
        command = ["read_slang"]
        command.extend(f"-I{_slang_path(path)}" for path in includes)
        command.extend(f"-D{define}" for define in defines)
        if top:
            command.extend(["--top", top])
        command.extend(f"-G{name}={value}" for name, value in parameters)
        command.extend(
            _slang_path(project_path(path, root)) for path in sources
        )
        lines = ["plugin -i slang", " ".join(command)]
    else:
        command = ["read_verilog"]
        if any(path.suffix.lower() == ".sv" for path in sources):
            command.append("-sv")
        command.extend(f"-I{_ys_quote(path)}" for path in includes)
        command.extend(f"-D{define}" for define in defines)
        command.extend(
            _ys_quote(project_path(path, root)) for path in sources
        )
        lines = [" ".join(command)]

    hierarchy = ["hierarchy", "-check", "-top" if top else "-auto-top"]
    if top:
        hierarchy.append(top)
    if frontend == "builtin":
        for name, value in parameters:
            hierarchy.extend(["-chparam", name, value])
    lines.append(" ".join(hierarchy))
    return lines


def _target_lines(
    target: str,
    top: Optional[str],
    flatten: bool,
    device: str,
    family: str,
    liberty: Optional[Path],
    clock_period: Optional[float],
    lut: Optional[int],
    root: Path,
) -> List[str]:
    top_args = ["-top", top] if top else []
    if target == "generic":
        command = ["synth", *top_args]
        if not top:
            command.append("-auto-top")
        if flatten:
            command.append("-flatten")
        if lut is not None:
            command.extend(["-lut", str(lut)])
        return [" ".join(command)]

    if target == "ice40":
        command = ["synth_ice40", *top_args, "-device", device]
        if not flatten:
            command.append("-noflatten")
        return [" ".join(command)]

    if target == "ecp5":
        command = ["synth_ecp5", *top_args]
        if not flatten:
            command.append("-noflatten")
        return [" ".join(command)]

    if target == "xilinx":
        command = ["synth_xilinx", *top_args, "-family", family]
        if flatten:
            command.append("-flatten")
        return [" ".join(command)]

    if liberty is None:
        raise click.UsageError("--liberty is required for --target asic.")
    liberty_path = _ys_quote(project_path(liberty, root))
    lines = [
        "proc",
        "opt",
    ]
    if flatten:
        lines.extend(["flatten", "opt"])
    lines.extend(
        [
            "memory",
            "opt",
            "techmap",
            "opt",
            f"dfflibmap -liberty {liberty_path}",
        ]
    )
    abc = f"abc -liberty {liberty_path}"
    if clock_period is not None:
        abc += f" -D {int(round(clock_period * 1000))}"
    lines.extend([abc, "clean", "check"])
    return lines


def _default_formats(target: str) -> Tuple[str, ...]:
    if target in {"ice40", "ecp5", "xilinx"}:
        return ("json",)
    return ("verilog", "json")


def resolve_output_prefix(root: Path, raw_prefix: Optional[str]) -> Path:
    """Resolve output basename under synthesis/out unless explicitly absolute."""
    if not raw_prefix:
        return root / "synthesis/out/synthesized"
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_prefix)))
    if expanded.suffix.lower() in set(OUTPUT_SUFFIXES.values()):
        raise click.UsageError("--output-prefix must not include a file extension.")
    return expanded if expanded.is_absolute() else root / "synthesis/out" / expanded


def generate_script(
    root: Path,
    sources: Sequence[Path],
    include_dirs: Sequence[Path],
    defines: Sequence[str],
    top: Optional[str],
    parameters: Sequence[Tuple[str, str]],
    frontend: str,
    target: str,
    device: str,
    family: str,
    liberty: Optional[Path],
    clock_period: Optional[float],
    lut: Optional[int],
    flatten: bool,
    formats: Sequence[str],
    output_prefix: Path,
) -> str:
    """Return the complete reproducible Yosys runtime script."""
    lines = [
        "# Generated by `saxoflow synth`.",
        "# This file is reproducible and may be inspected or rerun directly.",
        "",
    ]
    if target == "asic" and liberty is not None:
        liberty_path = _ys_quote(project_path(liberty, root))
        lines.append(f"read_liberty -lib {liberty_path}")

    lines.extend(
        _frontend_lines(
            root,
            sources,
            include_dirs,
            defines,
            top,
            parameters,
            frontend,
        )
    )
    lines.extend(
        _target_lines(
            target,
            top,
            flatten,
            device,
            family,
            liberty,
            clock_period,
            lut,
            root,
        )
    )

    stat_args = ""
    if target == "asic" and liberty is not None:
        stat_args = " -liberty " + _ys_quote(project_path(liberty, root))
    lines.extend(
        [
            "",
            "tee -o synthesis/reports/stats.txt stat" + stat_args,
            "tee -o synthesis/reports/stats.json stat -json" + stat_args,
            "",
        ]
    )
    for output_format in formats:
        output_path = Path(str(output_prefix) + OUTPUT_SUFFIXES[output_format])
        output_arg = _ys_quote(project_path(output_path, root))
        if output_format == "verilog":
            lines.append(f"write_verilog -noattr {output_arg}")
        elif output_format == "json":
            lines.append(f"write_json {output_arg}")
        elif output_format == "blif":
            lines.append(f"write_blif {output_arg}")
        else:
            lines.append(f"write_edif {output_arg}")
    return "\n".join(lines) + "\n"


def _custom_script_conflicts(
    rtl_specs: Sequence[str],
    include_specs: Sequence[str],
    defines: Sequence[str],
    top: Optional[str],
    parameters: Sequence[str],
    frontend: str,
    target: str,
    device: str,
    family: str,
    liberty: Optional[str],
    clock_period: Optional[float],
    lut: Optional[int],
    flatten: bool,
    formats: Sequence[str],
    output_prefix: Optional[str],
) -> bool:
    return bool(
        rtl_specs
        or include_specs
        or defines
        or top
        or parameters
        or frontend != "auto"
        or target != "generic"
        or device != "hx"
        or family != "xc7"
        or liberty
        or clock_period is not None
        or lut is not None
        or not flatten
        or formats
        or output_prefix
    )


def _validate_target_options(
    target: str,
    device: str,
    family: str,
    liberty: Optional[str],
    clock_period: Optional[float],
    lut: Optional[int],
) -> None:
    if target != "ice40" and device != "hx":
        raise click.UsageError("--device is only valid with --target ice40.")
    if target != "xilinx" and family != "xc7":
        raise click.UsageError("--family is only valid with --target xilinx.")
    if target != "asic" and liberty:
        raise click.UsageError("--liberty is only valid with --target asic.")
    if target != "asic" and clock_period is not None:
        raise click.UsageError(
            "--clock-period is only valid with --target asic."
        )
    if target != "generic" and lut is not None:
        raise click.UsageError("--lut is only valid with --target generic.")


def _run_preflight(
    root: Path,
    sources: Optional[Sequence[Path]] = None,
    include_dirs: Optional[Sequence[Path]] = None,
    top: Optional[str] = None,
) -> None:
    command = [sys.executable, "-m", "saxoflow.cli", "lint"]
    for source in sources or ():
        command.extend(["--rtl", project_path(source, root)])
    for include_dir in include_dirs or ():
        command.extend(["--include", project_path(include_dir, root)])
    if top:
        command.extend(["--top", top])
    result = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    output = f"{result.stdout}{result.stderr}"
    if output:
        click.echo(output, nl=not output.endswith("\n"))
    if result.returncode != 0:
        raise click.ClickException("Synthesis preflight lint failed.")


def _show_yosys_log(
    root: Path,
    *,
    full: bool,
    line_limit: int = 40,
) -> None:
    log_path = root / "synthesis/reports/yosys.log"
    if not log_path.is_file():
        return
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines:
        return
    if full:
        click.secho("Yosys log:", fg="cyan")
        for line in lines:
            click.echo(line)
        return

    click.secho("Yosys log excerpt:", fg="red")
    for line in lines[-line_limit:]:
        click.echo(f"  {line}")


def _show_outputs(root: Path) -> None:
    reports = sorted(
        path
        for path in (root / "synthesis/reports").glob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    outputs = sorted(
        path
        for path in (root / "synthesis/out").rglob("*")
        if path.is_file() and not path.name.startswith(".")
    )
    if reports:
        click.secho(
            "Reports: "
            + ", ".join(project_path(path, root) for path in reports),
            fg="yellow",
        )
    if outputs:
        click.secho(
            "Outputs: "
            + ", ".join(project_path(path, root) for path in outputs),
            fg="yellow",
        )


def _write_synthesis_manifest(
    root: Path,
    *,
    status: str,
    target: str,
    top: Optional[str],
    frontend: str,
    yosys_binary: str,
    sources: Sequence[Path],
    include_dirs: Sequence[Path],
    defines: Sequence[str],
    parameters: Mapping[str, str],
    liberty: Optional[Path],
    output_prefix: Optional[Path],
    script: Optional[Path],
) -> Path:
    """Write reproducible synthesis metadata for downstream P&R."""
    reports = root / "synthesis/reports"
    reports.mkdir(parents=True, exist_ok=True)
    if output_prefix is not None:
        outputs = sorted(
            Path(str(output_prefix) + suffix)
            for suffix in OUTPUT_SUFFIXES.values()
            if Path(str(output_prefix) + suffix).is_file()
        )
    else:
        outputs = sorted(
            path
            for path in (root / "synthesis/out").rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )
    try:
        version_result = subprocess.run(
            [yosys_binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        yosys_version = (version_result.stdout or version_result.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        yosys_version = "unknown"
    data = {
        "schema_version": 1,
        "status": status,
        "target": target,
        "top": top,
        "frontend": frontend,
        "yosys_binary": yosys_binary,
        "yosys_version": yosys_version.splitlines()[0] if yosys_version else "unknown",
        "sources": [project_path(path, root) for path in sources],
        "include_dirs": [project_path(path, root) for path in include_dirs],
        "defines": list(defines),
        "parameters": dict(parameters),
        "liberty": project_path(liberty, root) if liberty else None,
        "output_prefix": project_path(output_prefix, root) if output_prefix else None,
        "script": project_path(script, root) if script else None,
        "outputs": [project_path(path, root) for path in outputs],
    }
    path = reports / "saxoflow_synth_manifest.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_synthesis(
    *,
    run_make: RunMake,
    rtl_specs: Sequence[str],
    include_specs: Sequence[str],
    defines: Sequence[str],
    top: Optional[str],
    parameter_specs: Sequence[str],
    frontend: str,
    target: str,
    device: str,
    family: str,
    liberty: Optional[str],
    clock_period: Optional[float],
    lut: Optional[int],
    flatten: bool,
    formats: Sequence[str],
    output_prefix: Optional[str],
    preflight_lint: bool,
    script: Optional[str],
    show_log: bool,
    create_schematic: bool,
    schematic_output: Optional[str],
    schematic_input: Optional[str],
    schematic_skin: Optional[str],
    schematic_timeout: int,
    open_schematic: bool,
) -> None:
    """Validate options, generate a runtime script, and run the Make target."""
    root = Path.cwd()
    if not (root / "Makefile").is_file():
        raise click.UsageError(
            "No Makefile found. Run `saxoflow synth` from a SaxoFlow unit root."
        )

    sources: List[Path] = []
    include_dirs: List[Path] = []
    parameters: Dict[str, str] = {}
    liberty_path: Optional[Path] = None
    prefix: Optional[Path] = None
    effective_frontend = frontend

    if script:
        if _custom_script_conflicts(
            rtl_specs,
            include_specs,
            defines,
            top,
            parameter_specs,
            frontend,
            target,
            device,
            family,
            liberty,
            clock_period,
            lut,
            flatten,
            formats,
            output_prefix,
        ):
            raise click.UsageError(
                "--script cannot be combined with generated-flow options."
            )
        script_path = _resolve_file(root, script, "--script")
        yosys_binary, _, _ = select_yosys("builtin", False)
        effective_frontend = "custom-script"
        if preflight_lint:
            _run_preflight(root)
    else:
        _validate_target_options(
            target,
            device,
            family,
            liberty,
            clock_period,
            lut,
        )
        if top:
            _validate_identifier(top, "--top")
        parameters = parse_parameters(parameter_specs)
        if parameters and not top:
            raise click.UsageError("--param requires an explicit --top module.")
        validate_defines(defines)

        sources, unmatched, vhdl_files = collect_sources(
            root,
            rtl_specs or DEFAULT_RTL_SPECS,
            explicit=bool(rtl_specs),
        )
        if unmatched:
            raise click.UsageError(
                "No Verilog/SystemVerilog files matched: "
                + ", ".join(unmatched)
            )
        if vhdl_files:
            raise click.UsageError(
                "VHDL synthesis is not supported by this wrapper: "
                + ", ".join(project_path(path, root) for path in vhdl_files)
            )
        if not sources:
            raise click.UsageError(
                "No Verilog/SystemVerilog RTL files found. Add sources under "
                "source/rtl or synthesis/src, or use --rtl PATH."
            )

        include_dirs, invalid_includes = collect_include_dirs(
            root,
            include_specs,
        )
        if invalid_includes:
            raise click.UsageError(
                "Include directory not found: " + ", ".join(invalid_includes)
            )

        liberty_path = (
            _resolve_file(root, liberty, "--liberty") if liberty else None
        )
        has_sv = any(path.suffix.lower() == ".sv" for path in sources)
        yosys_binary, effective_frontend, warning = select_yosys(
            frontend,
            has_sv,
        )
        if warning:
            click.secho(f"WARNING: {warning}", fg="yellow")

        selected_formats = tuple(formats) or _default_formats(target)
        if create_schematic and "json" not in selected_formats:
            selected_formats = (*selected_formats, "json")
        prefix = resolve_output_prefix(root, output_prefix)
        prefix.parent.mkdir(parents=True, exist_ok=True)
        reports_dir = root / "synthesis/reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        script_path = reports_dir / "saxoflow_synth.ys"
        script_path.write_text(
            generate_script(
                root,
                sources,
                include_dirs,
                defines,
                top,
                parameters,
                effective_frontend,
                target,
                device,
                family,
                liberty_path,
                clock_period,
                lut,
                flatten,
                selected_formats,
                prefix,
            ),
            encoding="utf-8",
        )
        if preflight_lint:
            _run_preflight(root, sources, include_dirs, top)
        click.secho(
            f"INFO: Discovered {len(sources)} RTL source file(s).",
            fg="cyan",
        )
        click.secho(
            f"INFO: Yosys frontend: {effective_frontend}; target: {target}.",
            fg="cyan",
        )

    click.secho("INFO: Running Yosys synthesis...", fg="cyan")
    result = run_make(
        "synth",
        {
            "YOSYS_BIN": yosys_binary,
            "YOSYS_SCRIPT": project_path(script_path, root),
        },
    )
    stdout = str(result.get("stdout", ""))
    stderr = str(result.get("stderr", ""))
    returncode = int(result.get("returncode", 0))
    if stdout:
        click.echo(stdout, nl=not stdout.endswith("\n"))
    if stderr:
        click.echo(stderr, err=True, nl=not stderr.endswith("\n"))
    if returncode != 0:
        _write_synthesis_manifest(
            root,
            status="failed",
            target=target,
            top=top,
            frontend=effective_frontend,
            yosys_binary=yosys_binary,
            sources=sources,
            include_dirs=include_dirs,
            defines=defines,
            parameters=parameters,
            liberty=liberty_path,
            output_prefix=prefix,
            script=script_path,
        )
        _show_yosys_log(root, full=show_log)
        raise click.Abort()

    _write_synthesis_manifest(
        root,
        status="success",
        target=target,
        top=top,
        frontend=effective_frontend,
        yosys_binary=yosys_binary,
        sources=sources,
        include_dirs=include_dirs,
        defines=defines,
        parameters=parameters,
        liberty=liberty_path,
        output_prefix=prefix,
        script=script_path,
    )

    if show_log:
        _show_yosys_log(root, full=True)

    if create_schematic:
        if schematic_input:
            json_path = Path(
                os.path.expandvars(os.path.expanduser(schematic_input))
            )
            if not json_path.is_absolute():
                json_path = root / json_path
        elif script:
            click.secho(
                "WARNING: Automatic schematic generation is skipped for a "
                "custom Yosys script. Use --schematic-input FILE to select "
                "the JSON produced by that script.",
                fg="yellow",
            )
            json_path = None
        else:
            json_path = Path(str(prefix) + OUTPUT_SUFFIXES["json"])
        output_path = Path(
            os.path.expandvars(
                os.path.expanduser(
                    schematic_output or "synthesis/reports/schematic.svg"
                )
            )
        )
        if not output_path.is_absolute():
            output_path = root / output_path
        skin_path = None
        if schematic_skin:
            skin_path = Path(
                os.path.expandvars(os.path.expanduser(schematic_skin))
            )
            if not skin_path.is_absolute():
                skin_path = root / skin_path
        if json_path is None:
            pass
        elif json_path.is_file():
            render_schematic(
                root=root,
                input_path=json_path,
                output_path=output_path,
                skin_path=skin_path,
                timeout=schematic_timeout,
                missing_ok=True,
                open_viewer=open_schematic,
            )
        else:
            click.secho(
                "WARNING: Schematic generation skipped because no Yosys JSON "
                f"netlist was found at {project_path(json_path, root)}.",
                fg="yellow",
            )
    _show_outputs(root)
