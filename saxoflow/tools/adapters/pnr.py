"""PnR adapter that wraps SaxoFlow's deterministic ORFS stage execution."""

from __future__ import annotations

import json
import os
import shlex
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence, Tuple

import click

from saxoflow import pnrflow
from saxoflow.source_manifests.service import SourceManifestResolutionError, resolve_rtl_specs
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


class PnrToolAdapter(BaseToolAdapter):
    """Capability adapter for `pnr.run` using the existing pnrflow helpers."""

    capability = "pnr.run"

    def _run(self, request: ToolRequest) -> ToolRun:
        root = Path(request.workspace).resolve()
        if not root.is_dir():
            raise ToolAdapterError(f"Tool request workspace does not exist: {request.workspace}")

        options = self._pnr_options(request, root)
        command_preview = self._command_preview(options)

        if request.dry_run:
            return ToolRun.from_mapping(
                {
                    "status": "skipped",
                    "capability": self.capability,
                    "tool_name": "orfs",
                    "command": command_preview,
                    "diagnostics": [],
                }
            )

        with _pushd(root):
            try:
                flow = pnrflow.resolve_flow(root, options)
                command = pnrflow.orfs_command(flow, options["stage"])
                log_path = root / "pnr/logs" / flow.variant / f"{options['stage']}.log"
                returncode = pnrflow.run_streaming(
                    command,
                    cwd=root,
                    log_path=log_path,
                    show_output=bool(options["show_log"]),
                )
                status = "success" if returncode == 0 else "failed"
                run_manifest = pnrflow._write_run_manifest(flow, options["stage"], status, command, log_path)
            except (click.ClickException, click.Abort, pnrflow.PnrError) as exc:
                return self._failed_run(str(exc), command_preview)

        run_manifest_data = self._read_json(run_manifest)
        stdout_lines = [f"Run manifest: {run_manifest.relative_to(root)}"]
        artifact_indexes = run_manifest_data.get("artifact_indexes", {}) if isinstance(run_manifest_data, dict) else {}
        if isinstance(artifact_indexes, Mapping):
            for category, path in sorted(artifact_indexes.items()):
                stdout_lines.append(f"{category} artifacts: {path}")

        if returncode != 0:
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
            message = self._failure_message(log_text, options["stage"])
            return self._failed_run(
                message,
                command_preview,
                exit_code=returncode,
                stderr=log_text.splitlines()[0] if log_text.strip() else None,
                stdout="\n".join(stdout_lines) or None,
                diagnostics_source="pnrflow",
            )

        return ToolRun.from_mapping(
            {
                "status": "success",
                "capability": self.capability,
                "tool_name": "orfs",
                "command": command_preview,
                "exit_code": 0,
                "stdout": "\n".join(stdout_lines) or None,
                "diagnostics": [],
            }
        )

    @staticmethod
    def _pnr_options(request: ToolRequest, root: Path) -> Dict[str, Any]:
        raw = request.options.get("pnr") if isinstance(request.options, Mapping) else None
        options = dict(raw) if isinstance(raw, Mapping) else {}
        source_manifest = (
            request.options.get("source_manifest")
            if isinstance(request.options, Mapping) and isinstance(request.options.get("source_manifest"), Mapping)
            else None
        )

        rtl_specs = PnrToolAdapter._as_string_tuple(options.get("rtl"), ())
        # Preserve prior implicit discovery behavior unless a source-manifest
        # provider or explicit RTL specs are requested.
        if not rtl_specs and source_manifest is None:
            resolved_rtl_specs = tuple()
        else:
            try:
                resolved_rtl_specs = resolve_rtl_specs(
                    root,
                    explicit_specs=rtl_specs,
                    default_specs=pnrflow.DEFAULT_RTL_SPECS,
                    source_manifest_options=source_manifest,
                    target="synth",
                )
            except SourceManifestResolutionError as exc:
                raise ToolAdapterError(str(exc)) from exc

        return {
            "platform": PnrToolAdapter._optional_string(options.get("platform")),
            "library": PnrToolAdapter._optional_string(options.get("library")),
            "corner": PnrToolAdapter._optional_string(options.get("corner")),
            "top": PnrToolAdapter._optional_string(options.get("top")),
            "netlist_specs": PnrToolAdapter._as_string_tuple(options.get("netlist"), ()),
            "sdc": PnrToolAdapter._optional_string(options.get("sdc")),
            "clock_port": PnrToolAdapter._optional_string(options.get("clock_port")),
            "clock_period": PnrToolAdapter._optional_float(options.get("clock_period")),
            "variant": PnrToolAdapter._optional_string(options.get("variant")) or "default",
            "synthesize": bool(options.get("synthesize", False)),
            "unsafe_netlist": bool(options.get("unsafe_netlist", False)),
            "rtl_specs": tuple(resolved_rtl_specs),
            "include_specs": PnrToolAdapter._as_string_tuple(options.get("include"), ()),
            "defines": PnrToolAdapter._as_string_tuple(options.get("define"), ()),
            "parameter_specs": PnrToolAdapter._as_string_tuple(options.get("param"), ()),
            "overrides": PnrToolAdapter._as_string_tuple(options.get("set"), ()),
            "dry_run": bool(options.get("dry_run", False)),
            "fresh": bool(options.get("fresh", False)),
            "show_log": bool(options.get("show_log", False)),
            "stage": PnrToolAdapter._optional_string(options.get("stage")) or "run",
        }

    @staticmethod
    def _optional_string(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        return float(value)

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
        raise ToolAdapterError("PnR options must be strings or lists of strings.")

    @staticmethod
    def _command_preview(options: Mapping[str, Any]) -> str:
        parts = ["saxoflow pnr", options["stage"]]
        if options["variant"]:
            parts.extend(["--variant", shlex.quote(str(options["variant"]))])
        if options["synthesize"]:
            parts.append("--synthesize")
        if options["top"]:
            parts.extend(["--top", shlex.quote(str(options["top"]))])
        return " ".join(parts)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _failure_message(log_text: str, stage: str) -> str:
        guidance = pnrflow._failure_guidance(log_text)
        if guidance:
            return guidance
        excerpt_lines = [line.strip() for line in log_text.splitlines() if line.strip()]
        if excerpt_lines:
            return excerpt_lines[-1]
        return f"ORFS stage `{stage}` failed."

    def _failed_run(
        self,
        message: str,
        command_preview: str,
        *,
        exit_code: int = 1,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        diagnostics_source: str = "pnr",
    ) -> ToolRun:
        return ToolRun.from_mapping(
            {
                "status": "failed",
                "capability": self.capability,
                "tool_name": "orfs",
                "command": command_preview,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
                "diagnostics": [
                    {
                        "message": message or "PnR flow failed.",
                        "severity": "error",
                        "source": diagnostics_source,
                    }
                ],
            }
        )
