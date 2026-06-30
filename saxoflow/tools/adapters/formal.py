"""Formal adapter that wraps SaxoFlow's deterministic SymbiYosys flow."""

from __future__ import annotations

import os
import re
import shlex
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple

import click

from saxoflow import makeflow
from saxoflow.source_manifests.service import SourceManifestResolutionError, resolve_rtl_specs
from saxoflow.schemas.diagnostics import DiagnosticEntry
from saxoflow.schemas.tools import ToolRequest, ToolRun
from saxoflow.tools.adapters.base import BaseToolAdapter, ToolAdapterError


@contextmanager
def _pushd(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FormalToolAdapter(BaseToolAdapter):
    """Capability adapter for `formal.run` using existing makeflow internals."""

    capability = "formal.run"

    _COUNTEREXAMPLE_FILE_RE = re.compile(r"([A-Za-z0-9_./\\-]+\.(?:vcd|fst|vvp|json|txt))(?::(\d+))?")

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._formal_options(request, root)
        command_preview = self._command_preview(options)

        if request.dry_run:
            return ToolRun.from_mapping(
                {
                    "status": "skipped",
                    "capability": self.capability,
                    "tool_name": "symbiyosys",
                    "command": command_preview,
                    "diagnostics": [],
                }
            )

        with _pushd(root):
            try:
                resolved_formal_sources = makeflow._resolve_formal_sources(
                    options["rtl_specs"],
                    options["sva_specs"],
                )
                generated_sby: Optional[Path] = None
                if resolved_formal_sources is not None:
                    rtl_paths, sva_path = resolved_formal_sources
                    generated_sby = makeflow._write_formal_spec_for_sources(rtl_paths, sva_path)
                elif options["rtl_specs"] or options["sva_specs"]:
                    return self._failed_run(
                        "Formal RTL/SVA inputs could not be resolved.",
                        command_preview,
                    )

                sby_files = (
                    [generated_sby]
                    if generated_sby is not None
                    else sorted(Path("formal/scripts").glob("*.sby"))
                )
                if not sby_files:
                    return self._failed_run(
                        "No .sby spec found in formal/scripts/.",
                        command_preview,
                    )

                selected_solver: Optional[str] = None
                if options["solver"] == "auto":
                    for candidate in makeflow.FORMAL_AUTO_SOLVER_PRIORITY:
                        if makeflow._solver_available(candidate):
                            selected_solver = candidate
                            break
                else:
                    if not makeflow._solver_available(options["solver"]):
                        return self._failed_run(
                            f"Requested solver '{options['solver']}' is not available in PATH.",
                            command_preview,
                        )
                    selected_solver = options["solver"]

                has_advanced_flags = any(
                    [
                        options["sby_task"],
                        options["autotune"],
                        options["timeout"] is not None,
                        options["dumptasks"],
                        options["dumpcfg"],
                        generated_sby is not None,
                    ]
                )
                if options["solver"] == "auto" and not has_advanced_flags:
                    result = makeflow.run_make("formal")
                else:
                    sby_file = sby_files[0].name
                    extra_vars: Dict[str, str] = {
                        "SBY_FILE": f"../scripts/{sby_file}",
                        "SBY_TASK": options["sby_task"] or "",
                        "SBY_TIMEOUT": str(options["timeout"]) if options["timeout"] is not None else "",
                        "SBY_AUTOTUNE": "1" if options["autotune"] else "",
                        "SBY_DUMPTASKS": "1" if options["dumptasks"] else "",
                        "SBY_DUMPCFG": "1" if options["dumpcfg"] else "",
                        "SBY_SOLVER": selected_solver or "",
                    }
                    result = makeflow.run_make("formal", extra_vars=extra_vars)
            except click.Abort:
                return self._failed_run("SymbiYosys formal verification failed.", command_preview)
            except click.UsageError as exc:
                return self._failed_run(str(exc), command_preview)

        stdout = str(result.get("stdout", ""))
        stderr = str(result.get("stderr", ""))
        returncode = int(result.get("returncode", 0))

        reports = sorted(
            path for path in (root / "formal/reports").glob("*") if path.is_file() and not path.name.startswith(".")
        )
        outputs = sorted(
            path for path in (root / "formal/out").glob("*") if path.is_file() and not path.name.startswith(".")
        )
        counterexample_refs = self._extract_counterexample_refs(
            root=root,
            stdout=stdout,
            stderr=stderr,
            outputs=outputs,
        )

        if returncode != 0:
            return self._failed_run(
                stderr.strip() or stdout.strip() or "SymbiYosys formal verification failed.",
                command_preview,
                exit_code=returncode,
                stderr=stderr or None,
                counterexample_refs=counterexample_refs,
            )

        stdout_lines = []
        if stdout.strip():
            stdout_lines.append(stdout.strip())
        if stderr.strip():
            stdout_lines.append(stderr.strip())
        if reports or outputs:
            parts = []
            if reports:
                parts.append("reports: " + ", ".join(str(path.relative_to(root)) for path in reports))
            if outputs:
                parts.append("out: " + ", ".join(str(path.relative_to(root)) for path in outputs))
            stdout_lines.append("Formal outputs: " + ", ".join(parts))
        if counterexample_refs:
            stdout_lines.append("Counterexample references: " + ", ".join(counterexample_refs))

        return ToolRun.from_mapping(
            {
                "status": "success",
                "capability": self.capability,
                "tool_name": "symbiyosys",
                "command": command_preview,
                "exit_code": 0,
                "stdout": "\n".join(line for line in stdout_lines if line).strip() or None,
                "diagnostics": [],
            }
        )

    @staticmethod
    def _formal_options(request: ToolRequest, root: Path) -> Dict[str, Any]:
        raw = request.options.get("formal") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        source_manifest = (
            request.options.get("source_manifest")
            if isinstance(request.options, Mapping) and isinstance(request.options.get("source_manifest"), Mapping)
            else None
        )

        rtl_specs = FormalToolAdapter._as_string_tuple(options.get("rtl"), ())
        # Preserve prior implicit discovery behavior unless a source-manifest
        # provider or explicit RTL specs are requested.
        if not rtl_specs and source_manifest is None:
            resolved_rtl_specs = tuple()
        else:
            try:
                resolved_rtl_specs = resolve_rtl_specs(
                    root,
                    explicit_specs=rtl_specs,
                    default_specs=makeflow.DEFAULT_FORMAL_RTL_SPECS,
                    source_manifest_options=source_manifest,
                    target="rtl",
                )
            except SourceManifestResolutionError as exc:
                raise ToolAdapterError(str(exc)) from exc

        return {
            "solver": str(options.get("solver", "auto")).strip().lower(),
            "sby_task": FormalToolAdapter._optional_string(options.get("sby_task")),
            "autotune": bool(options.get("autotune", False)),
            "timeout": FormalToolAdapter._optional_int(options.get("timeout")),
            "dumptasks": bool(options.get("dumptasks", False)),
            "dumpcfg": bool(options.get("dumpcfg", False)),
            "rtl_specs": tuple(resolved_rtl_specs),
            "sva_specs": FormalToolAdapter._as_string_tuple(options.get("sva"), ()),
        }

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _as_string_tuple(value: Any, default: Sequence[str]) -> Tuple[str, ...]:
        if value is None:
            return tuple(default)
        if isinstance(value, str):
            text = value.strip()
            return (text,) if text else tuple(default)
        if isinstance(value, Sequence):
            items = [str(item).strip() for item in value if str(item).strip()]
            return tuple(items) if items else tuple(default)
        raise ToolAdapterError("Formal options must be strings or lists of strings.")

    @staticmethod
    def _command_preview(options: Mapping[str, Any]) -> str:
        parts = ["saxoflow formal"]
        if options["solver"] != "auto":
            parts.extend(["--solver", shlex.quote(options["solver"])])
        if options["sby_task"]:
            parts.extend(["--task", shlex.quote(options["sby_task"])])
        if options["autotune"]:
            parts.append("--autotune")
        if options["timeout"] is not None:
            parts.extend(["--timeout", str(options["timeout"])])
        if options["dumptasks"]:
            parts.append("--dumptasks")
        if options["dumpcfg"]:
            parts.append("--dumpcfg")
        return " ".join(parts)

    def _failed_run(
        self,
        message: str,
        command_preview: str,
        *,
        exit_code: int = 1,
        stderr: Optional[str] = None,
        counterexample_refs: Tuple[str, ...] = tuple(),
    ) -> ToolRun:
        if counterexample_refs:
            message = f"{message} Counterexample references: {', '.join(counterexample_refs)}"

        diagnostics = [
            {
                "message": message or "SymbiYosys formal verification failed.",
                "severity": "error",
                "source": "formal",
            }
        ]
        for reference in counterexample_refs:
            diagnostics.append(
                {
                    "message": f"Counterexample reference: {reference}",
                    "severity": "warning",
                    "source": "formal",
                }
            )

        return ToolRun.from_mapping(
            {
                "status": "failed",
                "capability": self.capability,
                "tool_name": "symbiyosys",
                "command": command_preview,
                "exit_code": exit_code,
                "stderr": stderr,
                "diagnostics": diagnostics,
            }
        )

    def _extract_counterexample_refs(
        self,
        *,
        root: Path,
        stdout: str,
        stderr: str,
        outputs: Sequence[Path],
    ) -> Tuple[str, ...]:
        refs: list[str] = []

        for path in outputs:
            lowered = path.name.lower()
            if any(token in lowered for token in ("counterexample", "trace")) or lowered.endswith((".vcd", ".fst")):
                refs.append(str(path.relative_to(root)))

        for text in (stdout, stderr):
            for match in self._COUNTEREXAMPLE_FILE_RE.finditer(text or ""):
                file_part = match.group(1)
                line_part = match.group(2)
                candidate = f"{file_part}:{line_part}" if line_part else file_part
                if "counterexample" in file_part.lower() or file_part.lower().endswith((".vcd", ".fst")):
                    refs.append(candidate)

        return tuple(dict.fromkeys(refs))
