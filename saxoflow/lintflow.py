"""Design-agnostic RTL linting for SaxoFlow unit projects."""

from __future__ import annotations

import glob
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import click

__all__ = ["lint"]

DEFAULT_RTL_SPECS: Tuple[str, ...] = (
    "source/rtl/systemverilog",
    "source/rtl/verilog",
)
DEFAULT_TB_SPECS: Tuple[str, ...] = (
    "source/tb/systemverilog",
    "source/tb/verilog",
)
DEFAULT_INCLUDE_SPECS: Tuple[str, ...] = ("source/rtl/include",)
HDL_SUFFIXES = {".v", ".sv"}
VHDL_SUFFIXES = {".vhd", ".vhdl"}
ENGINE_BINARIES = {
    "verible": "verible-verilog-lint",
    "verilator": "verilator",
}
_PACKAGE_RE = re.compile(r"(?m)^\s*package\s+(?!body\b)[A-Za-z_][A-Za-z0-9_$]*\b")


def _require_unit_root(root: Path) -> None:
    """Require commands to run from a SaxoFlow unit project root."""
    if not (root / "Makefile").is_file():
        raise click.UsageError(
            "No Makefile found. Run `saxoflow lint` from a SaxoFlow unit root."
        )


def _has_glob_magic(value: str) -> bool:
    return any(char in value for char in "*?[")


def _expand_spec(root: Path, raw_spec: str) -> List[Path]:
    """Expand a file, directory, or glob relative to *root*."""
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


def _collect_sources(
    root: Path,
    specs: Sequence[str],
) -> Tuple[List[Path], List[str], List[Path]]:
    """Collect Verilog/SystemVerilog files and report invalid specifications."""
    sources: List[Path] = []
    unmatched: List[str] = []
    vhdl_files: List[Path] = []
    seen = set()

    for spec in specs:
        matches = _expand_spec(root, spec)
        if not matches:
            unmatched.append(spec)
            continue

        matched_hdl = False
        for path in matches:
            suffix = path.suffix.lower()
            if suffix in VHDL_SUFFIXES:
                vhdl_files.append(path)
                continue
            if suffix not in HDL_SUFFIXES:
                continue
            matched_hdl = True
            key = path.resolve()
            if key not in seen:
                sources.append(path)
                seen.add(key)

        if not matched_hdl and not any(
            path.suffix.lower() in VHDL_SUFFIXES for path in matches
        ):
            unmatched.append(spec)

    return sorted(sources, key=lambda path: path.as_posix()), unmatched, vhdl_files


def _collect_include_dirs(
    root: Path,
    explicit_specs: Sequence[str],
) -> Tuple[List[Path], List[str]]:
    """Collect default and explicit include directories."""
    include_dirs: List[Path] = []
    invalid: List[str] = []
    seen = set()

    specs = list(DEFAULT_INCLUDE_SPECS) + list(explicit_specs)
    for spec in specs:
        expanded = os.path.expandvars(os.path.expanduser(spec.strip()))
        candidate = Path(expanded)
        pattern = str(candidate if candidate.is_absolute() else root / candidate)
        if _has_glob_magic(expanded):
            matches = [Path(item) for item in sorted(glob.glob(pattern))]
        else:
            matches = [Path(pattern)]

        valid_for_spec = False
        for path in matches:
            if not path.is_dir():
                continue
            valid_for_spec = True
            key = path.resolve()
            if key not in seen:
                include_dirs.append(path)
                seen.add(key)

        if spec in explicit_specs and not valid_for_spec:
            invalid.append(spec)

    return include_dirs, invalid


def _command_path(path: Path, root: Path) -> str:
    """Return a stable project-relative path when possible."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _is_package_file(path: Path) -> bool:
    """Return True when a SystemVerilog file declares a package."""
    if path.suffix.lower() != ".sv":
        return False
    try:
        return bool(_PACKAGE_RE.search(path.read_text(encoding="utf-8", errors="ignore")))
    except OSError:
        return False


def _verilator_source_order(sources: Sequence[Path]) -> List[Path]:
    """Place package declarations before other sources, then sort by path."""
    return sorted(
        sources,
        key=lambda path: (
            0 if _is_package_file(path) else 1,
            path.as_posix(),
        ),
    )


def _find_engine_binary(engine: str) -> Optional[str]:
    """Find an engine in PATH or SaxoFlow's managed user install locations."""
    binary = ENGINE_BINARIES[engine]
    found = shutil.which(binary)
    if found:
        return found

    home = Path.home()
    candidates = {
        "verible": [home / ".local/verible/bin/verible-verilog-lint"],
        "verilator": [
            home / ".local/verilator/bin/verilator",
            home / ".local/bin/verilator",
        ],
    }
    for candidate in candidates[engine]:
        if candidate.is_file() and os.access(str(candidate), os.X_OK):
            return str(candidate)
    return None


def _select_engines(tool: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Resolve requested engines and return selected and missing names."""
    requested = ["verible", "verilator"] if tool in {"auto", "all"} else [tool]
    selected: List[Tuple[str, str]] = []
    missing: List[str] = []
    for engine in requested:
        binary = _find_engine_binary(engine)
        if binary:
            selected.append((engine, binary))
        else:
            missing.append(engine)
    return selected, missing


def _resolve_existing_file(root: Path, raw_path: str, option_name: str) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(raw_path)))
    path = expanded if expanded.is_absolute() else root / expanded
    if not path.is_file():
        raise click.UsageError(f"{option_name} file not found: {raw_path}")
    return path


def _build_verible_command(
    binary: str,
    root: Path,
    sources: Sequence[Path],
    ruleset: str,
    rules: Optional[str],
    config: Optional[Path],
    waivers: Sequence[Path],
) -> List[str]:
    command = [binary, f"--ruleset={ruleset}"]
    if config:
        command.append(f"--rules_config={_command_path(config, root)}")
    else:
        command.append("--rules_config_search")
    if rules:
        command.append(f"--rules={rules}")
    if waivers:
        waiver_paths = ",".join(_command_path(path, root) for path in waivers)
        command.append(f"--waiver_files={waiver_paths}")
    command.extend(_command_path(path, root) for path in sources)
    return command


def _build_verilator_command(
    binary: str,
    root: Path,
    sources: Sequence[Path],
    include_dirs: Sequence[Path],
    top: Optional[str],
    include_tb: bool,
) -> List[str]:
    command = [binary, "--lint-only", "-Wall"]
    if include_tb:
        command.append("--timing")
    if top:
        command.extend(["--top-module", top])
    command.extend(f"-I{_command_path(path, root)}" for path in include_dirs)
    command.extend(
        _command_path(path, root) for path in _verilator_source_order(sources)
    )
    return command


def _run_engine(command: Sequence[str], root: Path) -> Tuple[int, str, bool]:
    """Run one lint engine and return status, output, and launch-error state."""
    try:
        result = subprocess.run(
            list(command),
            cwd=str(root),
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return 127, f"Failed to execute {command[0]}: {exc}", True

    parts = [part.strip() for part in (result.stdout, result.stderr) if part.strip()]
    return result.returncode, "\n".join(parts), False


def _write_report(
    report_dir: Path,
    timestamp: str,
    engine: str,
    command: Sequence[str],
    output: str,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{timestamp}-{engine}.log"
    body = f"$ {shlex.join(command)}\n\n{output}"
    if not body.endswith("\n"):
        body += "\n"
    report_path.write_text(body, encoding="utf-8")
    return report_path


def _print_output_excerpt(output: str, limit: int = 20) -> None:
    lines = output.splitlines()
    for line in lines[:limit]:
        click.echo(f"  {line}")
    if len(lines) > limit:
        click.echo(f"  ... {len(lines) - limit} more lines in the report")


@click.command("lint")
@click.option(
    "--rtl",
    "rtl_specs",
    multiple=True,
    metavar="PATH",
    help="RTL file, directory, or glob. Repeat for multiple inputs.",
)
@click.option(
    "--include",
    "include_specs",
    multiple=True,
    metavar="DIR",
    help="Additional Verilator include directory. Repeat for multiple directories.",
)
@click.option("--top", metavar="MODULE", help="Top module for Verilator.")
@click.option(
    "--include-tb",
    is_flag=True,
    help="Also lint Verilog/SystemVerilog files under source/tb.",
)
@click.option(
    "--tool",
    type=click.Choice(["auto", "all", "verible", "verilator"]),
    default="auto",
    show_default=True,
    help="Lint engine selection. Auto runs every available engine.",
)
@click.option(
    "--ruleset",
    type=click.Choice(["default", "all", "none"]),
    default="default",
    show_default=True,
    help="Verible base ruleset.",
)
@click.option("--rules", help="Verible rule enable, disable, or configuration string.")
@click.option(
    "--config",
    type=click.Path(dir_okay=False, path_type=str),
    help="Explicit Verible .rules.verible_lint configuration file.",
)
@click.option(
    "--waiver",
    "waiver_specs",
    multiple=True,
    type=click.Path(dir_okay=False, path_type=str),
    help="Verible waiver file. Repeat for multiple files.",
)
@click.option(
    "--no-fail",
    is_flag=True,
    help="Return success after completed lint runs even when violations are found.",
)
def lint(
    rtl_specs: Sequence[str],
    include_specs: Sequence[str],
    top: Optional[str],
    include_tb: bool,
    tool: str,
    ruleset: str,
    rules: Optional[str],
    config: Optional[str],
    waiver_specs: Sequence[str],
    no_fail: bool,
) -> None:
    """Lint Verilog and SystemVerilog sources in the current unit."""
    root = Path.cwd()
    _require_unit_root(root)

    source_specs = list(rtl_specs or DEFAULT_RTL_SPECS)
    sources, unmatched, vhdl_files = _collect_sources(root, source_specs)
    if include_tb:
        tb_sources, _, tb_vhdl_files = _collect_sources(root, DEFAULT_TB_SPECS)
        existing = {path.resolve() for path in sources}
        sources.extend(
            path for path in tb_sources if path.resolve() not in existing
        )
        vhdl_files.extend(tb_vhdl_files)

    if vhdl_files:
        paths = ", ".join(_command_path(path, root) for path in vhdl_files)
        raise click.UsageError(
            f"VHDL linting is not supported by this command: {paths}"
        )
    if unmatched and rtl_specs:
        raise click.UsageError(
            "No Verilog/SystemVerilog files matched: " + ", ".join(unmatched)
        )
    if not sources:
        raise click.UsageError(
            "No Verilog/SystemVerilog RTL files found. Add files under "
            "source/rtl or use --rtl PATH."
        )

    selected, missing = _select_engines(tool)
    if tool == "all" and missing:
        raise click.UsageError(
            "Requested lint engines are missing: "
            + ", ".join(missing)
            + ". Install Verible with `saxoflow install lint` and install "
            "Verilator with `saxoflow install verilator`."
        )
    if tool in {"verible", "verilator"} and missing:
        guidance = (
            "`saxoflow install lint`"
            if tool == "verible"
            else "`saxoflow install verilator`"
        )
        raise click.UsageError(f"{tool} is not installed. Run {guidance}.")
    if not selected:
        raise click.UsageError(
            "No lint engine is installed. Run `saxoflow install lint` for "
            "Verible and `saxoflow install verilator` for Verilator."
        )
    if tool == "auto" and missing:
        click.secho(
            "WARNING: Skipping unavailable lint engine(s): " + ", ".join(missing),
            fg="yellow",
        )

    uses_verible = any(engine == "verible" for engine, _ in selected)
    uses_verilator = any(engine == "verilator" for engine, _ in selected)
    include_dirs: List[Path] = []
    if uses_verilator:
        include_dirs, invalid_includes = _collect_include_dirs(root, include_specs)
        if invalid_includes:
            raise click.UsageError(
                "Include directory not found: " + ", ".join(invalid_includes)
            )
    elif include_specs or top:
        click.secho(
            "WARNING: Verilator-specific options were ignored because "
            "Verilator is not selected.",
            fg="yellow",
        )

    config_path = (
        _resolve_existing_file(root, config, "--config")
        if config and uses_verible
        else None
    )
    waiver_paths = (
        [
            _resolve_existing_file(root, waiver, "--waiver")
            for waiver in waiver_specs
        ]
        if uses_verible
        else []
    )
    if not uses_verible and (
        config or waiver_specs or rules or ruleset != "default"
    ):
        click.secho(
            "WARNING: Verible-specific options were ignored because Verible "
            "is not selected.",
            fg="yellow",
        )

    click.secho(
        f"INFO: Linting {len(sources)} source file(s) with "
        + ", ".join(engine for engine, _ in selected),
        fg="cyan",
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    report_dir = root / "lint/reports"
    failures: Dict[str, int] = {}
    launch_failures = set()

    for engine, binary in selected:
        if engine == "verible":
            command = _build_verible_command(
                binary,
                root,
                sources,
                ruleset,
                rules,
                config_path,
                waiver_paths,
            )
        else:
            command = _build_verilator_command(
                binary,
                root,
                sources,
                include_dirs,
                top,
                include_tb,
            )

        returncode, output, launch_error = _run_engine(command, root)
        report_path = _write_report(
            report_dir,
            timestamp,
            engine,
            command,
            output,
        )
        relative_report = report_path.relative_to(root).as_posix()
        if returncode == 0:
            click.secho(f"SUCCESS: {engine} passed.", fg="green")
        else:
            failures[engine] = returncode
            if launch_error:
                launch_failures.add(engine)
            click.secho(
                f"ERROR: {engine} reported issues (exit {returncode}).",
                fg="red",
            )
            _print_output_excerpt(output)
        click.secho(f"INFO: Report: {relative_report}", fg="cyan")

    if launch_failures or (failures and not no_fail):
        raise click.exceptions.Exit(1)
    if failures:
        click.secho(
            "WARNING: Lint issues were found, but --no-fail was requested.",
            fg="yellow",
        )
