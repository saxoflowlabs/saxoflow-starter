"""Lint adapter that wraps SaxoFlow's deterministic lint flow."""

from __future__ import annotations

import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import click

from saxoflow import lintflow
from saxoflow.source_manifests.service import SourceManifestResolutionError, resolve_rtl_specs
from saxoflow.schemas.diagnostics import DiagnosticEntry
from saxoflow.schemas.tools import ToolRequest, ToolRun
from saxoflow.tools.adapters.base import BaseToolAdapter, ToolAdapterError

_DIAG_PATH_RE = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<message>.+)$"
)
_DIAG_PERCENT_RE = re.compile(r"^%(?P<severity>Warning|Error)(?:-[^:]+)?:\s*(?P<message>.+)$")


class LintToolAdapter(BaseToolAdapter):
    """Capability adapter for `lint.run` using existing lintflow internals."""

    capability = "lint.run"

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._lint_options(request, root)
        try:
            sources, include_dirs, selected, command_build_inputs = self._prepare(root, options)
        except click.UsageError as exc:
            return ToolRun.from_mapping(
                {
                    "status": "failed",
                    "capability": self.capability,
                    "tool_name": options.get("tool", "lint"),
                    "exit_code": 1,
                    "diagnostics": [
                        {
                            "message": str(exc),
                            "severity": "error",
                            "source": "lintflow",
                        }
                    ],
                }
            )

        commands = self._build_commands(
            root=root,
            sources=sources,
            include_dirs=include_dirs,
            selected=selected,
            options=options,
        )

        if request.dry_run:
            return ToolRun.from_mapping(
                {
                    "status": "skipped",
                    "capability": self.capability,
                    "tool_name": ",".join(engine for engine, _ in selected),
                    "command": " && ".join(shlex.join(command) for command in commands),
                    "diagnostics": [],
                }
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        report_dir = root / "lint/reports"

        all_diagnostics: List[DiagnosticEntry] = []
        outputs: List[str] = []
        failures: Dict[str, int] = {}
        launch_failures = set()

        for (engine, _), command in zip(selected, commands):
            returncode, output, launch_error = lintflow._run_engine(command, root)
            lintflow._write_report(report_dir, timestamp, engine, command, output)
            outputs.append(output)
            if returncode != 0:
                failures[engine] = returncode
                if launch_error:
                    launch_failures.add(engine)
                all_diagnostics.extend(self._parse_diagnostics(output, engine))

        if failures and not all_diagnostics:
            all_diagnostics.append(
                DiagnosticEntry(
                    message="Lint failed without diagnostic output.",
                    severity="error",
                    source="lintflow",
                )
            )

        should_fail = bool(launch_failures or (failures and not options["no_fail"]))
        status = "failed" if should_fail else "success"
        exit_code = max(failures.values()) if failures else 0
        command_text = " && ".join(shlex.join(command) for command in commands)

        run_payload = {
            "status": status,
            "capability": self.capability,
            "tool_name": ",".join(engine for engine, _ in selected),
            "command": command_text,
            "exit_code": exit_code,
            "stdout": "\n".join(chunk for chunk in outputs if chunk.strip()) or None,
            "diagnostics": [diag.to_dict() for diag in all_diagnostics],
        }

        return ToolRun.from_mapping(run_payload)

    def _lint_options(self, request: ToolRequest, root: Path) -> Dict[str, Any]:
        raw = request.options.get("lint") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        source_manifest = (
            request.options.get("source_manifest")
            if isinstance(request.options, Mapping) and isinstance(request.options.get("source_manifest"), Mapping)
            else None
        )

        tool = str(options.get("tool", "auto")).strip().lower()
        if tool not in {"auto", "all", "verible", "verilator"}:
            raise ToolAdapterError("Lint option `tool` must be one of: auto, all, verible, verilator.")

        ruleset = str(options.get("ruleset", "default")).strip().lower()
        if ruleset not in {"default", "all", "none"}:
            raise ToolAdapterError("Lint option `ruleset` must be one of: default, all, none.")

        rtl_specs = self._as_string_list(options.get("rtl"), ())
        explicit_rtl_specs = options.get("rtl") is not None
        try:
            resolved_rtl_specs = resolve_rtl_specs(
                root,
                explicit_specs=rtl_specs,
                default_specs=lintflow.DEFAULT_RTL_SPECS,
                source_manifest_options=source_manifest,
                target="rtl",
            )
        except SourceManifestResolutionError as exc:
            raise ToolAdapterError(str(exc)) from exc

        return {
            "rtl_specs": list(resolved_rtl_specs),
            "explicit_rtl_specs": explicit_rtl_specs,
            "include_specs": self._as_string_list(options.get("include"), ()),
            "include_tb": bool(options.get("include_tb", False)),
            "tool": tool,
            "top": self._optional_string(options.get("top")),
            "ruleset": ruleset,
            "rules": self._optional_string(options.get("rules")),
            "config": self._optional_string(options.get("config")),
            "waiver_specs": self._as_string_list(options.get("waiver"), ()),
            "no_fail": bool(options.get("no_fail", False)),
        }

    @staticmethod
    def _as_string_list(value: Any, default: Sequence[str]) -> List[str]:
        if value is None:
            return list(default)
        if isinstance(value, str):
            return [value]
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item).strip()]
        raise ToolAdapterError("Lint option must be a string or list of strings.")

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _prepare(
        self,
        root: Path,
        options: Mapping[str, Any],
    ) -> Tuple[List[Path], List[Path], List[Tuple[str, str]], Dict[str, Any]]:
        lintflow._require_unit_root(root)

        sources, unmatched, vhdl_files = lintflow._collect_sources(root, options["rtl_specs"])
        if options["include_tb"]:
            tb_sources, _, tb_vhdl_files = lintflow._collect_sources(root, lintflow.DEFAULT_TB_SPECS)
            existing = {path.resolve() for path in sources}
            sources.extend(path for path in tb_sources if path.resolve() not in existing)
            vhdl_files.extend(tb_vhdl_files)

        if vhdl_files:
            paths = ", ".join(lintflow._command_path(path, root) for path in vhdl_files)
            raise click.UsageError(f"VHDL linting is not supported by this command: {paths}")
        if unmatched and options["explicit_rtl_specs"]:
            raise click.UsageError("No Verilog/SystemVerilog files matched: " + ", ".join(unmatched))
        if not sources:
            raise click.UsageError(
                "No Verilog/SystemVerilog RTL files found. Add files under source/rtl or use --rtl PATH."
            )

        selected, missing = lintflow._select_engines(options["tool"])
        if options["tool"] == "all" and missing:
            raise click.UsageError("Requested lint engines are missing: " + ", ".join(missing))
        if options["tool"] in {"verible", "verilator"} and missing:
            raise click.UsageError(f"{options['tool']} is not installed.")
        if not selected:
            raise click.UsageError("No lint engine is installed.")

        include_dirs: List[Path] = []
        uses_verilator = any(engine == "verilator" for engine, _ in selected)
        if uses_verilator:
            include_dirs, invalid_includes = lintflow._collect_include_dirs(root, options["include_specs"])
            if invalid_includes:
                raise click.UsageError("Include directory not found: " + ", ".join(invalid_includes))

        return sources, include_dirs, selected, {"missing": missing}

    def _build_commands(
        self,
        root: Path,
        sources: Sequence[Path],
        include_dirs: Sequence[Path],
        selected: Sequence[Tuple[str, str]],
        options: Mapping[str, Any],
    ) -> List[List[str]]:
        config_path = (
            lintflow._resolve_existing_file(root, options["config"], "--config")
            if options["config"] and any(engine == "verible" for engine, _ in selected)
            else None
        )
        waiver_paths = (
            [lintflow._resolve_existing_file(root, spec, "--waiver") for spec in options["waiver_specs"]]
            if any(engine == "verible" for engine, _ in selected)
            else []
        )

        commands: List[List[str]] = []
        for engine, binary in selected:
            if engine == "verible":
                command = lintflow._build_verible_command(
                    binary=binary,
                    root=root,
                    sources=sources,
                    ruleset=options["ruleset"],
                    rules=options["rules"],
                    config=config_path,
                    waivers=waiver_paths,
                )
            else:
                command = lintflow._build_verilator_command(
                    binary=binary,
                    root=root,
                    sources=sources,
                    include_dirs=include_dirs,
                    top=options["top"],
                    include_tb=bool(options["include_tb"]),
                )
            commands.append(command)
        return commands

    @staticmethod
    def _parse_diagnostics(output: str, engine: str) -> List[DiagnosticEntry]:
        diagnostics: List[DiagnosticEntry] = []

        for line in output.splitlines():
            text = line.strip()
            if not text:
                continue

            path_match = _DIAG_PATH_RE.match(text)
            if path_match:
                message = path_match.group("message").strip()
                severity = "warning" if "warning" in message.lower() else "error"
                diagnostics.append(
                    DiagnosticEntry(
                        message=message,
                        severity=severity,
                        source=engine,
                        path=path_match.group("path"),
                        line=int(path_match.group("line")),
                        column=int(path_match.group("column")) if path_match.group("column") else None,
                    )
                )
                continue

            percent_match = _DIAG_PERCENT_RE.match(text)
            if percent_match:
                severity = "warning" if percent_match.group("severity").lower() == "warning" else "error"
                diagnostics.append(
                    DiagnosticEntry(
                        message=percent_match.group("message").strip(),
                        severity=severity,
                        source=engine,
                    )
                )

        if not diagnostics and output.strip():
            diagnostics.append(
                DiagnosticEntry(
                    message=output.strip().splitlines()[0],
                    severity="error",
                    source=engine,
                )
            )
        return diagnostics
